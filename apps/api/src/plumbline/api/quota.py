"""Visitors and daily question quotas (Lane D; Lane P hardens them in P3).

A visitor is a random id in a signed, HttpOnly, SameSite=Lax cookie. Each question counts
against two daily counters, the visitor's and the IP address's, which expire at the next
UTC midnight; past DAILY_QUESTIONS_PER_IP on either, /api/ask answers 429 with
Retry-After set to that midnight, and the front end shows its quota-reached state.
Lease checks are counted apart, at a tenth of that: a check is many model calls. Law
searches (/api/law/search) are counted apart too, at ten times it: no model call.

- The cookie's signing secret is made once and kept in the settings table, so every
  worker, and the next process, accepts the cookies the others set.
- Addresses are counted under an HMAC of the address, never the address itself. Behind
  the Cloudflare Tunnel the address is CF-Connecting-IP, the only way the API is reached.
- If Redis cannot count, the question goes through and the failure is logged: the spend
  caps (C6) and the kill switch (P5) stop runaway cost; this only rations a fair share.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final, Literal, Protocol

from fastapi import Request, Response
from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.api.problems import ApiError
from plumbline.db.models import PUBLIC_TENANT, Setting
from plumbline.db.session import tenant_session
from plumbline.settings import Settings

log = logging.getLogger(__name__)

COOKIE: Final = "plumbline_visitor"
COOKIE_DAYS: Final = 365
SIGNING_SETTING: Final = "visitor_cookie_secret"  # the settings row holding it
LEASE_SHARE: Final = 10  # one lease check is allowed for every ten questions
SEARCH_SHARE: Final = 10  # ten law searches for every question: no model call, one embedding
Kind = Literal["question", "lease", "search"]
WORDS: Final[dict[Kind, tuple[str, str]]] = {
    "question": ("questions", "asking"),
    "lease": ("lease checks", "checking"),
    "search": ("searches", "searching"),
}


class Counter(Protocol):
    async def increment(self, key: str, expire_at: datetime) -> int:
        """Add one to `key`, which disappears at `expire_at`; the new count."""
        ...

    async def get(self, key: str) -> int:
        """The count of `key`, 0 when it has none."""
        ...


class RedisCounter:
    def __init__(self, url: str) -> None:
        self._redis = Redis.from_url(url)

    async def increment(self, key: str, expire_at: datetime) -> int:
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expireat(key, expire_at)
            count, _ = await pipe.execute()
        return int(count)

    async def get(self, key: str) -> int:
        return int(await self._redis.get(key) or 0)


class MemoryCounter:
    """For tests, and for a process that should not need Redis."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def increment(self, key: str, expire_at: datetime) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def get(self, key: str) -> int:
        return self.counts.get(key, 0)


class Usage(BaseModel):
    """Today's questions: `used` is the larger of the visitor's and the address's counts."""

    used: int
    limit: int
    resets_at: datetime  # the next 00:00 UTC


@dataclass(frozen=True)
class Visitor:
    id: str
    cookie: str | None  # a new signed cookie to set; None when the request brought a valid one


class Quota:
    def __init__(
        self,
        settings: Settings,
        sessions: async_sessionmaker[AsyncSession],
        counter: Counter,
    ) -> None:
        self._limits: dict[Kind, int] = {
            "question": settings.daily_questions_per_ip,
            "lease": max(1, settings.daily_questions_per_ip // LEASE_SHARE),
            "search": settings.daily_questions_per_ip * SEARCH_SHARE,
        }
        self._sessions = sessions
        self._counter = counter
        self._secret: bytes | None = None

    async def visitor(self, request: Request) -> Visitor:
        """The visitor the request's cookie names, or a new one with a cookie to set."""
        return _visitor(request.cookies.get(COOKIE), await self._signing_secret())

    async def owner(self, request: Request) -> str | None:
        """The id in the request's cookie when we signed it; None for anyone else."""
        return _valid_visitor(request.cookies.get(COOKIE), await self._signing_secret())

    async def admit(
        self,
        request: Request,
        kind: Kind = "question",
        *,
        visitor: Visitor | None = None,
        count: bool = True,
    ) -> Visitor:
        """The visitor, after counting one more `kind`; 429 when it is one too many. With
        count=False nothing is counted and the 429 is for a visitor who has none left."""
        secret = await self._signing_secret()
        known = visitor if visitor is not None else _visitor(request.cookies.get(COOKIE), secret)
        now = datetime.now(UTC)
        midnight = _next_midnight(now)
        # Questions keep the bare prefix, which /api/usage reads; other kinds count apart.
        prefix = f"quota:{now.date().isoformat()}:" + ("" if kind == "question" else f"{kind}:")
        keys = [f"{prefix}visitor:{known.id}", f"{prefix}ip:{_sign(secret, _address(request))}"]
        noun, verb = WORDS[kind]
        try:
            if count:
                counts = [await self._counter.increment(key, midnight) for key in keys]
            else:
                counts = [await self._counter.get(key) + 1 for key in keys]
        except (RedisError, OSError) as exc:
            log.warning("%s are not being counted: %s", noun, exc)
            return known
        limit = self._limits[kind]
        if max(counts) > limit:
            retry_after = max(1, int((midnight - now).total_seconds()))
            raise ApiError(
                429,
                "quota_reached",
                f"Today's {limit} {noun} are used up; {verb} opens again at 00:00 UTC.",
                headers={"Retry-After": str(retry_after)},
            )
        return known

    async def usage(self, request: Request) -> Usage:
        """How many of today's questions this reader has used. Counts nothing and sets no
        cookie: the sidebar's meter and the composer's limit read it."""
        secret = await self._signing_secret()
        now = datetime.now(UTC)
        keys = [f"quota:{now.date().isoformat()}:ip:{_sign(secret, _address(request))}"]
        if (visitor := _valid_visitor(request.cookies.get(COOKIE), secret)) is not None:
            keys.append(f"quota:{now.date().isoformat()}:visitor:{visitor}")
        try:
            used = max([await self._counter.get(key) for key in keys])
        except (RedisError, OSError) as exc:
            log.warning("the usage cannot be read: %s", exc)
            used = 0
        return Usage(used=used, limit=self._limits["question"], resets_at=_next_midnight(now))

    async def _signing_secret(self) -> bytes:
        if self._secret is not None:
            return self._secret
        made = secrets.token_hex(32)
        try:
            async with tenant_session(self._sessions, PUBLIC_TENANT) as session:
                await session.execute(
                    insert(Setting).values(key=SIGNING_SETTING, value=made).on_conflict_do_nothing()
                )
                stored = await session.scalar(
                    select(Setting.value).where(Setting.key == SIGNING_SETTING)
                )
            self._secret = str(stored).encode()
        except (SQLAlchemyError, OSError) as exc:
            # Cookies this process signs will not pass in another; tolerable for a while.
            log.warning("the visitor secret is not shared: %s", exc)
            self._secret = made.encode()
        return self._secret


def set_visitor_cookie(response: Response, visitor: Visitor, settings: Settings) -> None:
    """Set `visitor`'s new cookie on a response, when the request did not bring one."""
    if visitor.cookie is None:
        return
    response.set_cookie(
        COOKIE,
        visitor.cookie,
        max_age=COOKIE_DAYS * 24 * 3600,
        path="/api",
        httponly=True,
        samesite="lax",
        secure=settings.environment == "prod",
    )


def _valid_visitor(cookie: str | None, secret: bytes) -> str | None:
    """The visitor id in a cookie we signed, or None."""
    if cookie and "." in cookie:
        visitor_id, signature = cookie.rsplit(".", 1)
        if hmac.compare_digest(signature, _sign(secret, visitor_id)):
            return visitor_id
    return None


def _visitor(cookie: str | None, secret: bytes) -> Visitor:
    if (known := _valid_visitor(cookie, secret)) is not None:
        return Visitor(known, None)
    visitor_id = secrets.token_urlsafe(16)
    return Visitor(visitor_id, f"{visitor_id}.{_sign(secret, visitor_id)}")


def _address(request: Request) -> str:
    return request.headers.get("cf-connecting-ip") or (
        request.client.host if request.client else "unknown"
    )


def _next_midnight(now: datetime) -> datetime:
    return datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), UTC)


def _sign(secret: bytes, value: str) -> str:
    return hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()[:32]

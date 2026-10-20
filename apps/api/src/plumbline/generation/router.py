"""The router: which model serves a request, under the demo tier and the daily spend caps;
and the redaction seam that every upload passes before any model sees it.

- fast: Gemini Flash-Lite, the default for a question.
- strong: Gemini Flash, for comparison and multi-hop questions.
- premium: Claude Sonnet, when the reader asks for it on the full tier and only while
  Anthropic's spend today is under its cap; past the cap the question goes to strong.
- lease: Gemini Flash for a lease check, on the full tier only. An upload is personal
  data, and only the full tier runs on billed keys, whose inputs Google does not use for
  training (free-tier inputs may be), so the free tier refuses lease checks.
- The static tier has no route: it serves stored answers and calls no model.

Spend is counted per provider and UTC day by a SpendMeter (in memory for tests, Redis for
the service, which Lane P's kill switch reads too), and only for live calls: a replayed
recording costs nothing.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Final, Protocol

from redis.asyncio import Redis

from plumbline.core.types import DemoTier, Frozen, Jurisdiction, Language
from plumbline.generation.llm import (
    FAST_MODEL,
    PREMIUM_MODEL,
    STRONG_MODEL,
    LLMClient,
    LLMRequest,
    LLMResult,
)


class Kind(StrEnum):
    QUESTION = "question"
    LEASE_CHECK = "lease_check"


@dataclass(frozen=True)
class Route:
    name: str  # AnswerTrace.route
    model: str
    provider: str  # as LLMClient.provider names it, and as the spend meter counts it


ROUTES: Final = {
    "fast": Route("fast", FAST_MODEL, "gemini"),
    "strong": Route("strong", STRONG_MODEL, "gemini"),
    "premium": Route("premium", PREMIUM_MODEL, "anthropic"),
    "lease": Route("lease", STRONG_MODEL, "gemini"),
}
# Comparison wording, or more than one question in one message: work for the strong model.
_COMPARISON: Final = re.compile(r"\b(compar\w*|differ\w*|versus|vs\.?)\b", re.IGNORECASE)


class RouteRefused(Exception):
    """No route serves this request on this tier; the message is for the reader."""


class SpendMeter(Protocol):
    async def spent_today(self, provider: str) -> float: ...

    async def add(self, provider: str, usd: float) -> float:
        """Count a live call's cost; the provider's total for today."""
        ...


def utc_today() -> date:
    return datetime.now(UTC).date()


class MemorySpendMeter:
    def __init__(self, today: Callable[[], date] = utc_today) -> None:
        self.today = today
        self.totals: dict[tuple[str, date], float] = {}

    async def spent_today(self, provider: str) -> float:
        return self.totals.get((provider, self.today()), 0.0)

    async def add(self, provider: str, usd: float) -> float:
        key = (provider, self.today())
        self.totals[key] = self.totals.get(key, 0.0) + usd
        return self.totals[key]


class RedisSpendMeter:
    """One float per provider and day, kept a day past its own so a late reader finds it."""

    def __init__(
        self, redis: Redis, prefix: str = "spend", today: Callable[[], date] = utc_today
    ) -> None:
        self.redis, self.prefix, self.today = redis, prefix, today

    def _key(self, provider: str, day: date) -> str:
        return f"{self.prefix}:{provider}:{day.isoformat()}"

    async def spent_today(self, provider: str) -> float:
        value = await self.redis.get(self._key(provider, self.today()))
        return float(value) if value is not None else 0.0

    async def add(self, provider: str, usd: float) -> float:
        day = self.today()
        expires = datetime.combine(day + timedelta(days=2), time(), tzinfo=UTC)
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.incrbyfloat(self._key(provider, day), usd)
            pipe.expireat(self._key(provider, day), expires)
            total, _ = await pipe.execute()
        return float(total)


class MeteredClient:
    """An LLMClient that counts the cost of its live calls on a SpendMeter."""

    def __init__(self, client: LLMClient, meter: SpendMeter) -> None:
        self.client, self.meter = client, meter
        self.provider = client.provider

    async def complete(self, request: LLMRequest) -> LLMResult:
        result = await self.client.complete(request)
        await self._count(result)
        return result

    async def stream(self, request: LLMRequest) -> AsyncIterator[str | LLMResult]:
        async for item in self.client.stream(request):
            if isinstance(item, LLMResult):
                await self._count(item)
            yield item

    async def _count(self, result: LLMResult) -> None:
        if not result.cached:
            await self.meter.add(self.provider, result.cost_usd)


class Router:
    def __init__(self, meter: SpendMeter, caps: Mapping[str, float]) -> None:
        self.meter = meter
        self.caps = caps  # USD per provider and UTC day: the settings' *_daily_cap_usd

    async def route(
        self,
        kind: Kind,
        *,
        tier: DemoTier,
        text: str = "",
        jurisdictions: Sequence[Jurisdiction] = (),
        premium: bool = False,  # the reader asked for the premium model
    ) -> Route:
        if tier is DemoTier.STATIC:
            raise RouteRefused("Plumbline is serving stored answers only right now.")
        if kind is Kind.LEASE_CHECK:
            if tier is not DemoTier.FULL:
                raise RouteRefused(
                    "Lease checks are paused: they run only on paid models that do not "
                    "train on what you upload."
                )
            return ROUTES["lease"]
        if premium and tier is DemoTier.FULL and await self._under_cap("anthropic"):
            return ROUTES["premium"]
        return ROUTES["strong"] if needs_strong(text, jurisdictions) else ROUTES["fast"]

    async def _under_cap(self, provider: str) -> bool:
        return await self.meter.spent_today(provider) < self.caps.get(provider, 0.0)


def needs_strong(text: str, jurisdictions: Sequence[Jurisdiction]) -> bool:
    """A comparison (two or more jurisdictions, or comparison wording) or a multi-hop
    question (more than one question mark). A heuristic, measured on the dev set's
    cross-jurisdiction and multi-article items."""
    return len(set(jurisdictions)) > 1 or bool(_COMPARISON.search(text)) or text.count("?") > 1


class Upload(Frozen):
    """A document a reader uploaded (a lease), before redaction."""

    text: str
    language: Language
    synthetic: bool = False  # one of the synthetic leases under data/leases


class Redactor(Protocol):
    """What runs on every upload before any model call sees it (Lane P's Presidio
    redactor implements it). Returns the text to send; raises RedactionRefused rather than
    let unredacted personal data through."""

    def redact(self, upload: Upload) -> str: ...


class RedactionRefused(Exception):
    pass


class SyntheticOnlyRedactor:
    """The stand-in until the Presidio redactor lands: a synthetic lease passes unchanged,
    and anything else is refused, so no real upload reaches a model unredacted."""

    def redact(self, upload: Upload) -> str:
        if not upload.synthetic:
            raise RedactionRefused("Uploads are disabled until redaction is in place.")
        return upload.text

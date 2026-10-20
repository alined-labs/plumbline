"""Visitors and daily quotas on /api/ask: the signed cookie, the per-visitor and per-address
counters, the 429 with Retry-After, and questions going through when nothing can count."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI, Request
from redis.exceptions import ConnectionError as RedisConnectionError

from plumbline.api.app import create_app
from plumbline.api.quota import COOKIE, Counter, MemoryCounter, RedisCounter
from plumbline.core.types import CacheMode
from plumbline.db import make_engine, make_sessionmaker
from plumbline.settings import Settings

pytestmark = pytest.mark.anyio
BODY = {"messages": [{"id": "m1", "role": "user", "parts": [{"type": "text", "text": "Rent?"}]}]}
NO_DATABASE = "postgresql+psycopg://plumbline:plumbline@127.0.0.1:1/none"


class Broken:
    async def increment(self, key: str, expire_at: datetime) -> int:
        raise RedisConnectionError("Redis is down")

    async def get(self, key: str) -> int:
        raise RedisConnectionError("Redis is down")


def _app(counter: Counter, limit: int = 2) -> FastAPI:
    # No database: the cookie secret falls back to one per process, which is all a test needs.
    settings = Settings(
        _env_file=None, cache_mode=CacheMode.REPLAY, daily_questions_per_ip=limit, stub_delay_ms=0
    )
    sessions = make_sessionmaker(make_engine(NO_DATABASE))
    return create_app(settings, sessions=sessions, counter=counter)


def _client(app: FastAPI) -> httpx.AsyncClient:
    """A browser: a cookie jar of its own."""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def api() -> AsyncIterator[httpx.AsyncClient]:
    async with _client(_app(MemoryCounter())) as client:
        yield client


async def test_a_new_visitor_gets_a_signed_httponly_cookie(api: httpx.AsyncClient) -> None:
    response = await api.post("/api/ask", json=BODY)
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/api" in cookie
    again = await api.post("/api/ask", json=BODY)  # the client sends the cookie back
    assert "set-cookie" not in again.headers


async def test_past_the_quota_the_answer_is_a_429_until_midnight(api: httpx.AsyncClient) -> None:
    for _ in range(2):
        assert (await api.post("/api/ask", json=BODY)).status_code == 200
    refused = await api.post("/api/ask", json=BODY)
    assert (refused.status_code, refused.headers["content-type"]) == (
        429,
        "application/problem+json",
    )
    now = datetime.now(UTC)
    midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), UTC)
    retry_after = int(refused.headers["retry-after"])
    assert 0 < retry_after <= (midnight - now).total_seconds() + 1
    assert "00:00 UTC" in refused.json()["detail"]
    assert refused.json()["code"] == "quota_reached"


async def test_an_address_is_counted_across_its_visitors() -> None:
    counter = MemoryCounter()
    app = _app(counter)
    address = {"cf-connecting-ip": f"203.0.113.{uuid.uuid4().int % 250}"}
    async with _client(app) as one, _client(app) as two:
        assert (await one.post("/api/ask", json=BODY, headers=address)).status_code == 200
        assert (await two.post("/api/ask", json=BODY, headers=address)).status_code == 200
        assert (await two.post("/api/ask", json=BODY, headers=address)).status_code == 429
    assert not any(address["cf-connecting-ip"] in key for key in counter.counts)  # only an HMAC


async def test_a_forged_cookie_is_a_new_visitor(api: httpx.AsyncClient) -> None:
    api.cookies.set(COOKIE, "someone-else.0000000000000000000000000000000", path="/api")
    response = await api.post("/api/ask", json=BODY)
    assert response.headers["set-cookie"].startswith(f"{COOKIE}=")


async def test_an_invalid_question_is_not_counted() -> None:
    counter = MemoryCounter()
    async with _client(_app(counter)) as client:
        assert (await client.post("/api/ask", json={"messages": []})).status_code == 422
    assert counter.counts == {}


async def test_when_nothing_can_count_questions_go_through() -> None:
    async with _client(_app(Broken(), limit=1)) as client:
        for _ in range(3):
            assert (await client.post("/api/ask", json=BODY)).status_code == 200


async def test_redis_counts_and_forgets_at_midnight() -> None:
    counter = RedisCounter(Settings(_env_file=None).redis_url)
    key = f"quota:test:{uuid.uuid4().hex}"
    expire_at = datetime.now(UTC) + timedelta(seconds=60)
    try:
        assert [await counter.increment(key, expire_at) for _ in range(3)] == [1, 2, 3]
    except (RedisConnectionError, OSError):
        pytest.skip("Redis is unreachable (make up starts it)")
    ttl = await counter._redis.ttl(key)
    assert 0 < ttl <= 60
    await counter._redis.delete(key)
    await counter._redis.aclose()


@pytest.mark.db
async def test_every_worker_accepts_the_cookie_another_set(database_url: str) -> None:
    engine = make_engine(database_url)
    settings = Settings(_env_file=None, cache_mode=CacheMode.REPLAY, stub_delay_ms=0)
    workers = [
        create_app(settings, sessions=make_sessionmaker(engine), counter=MemoryCounter())
        for _ in range(2)
    ]
    async with _client(workers[0]) as browser:
        first = await browser.post("/api/ask", json=BODY)
        cookie = first.cookies[COOKIE]
    async with _client(workers[1]) as browser:
        browser.cookies.set(COOKIE, cookie, path="/api")
        second = await browser.post("/api/ask", json=BODY)
    assert "set-cookie" not in second.headers  # the second worker trusts the first's cookie
    await engine.dispose()


async def test_the_usage_counts_without_counting(api: httpx.AsyncClient) -> None:
    empty = (await api.get("/api/usage")).json()
    assert (empty["used"], empty["limit"]) == (0, 2)
    assert "set-cookie" not in (await api.get("/api/usage")).headers
    await api.post("/api/ask", json=BODY)
    await api.post("/api/ask", json=BODY)
    after = (await api.get("/api/usage")).json()
    assert after["used"] == 2
    assert (await api.get("/api/usage")).json()["used"] == 2  # reading it used nothing
    reset = datetime.fromisoformat(after["resets_at"])
    assert (reset.hour, reset.minute, reset.second) == (0, 0, 0)
    assert reset > datetime.now(UTC)
    assert reset - datetime.now(UTC) <= timedelta(days=1)


async def test_the_usage_is_the_larger_of_the_visitors_and_the_addresss() -> None:
    app = _app(MemoryCounter(), limit=5)
    address = {"cf-connecting-ip": "203.0.113.7"}
    async with _client(app) as first, _client(app) as second:
        for _ in range(3):
            await first.post("/api/ask", json=BODY, headers=address)
        await second.post("/api/ask", json=BODY, headers=address)
        # The second browser has used 1 of its own, but the shared address has used 4.
        assert (await second.get("/api/usage", headers=address)).json()["used"] == 4
        # A browser from another address that never asked has used nothing.
        other = {"cf-connecting-ip": "203.0.113.8"}
        assert (await _client(app).get("/api/usage", headers=other)).json()["used"] == 0


async def test_the_usage_reads_zero_when_nothing_can_count() -> None:
    async with _client(_app(Broken())) as client:
        assert (await client.get("/api/usage")).json()["used"] == 0


def _probe(app: FastAPI) -> FastAPI:
    """Routes that use the quota the way the lease routes do."""

    @app.post("/api/test-lease")
    async def lease(request: Request, count: bool = True) -> dict[str, str]:
        return {"visitor": (await request.app.state.quota.admit(request, "lease", count=count)).id}

    @app.get("/api/test-owner")
    async def owner(request: Request) -> dict[str, str | None]:
        return {"owner": await request.app.state.quota.owner(request)}

    return app


async def test_lease_checks_are_allowed_a_tenth_of_the_questions() -> None:
    async with _client(_probe(_app(MemoryCounter(), limit=20))) as client:
        assert [(await client.post("/api/test-lease")).status_code for _ in range(2)] == [200, 200]
        refused = await client.post("/api/test-lease")
    body = refused.json()
    assert (refused.status_code, body["code"]) == (429, "quota_reached")
    assert (
        body["detail"] == "Today's 2 lease checks are used up; checking opens again at 00:00 UTC."
    )
    assert 0 < int(refused.headers["retry-after"]) <= 24 * 3600


async def test_there_is_always_one_lease_check_a_day() -> None:
    async with _client(_probe(_app(MemoryCounter(), limit=5))) as client:
        assert (await client.post("/api/test-lease")).status_code == 200
        assert (await client.post("/api/test-lease")).status_code == 429


async def test_lease_checks_and_questions_are_counted_apart() -> None:
    async with _client(_probe(_app(MemoryCounter(), limit=10))) as client:
        assert (await client.post("/api/test-lease")).status_code == 200
        assert (await client.post("/api/test-lease")).status_code == 429  # the one is used
        for _ in range(10):  # and all ten questions are still there
            assert (await client.post("/api/ask", json=BODY)).status_code == 200
        assert (await client.post("/api/ask", json=BODY)).status_code == 429


async def test_a_look_at_the_quota_counts_nothing() -> None:
    async with _client(_probe(_app(MemoryCounter(), limit=10))) as client:
        for _ in range(5):
            assert (
                await client.post("/api/test-lease", params={"count": "false"})
            ).status_code == 200
        assert (await client.post("/api/test-lease")).status_code == 200  # the one is still there
        refused = await client.post("/api/test-lease", params={"count": "false"})
    assert refused.status_code == 429  # a look, now, finds none left


async def test_a_request_is_owned_by_the_visitor_whose_signed_cookie_it_carries() -> None:
    app = _probe(_app(MemoryCounter()))
    async with _client(app) as client, _client(app) as stranger:
        assert (await client.get("/api/test-owner")).json() == {"owner": None}  # no cookie yet
        await client.post("/api/ask", json=BODY)  # which sets one
        cookie = client.cookies[COOKIE]
        assert (await client.get("/api/test-owner")).json() == {"owner": cookie.rsplit(".", 1)[0]}
        forged = await stranger.get("/api/test-owner", headers={"cookie": f"{COOKIE}=someone.0000"})
        assert forged.json() == {"owner": None}

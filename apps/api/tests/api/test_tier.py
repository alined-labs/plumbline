"""The demo tier: stored in the settings table, read through a 10-second cache, flipped by
the admin route, and the server's default whenever the database cannot say."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.api import answering
from plumbline.api.answering import ServedPipeline
from plumbline.api.app import create_app
from plumbline.api.quota import MemoryCounter
from plumbline.api.tier import TIER_KEY, TTL_S, TierStore
from plumbline.core.stream import Question, StreamEvent, TextDelta
from plumbline.core.types import CacheMode, DemoTier
from plumbline.db import make_engine, make_sessionmaker
from plumbline.db.models import Setting
from plumbline.generation.router import MemorySpendMeter, SyntheticOnlyRedactor
from plumbline.settings import Settings

pytestmark = pytest.mark.anyio
Sessions = async_sessionmaker[AsyncSession]
AUTH = {"Authorization": "Bearer test-admin-token"}


@pytest.fixture
async def sessions(database_url: str) -> AsyncIterator[Sessions]:
    engine = make_engine(database_url)
    sessions = make_sessionmaker(engine)
    async with sessions() as session, session.begin():  # every test starts with no tier set
        await session.execute(delete(Setting).where(Setting.key == TIER_KEY))
    yield sessions
    await engine.dispose()


@pytest.fixture
async def api(sessions: Sessions) -> AsyncIterator[httpx.AsyncClient]:
    # Every setting the test relies on is explicit: DeepEval's pytest plugin copies a
    # developer's .env into os.environ.
    settings = Settings(
        _env_file=None,
        cache_mode=CacheMode.REPLAY,
        admin_token=SecretStr("test-admin-token"),
        demo_tier=DemoTier.FULL,
        stub_delay_ms=0,
    )
    transport = httpx.ASGITransport(app=create_app(settings, sessions=sessions))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.db
async def test_the_tier_is_the_servers_default_until_it_is_set(api: httpx.AsyncClient) -> None:
    assert (await api.get("/api/settings/tier")).json() == {"tier": "full", "updated_at": None}


@pytest.mark.db
async def test_the_admin_flips_the_tier_and_every_route_sees_it(api: httpx.AsyncClient) -> None:
    assert (await api.put("/api/admin/settings/tier", json={"tier": "free"})).status_code == 401
    flipped = await api.put("/api/admin/settings/tier", json={"tier": "free"}, headers=AUTH)
    assert flipped.json()["tier"] == "free"
    assert flipped.json()["updated_at"] is not None
    assert (await api.get("/api/settings/tier")).json()["tier"] == "free"
    assert (await api.get("/api/health")).json()["tier"] == "free"
    asked = await api.post(
        "/api/ask",
        json={"messages": [{"id": "m1", "role": "user", "parts": [{"type": "text", "text": "q"}]}]},
    )
    trace = next(
        json.loads(line[6:])
        for line in asked.text.splitlines()
        if line.startswith("data: {") and '"data-trace"' in line
    )
    assert trace["data"]["tier"] == "free"


@pytest.mark.db
async def test_an_unknown_tier_is_refused(api: httpx.AsyncClient) -> None:
    response = await api.put("/api/admin/settings/tier", json={"tier": "gold"}, headers=AUTH)
    assert response.status_code == 422


@pytest.mark.db
async def test_another_worker_sees_a_flip_within_the_cache_time(sessions: Sessions) -> None:
    now = [0.0]
    worker = TierStore(sessions, DemoTier.FULL, clock=lambda: now[0])
    assert await worker.current() is DemoTier.FULL
    await TierStore(sessions, DemoTier.FULL).set(DemoTier.STATIC)  # another process flips it
    now[0] = TTL_S - 0.1
    assert await worker.current() is DemoTier.FULL  # still cached
    now[0] = TTL_S
    assert await worker.current() is DemoTier.STATIC


async def test_without_a_database_the_tier_is_the_servers_default() -> None:
    engine = make_engine("postgresql+psycopg://plumbline:plumbline@127.0.0.1:1/none")
    store = TierStore(make_sessionmaker(engine), DemoTier.FREE)
    assert await store.current() is DemoTier.FREE
    await engine.dispose()


class _Answers:
    """The served pipeline's inner pipeline: counts the questions that reach a model."""

    def __init__(self) -> None:
        self.questions = 0

    async def stream(self, question: Question) -> AsyncIterator[StreamEvent]:
        self.questions += 1
        yield TextDelta(text="answered")


@pytest.mark.db
async def test_the_served_path_follows_each_tier_the_admin_sets(sessions: Sessions) -> None:
    # What production runs (api/answering.py), with the model calls replaced: the tier the
    # admin route sets, or the kill switch through the same row, decides what may spend.
    settings = Settings(
        _env_file=None,
        cache_mode=CacheMode.REPLAY,
        admin_token=SecretStr("test-admin-token"),
        demo_tier=DemoTier.FULL,
    )
    meter = MemorySpendMeter()
    answers = _Answers()
    checker = answering.ClaudeLeaseChecker(
        router=answering.router_for(settings, meter),
        meter=meter,
        redactor=SyntheticOnlyRedactor(),
        search=None,  # type: ignore[arg-type]  # a refused check never searches
    )
    app = create_app(
        settings,
        pipeline=ServedPipeline(lambda: answers, answering.router_for(settings, meter)),
        sessions=sessions,
        counter=MemoryCounter(),
        lease_checker=checker,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:

        async def ask() -> str:
            body = {
                "messages": [{"id": "m1", "role": "user", "parts": [{"type": "text", "text": "q"}]}]
            }
            return (await api.post("/api/ask", json=body)).text

        async def lease_code() -> str:
            # An empty body: past the tier, the check would stop at the file (422), not start.
            response = await api.post("/api/check-lease", content=b"")
            return str(response.json()["code"])

        assert "answered" in await ask()
        assert await lease_code() == "unreadable"  # the tier let it through to the file

        await api.put("/api/admin/settings/tier", json={"tier": "free"}, headers=AUTH)
        assert "answered" in await ask()
        assert await lease_code() == "lease_checks_paused"

        await api.put("/api/admin/settings/tier", json={"tier": "static"}, headers=AUTH)
        assert "serving stored answers only" in await ask()
        assert await lease_code() == "lease_checks_paused"

        await api.put("/api/admin/settings/tier", json={"tier": "full"}, headers=AUTH)
        assert "answered" in await ask()
    assert answers.questions == 3  # the static tier's question reached no model

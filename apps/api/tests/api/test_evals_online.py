"""GET /api/evals/online: the last nights of P8b's judged production sample, newest first,
read from eval_runs; nothing else that run table holds."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.api.app import create_app
from plumbline.api.evals import NIGHTS
from plumbline.api.quota import MemoryCounter
from plumbline.core.types import CacheMode
from plumbline.db import make_engine, make_sessionmaker
from plumbline.db.models import EvalRunRow
from plumbline.settings import Settings

pytestmark = pytest.mark.anyio
Sessions = async_sessionmaker[AsyncSession]
FIRST = date(2026, 10, 23)
SETTINGS = Settings(_env_file=None, cache_mode=CacheMode.REPLAY)
# Only the rows these tests write: the test database is shared by the session.
MINE = EvalRunRow.run_id.startswith("online-") | (EvalRunRow.run_id == "dev-A2-claude")


def _summary(day: date, judged: int = 10, faithful: int = 9) -> dict[str, Any]:
    # P8b's shape (security/online_eval.py, Score.summary).
    return {
        "day": day.isoformat(),
        "answered": 100,
        "sampled": 10,
        "judged": judged,
        "faithful": faithful,
        "faithfulness": faithful / judged if judged else None,
        "interval_95": [0.6, 0.98] if judged else None,
        "cost_usd": 0.004,
        "skipped": {"no sources": 1},
    }


def _run(run_id: str, summary: Any, golden_file: str = "production") -> EvalRunRow:
    return EvalRunRow(
        run_id=run_id,
        schema_version=1,
        config_name="A2-claude",
        config_hash="f8b25ab8",
        git_sha="abc1234",
        golden_file=golden_file,
        split="all",
        judged=True,
        n_items=10,
        summary=summary,
        notes=None,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
async def sessions(database_url: str) -> AsyncIterator[Sessions]:
    engine = make_engine(database_url)
    sessions = make_sessionmaker(engine)
    async with sessions() as session, session.begin():
        await session.execute(delete(EvalRunRow).where(MINE))
    yield sessions
    async with sessions() as session, session.begin():
        await session.execute(delete(EvalRunRow).where(MINE))
    await engine.dispose()


async def _get(sessions: Sessions) -> httpx.Response:
    app = create_app(SETTINGS, sessions=sessions, counter=MemoryCounter())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/evals/online")


@pytest.mark.db
async def test_nothing_before_the_first_night(sessions: Sessions) -> None:
    response = await _get(sessions)
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.db
async def test_the_last_nights_newest_first_and_nothing_else(sessions: Sessions) -> None:
    days = [FIRST + timedelta(days=n) for n in range(NIGHTS + 2)]
    async with sessions() as session, session.begin():
        session.add_all(_run(f"online-{day.isoformat()}", _summary(day)) for day in days)
        session.add(_run("dev-A2-claude", _summary(FIRST), golden_file="golden/v1.jsonl"))
        session.add(_run("online-2026-10-20", _summary(date(2026, 10, 20)), golden_file="x"))
    response = await _get(sessions)
    nights = response.json()
    assert [n["day"] for n in nights] == [d.isoformat() for d in reversed(days)][:NIGHTS]
    assert nights[0] == {
        "day": days[-1].isoformat(),
        "config_name": "A2-claude",
        "answered": 100,
        "sampled": 10,
        "judged": 10,
        "faithful": 9,
        "faithfulness": 0.9,
        "interval_95": [0.6, 0.98],
    }  # the counts and the rate; the night's cost and skip reasons stay internal
    assert response.headers["cache-control"] == "public, max-age=3600"


@pytest.mark.db
async def test_a_night_with_nothing_judged_or_a_foreign_summary(sessions: Sessions) -> None:
    async with sessions() as session, session.begin():
        session.add(_run("online-2026-10-24", _summary(date(2026, 10, 24), judged=0, faithful=0)))
        session.add(_run("online-2026-10-23", {"day": "2026-10-23", "note": "not P8b's shape"}))
    nights = (await _get(sessions)).json()
    assert len(nights) == 1
    assert (nights[0]["faithfulness"], nights[0]["interval_95"]) == (None, None)


async def test_a_database_that_cannot_answer_is_a_503() -> None:
    engine = make_engine("postgresql+psycopg://nobody@127.0.0.1:1/none")
    response = await _get(make_sessionmaker(engine))
    await engine.dispose()
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")

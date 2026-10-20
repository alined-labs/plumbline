"""POST /api/feedback: a reader's verdict is stored as sent, and anything else is refused."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.api.app import create_app
from plumbline.core.types import CacheMode
from plumbline.db import make_engine, make_sessionmaker
from plumbline.db.models import PUBLIC_TENANT, FeedbackRow
from plumbline.db.session import tenant_session
from plumbline.settings import Settings

pytestmark = [pytest.mark.db, pytest.mark.anyio]
Sessions = async_sessionmaker[AsyncSession]


@pytest.fixture
async def sessions(database_url: str) -> AsyncIterator[Sessions]:
    engine = make_engine(database_url)
    yield make_sessionmaker(engine)
    await engine.dispose()


@pytest.fixture
async def api(sessions: Sessions) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(_env_file=None, cache_mode=CacheMode.REPLAY)
    transport = httpx.ASGITransport(app=create_app(settings, sessions=sessions))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _verdict(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "request_id": f"req_{uuid.uuid4().hex[:16]}",
        "helpful": False,
        "reasons": ["wrong_citation", "outdated_law"],
        "note": "Article 9 changed in 2019.",
    }
    return {**body, **changes}


async def test_a_verdict_is_stored_as_sent(api: httpx.AsyncClient, sessions: Sessions) -> None:
    body = _verdict()
    response = await api.post("/api/feedback", json=body)
    assert (response.status_code, response.content) == (204, b"")
    async with tenant_session(sessions, PUBLIC_TENANT) as session:
        row = (
            await session.scalars(
                select(FeedbackRow).where(FeedbackRow.request_id == body["request_id"])
            )
        ).one()
    assert (row.helpful, row.reasons, row.note) == (False, body["reasons"], body["note"])


async def test_a_bare_verdict_is_enough(api: httpx.AsyncClient) -> None:
    body = {"request_id": "req_0123456789abcdef", "helpful": True}
    assert (await api.post("/api/feedback", json=body)).status_code == 204


@pytest.mark.parametrize(
    "changes",
    [
        {"reasons": ["too_long"]},
        {"reasons": ["hard_to_follow", "hard_to_follow"]},
        {"note": "x" * 1001},
        {"request_id": ""},
        {"helpful": "maybe"},
        {"rating": 5},
    ],
)
async def test_anything_else_is_refused(api: httpx.AsyncClient, changes: dict[str, Any]) -> None:
    assert (await api.post("/api/feedback", json=_verdict(**changes))).status_code == 422

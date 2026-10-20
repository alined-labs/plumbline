"""The admin job routes against Postgres: the token, the job list, and a job's event
stream (complete, resumable, and ending on time). The app, its engine and the test share
one event loop, as async database connections cannot cross loops."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.api import admin
from plumbline.api.app import create_app
from plumbline.core.types import CacheMode
from plumbline.db import make_engine, make_sessionmaker
from plumbline.db.models import PUBLIC_TENANT
from plumbline.db.session import tenant_session
from plumbline.jobs.queue import add_event, claim, enqueue, finish
from plumbline.settings import Settings

pytestmark = [pytest.mark.db, pytest.mark.anyio]
Sessions = async_sessionmaker[AsyncSession]
TOKEN = "test-admin-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
async def sessions(database_url: str) -> AsyncIterator[Sessions]:
    engine = make_engine(database_url)
    yield make_sessionmaker(engine)
    await engine.dispose()


def _client(sessions: Sessions, token: str | None) -> httpx.AsyncClient:
    # Every setting the test relies on is explicit: DeepEval's pytest plugin copies a
    # developer's .env into os.environ.
    settings = Settings(
        _env_file=None,
        cache_mode=CacheMode.REPLAY,
        admin_token=SecretStr(token) if token else None,
    )
    app = create_app(settings, sessions=sessions)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def api(sessions: Sessions) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(sessions, TOKEN) as client:
        yield client


async def _job(sessions: Sessions, *, done: bool) -> uuid.UUID:
    """A public-corpus job that was queued, started and reported progress, and maybe finished."""
    content_hash = uuid.uuid4().hex * 2
    async with tenant_session(sessions, PUBLIC_TENANT) as session:
        job, _ = await enqueue(
            session,
            tenant_id=PUBLIC_TENANT,
            kind="parse",
            source_id=f"src-{content_hash[:8]}",
            content_hash=content_hash,
        )
        job_id = job.id
    async with tenant_session(sessions, PUBLIC_TENANT) as session:
        while (claimed := await claim(session, "worker-1")) is not None and claimed.id != job_id:
            pass  # older jobs from other tests stay running; they are not ours
        add_event(session, job_id, PUBLIC_TENANT, "progress", "page 1 of 1", {"page": 1})
        if done:
            await finish(session, job_id, {"pages": 1})
    return job_id


def _events(body: str) -> list[dict[str, Any]]:
    """The SSE body as one dict per event (comment lines dropped)."""
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(
            line.split(": ", 1) for line in block.splitlines() if not line.startswith(":")
        )
        if fields:
            events.append(fields)
    return events


async def test_the_routes_want_the_admin_token(api: httpx.AsyncClient) -> None:
    assert (await api.get("/api/admin/jobs")).status_code == 401
    wrong = await api.get("/api/admin/jobs", headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 401
    assert wrong.headers["www-authenticate"] == "Bearer"


async def test_without_an_admin_token_the_routes_do_not_exist(sessions: Sessions) -> None:
    async with _client(sessions, None) as client:
        assert (await client.get("/api/admin/jobs", headers=AUTH)).status_code == 404


async def test_the_job_list_shows_the_newest_first(
    api: httpx.AsyncClient, sessions: Sessions
) -> None:
    older = await _job(sessions, done=True)
    newer = await _job(sessions, done=True)
    response = await api.get("/api/admin/jobs", params={"status": "succeeded"}, headers=AUTH)
    jobs = response.json()
    ids = [job["id"] for job in jobs]
    assert ids.index(str(newer)) < ids.index(str(older))
    assert {job["status"] for job in jobs} == {"succeeded"}
    one = (await api.get(f"/api/admin/jobs/{newer}", headers=AUTH)).json()
    assert (one["result"], one["attempts"]) == ({"pages": 1}, 1)
    assert (await api.get(f"/api/admin/jobs/{uuid.uuid4()}", headers=AUTH)).status_code == 404


async def test_a_finished_jobs_stream_sends_every_event_and_ends(
    api: httpx.AsyncClient, sessions: Sessions
) -> None:
    job_id = await _job(sessions, done=True)
    response = await api.get(f"/api/admin/jobs/{job_id}/events", headers=AUTH)
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response.text)
    assert [e["event"] for e in events] == ["queued", "started", "progress", "succeeded"]
    assert json.loads(events[2]["data"])["data"] == {"page": 1}
    ids = [int(e["id"]) for e in events]
    assert ids == sorted(ids)
    resumed = await api.get(
        f"/api/admin/jobs/{job_id}/events", headers={**AUTH, "Last-Event-ID": str(ids[1])}
    )
    assert [e["event"] for e in _events(resumed.text)] == ["progress", "succeeded"]


async def test_a_running_jobs_stream_still_ends(
    api: httpx.AsyncClient, sessions: Sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(admin, "POLL_S", 0.01)
    monkeypatch.setattr(admin, "MAX_STREAM_S", 0.05)
    job_id = await _job(sessions, done=False)
    events = _events((await api.get(f"/api/admin/jobs/{job_id}/events", headers=AUTH)).text)
    assert [e["event"] for e in events] == ["queued", "started", "progress", "timeout"]

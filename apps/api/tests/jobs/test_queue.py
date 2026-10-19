"""The job queue against Postgres: idempotent queuing, SKIP LOCKED claims, the event log,
the worker loop, stale jobs and tenant isolation."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Mapping
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.db import make_engine, make_sessionmaker
from plumbline.db.models import IngestionJob, IngestionJobEvent, Tenant
from plumbline.db.session import tenant_session
from plumbline.jobs.queue import JobContext, claim, enqueue, fail, finish, requeue_stale, work

pytestmark = [pytest.mark.db, pytest.mark.anyio]
Sessions = async_sessionmaker[AsyncSession]


@pytest.fixture
async def sessions(database_url: str) -> AsyncIterator[Sessions]:
    engine = make_engine(database_url)
    yield make_sessionmaker(engine)
    await engine.dispose()


async def _tenant(sessions: Sessions) -> uuid.UUID:
    tenant = uuid.uuid4()
    async with sessions() as session, session.begin():  # as the owner: the app adds no tenants
        session.add(Tenant(id=tenant, slug=f"t-{tenant.hex}", name="Test"))
    return tenant


@pytest.fixture
async def tenant(sessions: Sessions) -> uuid.UUID:
    return await _tenant(sessions)


async def _enqueue(
    session: AsyncSession, tenant: uuid.UUID, content_hash: str
) -> tuple[IngestionJob, bool]:
    return await enqueue(
        session,
        tenant_id=tenant,
        kind="parse",
        source_id=f"src-{content_hash[:4]}",
        content_hash=content_hash,
    )


async def _events(sessions: Sessions, tenant: uuid.UUID, job_id: uuid.UUID) -> list[str]:
    async with tenant_session(sessions, tenant) as session:
        kinds = await session.scalars(
            select(IngestionJobEvent.kind)
            .where(IngestionJobEvent.job_id == job_id)
            .order_by(IngestionJobEvent.id)
        )
        return list(kinds)


async def test_the_same_input_is_queued_once(sessions: Sessions, tenant: uuid.UUID) -> None:
    async with tenant_session(sessions, tenant) as session:
        first, created = await _enqueue(session, tenant, "a" * 64)
        again, created_again = await _enqueue(session, tenant, "a" * 64)
    assert (created, created_again) == (True, False)
    assert again.id == first.id
    assert await _events(sessions, tenant, first.id) == ["queued"]


async def test_queuing_again_retries_a_failed_job_but_not_a_finished_one(
    sessions: Sessions, tenant: uuid.UUID
) -> None:
    async with tenant_session(sessions, tenant) as session:
        failed, _ = await _enqueue(session, tenant, "b" * 64)
        finished, _ = await _enqueue(session, tenant, "c" * 64)
        await fail(session, failed.id, "boom")
        await finish(session, finished.id, {"pages": 3})
    async with tenant_session(sessions, tenant) as session:
        retried, requeued = await _enqueue(session, tenant, "b" * 64)
        kept, redone = await _enqueue(session, tenant, "c" * 64)
        assert (retried.status, requeued, retried.error) == ("queued", True, None)
        assert (kept.status, redone) == ("succeeded", False)


async def test_two_workers_never_claim_the_same_job(sessions: Sessions, tenant: uuid.UUID) -> None:
    async with tenant_session(sessions, tenant) as session:
        older, _ = await _enqueue(session, tenant, "d" * 64)
        newer, _ = await _enqueue(session, tenant, "e" * 64)
    # Each worker holds its claim's lock until its transaction ends.
    async with tenant_session(sessions, tenant) as one, tenant_session(sessions, tenant) as two:
        first = await claim(one, "worker-1")
        second = await claim(two, "worker-2")
        assert first is not None
        assert second is not None
        assert (first.id, second.id) == (older.id, newer.id)
        assert await claim(two, "worker-2") is None
    async with tenant_session(sessions, tenant) as session:
        assert await claim(session, "worker-3") is None  # both are running now
    assert await _events(sessions, tenant, older.id) == ["queued", "started"]


async def test_a_worker_runs_each_job_and_records_how_it_went(
    sessions: Sessions, tenant: uuid.UUID
) -> None:
    async def parse(job: JobContext) -> Mapping[str, Any]:
        if job.source_id == "src-gggg":
            raise ValueError("unreadable page 3")
        await job.progress("page 1 of 2", {"page": 1})
        return {"pages": 2}

    async with tenant_session(sessions, tenant) as session:
        good, _ = await _enqueue(session, tenant, "f" * 64)
        bad, _ = await _enqueue(session, tenant, "g" * 64)
    assert await work(sessions, tenant, {"parse": parse}, "worker-1") == 2
    async with tenant_session(sessions, tenant) as session:
        done = await session.get_one(IngestionJob, good.id)
        failed = await session.get_one(IngestionJob, bad.id)
        assert (done.status, done.result, done.attempts) == ("succeeded", {"pages": 2}, 1)
        assert (failed.status, failed.error) == ("failed", "ValueError: unreadable page 3")
    assert await _events(sessions, tenant, good.id) == [
        "queued",
        "started",
        "progress",
        "succeeded",
    ]
    assert await _events(sessions, tenant, bad.id) == ["queued", "started", "failed"]


async def test_a_job_of_an_unknown_kind_fails(sessions: Sessions, tenant: uuid.UUID) -> None:
    async with tenant_session(sessions, tenant) as session:
        job, _ = await _enqueue(session, tenant, "h" * 64)
    await work(sessions, tenant, {}, "worker-1")
    async with tenant_session(sessions, tenant) as session:
        failed = await session.get_one(IngestionJob, job.id)
        assert failed.error == "LookupError: no handler for parse jobs"


async def test_a_job_whose_worker_died_goes_back_to_the_queue(
    sessions: Sessions, tenant: uuid.UUID
) -> None:
    async with tenant_session(sessions, tenant) as session:
        job, _ = await _enqueue(session, tenant, "i" * 64)
        await claim(session, "worker-1")
    async with tenant_session(sessions, tenant) as session:
        an_hour_ago = IngestionJob.started_at - timedelta(hours=1)
        await session.execute(
            update(IngestionJob).where(IngestionJob.id == job.id).values(started_at=an_hour_ago)
        )
        assert await requeue_stale(session, timedelta(minutes=30)) == 1
    async with tenant_session(sessions, tenant) as session:
        assert (await session.get_one(IngestionJob, job.id)).status == "queued"
    assert await _events(sessions, tenant, job.id) == ["queued", "started", "requeued"]


async def test_a_tenant_never_sees_or_claims_another_tenants_jobs(
    sessions: Sessions, tenant: uuid.UUID
) -> None:
    other = await _tenant(sessions)
    async with tenant_session(sessions, tenant) as session:
        job, _ = await _enqueue(session, tenant, "j" * 64)
    async with tenant_session(sessions, other) as session:
        assert await claim(session, "worker-1") is None
        assert await session.get(IngestionJob, job.id) is None


async def test_the_event_log_cannot_be_rewritten(sessions: Sessions, tenant: uuid.UUID) -> None:
    async with tenant_session(sessions, tenant) as session:
        job, _ = await _enqueue(session, tenant, "k" * 64)
    edit = update(IngestionJobEvent).where(IngestionJobEvent.job_id == job.id)
    with pytest.raises(DBAPIError, match="permission denied"):
        async with tenant_session(sessions, tenant) as session:
            await session.execute(edit.values(message="edited"))

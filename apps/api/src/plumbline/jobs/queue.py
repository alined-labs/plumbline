"""The ingestion job queue (Lane D), in Postgres: no broker to run, and a job and its
events commit with the work they describe.

- Idempotent by content: a job is unique per tenant, kind and content hash. Queuing the
  same input again returns the existing job; only a failed job goes back to the queue, so
  a re-run retries failures and never redoes finished work.
- Workers claim the oldest queued job with SELECT ... FOR UPDATE SKIP LOCKED, so any
  number of them can poll at once and none waits on, or takes, another's job.
- Every step appends an event, each in its own short transaction, so the job's event
  stream shows progress while the work is still running.
- A job left running by a worker that died goes back to the queue after a timeout.

Every function takes a session from plumbline.db.session.tenant_session, so row-level
security confines it to one tenant's jobs.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Final

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.db.models import IngestionJob, IngestionJobEvent
from plumbline.db.session import tenant_session

log = logging.getLogger(__name__)

QUEUED: Final = "queued"
RUNNING: Final = "running"
SUCCEEDED: Final = "succeeded"
FAILED: Final = "failed"
FINISHED: Final = frozenset({SUCCEEDED, FAILED})


async def enqueue(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    kind: str,
    source_id: str,
    content_hash: str,
    payload: Mapping[str, Any] | None = None,
) -> tuple[IngestionJob, bool]:
    """The job for this input, and whether it was (re)queued now."""
    new_id = await session.scalar(
        insert(IngestionJob)
        .values(
            tenant_id=tenant_id,
            kind=kind,
            source_id=source_id,
            content_hash=content_hash,
            payload=dict(payload or {}),
            # now() is the transaction's start, the same for every job queued in it; the
            # clock keeps first-in, first-out among them.
            created_at=func.clock_timestamp(),
        )
        .on_conflict_do_nothing(constraint="uq_ingestion_jobs_input")
        .returning(IngestionJob.id)
    )
    if new_id is not None:
        add_event(session, new_id, tenant_id, QUEUED, f"{kind} {source_id}")
        return await _get(session, new_id), True
    job = (
        await session.scalars(
            select(IngestionJob).where(
                IngestionJob.tenant_id == tenant_id,
                IngestionJob.kind == kind,
                IngestionJob.content_hash == content_hash,
            )
        )
    ).one()
    if job.status != FAILED:
        return job, False
    job.status, job.error, job.finished_at = QUEUED, None, None
    add_event(session, job.id, tenant_id, "requeued", "retrying after a failure")
    return job, True


async def claim(session: AsyncSession, worker: str) -> IngestionJob | None:
    """The oldest queued job, now running for `worker`; None when there is none. The row
    stays locked until the session commits, which is what keeps two workers apart."""
    job = (
        await session.scalars(
            select(IngestionJob)
            .where(IngestionJob.status == QUEUED)
            .order_by(IngestionJob.created_at, IngestionJob.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
    ).first()
    if job is None:
        return None
    job.status, job.worker, job.started_at = RUNNING, worker, func.now()
    job.attempts += 1
    add_event(session, job.id, job.tenant_id, "started", f"attempt {job.attempts} on {worker}")
    await session.flush()
    await session.refresh(job)  # started_at was a SQL expression until the flush
    return job


def add_event(
    session: AsyncSession,
    job_id: uuid.UUID,
    tenant_id: uuid.UUID,
    kind: str,
    message: str = "",
    data: Mapping[str, Any] | None = None,
) -> None:
    session.add(
        IngestionJobEvent(
            job_id=job_id, tenant_id=tenant_id, kind=kind, message=message, data=dict(data or {})
        )
    )


async def finish(session: AsyncSession, job_id: uuid.UUID, result: Mapping[str, Any]) -> None:
    job = await _get(session, job_id)
    job.status, job.result, job.finished_at = SUCCEEDED, dict(result), func.now()
    add_event(session, job_id, job.tenant_id, SUCCEEDED, "done", result)


async def fail(session: AsyncSession, job_id: uuid.UUID, error: str) -> None:
    job = await _get(session, job_id)
    job.status, job.error, job.finished_at = FAILED, error, func.now()
    add_event(session, job_id, job.tenant_id, FAILED, error)


async def requeue_stale(session: AsyncSession, older_than: timedelta) -> int:
    """Put back jobs that have been running longer than `older_than`: their worker died."""
    stale = (
        await session.scalars(
            update(IngestionJob)
            .where(
                IngestionJob.status == RUNNING, IngestionJob.started_at < func.now() - older_than
            )
            .values(status=QUEUED, worker=None)
            .returning(IngestionJob)
        )
    ).all()
    for job in stale:
        add_event(session, job.id, job.tenant_id, "requeued", f"no word from it for {older_than}")
    return len(stale)


Progress = Callable[[str, Mapping[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class JobContext:
    """What a handler gets: the job's input, and a way to report progress."""

    id: uuid.UUID
    kind: str
    source_id: str
    payload: Mapping[str, Any]
    progress: Progress


Handler = Callable[[JobContext], Awaitable[Mapping[str, Any]]]  # returns the job's result


async def work(
    sessions: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    handlers: Mapping[str, Handler],
    worker: str,
) -> int:
    """Run queued jobs until the queue is empty; the number of jobs run. A handler that
    raises fails its job and the worker moves on to the next."""
    done = 0
    while True:
        async with tenant_session(sessions, tenant_id) as session:
            job = await claim(session, worker)
            if job is None:
                return done
            context = JobContext(
                job.id, job.kind, job.source_id, dict(job.payload), _reporter(sessions, job)
            )
        try:
            if context.kind not in handlers:
                raise LookupError(f"no handler for {context.kind} jobs")
            result = await handlers[context.kind](context)
        except Exception as exc:
            log.exception("job %s (%s %s) failed", context.id, context.kind, context.source_id)
            async with tenant_session(sessions, tenant_id) as session:
                await fail(session, context.id, f"{type(exc).__name__}: {exc}")
        else:
            async with tenant_session(sessions, tenant_id) as session:
                await finish(session, context.id, result)
        done += 1


def _reporter(sessions: async_sessionmaker[AsyncSession], job: IngestionJob) -> Progress:
    job_id, tenant_id = job.id, job.tenant_id

    async def progress(message: str, data: Mapping[str, Any]) -> None:
        async with tenant_session(sessions, tenant_id) as session:
            add_event(session, job_id, tenant_id, "progress", message, data)

    return progress


async def _get(session: AsyncSession, job_id: uuid.UUID) -> IngestionJob:
    return (await session.scalars(select(IngestionJob).where(IngestionJob.id == job_id))).one()

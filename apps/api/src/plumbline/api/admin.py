"""Admin routes (Lane D): the public corpus's ingestion jobs and their event streams.

They take `Authorization: Bearer <ADMIN_TOKEN>`, compared in constant time; with no
ADMIN_TOKEN set they answer 404, as if they did not exist. The jobs are the public
tenant's, since the corpus is all that is ingested, and every query still runs under
row-level security.
"""

from __future__ import annotations

import secrets
import time
import uuid
from collections.abc import AsyncIterable
from typing import Annotated, Final

import anyio
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.api.schemas import JobEventView, JobStatus, JobView
from plumbline.db.models import PUBLIC_TENANT, IngestionJob, IngestionJobEvent
from plumbline.db.session import tenant_session
from plumbline.jobs.queue import FINISHED
from plumbline.settings import Settings

POLL_S: Final = 0.5  # how often a stream looks for new events
PING_S: Final = 15.0  # a comment line this often keeps proxies from closing an idle stream
MAX_STREAM_S: Final = 30 * 60.0  # a stream ends by then even if its job never does

bearer = HTTPBearer(auto_error=False, description="The ADMIN_TOKEN from the server's settings.")


def require_admin(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    settings: Settings = request.app.state.settings
    if settings.admin_token is None:
        raise HTTPException(status_code=404, detail="Not Found")
    given = credentials.credentials if credentials else ""
    if not secrets.compare_digest(given.encode(), settings.admin_token.get_secret_value().encode()):
        raise HTTPException(
            status_code=401,
            detail="A valid admin token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )


router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    sessions: async_sessionmaker[AsyncSession] = request.app.state.sessions
    return sessions


async def _job(request: Request, job_id: uuid.UUID) -> JobView:
    async with tenant_session(_sessions(request), PUBLIC_TENANT) as session:
        job = await session.get(IngestionJob, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="No such job.")
        return JobView.model_validate(job)


@router.get("/jobs")
async def list_jobs(
    request: Request,
    status: JobStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[JobView]:
    """The most recent jobs first."""
    query = select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(limit)
    if status is not None:
        query = query.where(IngestionJob.status == status)
    async with tenant_session(_sessions(request), PUBLIC_TENANT) as session:
        return [JobView.model_validate(job) for job in await session.scalars(query)]


@router.get("/jobs/{job_id}")
async def get_job(job: Annotated[JobView, Depends(_job)]) -> JobView:
    return job


@router.get(
    "/jobs/{job_id}/events",
    response_class=EventSourceResponse,
    responses={
        200: {
            "description": "The job's events as server-sent events: `event` is the kind, `id`"
            " the event's id (send it back as Last-Event-ID to resume), `data` a JobEventView."
            " The stream ends once the job has finished, or with a `timeout` event."
        }
    },
)
async def job_events(
    request: Request,
    job: Annotated[JobView, Depends(_job)],
    last_event_id: Annotated[int | None, Header()] = None,
) -> AsyncIterable[ServerSentEvent]:
    sessions = _sessions(request)
    after = last_event_id or 0
    started = last_ping = time.monotonic()
    while True:
        events, finished = await _events_after(sessions, job.id, after)
        for event in events:
            yield ServerSentEvent(data=event, event=event.kind, id=str(event.id))
            after = event.id
        if finished or await request.is_disconnected():
            return
        now = time.monotonic()
        if now - started >= MAX_STREAM_S:
            yield ServerSentEvent(data={"message": "the job is still running"}, event="timeout")
            return
        if now - last_ping >= PING_S:
            yield ServerSentEvent(comment="ping")
            last_ping = now
        await anyio.sleep(POLL_S)


async def _events_after(
    sessions: async_sessionmaker[AsyncSession], job_id: uuid.UUID, after: int
) -> tuple[list[JobEventView], bool]:
    """The job's events after `after`, and whether the job has finished. The status is
    read first: a job's final status and final event commit in one transaction, so once
    the status says finished, the events read after it include the last one."""
    async with tenant_session(sessions, PUBLIC_TENANT) as session:
        status = await session.scalar(select(IngestionJob.status).where(IngestionJob.id == job_id))
        rows = await session.scalars(
            select(IngestionJobEvent)
            .where(IngestionJobEvent.job_id == job_id, IngestionJobEvent.id > after)
            .order_by(IngestionJobEvent.id)
        )
        return [JobEventView.model_validate(row) for row in rows], status in FINISHED

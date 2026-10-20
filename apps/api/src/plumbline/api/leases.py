"""Lease checks over HTTP (Lane D, task D7): upload a lease and follow the check as a stream
of events.

    POST /api/check-lease?jurisdiction=&signed_on=   the file as the request body -> 202 {id}
    GET  /api/check-lease/{id}/events                server-sent events; Last-Event-ID resumes
    GET  /api/check-lease/{id}                       the check so far, for a page that reloaded

The file is the request body, not a multipart form: a form needs a parser dependency and
writes its larger parts to a temporary file, while a body is read here, in memory, with the
size limit enforced as it arrives. The lease is never written to disk, logged or kept: a
check keeps only its events (stages and findings, which quote clauses after redaction) for
half an hour, for the visitor who started it (api/runs.py).

Until the real redactor runs, only the invented leases in data/leases may be checked: a file
whose bytes match one of them byte for byte is marked synthetic, which the stand-in
redactor lets through, and every other file is refused before any model call.

A check that starts ends with `done`, or with `failed` and why. What stops one from
starting is answered as problem details with a code, in this order: 503 `lease_checks_paused`
when the demo tier does not run them, 429 `quota_reached` when today's checks are used up,
503 `busy` when the server is full (all three before a byte of the file is read), then the
file's own faults, 413 `too_large`, 415 `unsupported_type` and 422 `unreadable`. A check is
counted against the day's allowance only once its file has been read: a file that fails
costs nothing.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterable, AsyncIterator
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Final, Literal, Protocol

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.sse import EventSourceResponse, ServerSentEvent
from starlette.requests import ClientDisconnect

from plumbline.api.problems import MEDIA_TYPE, ApiError
from plumbline.api.quota import Quota, set_visitor_cookie
from plumbline.api.runs import Busy, Run, Runs, Work
from plumbline.api.schemas import (
    LeaseDoneEvent,
    LeaseFailedEvent,
    LeaseResult,
    LeaseStageEvent,
    LeaseStarted,
)
from plumbline.api.tier import tier_store
from plumbline.core.types import DemoTier, Jurisdiction
from plumbline.generation.router import Route, RouteRefused, Upload
from plumbline.ingest.upload import (
    MAX_BYTES,
    UploadedText,
    UploadError,
    guess_language,
    read_upload,
)
from plumbline.leases.checker import LeaseCheckError, LeaseDone, LeaseEvent, LeaseStage
from plumbline.leases.schema import Finding
from plumbline.settings import ROOT

PING_S: Final = 15.0  # a comment this often keeps a quiet stream from being closed on the way
MEGABYTE: Final = 1024 * 1024
FORMS: Final = ("multipart/", "application/x-www-form-urlencoded")
SAMPLES: Final = ROOT / "data" / "leases"


class LeaseChecker(Protocol):
    """What the routes need of the lease checker (Lane C's, wired with retrieval and the
    redactor): the model route this tier allows, and the check itself."""

    async def route(self, tier: DemoTier) -> Route:
        """RouteRefused when the tier does not run lease checks."""
        ...

    def stream(
        self,
        upload: Upload,
        route: Route,
        *,
        jurisdiction: Jurisdiction | None,
        as_of: date | None,
    ) -> AsyncIterator[LeaseEvent]: ...


router = APIRouter(prefix="/api/check-lease", tags=["leases"])


def sample_digests(folder: Path = SAMPLES) -> frozenset[str]:
    """The SHA-256 of each invented lease the site offers: the Markdown leases, sent as their
    own text, and the scanned PDFs."""
    files = [*folder.glob("*-lease-*.md"), *folder.glob("scans/*.pdf")]
    return frozenset(_digest(path.read_bytes()) for path in files)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def failure(code: str, message: str) -> tuple[str, LeaseFailedEvent]:
    """The event that ends a run that failed for a reason of ours (see api/runs.py)."""
    return "failed", LeaseFailedEvent.model_validate({"code": code, "message": message})


def _problem(description: str, **extra: Any) -> dict[str, Any]:
    schema = {"$ref": "#/components/schemas/Problem"}
    return {"description": description, "content": {MEDIA_TYPE: {"schema": schema}}, **extra}


RETRY_AFTER: Final = {"Retry-After": {"schema": {"type": "integer"}}}
REQUEST_BODY: Final = {
    "required": True,
    "description": "The lease itself, not a form: a PDF, a Word document (DOCX) or plain text,"
    f" up to {MAX_BYTES // MEGABYTE} MB. The type is read from the bytes, whatever the"
    " Content-Type says.",
    "content": {
        media: {"schema": {"type": "string", "format": "binary"}}
        for media in (
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/plain",
            "application/octet-stream",
        )
    },
}


@router.post(
    "",
    status_code=202,
    openapi_extra={"requestBody": REQUEST_BODY},
    responses={
        202: {"description": "The check started."},
        413: _problem("`too_large`: the file is over the size or length limit."),
        415: _problem(
            "`unsupported_type`: not a PDF, a Word document or text (or sent as a form)."
        ),
        422: _problem("`unreadable`: no text could be read from the file (a scan, a broken file)."),
        429: _problem(
            "`quota_reached`: today's lease checks are used up; Retry-After gives the seconds"
            " until 00:00 UTC.",
            headers=RETRY_AFTER,
        ),
        503: _problem(
            "`lease_checks_paused` (the demo tier does not run them) or `busy` (too many checks"
            " are running; Retry-After gives the seconds).",
            headers=RETRY_AFTER,
        ),
    },
)
async def start(
    request: Request,
    response: Response,
    jurisdiction: Annotated[
        Jurisdiction | None, Query(description="The governing jurisdiction, when the reader knows.")
    ] = None,
    signed_on: Annotated[
        date | None, Query(description="When the lease was signed: the law in force then.")
    ] = None,
) -> LeaseStarted:
    state = request.app.state
    checker: LeaseChecker = state.lease_checker
    try:
        route = await checker.route(await tier_store(request).current())
    except RouteRefused as exc:
        raise ApiError(503, "lease_checks_paused", str(exc)) from exc
    quota: Quota = state.quota
    runs: Runs = state.runs
    visitor = await quota.visitor(request)
    await quota.admit(request, "lease", visitor=visitor, count=False)
    _room(runs, visitor.id)
    data = await _body(request)
    read = await _read(data)
    await quota.admit(request, "lease", visitor=visitor)
    synthetic = _digest(data) in state.sample_leases
    upload = Upload(text=read.text, language=guess_language(read.text), synthetic=synthetic)
    try:
        run = runs.start(visitor.id, _work(checker, upload, route, jurisdiction, signed_on))
    except Busy as exc:  # (another check began since the look: rare, and then it is counted)
        raise _busy(exc) from exc
    set_visitor_cookie(response, visitor, state.settings)
    response.headers["Location"] = f"{router.prefix}/{run.id}"
    return LeaseStarted(id=run.id)


def _room(runs: Runs, owner: str) -> None:
    try:
        runs.check_room(owner)
    except Busy as exc:
        raise _busy(exc) from exc


def _busy(busy: Busy) -> ApiError:
    return ApiError(
        503,
        "busy",
        "Other lease checks are running. Please try again in a moment.",
        headers={"Retry-After": str(busy.retry_after)},
    )


async def _body(request: Request) -> bytes:
    """The request body, which is the file, at most MAX_BYTES of it."""
    if request.headers.get("content-type", "").lower().startswith(FORMS):
        raise ApiError(
            415, "unsupported_type", "Send the file itself as the request body, not a form."
        )
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BYTES:
        raise _too_large()
    chunks: list[bytes] = []
    size = 0
    try:
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_BYTES:
                raise _too_large()
            chunks.append(chunk)
    except ClientDisconnect as exc:
        raise HTTPException(status_code=400, detail="The upload was interrupted.") from exc
    return b"".join(chunks)


def _too_large() -> ApiError:
    return ApiError(413, "too_large", f"The file is over {MAX_BYTES // MEGABYTE} MB.")


async def _read(data: bytes) -> UploadedText:
    try:
        return await asyncio.to_thread(read_upload, data)
    except UploadError as exc:
        raise ApiError(exc.status, exc.code, exc.message) from exc


def _work(
    checker: LeaseChecker,
    upload: Upload,
    route: Route,
    jurisdiction: Jurisdiction | None,
    as_of: date | None,
) -> Work:
    """The run: the checker's events become the run's, and a failure of the lease's own
    (no clauses, no jurisdiction) ends it with the checker's message for the reader."""

    async def work(run: Run) -> None:
        run.emit("stage", LeaseStageEvent(stage="uploaded"))
        try:
            async for item in checker.stream(upload, route, jurisdiction=jurisdiction, as_of=as_of):
                if isinstance(item, LeaseStage):
                    run.emit(
                        "stage", LeaseStageEvent(stage=item.stage, done=item.done, total=item.total)
                    )
                elif isinstance(item, Finding):
                    run.emit("finding", item)
                elif isinstance(item, LeaseDone):
                    run.end("done", LeaseDoneEvent(findings=item.findings, language=item.language))
        except LeaseCheckError as exc:
            run.end("failed", LeaseFailedEvent(code=exc.code, message=str(exc)))

    return work


async def _run(request: Request, run_id: str) -> Run:
    """The check, if it exists and this visitor started it; anyone else gets a 404."""
    owner = await request.app.state.quota.owner(request)
    run: Run | None = request.app.state.runs.get(run_id, owner)
    if run is None:
        raise ApiError(404, "not_found", "No such check. It may have expired.")
    return run


@router.get(
    "/{run_id}/events",
    response_class=EventSourceResponse,
    responses={
        200: {
            "description": "The check's events as server-sent events: `event` is `stage`"
            " (LeaseStageEvent), `finding` (Finding), `done` (LeaseDoneEvent) or `failed`"
            " (LeaseFailedEvent); `id` numbers them from 1, and sending the last one back as"
            " Last-Event-ID resumes after it. The stream ends after `done` or `failed`."
        },
        404: _problem("`not_found`: no such check, it expired, or it is another visitor's."),
    },
)
async def events(
    request: Request,
    run: Annotated[Run, Depends(_run)],
    last_event_id: Annotated[int | None, Header()] = None,
) -> AsyncIterable[ServerSentEvent]:
    after = min(max(last_event_id or 0, 0), len(run.events))
    while True:
        for event in run.events[after:]:
            yield ServerSentEvent(data=event.data, event=event.name, id=str(event.id))
            after = event.id
        if run.ended and after == len(run.events):
            return
        try:
            await asyncio.wait_for(run.wait(after), PING_S)
        except TimeoutError:
            if await request.is_disconnected():
                return
            yield ServerSentEvent(comment="ping")


@router.get(
    "/{run_id}",
    responses={
        404: _problem("`not_found`: no such check, it expired, or it is another visitor's.")
    },
)
async def result(response: Response, run: Annotated[Run, Depends(_run)]) -> LeaseResult:
    findings: list[Finding] = []
    language = None
    failed = None
    for event in run.events:
        if isinstance(event.data, Finding):
            findings.append(event.data)
        elif isinstance(event.data, LeaseDoneEvent):
            language = event.data.language
        elif isinstance(event.data, LeaseFailedEvent):
            failed = event.data
    response.headers["Cache-Control"] = "no-store"  # a lease's findings are private
    status: Literal["running", "done", "failed"] = (
        "failed" if failed else "done" if run.ended else "running"
    )
    return LeaseResult(
        id=run.id, status=status, language=language, findings=findings, failure=failed
    )

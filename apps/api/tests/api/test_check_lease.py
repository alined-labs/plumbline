"""A lease check over HTTP: the file as the body, what the reader may add, what a file or a
checker can get wrong, what keeps a check from starting, and the stream of its events."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import date
from typing import Any, Literal, cast

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.sse import ServerSentEvent

from plumbline.api import leases
from plumbline.api.app import create_app
from plumbline.api.lease_stub import CITATION, StubLeaseChecker
from plumbline.api.leases import SAMPLES, LeaseChecker, sample_digests
from plumbline.api.quota import COOKIE, MemoryCounter
from plumbline.api.runs import Run, Runs
from plumbline.api.schemas import LeaseDoneEvent, LeaseStageEvent
from plumbline.core.types import CacheMode, DemoTier, Jurisdiction, Language
from plumbline.db import make_engine, make_sessionmaker
from plumbline.generation.router import Route, Upload
from plumbline.leases.checker import MESSAGES, LeaseCheckError, LeaseDone, LeaseEvent, LeaseStage
from plumbline.leases.schema import Finding, Severity
from plumbline.settings import Settings

pytestmark = pytest.mark.anyio
NO_DATABASE = "postgresql+psycopg://plumbline:plumbline@127.0.0.1:1/none"
LEASE = "\n".join(
    f"Clause {n}. The Tenant shall pay the rent on the first day of each month, and the Landlord"
    " shall keep the dwelling in a state fit to live in for the whole of the term."
    for n in range(1, 5)
)
SPANISH = "\n".join(
    f"Cláusula {n}. El arrendatario pagará la renta el primer día de cada mes y el arrendador"
    " mantendrá la vivienda en estado de servir para el uso convenido durante todo el contrato."
    for n in range(1, 5)
)
Wait = Literal["wait"]
FINDING = Finding(
    n=1,
    clause_number="7",
    clause_text="The tenant waives every right.",
    clause_language=Language.EN,
    severity=Severity.CONFLICT,
    title="A waiver the law does not allow",
    why="The clause says one thing and the Stub Act says another.",
    citations=[CITATION],
    confidence=0.9,
)
ALL_THE_WAY = (
    LeaseStage("redacting"),
    LeaseStage("reading"),
    LeaseStage("checking", done=0, total=1),
    FINDING,
    LeaseStage("checking", done=1, total=1),
    LeaseDone(findings=1, language=Language.EN),
)


class Scripted(StubLeaseChecker):
    """The stub's route, and so its tier rule, with a script for the check: events to
    yield, an error to raise, or "wait" for the gate."""

    def __init__(self, *script: LeaseEvent | Exception | Wait) -> None:
        super().__init__(delay_ms=0)
        self.script = script
        self.gate = asyncio.Event()
        self.seen: list[tuple[Upload, Jurisdiction | None, date | None]] = []

    async def stream(
        self,
        upload: Upload,
        route: Route,
        *,
        jurisdiction: Jurisdiction | None,
        as_of: date | None,
    ) -> AsyncIterator[LeaseEvent]:
        self.seen.append((upload, jurisdiction, as_of))
        for item in self.script:
            if isinstance(item, Exception):
                raise item
            if item == "wait":
                await self.gate.wait()
            else:
                yield item


def _app(
    checker: LeaseChecker | None = None, tier: DemoTier = DemoTier.FULL, questions: int = 30
) -> FastAPI:
    settings = Settings(
        _env_file=None,
        cache_mode=CacheMode.REPLAY,
        demo_tier=tier,
        daily_questions_per_ip=questions,  # lease checks are allowed a tenth of it
        stub_delay_ms=0,
    )
    sessions = make_sessionmaker(make_engine(NO_DATABASE))  # no database: the tier is the setting
    return create_app(settings, sessions=sessions, counter=MemoryCounter(), lease_checker=checker)


def _client(app: FastAPI) -> httpx.AsyncClient:
    """A browser: a cookie jar of its own."""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _start(client: httpx.AsyncClient, body: bytes = LEASE.encode(), **query: str) -> Any:
    return await client.post(
        "/api/check-lease", content=body, params=query, headers={"Content-Type": "text/plain"}
    )


async def _events(
    app: FastAPI, client: httpx.AsyncClient, run_id: str
) -> list[tuple[int, str, Any]]:
    """The events of a check once it has ended, as (id, event, data)."""
    owner = client.cookies[COOKIE].rsplit(".", 1)[0]
    run = app.state.runs.get(run_id, owner)
    while not run.ended:
        await asyncio.wait_for(run.wait(len(run.events)), 5)
    return [(e.id, e.name, json.loads(e.data.model_dump_json())) for e in run.events]


async def _checked(
    app: FastAPI, client: httpx.AsyncClient, body: bytes = LEASE.encode(), **query: str
) -> list[tuple[int, str, Any]]:
    started = await _start(client, body, **query)
    assert started.status_code == 202, started.text
    return await _events(app, client, started.json()["id"])


async def _follow(
    client: httpx.AsyncClient, run_id: str, last_event_id: int | None = None
) -> list[tuple[int, str, Any]]:
    """The events of a check read from its stream, as (id, event, data), until it ends."""
    headers = {} if last_event_id is None else {"Last-Event-ID": str(last_event_id)}
    events: list[tuple[int, str, Any]] = []
    async with client.stream("GET", f"/api/check-lease/{run_id}/events", headers=headers) as sse:
        assert sse.status_code == 200
        assert sse.headers["content-type"].startswith("text/event-stream")
        fields: dict[str, str] = {}
        async for line in sse.aiter_lines():
            if line:
                name, _, value = line.partition(":")
                fields[name] = value.strip()
            elif "event" in fields:
                events.append((int(fields["id"]), fields["event"], json.loads(fields["data"])))
                fields = {}
    return events


class Reader:
    """The request of a stream's reader, for the generator itself: httpx's ASGI transport
    collects a whole response, so a stream that must be read while it is still going is
    driven directly."""

    def __init__(self, gone: bool) -> None:
        self.gone = gone

    async def is_disconnected(self) -> bool:
        return self.gone


def _waiting_run(gate: asyncio.Event) -> Run:
    async def work(run: Run) -> None:
        run.emit("stage", LeaseStageEvent(stage="reading"))
        await gate.wait()
        run.end("done", LeaseDoneEvent(findings=0, language=Language.EN))

    return Runs(leases.failure).start("v1", work)


async def test_a_lease_is_checked_and_its_events_are_kept_numbered() -> None:
    app = _app(Scripted(*ALL_THE_WAY))
    async with _client(app) as client:
        started = await _start(client)
        run_id = started.json()["id"]
        events = await _events(app, client, run_id)
    assert started.status_code == 202
    assert started.headers["location"] == f"/api/check-lease/{run_id}"
    assert started.headers["set-cookie"].startswith(f"{COOKIE}=")
    assert [(n, name) for n, name, _ in events] == [
        *zip(range(1, 8), ["stage"] * 4 + ["finding", "stage", "done"], strict=True)
    ]
    assert events[0][2] == {"stage": "uploaded", "done": None, "total": None}
    assert events[3][2] == {"stage": "checking", "done": 0, "total": 1}
    assert events[4][2]["clause_number"] == "7"
    assert events[4][2]["citations"][0]["label"] == "Stub Act, s. 1"
    assert events[-1][2] == {"findings": 1, "language": "en"}


async def test_what_the_reader_gives_reaches_the_checker() -> None:
    checker = Scripted(*ALL_THE_WAY)
    app = _app(checker)
    async with _client(app) as client:
        await _checked(app, client, jurisdiction="spain", signed_on="2026-03-01")
        await _checked(app, client, SPANISH.encode())  # (the first has ended: another may start)
    (upload, jurisdiction, as_of), (spanish, none, never) = checker.seen
    assert upload.text.startswith("Clause 1.")
    assert (upload.language, upload.synthetic) == (Language.EN, False)
    assert (jurisdiction, as_of) == (Jurisdiction.SPAIN, date(2026, 3, 1))
    assert (spanish.language, none, never) == (Language.ES, None, None)


async def test_only_the_invented_leases_count_as_synthetic() -> None:
    sample = SAMPLES / "fl-lease-01.md"
    assert len(sample_digests()) >= 10  # the ten leases and the scans
    checker = Scripted(*ALL_THE_WAY)
    app = _app(checker)
    async with _client(app) as client:
        await _checked(app, client, sample.read_bytes())
        await _checked(app, client, sample.read_bytes() + b"\nJohn Smith, tenant.")
    (invented, _, _), (changed, _, _) = checker.seen
    assert invented.synthetic  # the stand-in redactor lets it through
    assert not changed.synthetic  # one byte off is a real upload: refused until P2


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        pytest.param(b"\x89PNG\r\n\x1a\n" + bytes(300), 415, "unsupported_type", id="an-image"),
        pytest.param(b"Too short to be a lease.", 422, "unreadable", id="too-little-text"),
        pytest.param(b"%PDF-1.4 truncated", 422, "unreadable", id="a-broken-pdf"),
        pytest.param(b"", 422, "unreadable", id="nothing"),
    ],
)
async def test_what_is_wrong_with_the_file_is_said_with_a_code(
    body: bytes, status: int, code: str
) -> None:
    checker = Scripted(*ALL_THE_WAY)
    async with _client(_app(checker)) as client:
        refused = await _start(client, body)
    assert (refused.status_code, refused.json()["code"]) == (status, code)
    assert refused.headers["content-type"] == "application/problem+json"
    assert checker.seen == []


async def test_the_lease_is_the_body_and_not_a_form() -> None:
    checker = Scripted(*ALL_THE_WAY)
    async with _client(_app(checker)) as client:
        form = await client.post("/api/check-lease", files={"file": ("lease.txt", LEASE.encode())})
    assert (form.status_code, form.json()["code"]) == (415, "unsupported_type")
    assert "not a form" in form.json()["detail"]
    assert checker.seen == []


async def test_a_file_over_the_limit_is_refused_whether_or_not_it_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(leases, "MAX_BYTES", 1000)
    exactly_the_limit = (LEASE * 3).encode()[:1000]
    assert len(exactly_the_limit) == 1000

    async def in_pieces() -> AsyncIterator[bytes]:  # no Content-Length: chunked
        for _ in range(5):
            yield b"x" * 300

    async with _client(_app(Scripted(*ALL_THE_WAY))) as client:
        declared = await _start(client, b"x" * 1001)
        streamed = await client.post("/api/check-lease", content=in_pieces())
        exact = await _start(client, exactly_the_limit)
    assert "content-length" not in streamed.request.headers
    for refused in (declared, streamed):
        assert (refused.status_code, refused.json()["code"]) == (413, "too_large")
    assert exact.status_code == 202  # the limit itself is allowed


async def test_a_lease_with_no_clauses_ends_with_the_checkers_own_message() -> None:
    script = (LeaseStage("redacting"), LeaseCheckError("no_clauses"))
    app = _app(Scripted(*script))
    async with _client(app) as client:
        events = await _checked(app, client)
    assert [name for _, name, _ in events] == ["stage", "stage", "failed"]
    assert events[-1][2] == {"code": "no_clauses", "message": MESSAGES["no_clauses"]}


async def test_an_error_in_the_checker_ends_the_check_and_leaks_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "Clause 7: Jane Doe pays 900 EUR a month"
    app = _app(Scripted(RuntimeError(secret)))
    with caplog.at_level(logging.DEBUG):
        async with _client(app) as client:
            events = await _checked(app, client)
    assert events[-1][1:] == (
        "failed",
        {"code": "internal", "message": "The check failed on our side. Please try again."},
    )
    assert "Jane Doe" not in json.dumps(events) + caplog.text
    assert "RuntimeError" in caplog.text


async def test_a_checker_that_stops_without_an_end_still_ends_the_check() -> None:
    app = _app(Scripted(LeaseStage("redacting")))
    async with _client(app) as client:
        events = await _checked(app, client)
    assert events[-1][1] == "failed"
    assert events[-1][2]["code"] == "internal"


async def test_the_free_tier_is_refused_before_a_byte_of_the_file_is_read() -> None:
    checker = Scripted(*ALL_THE_WAY)
    async with _client(_app(checker, tier=DemoTier.FREE)) as client:
        refused = await _start(client, b"\x89PNG" + bytes(300))  # which would be a 415
    assert (refused.status_code, refused.json()["code"]) == (503, "lease_checks_paused")
    assert "paid models" in refused.json()["detail"]
    assert checker.seen == []


async def test_only_one_check_at_a_time_for_a_visitor() -> None:
    checker = Scripted("wait", LeaseDone(findings=0, language=Language.EN))
    app = _app(checker)
    async with _client(app) as client:
        first = await _start(client)
        second = await _start(client)
        assert (second.status_code, second.json()["code"]) == (503, "busy")
        assert second.headers["retry-after"] == "30"
        checker.gate.set()
        await _events(app, client, first.json()["id"])
        third = await _start(client)  # the first has ended
    assert third.status_code == 202


async def test_closing_the_app_ends_the_checks_still_going() -> None:
    app = _app(Scripted("wait"))
    async with app.router.lifespan_context(app), _client(app) as client:
        run_id = (await _start(client)).json()["id"]
        owner = client.cookies[COOKIE].rsplit(".", 1)[0]
        await asyncio.sleep(0.01)  # the check has begun and is waiting
    run = app.state.runs.get(run_id, owner)
    assert run.ended
    assert run.events[-1].name == "failed"
    assert json.loads(run.events[-1].data.model_dump_json())["code"] == "interrupted"


async def test_lease_checks_are_rationed_by_the_day() -> None:
    checker = Scripted(*ALL_THE_WAY)
    app = _app(checker, questions=10)  # one lease check a day
    async with _client(app) as client:
        await _checked(app, client)
        refused = await _start(client)
    body = refused.json()
    assert (refused.status_code, body["code"]) == (429, "quota_reached")
    assert "lease checks" in body["detail"]
    assert 0 < int(refused.headers["retry-after"]) <= 24 * 3600
    assert len(checker.seen) == 1


async def test_a_visitor_who_has_none_left_is_told_before_the_file_is_read() -> None:
    app = _app(Scripted(*ALL_THE_WAY), questions=10)
    async with _client(app) as client:
        await _checked(app, client)
        refused = await _start(client, b"\x89PNG" + bytes(300))  # which would be a 415
    assert (refused.status_code, refused.json()["code"]) == (429, "quota_reached")


async def test_a_refused_check_costs_nothing() -> None:
    gate_checker = Scripted("wait", LeaseDone(findings=0, language=Language.EN))
    app = _app(gate_checker, questions=20)  # two lease checks a day
    async with _client(app) as client:
        for body in (b"\x89PNG" + bytes(300), b"Too short.", b""):  # the file's faults
            assert (await _start(client, body)).status_code in (415, 422)
        first = await _start(client)  # the first of the two
        assert (await _start(client)).json()["code"] == "busy"  # refused while the first goes on
        gate_checker.gate.set()
        await _events(app, client, first.json()["id"])
        second = await _start(client)  # so the second is still there
        third = await _start(client)
    assert (first.status_code, second.status_code, third.status_code) == (202, 202, 429)


async def test_a_busy_server_is_told_before_the_file_is_read() -> None:
    checker = Scripted("wait", LeaseDone(findings=0, language=Language.EN))
    async with _client(_app(checker)) as client:
        assert (await _start(client)).status_code == 202
        busy = await _start(client, b"\x89PNG" + bytes(300))  # which would be a 415
        checker.gate.set()
    assert (busy.status_code, busy.json()["code"]) == (503, "busy")


async def test_the_default_checker_is_the_stand_in() -> None:
    app = _app()
    async with _client(app) as client:
        events = await _checked(app, client)
    findings = [data for _, name, data in events if name == "finding"]
    assert {f["severity"] for f in findings} == {"conflict", "check", "note", "match"}
    assert events[-1][1:] == ("done", {"findings": 4, "language": "en"})


async def test_the_events_come_as_a_stream_with_ids() -> None:
    app = _app(Scripted(*ALL_THE_WAY))
    async with _client(app) as client:
        run_id = (await _start(client)).json()["id"]
        streamed = await _follow(client, run_id)
        kept = await _events(app, client, run_id)
    assert streamed == kept
    assert [n for n, _, _ in streamed] == list(range(1, 8))
    assert [name for _, name, _ in streamed][-3:] == ["finding", "stage", "done"]


async def test_a_dropped_stream_resumes_after_the_last_event_it_saw() -> None:
    async with _client(_app(Scripted(*ALL_THE_WAY))) as client:
        run_id = (await _start(client)).json()["id"]
        whole = await _follow(client, run_id)
        assert await _follow(client, run_id, last_event_id=5) == whole[5:]
        assert await _follow(client, run_id, last_event_id=len(whole)) == []  # saw it all
        assert await _follow(client, run_id, last_event_id=999) == []  # from the future


async def test_a_check_is_followed_only_by_the_visitor_who_started_it() -> None:
    app = _app(Scripted(*ALL_THE_WAY))
    async with _client(app) as owner, _client(app) as stranger:
        run_id = (await _start(owner)).json()["id"]
        refused = await stranger.get(f"/api/check-lease/{run_id}/events")  # no cookie
        missing = await owner.get("/api/check-lease/unknown/events")
        assert (await _follow(owner, run_id))[-1][1] == "done"
    for response in (refused, missing):  # a check that is not yours does not exist
        assert (response.status_code, response.json()["code"]) == (404, "not_found")


async def test_a_quiet_stream_keeps_itself_alive_and_ends_with_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(leases, "PING_S", 0.02)
    gate = asyncio.Event()
    run = _waiting_run(gate)
    sent: list[ServerSentEvent] = []
    async with asyncio.timeout(5):
        async for item in leases.events(cast(Request, Reader(gone=False)), run, None):
            sent.append(item)
            if item.comment == "ping":
                gate.set()  # the check was waiting; the pings went on meanwhile
    assert [item.event for item in sent if item.comment is None] == ["stage", "done"]
    assert any(item.comment == "ping" for item in sent)


async def test_a_reader_who_has_left_ends_the_stream_and_not_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(leases, "PING_S", 0.02)
    gate = asyncio.Event()
    run = _waiting_run(gate)
    async with asyncio.timeout(5):
        sent = [item async for item in leases.events(cast(Request, Reader(gone=True)), run, None)]
    assert [item.event for item in sent] == ["stage"]
    assert not run.ended  # it goes on, for the reader who comes back
    gate.set()


async def test_a_slow_reader_still_gets_every_event_and_the_last_one_ends_the_stream() -> None:
    run = Run(id="r", owner="v1")
    run.emit("stage", LeaseStageEvent(stage="reading"))
    stream = leases.events(cast(Request, Reader(gone=False)), run, None)
    first = await anext(stream)  # the reader is away from its next read ...
    run.emit("stage", LeaseStageEvent(stage="checking", done=0, total=1))
    run.end("done", LeaseDoneEvent(findings=0, language=Language.EN))  # ... and the check ends
    rest = [item async for item in stream]
    assert [first.id, *(item.id for item in rest)] == ["1", "2", "3"]
    assert [first.event, *(item.event for item in rest)] == ["stage", "stage", "done"]


async def test_a_finished_check_can_be_read_back_by_its_visitor_alone() -> None:
    app = _app(Scripted(*ALL_THE_WAY))
    async with _client(app) as client, _client(app) as stranger:
        run_id = (await _start(client)).json()["id"]
        await _events(app, client, run_id)
        read = await client.get(f"/api/check-lease/{run_id}")
        other = await stranger.get(f"/api/check-lease/{run_id}")
    body = read.json()
    assert (read.status_code, read.headers["cache-control"]) == (200, "no-store")
    assert (body["id"], body["status"], body["language"], body["failure"]) == (
        run_id,
        "done",
        "en",
        None,
    )
    assert [f["clause_number"] for f in body["findings"]] == ["7"]
    assert (other.status_code, other.json()["code"]) == (404, "not_found")


async def test_a_check_that_is_going_shows_the_findings_so_far() -> None:
    checker = Scripted(FINDING, "wait", LeaseDone(findings=1, language=Language.EN))
    app = _app(checker)
    async with _client(app) as client:
        run_id = (await _start(client)).json()["id"]
        await asyncio.sleep(0.01)  # the finding is in, and the check waits
        going = (await client.get(f"/api/check-lease/{run_id}")).json()
        checker.gate.set()
        await _events(app, client, run_id)
        done = (await client.get(f"/api/check-lease/{run_id}")).json()
    assert (going["status"], going["language"], len(going["findings"])) == ("running", None, 1)
    assert (done["status"], done["language"]) == ("done", "en")


async def test_a_check_that_failed_says_why() -> None:
    app = _app(Scripted(LeaseCheckError("jurisdiction_unknown")))
    async with _client(app) as client:
        run_id = (await _start(client)).json()["id"]
        await _events(app, client, run_id)
        body = (await client.get(f"/api/check-lease/{run_id}")).json()
    assert (body["status"], body["findings"], body["language"]) == ("failed", [], None)
    assert body["failure"] == {
        "code": "jurisdiction_unknown",
        "message": MESSAGES["jurisdiction_unknown"],
    }


async def test_the_schema_describes_the_routes_and_the_events_they_carry() -> None:
    async with _client(_app()) as client:
        schema = (await client.get("/api/openapi.json")).json()
    start = schema["paths"]["/api/check-lease"]["post"]
    assert {"application/pdf", "text/plain"} <= set(start["requestBody"]["content"])
    assert {"202", "413", "415", "422", "429", "503"} <= set(start["responses"])
    assert "description" in start["responses"]["422"]
    assert "/api/check-lease/{run_id}/events" in schema["paths"]
    components = schema["components"]["schemas"]
    wanted = {"LeaseStarted", "LeaseStageEvent", "LeaseDoneEvent", "LeaseFailedEvent", "Finding"}
    assert "LeaseResult" in components
    assert wanted <= set(components)
    codes = components["Problem"]["properties"]["code"]["anyOf"][0]["enum"]
    assert {"too_large", "unsupported_type", "unreadable", "busy", "not_found"} <= set(codes)


async def test_a_page_on_another_origin_may_read_the_headers_it_needs() -> None:
    async with _client(_app()) as client:
        response = await client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    exposed = response.headers["access-control-expose-headers"]
    assert "Retry-After" in exposed
    assert "Location" in exposed

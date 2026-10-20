"""One example for every operation of the API, written into the OpenAPI schema by
api/openapi.py: its request (a JSON body, or the text of an uploaded lease), its parameters
and its successful response (JSON, or the event stream as it arrives).

Every example is built from the route's own models, so it validates when this module is
imported and cannot drift from them silently; tests/api/test_openapi_examples.py fails when
an operation has none, when one names an operation that does not exist, or when an
example's model is not the one the schema names. The law in them is real (Fla. Stat.
§ 83.49 as indexed), the leases and people invented.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Final

from pydantic import BaseModel

from plumbline.api import stream
from plumbline.api.chunks import ChunkArticle, PublishedArticle, SourceLink, Span
from plumbline.api.evals import OnlineNight
from plumbline.api.quota import Usage
from plumbline.api.schemas import (
    AskRequest,
    FeedbackRequest,
    Health,
    JobEventView,
    JobView,
    LeaseDoneEvent,
    LeaseResult,
    LeaseStageEvent,
    LeaseStarted,
    UIMessage,
    UIMessagePart,
)
from plumbline.api.search import SearchResult
from plumbline.api.sources import PageBox, QuoteBoxes
from plumbline.api.tier import TierChange, TierState
from plumbline.core.stream import (
    AnswerSummary,
    Stage,
    StatusEvent,
    StreamEvent,
    TextDelta,
    TraceSummary,
)
from plumbline.core.types import (
    AnswerStatus,
    ArticleRef,
    CacheMode,
    Chunk,
    Citation,
    DemoTier,
    Jurisdiction,
    Language,
    ProvisionStatus,
    RetrievalScores,
    Retrieved,
)
from plumbline.leases.schema import Finding, Severity


@dataclass(frozen=True)
class Example:
    summary: str
    request: BaseModel | str | None = None  # a JSON body, or the raw text of an upload
    response: BaseModel | Sequence[BaseModel] | str | None = None  # str: an event stream
    parameters: Mapping[str, object] = field(default_factory=dict)


def sse(event: str | None, data: BaseModel | Mapping[str, Any], event_id: int | None) -> str:
    """One server-sent event, laid out as FastAPI's EventSourceResponse writes it."""
    body = data.model_dump_json() if isinstance(data, BaseModel) else json.dumps(data)
    lines = ([f"event: {event}"] if event else []) + [f"data: {body}"]
    lines += [f"id: {event_id}"] if event_id is not None else []
    return "\n".join(lines) + "\n\n"


NOW: Final = datetime(2026, 10, 20, 14, 5, 12, tzinfo=UTC)
JOB_ID: Final = uuid.UUID("0b6f3c1e-8a52-4d1e-9a51-6f2d7c3b9e10")
LEASE_ID: Final = "HvG-KjlR9wCq2YhNKSgo-w"
QUESTION: Final = "How long does a Florida landlord have to return a security deposit?"
DOCUMENT: Final = "fl-stat-83-2026"
ARTICLE_ID: Final = "fl-stat-83-2026:3b03420f9e67a613"
CHUNK_ID: Final = "fl-stat-83-2026:37656826b4941f09"  # s. 83.49(3), a paragraph of the article
HEADING: Final = "Deposit money or advance rent; duty of landlord and tenant"
REF: Final = ArticleRef(
    jurisdiction=Jurisdiction.FLORIDA, law=DOCUMENT, article="83.49", paragraph="3", edition="2026"
)
QUOTE: Final = (
    "the landlord must return the security deposit, together with interest if otherwise"
    " required, within 15 days after the termination of the rental agreement"
)
PARAGRAPH: Final = (
    "(3) The landlord or the landlord’s agent may disburse advance rents from the deposit"
    " account to the landlord’s benefit when the advance rental period commences and without"
    " notice to the tenant. For all other deposits:\n(a) Upon the vacating of the premises for"
    " termination of the rental agreement, if the landlord does not intend to impose a claim"
    f" on the security deposit, {QUOTE}."
)
CITATION: Final = Citation(
    n=1,
    chunk_id=CHUNK_ID,
    ref=REF,
    label="Fla. Stat. § 83.49(3)",
    quote=QUOTE,
    language=Language.EN,
    verified=True,
    page=1,
)
TRACE: Final = TraceSummary(
    request_id="req_9223edc789df35f3",
    config_name="A2",
    config_hash="5b405538b487",
    route="fast",
    model="gemini-3.5-flash-lite",
    tier=DemoTier.FULL,
    timings_ms={"detect": 0.2, "retrieve": 84.0, "generate": 2140.5, "verify": 1.1},
    input_tokens=4210,
    output_tokens=212,
    cost_usd=0.00179,
)
ANSWER_TEXT: Final = (
    "If the landlord does not intend to claim any of the deposit, they must return it, with"
    " any interest that is due, within 15 days after the rental agreement ends [1]."
)
ASK_EVENTS: Final[list[StreamEvent]] = [
    StatusEvent(stage=Stage.DETECTING),
    StatusEvent(stage=Stage.RETRIEVING),
    StatusEvent(stage=Stage.GENERATING),
    TextDelta(text=ANSWER_TEXT),
    StatusEvent(stage=Stage.VERIFYING),
    CITATION,
    AnswerSummary(
        status=AnswerStatus.ANSWERED, jurisdictions=[Jurisdiction.FLORIDA], confidence=0.92
    ),
    TRACE,
]
ASK_MESSAGE_ID: Final = "msg_9223edc789df35f3"
# What api/stream.py's ui_message_stream writes for ASK_EVENTS, laid out here without an
# event loop; the guard test compares the two.
ASK_STREAM: Final = "".join(
    [
        stream.sse({"type": "start", "messageId": ASK_MESSAGE_ID}),
        stream.sse({"type": "start-step"}),
        *(stream.sse(stream.data_part(e)) for e in ASK_EVENTS[:3]),
        stream.sse({"type": "text-start", "id": stream.TEXT_ID}),
        stream.sse({"type": "text-delta", "id": stream.TEXT_ID, "delta": ANSWER_TEXT}),
        *(stream.sse(stream.data_part(e)) for e in ASK_EVENTS[4:]),
        stream.sse({"type": "text-end", "id": stream.TEXT_ID}),
        stream.sse({"type": "finish-step"}),
        stream.sse({"type": "finish", "finishReason": "stop"}),
        stream.sse("[DONE]"),
    ]
)

JOB: Final = JobView(
    id=JOB_ID,
    kind="ingest",
    source_id=DOCUMENT,
    content_hash="9f2c4e7d1a0b",
    status="succeeded",
    attempts=1,
    worker="mx1-1",
    error=None,
    result={"chunks": 299, "articles": 43},
    created_at=NOW,
    started_at=NOW,
    finished_at=NOW,
)
JOB_EVENTS: Final = [
    JobEventView(id=1, job_id=JOB_ID, kind="started", message="", data={}, created_at=NOW),
    JobEventView(
        id=2,
        job_id=JOB_ID,
        kind="progress",
        message="embedded",
        data={"done": 299, "total": 299},
        created_at=NOW,
    ),
    JobEventView(
        id=3, job_id=JOB_ID, kind="succeeded", message="", data={"chunks": 299}, created_at=NOW
    ),
]

FINDING: Final = Finding(
    n=1,
    clause_number="4",
    clause_text=(
        "The Landlord will return the security deposit within 45 days after the Tenant moves out."
    ),
    clause_language=Language.EN,
    severity=Severity.CONFLICT,
    title="The deposit comes back later than the law allows",
    why=(
        "The clause gives the landlord 45 days to return the deposit. Florida law requires"
        " its return within 15 days after the rental agreement ends when the landlord makes"
        " no claim on it, and the statute prevails over the lease."
    ),
    citations=[CITATION],
    confidence=0.9,
)
LEASE_TEXT: Final = (
    "Residential Lease (an invented example)\n\nClause 1. Premises\nThe Landlord leases to the"
    " Tenant Apartment 3C, Miami, Florida.\n\nClause 4. Security deposit\nThe Landlord will"
    " return the security deposit within 45 days after the Tenant moves out.\n"
)
LEASE_STREAM: Final = "".join(
    [
        sse("stage", LeaseStageEvent(stage="uploaded"), 1),
        sse("stage", LeaseStageEvent(stage="redacting"), 2),
        sse("stage", LeaseStageEvent(stage="reading"), 3),
        sse("stage", LeaseStageEvent(stage="checking", done=0, total=2), 4),
        sse("finding", FINDING, 5),
        sse("stage", LeaseStageEvent(stage="checking", done=2, total=2), 6),
        sse("done", LeaseDoneEvent(findings=1, language=Language.EN), 7),
    ]
)

ARTICLE_TEXT: Final = "(1) Whenever money is deposited or advanced by a tenant …\n" + PARAGRAPH
HIT: Final = Retrieved(
    chunk=Chunk(
        id=CHUNK_ID,
        document_id=DOCUMENT,
        parent_id=ARTICLE_ID,
        jurisdiction=Jurisdiction.FLORIDA,
        law=DOCUMENT,
        language=Language.EN,
        edition="2026",
        article="83.49",
        path=["Part II", "83.49", "3"],
        label="Fla. Stat. § 83.49(3)",
        heading=HEADING,
        text=PARAGRAPH,
        text_for_search=f"[Florida | Fla. Stat. ch. 83 | s. 83.49 | {HEADING}]\n{PARAGRAPH}",
        context_header=f"[Florida | Fla. Stat. ch. 83 | s. 83.49 | {HEADING}]",
        page=1,
    ),
    rank=1,
    score=0.0323,
    scores=RetrievalScores(dense=0.71, bm25=14.2, rrf=0.0323, dense_rank=1, bm25_rank=2),
)
EXAMPLES: Final[dict[str, Example]] = {
    "GET /api/health": Example(
        "The server is up",
        response=Health(version="0.9.0", tier=DemoTier.FULL, cache_mode=CacheMode.REPLAY),
    ),
    "POST /api/ask": Example(
        "A question about Florida, answered with one verified citation",
        request=AskRequest(
            id="chat_4f1d",
            messages=[
                UIMessage(id="m1", role="user", parts=[UIMessagePart(type="text", text=QUESTION)])
            ],
            jurisdictions=[Jurisdiction.FLORIDA],
        ),
        response=ASK_STREAM,
    ),
    "POST /api/feedback": Example(
        "A reader found the answer helpful",
        request=FeedbackRequest(request_id=TRACE.request_id, helpful=True),
    ),
    "GET /api/usage": Example(
        "Four of today's thirty questions used",
        response=Usage(used=4, limit=30, resets_at=datetime(2026, 10, 21, tzinfo=UTC)),
    ),
    "GET /api/evals/online": Example(
        "Two nights of judged production answers, newest first",
        response=[
            OnlineNight(
                day=date(2026, 10, 24),
                config_name="A2-claude",
                answered=212,
                sampled=21,
                judged=20,
                faithful=19,
                faithfulness=0.95,
                interval_95=(0.7639, 0.9911),
            ),
            OnlineNight(
                day=date(2026, 10, 23),
                config_name="A2-claude",
                answered=96,
                sampled=10,
                judged=10,
                faithful=9,
                faithfulness=0.9,
                interval_95=(0.5958, 0.9821),
            ),
        ],
    ),
    "GET /api/admin/jobs": Example(
        "The latest ingestion job", response=[JOB], parameters={"status": "succeeded", "limit": 20}
    ),
    "GET /api/admin/jobs/{job_id}": Example(
        "A job that indexed Florida's chapter 83", response=JOB, parameters={"job_id": str(JOB_ID)}
    ),
    "GET /api/admin/jobs/{job_id}/events": Example(
        "A job's events, from the start to its end",
        response="".join(sse(e.kind, e, e.id) for e in JOB_EVENTS),
        parameters={"job_id": str(JOB_ID), "last-event-id": 0},
    ),
    "GET /api/settings/tier": Example(
        "The full demo: every route on",
        response=TierState(tier=DemoTier.FULL, updated_at=None),
    ),
    "PUT /api/admin/settings/tier": Example(
        "The kill switch: stored answers only",
        request=TierChange(tier=DemoTier.STATIC),
        response=TierState(tier=DemoTier.STATIC, updated_at=NOW),
    ),
    "GET /api/sources/{source_id}/pages/{n}.png": Example(
        "A page of a source, as an image",
        parameters={"source_id": "fl-stat-83-2026", "n": 1, "scale": 2},
    ),
    "GET /api/sources/{source_id}/pages/{n}/boxes": Example(
        "Where a quote is on its page",
        response=QuoteBoxes(
            source_id=DOCUMENT,
            page=1,
            available=True,
            found=True,
            boxes=[PageBox(x0=0.12, y0=0.41, x1=0.88, y1=0.47)],
        ),
        parameters={"source_id": DOCUMENT, "n": 1, "quote": QUOTE},
    ),
    "GET /api/search": Example(
        "What retrieval finds for a question, with every score",
        response=SearchResult(
            query=QUESTION,
            config="A2",
            config_hash="5b405538b487",
            k=1,
            jurisdictions=[Jurisdiction.FLORIDA],
            as_of=date(2026, 10, 20),
            candidates=20,
            timings_ms={"search": 84.0},
            hits=[HIT],
        ),
        parameters={
            "q": QUESTION,
            "k": 1,
            "jurisdictions": ["florida"],
            "as_of": "2026-10-20",
            "config": "A2",
        },
    ),
    "GET /api/chunks/{chunk_id}": Example(
        "The article a citation quotes, with the quote's span",
        response=ChunkArticle(
            chunk_id=CHUNK_ID,
            article=PublishedArticle(
                ref=REF.model_copy(update={"paragraph": None}),
                label="Fla. Stat. § 83.49",
                heading=HEADING,
                text=ARTICLE_TEXT,
                language=Language.EN,
                page=1,
                status=ProvisionStatus.IN_FORCE,
                validity_note=None,
                effective_from=None,
                effective_to=None,
            ),
            span=Span(start=ARTICLE_TEXT.index(QUOTE), end=ARTICLE_TEXT.index(QUOTE) + len(QUOTE)),
            source=SourceLink(
                id=DOCUMENT,
                title="Florida Statutes 2026, chapter 83 (Landlord and Tenant), part II",
                url="https://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute"
                "&URL=0000-0099/0083/0083.html&StatuteYear=2026",
            ),
            restricted=False,
        ),
        parameters={"chunk_id": CHUNK_ID, "quote": QUOTE},
    ),
    "POST /api/check-lease": Example(
        "A short invented Florida lease, sent as text",
        request=LEASE_TEXT,
        response=LeaseStarted(id=LEASE_ID),
        parameters={"jurisdiction": "florida", "signed_on": "2026-08-15"},
    ),
    "GET /api/check-lease/{run_id}/events": Example(
        "A check from the upload to its one finding",
        response=LEASE_STREAM,
        parameters={"run_id": LEASE_ID, "last-event-id": 0},
    ),
    "GET /api/check-lease/{run_id}": Example(
        "A finished check",
        response=LeaseResult(
            id=LEASE_ID, status="done", language=Language.EN, findings=[FINDING], failure=None
        ),
        parameters={"run_id": LEASE_ID},
    ),
}


def dump(value: BaseModel | Sequence[BaseModel] | str) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, str):
        return value
    return [item.model_dump(mode="json") for item in value]


def add_examples(schema: dict[str, Any]) -> None:
    """Write EXAMPLES into the schema: a request body's and the first successful response's
    content (each of their media types), and a parameter's `example`."""
    for path, operations in schema.get("paths", {}).items():
        for method, operation in operations.items():
            example = EXAMPLES.get(f"{method.upper()} {path}")
            if example is None:
                continue  # the guard test names it
            if example.request is not None:
                content = operation.get("requestBody", {}).get("content", {})
                media = (
                    "application/json" if isinstance(example.request, BaseModel) else "text/plain"
                )
                if media in content:
                    content[media]["examples"] = {
                        "example": {"summary": example.summary, "value": dump(example.request)}
                    }
            success = sorted(code for code in operation.get("responses", {}) if code[0] == "2")
            if example.response is not None and success:
                for media in operation["responses"][success[0]].get("content", {}).values():
                    media["examples"] = {
                        "example": {"summary": example.summary, "value": dump(example.response)}
                    }
            for parameter in operation.get("parameters", []):
                if parameter["name"] in example.parameters:
                    parameter["example"] = example.parameters[parameter["name"]]

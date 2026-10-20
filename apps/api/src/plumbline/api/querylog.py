"""One row per question in the queries table (Lane D): what was asked, what came back,
what it cost and how long it took, for the nightly online evaluation and the cost model.

/api/ask records it from the events it forwards, so pipelines stay free of storage. The
row is written when the stream ends, however it ends: answered, failed, or abandoned by a
browser that went away. Writing it never disturbs the answer: if the database cannot take
it, the failure is logged and the reader still gets the stream.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import anyio
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.core.stream import (
    AnswerSummary,
    Question,
    StreamError,
    StreamEvent,
    TextDelta,
    TraceSummary,
)
from plumbline.core.types import Citation
from plumbline.db.models import PUBLIC_TENANT, QueryRow
from plumbline.db.session import tenant_session

log = logging.getLogger(__name__)


async def recorded(
    events: AsyncIterator[StreamEvent],
    question: Question,
    sessions: async_sessionmaker[AsyncSession],
) -> AsyncIterator[StreamEvent]:
    """The pipeline's events, unchanged, with the question's row written at the end."""
    started = time.perf_counter()
    text: list[str] = []
    citations: list[Citation] = []
    summary: AnswerSummary | None = None
    trace: TraceSummary | None = None
    error: str | None = None
    try:
        async for event in events:
            if isinstance(event, TextDelta):
                text.append(event.text)
            elif isinstance(event, Citation):
                citations.append(event)
            elif isinstance(event, AnswerSummary):
                summary = event
            elif isinstance(event, TraceSummary):
                trace = event
            elif isinstance(event, StreamError):
                error = event.message
            yield event
    except Exception as exc:
        error = f"{type(exc).__name__} in the pipeline"  # the message may hold internals
        raise
    finally:
        answer = None
        if summary is not None:
            answer = {
                "text": "".join(text),
                "citations": [c.model_dump(mode="json") for c in citations],
                "summary": summary.model_dump(mode="json"),
            }
        row = _row(question, summary, trace, answer, error, time.perf_counter() - started)
        # Shielded: a browser that leaves cancels the stream, not the row about it.
        with anyio.CancelScope(shield=True):
            await _write(sessions, row)


def _row(
    question: Question,
    summary: AnswerSummary | None,
    trace: TraceSummary | None,
    answer: dict[str, Any] | None,
    error: str | None,
    seconds: float,
) -> QueryRow:
    return QueryRow(
        tenant_id=PUBLIC_TENANT,  # anonymous readers, until visitors have their own (D7)
        request_id=question.request_id,
        question=question.text,
        as_of=question.as_of,
        jurisdictions=[j.value for j in question.jurisdictions],
        tier=question.tier.value,
        status=summary.status.value if summary else None,
        route=trace.route if trace else None,
        model=trace.model if trace else None,
        config_name=trace.config_name if trace else None,
        config_hash=trace.config_hash if trace else None,
        latency_ms=round(seconds * 1000, 1),
        input_tokens=trace.input_tokens if trace else 0,
        output_tokens=trace.output_tokens if trace else 0,
        cost_usd=trace.cost_usd if trace else 0.0,
        cached=trace.cached if trace else False,
        trace_url=trace.trace_url if trace else None,
        error=error,
        answer=answer,
        trace=trace.model_dump(mode="json") if trace else None,
    )


async def _write(sessions: async_sessionmaker[AsyncSession], row: QueryRow) -> None:
    try:
        async with tenant_session(sessions, PUBLIC_TENANT) as session:
            session.add(row)
    except (SQLAlchemyError, OSError) as exc:
        log.warning("the row for %s was not recorded: %s", row.request_id, exc)

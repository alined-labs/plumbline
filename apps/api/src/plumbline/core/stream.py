"""The answer stream: the events an answer pipeline yields, and the data parts the API sends
to the browser over the AI SDK's UI message stream. Frozen: a change needs a brain block.

A pipeline yields, in order: StatusEvent (any number), TextDelta (the answer as it is
written), Citation (one per verified or rejected [n] marker), one AnswerSummary and one
TraceSummary; a StreamError ends the stream early. The API maps them one to one:

    TextDelta     -> text-start, text-delta, text-end
    StatusEvent   -> data-status, transient (shown while waiting, never stored)
    Citation      -> data-citation, id "citation-<n>"
    AnswerSummary -> data-answer, id "answer"
    TraceSummary  -> data-trace, id "trace"
    StreamError   -> error

The browser types these payloads from the OpenAPI components, so a field added here
reaches the front end through `make openapi`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from enum import StrEnum
from typing import Annotated, Final, Protocol

from pydantic import Field, StringConstraints

from plumbline.core.types import AnswerStatus, Citation, DemoTier, Frozen, Jurisdiction

DISCLAIMER: Final = (
    "Legal information, not legal advice. No lawyer has reviewed Plumbline's answers: "
    "read the cited article, and consult a qualified professional before acting."
)
MAX_QUESTION_CHARS: Final = 2000


class Stage(StrEnum):
    DETECTING = "detecting"  # which jurisdictions the question is about
    RETRIEVING = "retrieving"
    RERANKING = "reranking"
    GENERATING = "generating"
    VERIFYING = "verifying"


class Question(Frozen):
    """One question as the API hands it to a pipeline."""

    text: Annotated[
        str, StringConstraints(min_length=1, max_length=MAX_QUESTION_CHARS, strip_whitespace=True)
    ]
    as_of: date | None = None  # answer for the law in force on this date; None: today
    jurisdictions: list[Jurisdiction] = Field(default_factory=list)  # empty: detect
    request_id: Annotated[str, StringConstraints(min_length=1)]
    tier: DemoTier = DemoTier.FULL


class StatusEvent(Frozen):
    stage: Stage
    detail: str | None = None


class TextDelta(Frozen):
    text: str


class AnswerSummary(Frozen):
    """What the answer is, once it is complete."""

    status: AnswerStatus
    jurisdictions: list[Jurisdiction] = Field(default_factory=list)
    as_of: date | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    abstain_reason: str | None = None
    invalid_citations: int = Field(default=0, ge=0)
    disclaimer: str = DISCLAIMER


class TraceSummary(Frozen):
    """What the answer cost and where it came from (the model-and-tier badge)."""

    request_id: str
    config_name: str
    config_hash: str
    route: str
    model: str
    tier: DemoTier
    timings_ms: dict[str, float] = Field(default_factory=dict)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0)
    cached: bool = False
    trace_url: str | None = None


class StreamError(Frozen):
    message: str
    retryable: bool = False


StreamEvent = StatusEvent | TextDelta | Citation | AnswerSummary | TraceSummary | StreamError

# The data-part name each payload travels under ("data-<name>").
DATA_PARTS: Final[dict[type[Frozen], str]] = {
    StatusEvent: "status",
    Citation: "citation",
    AnswerSummary: "answer",
    TraceSummary: "trace",
}


class AnswerPipeline(Protocol):
    """Anything that answers a question as a stream of events."""

    def stream(self, question: Question) -> AsyncIterator[StreamEvent]: ...

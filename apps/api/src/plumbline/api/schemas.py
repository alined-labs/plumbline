"""Request and response bodies of the HTTP API (Lane D). The browser's types are generated
from the OpenAPI schema these produce (`make openapi`)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from plumbline.core.stream import MAX_QUESTION_CHARS
from plumbline.core.types import CacheMode, DemoTier, Jurisdiction


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    tier: DemoTier
    cache_mode: CacheMode


class UIMessagePart(BaseModel):
    """A part of a chat message as the AI SDK sends it; only text parts are read."""

    model_config = ConfigDict(extra="allow")

    type: str
    text: str | None = None


class UIMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    role: Literal["system", "user", "assistant"]
    parts: list[UIMessagePart] = Field(default_factory=list)


class AskRequest(BaseModel):
    """The body `useChat` posts: the chat so far, plus Plumbline's own controls. Each
    question is answered on its own; earlier turns are not used yet."""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None  # the chat id
    messages: list[UIMessage] = Field(min_length=1)
    as_of: date | None = None
    jurisdictions: list[Jurisdiction] = Field(default_factory=list)

    def question_text(self) -> str:
        """The text of the latest user message, or an empty string when there is none."""
        for message in reversed(self.messages):
            if message.role == "user":
                text = "".join(p.text or "" for p in message.parts if p.type == "text")
                return text.strip()[: MAX_QUESTION_CHARS + 1]
        return ""


JobStatus = Literal["queued", "running", "succeeded", "failed"]
JobEventKind = Literal["queued", "requeued", "started", "progress", "succeeded", "failed"]


class JobView(BaseModel):
    """An ingestion job as the admin routes show it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    source_id: str
    content_hash: str
    status: JobStatus
    attempts: int
    worker: str | None
    error: str | None
    result: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobEventView(BaseModel):
    """One step of a job: the data of each event on its stream."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: uuid.UUID
    kind: JobEventKind
    message: str
    data: dict[str, Any]
    created_at: datetime


FeedbackReason = Literal[
    "wrong_citation", "missed_statute", "outdated_law", "hard_to_follow", "something_else"
]


class FeedbackRequest(BaseModel):
    """A reader's verdict on one answer. The note is free text and may hold personal data:
    it is stored, never sent to a model, and never logged."""

    model_config = ConfigDict(extra="forbid")

    request_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    helpful: bool
    reasons: list[FeedbackReason] = Field(default_factory=list, max_length=5)
    note: Annotated[str, StringConstraints(max_length=1000)] | None = None

    @field_validator("reasons")
    @classmethod
    def _no_repeats(cls, reasons: list[FeedbackReason]) -> list[FeedbackReason]:
        if len(set(reasons)) != len(reasons):
            raise ValueError("a reason appears twice")
        return reasons

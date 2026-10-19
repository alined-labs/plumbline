"""Request and response bodies of the HTTP API (Lane D). The browser's types are generated
from the OpenAPI schema these produce (`make openapi`)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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

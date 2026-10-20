"""Encode a pipeline's events as the AI SDK UI message stream (server-sent events).

Each part is one `data: <json>` line and a blank line; the stream ends with
`data: [DONE]`. The response carries `x-vercel-ai-ui-message-stream: v1`, which tells
`useChat` which protocol it is reading. Plumbline's own payloads travel as data parts
(see plumbline.core.stream for the mapping).
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Final

from plumbline.core.stream import DATA_PARTS, StatusEvent, StreamError, StreamEvent, TextDelta
from plumbline.core.types import Citation, Frozen

log = logging.getLogger(__name__)

HEADERS: Final = {
    "x-vercel-ai-ui-message-stream": "v1",
    "cache-control": "no-cache, no-transform",
    "x-accel-buffering": "no",
}
TEXT_ID: Final = "answer-text"


def sse(part: dict[str, Any] | str) -> str:
    data = part if isinstance(part, str) else json.dumps(part, ensure_ascii=False)
    return f"data: {data}\n\n"


def data_part(event: Frozen) -> dict[str, Any]:
    """A data part: status parts are transient; the others carry an id, so a later part
    with the same id replaces the earlier one in the browser."""
    name = DATA_PARTS[type(event)]
    part: dict[str, Any] = {"type": f"data-{name}", "data": event.model_dump(mode="json")}
    if isinstance(event, StatusEvent):
        part["transient"] = True
    elif isinstance(event, Citation):
        part["id"] = f"citation-{event.n}"
    else:
        part["id"] = name
    return part


async def ui_message_stream(
    events: AsyncIterator[StreamEvent], *, message_id: str
) -> AsyncIterator[str]:
    """The whole response body, part by part. A pipeline exception becomes an error part,
    so the browser always sees a well-formed, finished stream. The events are closed once
    read, even after a StreamError cuts them short, so whatever wraps the pipeline (the
    query log) finishes its work."""
    yield sse({"type": "start", "messageId": message_id})
    yield sse({"type": "start-step"})
    text_open = False
    failed = False
    try:
        async for event in events:
            if isinstance(event, TextDelta):
                if not text_open:
                    yield sse({"type": "text-start", "id": TEXT_ID})
                    text_open = True
                yield sse({"type": "text-delta", "id": TEXT_ID, "delta": event.text})
            elif isinstance(event, StreamError):
                yield sse({"type": "error", "errorText": event.message})
                failed = True
                break
            else:
                yield sse(data_part(event))
    except Exception:
        log.exception("answer pipeline failed (message %s)", message_id)
        yield sse({"type": "error", "errorText": "Something went wrong while answering."})
        failed = True
    finally:
        close = getattr(events, "aclose", None)  # an async generator stopped early
        if close is not None:
            await close()
    if text_open:
        yield sse({"type": "text-end", "id": TEXT_ID})
    yield sse({"type": "finish-step"})
    yield sse({"type": "finish", "finishReason": "error" if failed else "stop"})
    yield sse("[DONE]")

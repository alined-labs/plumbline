"""HTTP routes (Lane D). Everything is under /api so one origin can serve the static front
end and the API behind the tunnel."""

from __future__ import annotations

import secrets
from importlib.metadata import version

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from plumbline.api.schemas import AskRequest, Health
from plumbline.api.stream import HEADERS, ui_message_stream
from plumbline.api.tier import tier_store
from plumbline.core.stream import AnswerPipeline, Question
from plumbline.settings import Settings

router = APIRouter(prefix="/api")


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


@router.get("/health", tags=["ops"])
async def health(request: Request) -> Health:
    settings = _settings(request)
    tier = await tier_store(request).current()
    return Health(version=version("plumbline"), tier=tier, cache_mode=settings.cache_mode)


@router.post(
    "/ask",
    tags=["answers"],
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "The answer as an AI SDK UI message stream (server-sent events).",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
async def ask(body: AskRequest, request: Request) -> StreamingResponse:
    request_id = f"req_{secrets.token_hex(8)}"
    try:
        question = Question(
            text=body.question_text(),
            as_of=body.as_of,
            jurisdictions=body.jurisdictions,
            request_id=request_id,
            tier=await tier_store(request).current(),
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="The question is empty or too long.") from exc
    pipeline: AnswerPipeline = request.app.state.pipeline
    stream = ui_message_stream(pipeline.stream(question), message_id=f"msg_{request_id[4:]}")
    return StreamingResponse(stream, media_type="text/event-stream", headers=HEADERS)

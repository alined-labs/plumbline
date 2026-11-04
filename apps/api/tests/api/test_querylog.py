"""One queries row per question, written when the stream ends, however it ends."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.api import answering
from plumbline.api.app import create_app
from plumbline.core.stream import AnswerPipeline, Question, StreamError, StreamEvent, TextDelta
from plumbline.core.types import CacheMode
from plumbline.db import make_engine, make_sessionmaker
from plumbline.db.models import PUBLIC_TENANT, QueryRow
from plumbline.db.session import tenant_session
from plumbline.generation.pipeline import UNREADABLE
from plumbline.security.killswitch import PIPELINE_ERROR, failing
from plumbline.settings import Settings

pytestmark = pytest.mark.anyio
Sessions = async_sessionmaker[AsyncSession]


class Failing:
    """Starts an answer, then breaks."""

    def __init__(self, how: str) -> None:
        self.how = how

    async def stream(self, question: Question) -> AsyncIterator[StreamEvent]:
        yield TextDelta(text="Under Article 9")
        if self.how == "error":
            yield StreamError(message="The generator is unavailable.", retryable=True)
        else:
            raise RuntimeError("secret internals")


@pytest.fixture
async def sessions(database_url: str) -> AsyncIterator[Sessions]:
    engine = make_engine(database_url)
    yield make_sessionmaker(engine)
    await engine.dispose()


async def _ask(sessions: Sessions, pipeline: AnswerPipeline | None = None) -> str:
    settings = Settings(_env_file=None, cache_mode=CacheMode.REPLAY, stub_delay_ms=0)
    app = create_app(settings, pipeline=pipeline, sessions=sessions)
    transport = httpx.ASGITransport(app=app)
    question = f"How long is a lease in Spain? {uuid.uuid4().hex}"
    body = {
        "messages": [{"id": "m1", "role": "user", "parts": [{"type": "text", "text": question}]}]
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/ask", json=body)
    assert response.status_code == 200
    assert response.text.rstrip().endswith("data: [DONE]")
    return question


async def _row(sessions: Sessions, question: str) -> QueryRow:
    async with tenant_session(sessions, PUBLIC_TENANT) as session:
        return (await session.scalars(select(QueryRow).where(QueryRow.question == question))).one()


@pytest.mark.db
async def test_an_answered_question_is_one_row(sessions: Sessions) -> None:
    row = await _row(sessions, await _ask(sessions))
    assert (row.status, row.route, row.tier, row.error) == ("answered", "stub", "full", None)
    assert row.request_id.startswith("req_")
    assert row.latency_ms is not None
    answer: dict[str, Any] = row.answer or {}
    assert answer["text"]
    assert answer["citations"]
    assert row.trace is not None
    assert row.trace["request_id"] == row.request_id


@pytest.mark.db
@pytest.mark.parametrize(
    ("how", "error"),
    [("error", "The generator is unavailable."), ("raise", "RuntimeError in the pipeline")],
)
async def test_a_failed_answer_is_recorded_with_its_error(
    sessions: Sessions, how: str, error: str
) -> None:
    row = await _row(sessions, await _ask(sessions, Failing(how)))
    assert (row.status, row.error, row.answer) == (None, error, None)
    assert "secret" not in (row.error or "")


async def test_the_answer_streams_even_when_the_row_cannot_be_written() -> None:
    engine = make_engine("postgresql+psycopg://plumbline:plumbline@127.0.0.1:1/none")
    await _ask(make_sessionmaker(engine))
    await engine.dispose()


def test_only_an_escaped_exception_reads_as_a_refusing_provider() -> None:
    # The kill switch (security/killswitch.py, #218) goes static after a run of answers whose
    # recorded error ends with PIPELINE_ERROR: an exception that escaped the pipeline, such as
    # a provider refusing a spent key. The API's own refusals record their sentence instead,
    # and must never read that way, or reaching our own cap would look like a dead provider.
    assert "RuntimeError in the pipeline".endswith(PIPELINE_ERROR)
    for own in (answering.SPENT, answering.PAUSED, answering.TOO_MUCH_LAW, UNREADABLE):
        assert not own.rstrip(".").endswith(PIPELINE_ERROR.strip())
    assert not failing([answering.SPENT] * 3)
    assert failing(["APIStatusError in the pipeline"] * 3)

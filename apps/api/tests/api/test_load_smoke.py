"""A small load smoke test: many questions at once through the whole app (quota, query log,
stream encoder) on the stub pipeline. Every stream must finish, whole and well formed."""

from __future__ import annotations

import json
import statistics
import time

import anyio
import httpx
import pytest

from plumbline.api.app import create_app
from plumbline.api.quota import MemoryCounter
from plumbline.core.types import CacheMode
from plumbline.db import make_engine, make_sessionmaker
from plumbline.settings import Settings

pytestmark = pytest.mark.anyio
QUESTIONS = 60
PARTS = ("start", "text-start", "text-end", "data-answer", "data-trace", "finish")


async def test_sixty_questions_at_once_all_finish_whole() -> None:
    settings = Settings(
        _env_file=None, cache_mode=CacheMode.REPLAY, stub_delay_ms=1, daily_questions_per_ip=10_000
    )
    no_database = make_sessionmaker(
        make_engine("postgresql+psycopg://plumbline:plumbline@127.0.0.1:1/none")
    )
    app = create_app(settings, sessions=no_database, counter=MemoryCounter())
    seconds: list[float] = []
    bodies: list[str] = []

    async def ask(client: httpx.AsyncClient, n: int) -> None:
        body = {
            "messages": [
                {
                    "id": f"m{n}",
                    "role": "user",
                    "parts": [{"type": "text", "text": f"Question {n}?"}],
                }
            ]
        }
        started = time.perf_counter()
        response = await client.post("/api/ask", json=body)
        seconds.append(time.perf_counter() - started)
        assert response.status_code == 200
        bodies.append(response.text)

    transport = httpx.ASGITransport(app=app)
    # The task group closes first, once every question is answered, then the client.
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        anyio.create_task_group() as group,
    ):
        for n in range(QUESTIONS):
            group.start_soon(ask, client, n)
    assert len(bodies) == QUESTIONS
    for body in bodies:
        lines = [line[6:] for line in body.splitlines() if line.startswith("data: ")]
        assert lines[-1] == "[DONE]"
        kinds = {json.loads(line)["type"] for line in lines[:-1]}
        assert set(PARTS) <= kinds, body[:200]
    message_ids = {json.loads(b.splitlines()[0][6:])["messageId"] for b in bodies}
    assert len(message_ids) == QUESTIONS  # no two answers share a request
    p95 = statistics.quantiles(seconds, n=20)[-1]
    assert p95 < 10, f"p95 {p95:.2f} s"

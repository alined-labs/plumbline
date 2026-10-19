"""The /api/ask stream against the AI SDK UI message stream protocol."""

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi.testclient import TestClient

from plumbline.api.app import create_app
from plumbline.core.stream import Question, StatusEvent, StreamEvent
from plumbline.settings import Settings


def body(text: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": "chat-1",
        "trigger": "submit-message",
        "messages": [{"id": "m1", "role": "user", "parts": [{"type": "text", "text": text}]}],
        **extra,
    }


def parts(client: TestClient, payload: dict[str, Any]) -> tuple[list[Any], dict[str, str]]:
    with client.stream("POST", "/api/ask", json=payload) as response:
        assert response.status_code == 200
        lines = [line for line in response.iter_lines() if line]
        headers = dict(response.headers)
    assert all(line.startswith("data: ") for line in lines)
    raw = [line.removeprefix("data: ") for line in lines]
    assert raw[-1] == "[DONE]"
    return [json.loads(r) for r in raw[:-1]], headers


def test_the_stream_follows_the_protocol(client: TestClient) -> None:
    events, headers = parts(client, body("Can my landlord keep my deposit?", as_of="2026-01-15"))
    assert headers["x-vercel-ai-ui-message-stream"] == "v1"
    assert headers["content-type"].startswith("text/event-stream")
    types = [e["type"] for e in events]
    assert types[:2] == ["start", "start-step"]
    assert types[-2:] == ["finish-step", "finish"]
    assert types.index("text-start") < types.index("text-delta") < types.index("text-end")
    status = [e for e in events if e["type"] == "data-status"]
    assert status
    assert all(e["transient"] for e in status)
    citation = next(e for e in events if e["type"] == "data-citation")
    assert citation["id"] == "citation-1"
    assert citation["data"]["verified"] is True
    answer = next(e for e in events if e["type"] == "data-answer")
    assert answer["data"]["status"] == "answered"
    assert answer["data"]["as_of"] == "2026-01-15"
    trace = next(e for e in events if e["type"] == "data-trace")
    assert trace["data"]["tier"] == "full"
    text = "".join(e["delta"] for e in events if e["type"] == "text-delta")
    assert "stub answer" in text


def test_abstained_answers_carry_no_citation(client: TestClient) -> None:
    events, _ = parts(client, body("abstain on this one"))
    assert not [e for e in events if e["type"] == "data-citation"]
    answer = next(e for e in events if e["type"] == "data-answer")
    assert answer["data"]["status"] == "abstained"


def test_empty_and_overlong_questions_are_refused(client: TestClient) -> None:
    assert client.post("/api/ask", json=body("   ")).status_code == 422
    assert client.post("/api/ask", json=body("x" * 2001)).status_code == 422
    assert client.post("/api/ask", json={"messages": []}).status_code == 422


class FailingPipeline:
    async def stream(self, question: Question) -> AsyncIterator[StreamEvent]:
        yield StatusEvent(stage="retrieving")  # type: ignore[arg-type]
        raise RuntimeError("index unavailable")


def test_a_failing_pipeline_still_ends_the_stream(settings: Settings) -> None:
    with TestClient(create_app(settings, pipeline=FailingPipeline())) as client:
        events, _ = parts(client, body("anything"))
    types = [e["type"] for e in events]
    assert "error" in types
    assert types[-2:] == ["finish-step", "finish"]
    assert "index unavailable" not in json.dumps(events)

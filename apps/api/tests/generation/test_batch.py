"""Gemini's Batch API through the cache, against a fake job API: only the misses are sent,
each answer is recorded under the key a plain call uses, at half the price."""

import asyncio
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

import pytest
from google.genai import types as genai_types
from pydantic import BaseModel

from plumbline.cache import CacheMiss, ResponseCache
from plumbline.core.types import CacheMode
from plumbline.generation.batch import BatchIncomplete, GeminiBatch, openapi_schema
from plumbline.generation.llm import STRONG_MODEL, GeminiClient, LLMRequest, Message, price_for
from plumbline.generation.llm import Usage as LLMUsage
from plumbline.generation.schema import portable_schema

State = genai_types.JobState


def request(text: str) -> LLMRequest:
    return LLMRequest(
        model=STRONG_MODEL, messages=[Message(role="user", content=text)], thinking="low"
    )


def answer(text: str, index: int) -> genai_types.InlinedResponse:
    return genai_types.InlinedResponse(
        metadata={"index": str(index)},
        response=genai_types.GenerateContentResponse(
            candidates=[
                genai_types.Candidate(
                    content=genai_types.Content(role="model", parts=[genai_types.Part(text=text)]),
                    finish_reason=genai_types.FinishReason.STOP,
                )
            ],
            usage_metadata=genai_types.GenerateContentResponseUsageMetadata(
                prompt_token_count=1000, candidates_token_count=100, thoughts_token_count=50
            ),
        ),
    )


@dataclass
class Batches:
    """The SDK's client.batches: a job that is pending once, then done."""

    fail: set[int] = field(default_factory=set)
    sent: list[list[dict[str, Any]]] = field(default_factory=list)
    polls: int = 0

    def create(self, *, model: str, src: list[dict[str, Any]], config: Any) -> Any:
        self.sent.append(src)
        return genai_types.BatchJob(name="batches/1", state=State.JOB_STATE_PENDING)

    def get(self, *, name: str) -> Any:
        self.polls += 1
        responses = [
            genai_types.InlinedResponse(
                metadata=r["metadata"], error=genai_types.JobError(message="quota")
            )
            if int(r["metadata"]["index"]) in self.fail
            else answer(f"answer {r['metadata']['index']}", int(r["metadata"]["index"]))
            for r in self.sent[-1]
        ]
        return genai_types.BatchJob(
            name=name,
            state=State.JOB_STATE_SUCCEEDED,
            dest=genai_types.BatchJobDestination(inlined_responses=responses),
        )


class SDK:
    def __init__(self, batches: Batches) -> None:
        self.batches = batches


def runner(tmp_path: Path, batches: Batches, mode: CacheMode = CacheMode.RECORD) -> GeminiBatch:
    client = GeminiClient(cache=ResponseCache(mode, tmp_path), sdk=SDK(batches))  # type: ignore[arg-type]
    return GeminiBatch(client, poll_s=0, sleep=lambda _: None, log=lambda _: None)


def test_only_the_misses_are_sent_and_recorded_at_half_price(tmp_path: Path) -> None:
    batches = Batches()
    first = runner(tmp_path, batches).run([request("a")])
    assert first.submitted == 1

    run = runner(tmp_path, batches).run([request("a"), request("b")])

    assert run.submitted == 1
    assert len(batches.sent) == 2
    assert [r["metadata"]["index"] for r in batches.sent[-1]] == ["1"]
    assert [r.text for r in run.results] == ["answer 0", "answer 1"]
    assert run.results[0].cached
    usage = LLMUsage(input_tokens=1000, output_tokens=150)
    full = price_for(STRONG_MODEL, date.today()).cost(usage)
    assert run.results[1].cost_usd == pytest.approx(full / 2)


class Verdict(BaseModel):
    reason: str
    verdict: Literal["agree", "dispute"]
    fix: str | None


def test_the_batch_sends_its_schema_as_response_schema(tmp_path: Path) -> None:
    batches = Batches()
    schema = portable_schema(Verdict)
    structured = request("a").model_copy(update={"json_schema": schema})
    runner(tmp_path, batches).run([structured])

    config = batches.sent[0][0]["config"]
    assert "response_json_schema" not in config  # the Batch API ignores it
    assert config["response_schema"] == openapi_schema(schema)
    assert config["thinking_config"] == {"thinking_level": "LOW"}
    # Recorded under what was sent: a plain call of the same request does not replay it.
    client = GeminiClient(cache=ResponseCache(CacheMode.REPLAY, tmp_path))
    with pytest.raises(CacheMiss):
        asyncio.run(client.complete(structured))


def test_openapi_schema_keeps_order_and_marks_nullable() -> None:
    converted = openapi_schema(portable_schema(Verdict))
    assert converted["propertyOrdering"] == ["reason", "verdict", "fix"]
    assert converted["properties"]["fix"] == {"type": "string", "nullable": True}
    assert converted["properties"]["verdict"]["enum"] == ["agree", "dispute"]
    assert "additionalProperties" not in converted


def test_replay_mode_refuses_to_submit(tmp_path: Path) -> None:
    batches = Batches()
    with pytest.raises(CacheMiss, match="1 llm recordings missing"):
        runner(tmp_path, batches, CacheMode.REPLAY).run([request("a")])
    assert batches.sent == []


def test_failed_requests_raise_after_the_answers_are_recorded(tmp_path: Path) -> None:
    with pytest.raises(BatchIncomplete) as raised:
        runner(tmp_path, Batches(fail={1})).run([request("a"), request("b")])
    assert raised.value.failed == [1]

    batches = Batches()
    run = runner(tmp_path, batches).run([request("a"), request("b")])
    assert run.submitted == 1
    assert [r["metadata"]["index"] for r in batches.sent[0]] == ["1"]


def test_one_model_per_job(tmp_path: Path) -> None:
    other = LLMRequest(model="gemini-other", messages=[Message(role="user", content="x")])
    with pytest.raises(ValueError, match="one model"):
        runner(tmp_path, Batches()).run([request("a"), other])

"""The LLM clients: recording and replay, retries, timeouts, streams, payloads and usage."""

import asyncio
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest
from google.genai import types as genai_types
from hypothesis import given
from hypothesis import strategies as st
from openai.types.chat import ChatCompletion

from plumbline.cache import CacheMiss, Json, ResponseCache
from plumbline.core.types import CacheMode
from plumbline.generation.llm import (
    JUDGE_MODEL,
    PRICES,
    AnthropicClient,
    BaseClient,
    Done,
    GeminiClient,
    LLMRequest,
    Message,
    OpenAICompatibleClient,
    Price,
    Rate,
    RetryPolicy,
    Usage,
    chunk_text,
    price_for,
)

PRICE = Price(date.min, Rate(input=1.0, output=2.0, cache_read=0.1))
REQUEST = LLMRequest(
    model="fake-1",
    system="Answer from the statute.",
    messages=[Message(role="user", content="What is the deposit cap?")],
    json_schema={"type": "object"},
)
ANSWER = "The landlord must return the deposit within fifteen days of the tenancy ending."


class Fake(BaseClient):
    """A provider whose calls follow a script: a string answers, an exception is raised."""

    provider = "fake"

    def __init__(self, script: list[Any], **kwargs: Any) -> None:
        super().__init__(price=PRICE, retry=RetryPolicy(timeout_s=0.5), **kwargs)
        self.script = script
        self.calls = 0

    def payload(self, request: LLMRequest) -> dict[str, Json]:
        return {"model": request.model, "prompt": request.messages[0].content}

    def _next(self) -> Any:
        self.calls += 1
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    async def _create(self, payload: dict[str, Json]) -> tuple[str, Done]:
        step = self._next()
        if step == "hang":
            await asyncio.sleep(10)
        return step, Done(Usage(input_tokens=1000, output_tokens=500), "stop")

    async def _stream(self, payload: dict[str, Json]) -> AsyncIterator[str | Done]:
        for word in self._next().split(" "):
            if word == "BOOM":
                raise httpx.ConnectError("dropped")
            yield word + " "
        yield Done(Usage(input_tokens=10, output_tokens=5), "stop")

    def _retryable(self, exc: Exception) -> bool:
        return False


def make(tmp_path: Path, mode: CacheMode, script: list[Any]) -> tuple[Fake, list[float]]:
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    return Fake(script, cache=ResponseCache(mode, tmp_path), sleep=sleep), sleeps


async def collect(client: BaseClient, request: LLMRequest = REQUEST) -> list[Any]:
    return [item async for item in client.stream(request)]


def test_a_recording_replays_with_its_cost_and_no_call(tmp_path: Path) -> None:
    client, _ = make(tmp_path, CacheMode.RECORD, [ANSWER])
    recorded = asyncio.run(client.complete(REQUEST))
    assert not recorded.cached
    assert recorded.cost_usd == pytest.approx(0.002)  # 1000 x $1 + 500 x $2, per million

    replay, _ = make(tmp_path, CacheMode.REPLAY, [])
    replayed = asyncio.run(replay.complete(REQUEST))
    assert (replayed.text, replayed.cost_usd, replayed.usage) == (ANSWER, 0.002, recorded.usage)
    assert replayed.cached
    assert replay.calls == 0


def test_a_replay_miss_never_calls_the_provider(tmp_path: Path) -> None:
    client, _ = make(tmp_path, CacheMode.REPLAY, [ANSWER])
    with pytest.raises(CacheMiss):
        asyncio.run(client.complete(REQUEST))
    with pytest.raises(CacheMiss):
        asyncio.run(collect(client))
    assert client.calls == 0


def test_retryable_errors_back_off_then_succeed(tmp_path: Path) -> None:
    client, sleeps = make(tmp_path, CacheMode.LIVE, [httpx.ConnectError("x"), "hang", ANSWER])
    assert asyncio.run(client.complete(REQUEST)).text == ANSWER
    assert client.calls == 3
    assert len(sleeps) == 2
    assert all(0 <= s <= client.retry.max_delay_s for s in sleeps)


def test_other_errors_and_the_last_attempt_raise(tmp_path: Path) -> None:
    client, sleeps = make(tmp_path, CacheMode.LIVE, [ValueError("bad request")])
    with pytest.raises(ValueError, match="bad request"):
        asyncio.run(client.complete(REQUEST))
    assert sleeps == []
    client, _ = make(tmp_path, CacheMode.LIVE, [httpx.ConnectError("x")] * 4)
    with pytest.raises(httpx.ConnectError):
        asyncio.run(client.complete(REQUEST))
    assert client.calls == 4


def test_a_stream_records_then_replays_in_small_chunks(tmp_path: Path) -> None:
    client, _ = make(tmp_path, CacheMode.RECORD, [ANSWER])
    *deltas, result = asyncio.run(collect(client))
    assert "".join(deltas) == ANSWER + " " == result.text
    assert not result.cached
    assert result.usage.output_tokens == 5

    replay, _ = make(tmp_path, CacheMode.REPLAY, [])
    *pieces, again = asyncio.run(collect(replay))
    assert "".join(pieces) == result.text
    assert len(pieces) > 1
    assert again.cached
    assert again.cost_usd == result.cost_usd
    assert asyncio.run(replay.complete(REQUEST)).text == result.text  # one recording for both


def test_a_stream_retries_only_before_its_first_delta(tmp_path: Path) -> None:
    client, sleeps = make(tmp_path, CacheMode.LIVE, ["BOOM", ANSWER])
    assert asyncio.run(collect(client))[-1].text == ANSWER + " "
    assert len(sleeps) == 1
    client, _ = make(tmp_path, CacheMode.LIVE, ["three words BOOM", ANSWER])
    with pytest.raises(httpx.ConnectError):
        asyncio.run(collect(client))
    assert client.calls == 1


def test_a_slow_reader_does_not_time_the_provider_out(tmp_path: Path) -> None:
    client, _ = make(tmp_path, CacheMode.LIVE, ["one two three"])
    client.retry = RetryPolicy(timeout_s=0.05)

    async def slow() -> str:
        text = ""
        async for item in client.stream(REQUEST):
            if isinstance(item, str):
                text += item
                await asyncio.sleep(0.03)
        return text

    assert asyncio.run(slow()) == "one two three "


@given(st.text(alphabet=st.sampled_from("ab \n"), max_size=200), st.integers(1, 40))
def test_chunks_join_back_exactly(text: str, size: int) -> None:
    pieces = chunk_text(text, size)
    assert "".join(pieces) == text
    assert all(0 < len(p) <= size for p in pieces)


def test_prices_follow_the_date_and_the_prompt_length() -> None:
    assert price_for("gemini-3.8-flash", date(2026, 12, 31)).rate.input == 0.75
    assert price_for("gemini-3.8-flash", date(2027, 1, 1)).rate.input == 1.50
    judge = price_for(JUDGE_MODEL, date(2026, 10, 19))
    assert judge.cost(Usage(input_tokens=100_000, output_tokens=1000)) == pytest.approx(0.0105)
    assert judge.cost(Usage(input_tokens=100_001)) == pytest.approx(0.0500005)
    assert all(prices[0].valid_from == date.min for prices in PRICES.values())
    with pytest.raises(KeyError, match="no price"):
        price_for("gpt-unknown", date(2026, 10, 19))


def sdk(path: str, response: Any) -> Any:
    """A stand-in SDK object whose method at `path` records its kwargs and returns `response`."""
    seen: dict[str, Any] = {}

    async def method(**kwargs: Any) -> Any:
        seen.update(kwargs)
        return response

    obj: Any = method
    for name in reversed(path.split(".")):
        obj = SimpleNamespace(**{name: obj})
    obj.seen = seen
    return obj


def live(client_type: type[BaseClient], fake: Any, tmp_path: Path, **kw: Any) -> BaseClient:
    return client_type(sdk=fake, cache=ResponseCache(CacheMode.LIVE, tmp_path), price=PRICE, **kw)


def test_gemini_payload_and_usage(tmp_path: Path) -> None:
    response = genai_types.GenerateContentResponse.model_validate(
        {
            "candidates": [
                {"content": {"role": "model", "parts": [{"text": "{}"}]}, "finish_reason": "STOP"}
            ],
            "usage_metadata": {
                "prompt_token_count": 1000,
                "cached_content_token_count": 600,
                "candidates_token_count": 50,
                "thoughts_token_count": 20,
            },
        }
    )
    fake = sdk("aio.models.generate_content", response)
    result = asyncio.run(live(GeminiClient, fake, tmp_path).complete(REQUEST))
    assert fake.seen["config"] == {
        "max_output_tokens": 1024,
        "system_instruction": "Answer from the statute.",
        "temperature": 0.0,
        "response_mime_type": "application/json",
        "response_json_schema": {"type": "object"},
    }
    assert fake.seen["contents"][0]["role"] == "user"
    assert result.usage == Usage(input_tokens=400, cache_read_tokens=600, output_tokens=70)
    assert (result.text, result.stop_reason) == ("{}", "STOP")


def test_anthropic_payload_and_usage(tmp_path: Path) -> None:
    message = anthropic.types.Message.model_validate(
        {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": JUDGE_MODEL,
            "content": [
                {"type": "thinking", "thinking": "Weigh it.", "signature": "s"},
                {"type": "text", "text": "PASS"},
            ],
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": 100,
                "cache_read_input_tokens": 900,
                "cache_creation_input_tokens": 0,
                "output_tokens": 30,
            },
        }
    )
    fake = sdk("messages.create", message)
    result = asyncio.run(live(AnthropicClient, fake, tmp_path).complete(REQUEST))
    assert "temperature" not in fake.seen
    assert fake.seen["system"] == [
        {"type": "text", "text": "Answer from the statute.", "cache_control": {"type": "ephemeral"}}
    ]
    assert fake.seen["output_config"] == {
        "format": {"type": "json_schema", "schema": {"type": "object"}}
    }
    assert result.text == "PASS"
    assert result.usage == Usage(input_tokens=100, cache_read_tokens=900, output_tokens=30)


def test_openai_compatible_payload_usage_and_key(tmp_path: Path) -> None:
    completion = ChatCompletion.model_validate(
        {
            "id": "c1",
            "object": "chat.completion",
            "created": 0,
            "model": "local-model",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "{}"},
                }
            ],
            "usage": {
                "prompt_tokens": 300,
                "completion_tokens": 20,
                "total_tokens": 320,
                "prompt_tokens_details": {"cached_tokens": 256},
            },
        }
    )
    fake = sdk("chat.completions.create", completion)
    client = live(OpenAICompatibleClient, fake, tmp_path, base_url="http://llm.lan/v1")
    result = asyncio.run(client.complete(REQUEST))
    assert fake.seen["messages"][0] == {"role": "system", "content": "Answer from the statute."}
    assert fake.seen["response_format"]["json_schema"]["strict"] is True
    assert result.usage == Usage(input_tokens=44, cache_read_tokens=256, output_tokens=20)
    assert client.cache_request({"model": "m"})["base_url"] == "http://llm.lan/v1"


def test_thinking_is_sent_only_when_asked_for(tmp_path: Path) -> None:
    calm = REQUEST.model_copy(update={"thinking": "minimal"})
    gemini = GeminiClient(sdk=object(), cache=ResponseCache(CacheMode.LIVE, tmp_path))  # type: ignore[arg-type]
    assert "thinking_config" not in gemini.payload(REQUEST)["config"]
    assert gemini.payload(calm)["config"]["thinking_config"] == {"thinking_level": "MINIMAL"}
    claude = AnthropicClient(sdk=object(), cache=ResponseCache(CacheMode.LIVE, tmp_path))  # type: ignore[arg-type]
    assert claude.payload(REQUEST)["output_config"] == {
        "format": {"type": "json_schema", "schema": {"type": "object"}}
    }
    assert claude.payload(calm)["output_config"]["effort"] == "low"  # Claude's lowest
    compatible = OpenAICompatibleClient(sdk=object(), cache=ResponseCache(CacheMode.LIVE, tmp_path))  # type: ignore[arg-type]
    assert "reasoning_effort" not in compatible.payload(REQUEST)
    assert compatible.payload(calm)["reasoning_effort"] == "minimal"

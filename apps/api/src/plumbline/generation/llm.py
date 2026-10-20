"""LLM clients: one protocol over Gemini, Anthropic and any OpenAI-compatible endpoint.

Every call goes through plumbline.cache (kind "llm"). The cache request is the payload sent
to the provider plus the provider's name, so it fully determines the response and never
holds a key, a timeout or a retry setting. A plain call and a streamed call of the same
request share one recording, and a recording replays as a stream by re-sending its text in
small chunks.

Retries and timeouts are ours, not the SDKs' (theirs are switched off), so every provider
fails the same way: a retryable error is retried with exponential backoff and full jitter
until the attempts run out, and a stream is retried only before its first delta, because
text already sent cannot be taken back.
"""

from __future__ import annotations

import asyncio
import random
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from typing import Any, Final, Literal, Protocol, Self

import anthropic
import httpx
import openai
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import Field, SecretStr, model_validator

from plumbline.cache import Cached, CacheMiss, Fresh, Json, ResponseCache, get_cache
from plumbline.core.types import CacheMode, Frozen
from plumbline.settings import Settings, get_settings

# The models behind each route, pinned on 2026-10-19 from Google's and Anthropic's model
# pages: the stable Flash-Lite that Google points new projects to, its newest stable Flash
# (there is no stable Pro yet), and the current Claude Sonnet and Haiku.
FAST_MODEL: Final = "gemini-3.5-flash-lite"
STRONG_MODEL: Final = "gemini-3.8-flash"
PREMIUM_MODEL: Final = "claude-sonnet-5-5"
JUDGE_MODEL: Final = "claude-haiku-5-5"


class Message(Frozen):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class LLMRequest(Frozen):
    model: str = Field(min_length=1)
    messages: list[Message] = Field(min_length=1)
    system: str = ""
    max_output_tokens: int = Field(default=1024, ge=1)
    temperature: float | None = Field(default=0.0, ge=0, le=2)  # Claude's current models take none
    json_schema: dict[str, Any] | None = None  # structured output: the text is JSON of this schema
    cache_system: bool = True  # mark the system prompt as a cacheable prefix where that is explicit
    # The start of the first user message, kept apart because it repeats across requests
    # (the whole law, for long context): Claude gets it as its own block with a cache
    # breakpoint, the others as the start of the text, where their implicit prefix caching
    # finds it. Empty, it is not sent, so a request without it keeps the key it always had.
    prefix: str = ""
    # How much the model may think before it answers; None leaves the model's default, and is
    # not sent, so a request without it keeps the key it always had.
    thinking: Literal["minimal", "low", "medium", "high"] | None = None

    @model_validator(mode="after")
    def _prefix_starts_a_user_message(self) -> Self:
        if self.prefix and self.messages[0].role != "user":
            raise ValueError("a prefix starts the first message, which must be the user's")
        return self

    def joined(self) -> list[dict[str, Json]]:
        """The messages as role and text, the prefix at the start of the first one."""
        messages = [m.model_dump() for m in self.messages]
        if self.prefix:
            messages[0]["content"] = f"{self.prefix}\n\n{messages[0]['content']}"
        return messages


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0  # billed at the full input rate
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0  # thinking included: it bills as output

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens


@dataclass(frozen=True)
class Rate:
    """USD per million tokens."""

    input: float
    output: float
    cache_read: float
    cache_write: float | None = None  # None: implicit caching, writes bill as plain input

    def cost(self, usage: Usage) -> float:
        write = self.input if self.cache_write is None else self.cache_write
        return (
            usage.input_tokens * self.input
            + usage.cache_read_tokens * self.cache_read
            + usage.cache_write_tokens * write
            + usage.output_tokens * self.output
        ) / 1_000_000


@dataclass(frozen=True)
class Price:
    valid_from: date
    rate: Rate
    long_prompt_tokens: int | None = None  # a prompt longer than this pays long_rate throughout
    long_rate: Rate | None = None

    def cost(self, usage: Usage) -> float:
        long = self.long_prompt_tokens is not None and usage.prompt_tokens > self.long_prompt_tokens
        return (self.long_rate if long and self.long_rate else self.rate).cost(usage)


# From ai.google.dev/gemini-api/docs/pricing and platform.claude.com's pricing page, paid
# tier, standard (not batch) prices. Gemini's caching here is implicit: no write charge
# and no storage. Claude's writes are the 5-minute ones, the only TTL this module asks for.
PRICES_CHECKED: Final = date(2026, 10, 19)
PRICES: Final[dict[str, tuple[Price, ...]]] = {
    FAST_MODEL: (Price(date.min, Rate(input=0.30, output=2.50, cache_read=0.03)),),
    STRONG_MODEL: (
        Price(date.min, Rate(input=0.75, output=3.75, cache_read=0.075)),
        Price(date(2027, 1, 1), Rate(input=1.50, output=7.50, cache_read=0.15)),
    ),
    PREMIUM_MODEL: (
        Price(date.min, Rate(input=2.00, output=10.00, cache_read=0.10, cache_write=2.50)),
    ),
    JUDGE_MODEL: (
        Price(
            date.min,
            Rate(input=0.10, output=0.50, cache_read=0.01, cache_write=0.125),
            long_prompt_tokens=100_000,
            long_rate=Rate(input=0.50, output=2.50, cache_read=0.05, cache_write=0.625),
        ),
    ),
}


def price_for(model: str, day: date) -> Price:
    if model not in PRICES:
        raise KeyError(f"no price for {model}: add it to PRICES or pass the client a price")
    return max((p for p in PRICES[model] if p.valid_from <= day), key=lambda p: p.valid_from)


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 4  # the first call included
    base_delay_s: float = 1.0
    max_delay_s: float = 20.0
    timeout_s: float = 60.0  # per attempt, spent waiting on the provider

    def delay(self, attempt: int) -> float:
        """Full jitter: clients that failed together do not retry together."""
        return random.uniform(0, min(self.max_delay_s, self.base_delay_s * 2**attempt))  # noqa: S311


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    usage: Usage
    cost_usd: float
    latency_ms: int  # of the original call, when replayed
    stop_reason: str | None
    cached: bool
    key: str  # the recording's cache key


class LLMClient(Protocol):
    provider: str

    async def complete(self, request: LLMRequest) -> LLMResult: ...

    def stream(self, request: LLMRequest) -> AsyncIterator[str | LLMResult]:
        """Text deltas as they arrive, then one LLMResult."""
        ...


@dataclass(frozen=True)
class Done:
    """The end of a provider's stream."""

    usage: Usage
    stop_reason: str | None


def chunk_text(text: str, size: int = 24) -> list[str]:
    """Small pieces that join back to `text` exactly, cut after a space where one is near."""
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        space = text.rfind(" ", start, end)
        if end < len(text) and space > start:
            end = space + 1
        pieces.append(text[start:end])
        start = end
    return pieces


class BaseClient(ABC):
    provider: str

    def __init__(
        self,
        *,
        cache: ResponseCache | None = None,
        retry: RetryPolicy | None = None,
        price: Price | None = None,  # overrides PRICES, for models the table does not know
        settings: Settings | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.cache = cache or get_cache()
        self.retry = retry or RetryPolicy()
        self.price = price
        self._settings = settings
        self._sleep = sleep

    @abstractmethod
    def payload(self, request: LLMRequest) -> dict[str, Json]:
        """The provider's request body: what is sent, and what the recording is keyed on."""

    @abstractmethod
    async def _create(self, payload: dict[str, Json]) -> tuple[str, Done]: ...

    @abstractmethod
    def _stream(self, payload: dict[str, Json]) -> AsyncGenerator[str | Done]: ...

    @abstractmethod
    def _retryable(self, exc: Exception) -> bool: ...

    @property
    def settings(self) -> Settings:
        return self._settings or get_settings()

    def cache_request(self, payload: dict[str, Json]) -> dict[str, Json]:
        return {"provider": self.provider, **payload}

    async def complete(self, request: LLMRequest) -> LLMResult:
        payload = self.payload(request)

        async def call() -> Fresh:
            price = self._price(request.model)
            for attempt in range(self.retry.attempts):
                try:
                    text, done = await asyncio.wait_for(self._create(payload), self.retry.timeout_s)
                    return _fresh(text, done, price)
                except Exception as exc:
                    await self._backoff(exc, attempt)
            raise AssertionError("unreachable: the last attempt raises")

        return _result(await self.cache.acall("llm", self.cache_request(payload), call))

    async def stream(self, request: LLMRequest) -> AsyncIterator[str | LLMResult]:
        payload = self.payload(request)
        key_request = self.cache_request(payload)
        hit = self.cache.get("llm", key_request)
        if hit is not None:
            for piece in chunk_text(str(hit.response["text"])):
                yield piece
            yield _result(hit)
            return
        if self.cache.mode is CacheMode.REPLAY:
            raise CacheMiss(
                f"no llm recording for {request.model}; record it with CACHE_MODE=record"
            )
        price = self._price(request.model)
        start = time.perf_counter()
        for attempt in range(self.retry.attempts):
            parts: list[str] = []
            try:
                async with aclosing(self._timed(self._stream(payload))) as items:
                    async for item in items:
                        if isinstance(item, Done):
                            fresh = _fresh("".join(parts), item, price)
                            latency = round((time.perf_counter() - start) * 1000)
                            put = self.cache.put("llm", key_request, fresh, latency_ms=latency)
                            yield _result(put)
                            return
                        parts.append(item)
                        yield item
                raise RuntimeError(f"{self.provider} stream ended without its usage")
            except Exception as exc:
                if parts:
                    raise
                await self._backoff(exc, attempt)

    async def _timed(self, items: AsyncGenerator[str | Done]) -> AsyncGenerator[str | Done]:
        """The provider's items, with the attempt's timeout counted only while waiting on the
        provider: a slow reader of this stream never times the provider out."""
        budget = self.retry.timeout_s
        try:
            while True:
                started = time.perf_counter()
                try:
                    item = await asyncio.wait_for(anext(items), max(budget, 0.0))
                except StopAsyncIteration:
                    return
                budget -= time.perf_counter() - started
                yield item
        finally:
            await items.aclose()

    async def _backoff(self, exc: Exception, attempt: int) -> None:
        """Sleep before the next attempt, or re-raise when there is none."""
        retryable = isinstance(exc, TimeoutError | httpx.TransportError) or self._retryable(exc)
        if not retryable or attempt + 1 >= self.retry.attempts:
            raise exc
        await self._sleep(self.retry.delay(attempt))

    def _price(self, model: str) -> Price:
        return self.price or price_for(model, datetime.now(UTC).date())

    def _key(self, secret: SecretStr | None, name: str) -> str:
        # An empty line in .env ("ANTHROPIC_API_KEY=") reads as an empty string, which the
        # SDKs accept and then fail on deep inside a request; refuse it here, by name.
        key = secret.get_secret_value().strip() if secret is not None else ""
        if not key:
            raise RuntimeError(f"{name} is not set: live and record modes need it in .env")
        return key


def _fresh(text: str, done: Done, price: Price) -> Fresh:
    return Fresh(
        response={"text": text, "usage": asdict(done.usage)},
        input_tokens=done.usage.prompt_tokens,
        output_tokens=done.usage.output_tokens,
        cost_usd=price.cost(done.usage),
        stop_reason=done.stop_reason,
    )


def _result(cached: Cached) -> LLMResult:
    return LLMResult(
        text=str(cached.response["text"]),
        model=cached.model,
        usage=Usage(**cached.response["usage"]),
        cost_usd=cached.cost_usd,
        latency_ms=cached.latency_ms,
        stop_reason=cached.stop_reason,
        cached=cached.cached,
        key=cached.key,
    )


def _http_retryable(status: int) -> bool:
    return status in (408, 409, 429) or status >= 500


class GeminiClient(BaseClient):
    """Gemini caches repeated prefixes implicitly; the usage reports the tokens it read."""

    provider = "gemini"

    def __init__(self, *, sdk: genai.Client | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._sdk = sdk

    def payload(self, request: LLMRequest) -> dict[str, Json]:
        config: dict[str, Json] = {"max_output_tokens": request.max_output_tokens}
        if request.system:
            config["system_instruction"] = request.system
        if request.temperature is not None:
            config["temperature"] = request.temperature
        if request.json_schema is not None:
            config["response_mime_type"] = "application/json"
            config["response_json_schema"] = request.json_schema
        if request.thinking is not None:
            config["thinking_config"] = {"thinking_level": request.thinking.upper()}
        contents = [
            {
                "role": "model" if m["role"] == "assistant" else "user",
                "parts": [{"text": m["content"]}],
            }
            for m in request.joined()
        ]
        return {"model": request.model, "contents": contents, "config": config}

    def _client(self) -> genai.Client:
        if self._sdk is None:
            options = genai_types.HttpOptions(
                timeout=round(self.retry.timeout_s * 1000),
                retry_options=genai_types.HttpRetryOptions(attempts=1),
            )
            key = self._key(self.settings.gemini_api_key, "GEMINI_API_KEY")
            self._sdk = genai.Client(api_key=key, http_options=options)
        return self._sdk

    async def _create(self, payload: dict[str, Json]) -> tuple[str, Done]:
        response = await self._client().aio.models.generate_content(**payload)
        return response.text or "", Done(_gemini_usage(response), _gemini_stop(response))

    async def _stream(self, payload: dict[str, Json]) -> AsyncGenerator[str | Done]:
        last: genai_types.GenerateContentResponse | None = None
        async for chunk in await self._client().aio.models.generate_content_stream(**payload):
            if chunk.text:
                yield chunk.text
            last = chunk
        yield Done(_gemini_usage(last), _gemini_stop(last))

    def _retryable(self, exc: Exception) -> bool:
        return isinstance(exc, genai_errors.APIError) and _http_retryable(exc.code)


def _gemini_usage(response: genai_types.GenerateContentResponse | None) -> Usage:
    meta = response.usage_metadata if response else None
    if meta is None:
        return Usage()
    cached = meta.cached_content_token_count or 0  # part of prompt_token_count
    return Usage(
        input_tokens=(meta.prompt_token_count or 0) - cached,
        cache_read_tokens=cached,
        output_tokens=(meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0),
    )


def _gemini_stop(response: genai_types.GenerateContentResponse | None) -> str | None:
    if not response or not response.candidates or response.candidates[0].finish_reason is None:
        return None
    return str(response.candidates[0].finish_reason.value)


# Claude's effort has no "minimal": its lowest level stands in for it.
_CLAUDE_EFFORT: Final = {"minimal": "low", "low": "low", "medium": "medium", "high": "high"}


class AnthropicClient(BaseClient):
    """Claude takes no sampling parameters, so `temperature` is not sent; the system prompt
    is marked as a 5-minute cache breakpoint (a no-op under the model's minimum length)."""

    provider = "anthropic"

    def __init__(self, *, sdk: anthropic.AsyncAnthropic | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._sdk = sdk

    def payload(self, request: LLMRequest) -> dict[str, Json]:
        messages: list[Json] = [m.model_dump() for m in request.messages]
        if request.prefix:
            cached: dict[str, Json] = {"type": "text", "text": request.prefix}
            cached["cache_control"] = {"type": "ephemeral"}
            first: list[Json] = [cached, {"type": "text", "text": request.messages[0].content}]
            messages[0] = {"role": "user", "content": first}
        body: dict[str, Json] = {
            "model": request.model,
            "max_tokens": request.max_output_tokens,
            "messages": messages,
        }
        if request.system:
            block: dict[str, Json] = {"type": "text", "text": request.system}
            if request.cache_system:
                block["cache_control"] = {"type": "ephemeral"}
            body["system"] = [block]
        output: dict[str, Json] = {}
        if request.json_schema is not None:
            output["format"] = {"type": "json_schema", "schema": request.json_schema}
        if request.thinking is not None:
            output["effort"] = _CLAUDE_EFFORT[request.thinking]
        if output:
            body["output_config"] = output
        return body

    def _client(self) -> anthropic.AsyncAnthropic:
        if self._sdk is None:
            key = self._key(self.settings.anthropic_api_key, "ANTHROPIC_API_KEY")
            self._sdk = anthropic.AsyncAnthropic(
                api_key=key, max_retries=0, timeout=self.retry.timeout_s
            )
        return self._sdk

    async def _create(self, payload: dict[str, Json]) -> tuple[str, Done]:
        message = await self._client().messages.create(**payload)
        return _anthropic_text(message), _anthropic_done(message)

    async def _stream(self, payload: dict[str, Json]) -> AsyncGenerator[str | Done]:
        async with self._client().messages.stream(**payload) as stream:
            async for text in stream.text_stream:
                yield text
            message = await stream.get_final_message()
        yield _anthropic_done(message)

    def _retryable(self, exc: Exception) -> bool:
        if isinstance(exc, anthropic.APIConnectionError):
            return True
        return isinstance(exc, anthropic.APIStatusError) and _http_retryable(exc.status_code)


def _anthropic_text(message: anthropic.types.Message) -> str:
    # Thinking blocks are skipped: the answer is the text blocks alone.
    return "".join(b.text for b in message.content if isinstance(b, anthropic.types.TextBlock))


def _anthropic_done(message: anthropic.types.Message) -> Done:
    u = message.usage
    usage = Usage(
        input_tokens=u.input_tokens,
        cache_read_tokens=u.cache_read_input_tokens or 0,
        cache_write_tokens=u.cache_creation_input_tokens or 0,
        output_tokens=u.output_tokens,
    )
    return Done(usage, message.stop_reason)


class OpenAICompatibleClient(BaseClient):
    """Chat Completions on any compatible endpoint. The endpoint is part of the recording's
    key, since the same model name can mean different models on different servers. OpenAI
    caches long prefixes on its own and reports the tokens it read."""

    provider = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str = "https://api.openai.com/v1",
        api_key: SecretStr | None = None,  # default: OPENAI_API_KEY
        sdk: openai.AsyncOpenAI | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.base_url = base_url
        self._api_key = api_key
        self._sdk = sdk

    def cache_request(self, payload: dict[str, Json]) -> dict[str, Json]:
        return {"provider": self.provider, "base_url": self.base_url, **payload}

    def payload(self, request: LLMRequest) -> dict[str, Json]:
        system = [{"role": "system", "content": request.system}] if request.system else []
        body: dict[str, Json] = {
            "model": request.model,
            "messages": system + request.joined(),
            "max_tokens": request.max_output_tokens,  # the field compatible servers all accept
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.json_schema is not None:
            schema = {"name": "response", "schema": request.json_schema, "strict": True}
            body["response_format"] = {"type": "json_schema", "json_schema": schema}
        if request.thinking is not None:
            body["reasoning_effort"] = request.thinking
        return body

    def _client(self) -> openai.AsyncOpenAI:
        if self._sdk is None:
            key = self._key(self._api_key or self.settings.openai_api_key, "OPENAI_API_KEY")
            self._sdk = openai.AsyncOpenAI(
                api_key=key, base_url=self.base_url, max_retries=0, timeout=self.retry.timeout_s
            )
        return self._sdk

    async def _create(self, payload: dict[str, Json]) -> tuple[str, Done]:
        completion = await self._client().chat.completions.create(**payload)
        choice = completion.choices[0]
        return choice.message.content or "", Done(
            _openai_usage(completion.usage), choice.finish_reason
        )

    async def _stream(self, payload: dict[str, Json]) -> AsyncGenerator[str | Done]:
        usage, stop = Usage(), None
        stream = await self._client().chat.completions.create(
            **payload, stream=True, stream_options={"include_usage": True}
        )
        async with stream:
            async for chunk in stream:
                if chunk.choices:
                    if chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                    stop = chunk.choices[0].finish_reason or stop
                if chunk.usage is not None:
                    usage = _openai_usage(chunk.usage)
        yield Done(usage, stop)

    def _retryable(self, exc: Exception) -> bool:
        if isinstance(exc, openai.APIConnectionError):
            return True
        return isinstance(exc, openai.APIStatusError) and _http_retryable(exc.status_code)


def _openai_usage(usage: openai.types.CompletionUsage | None) -> Usage:
    if usage is None:
        return Usage()
    details = usage.prompt_tokens_details
    cached = (details.cached_tokens if details else None) or 0  # part of prompt_tokens
    return Usage(
        input_tokens=usage.prompt_tokens - cached,
        cache_read_tokens=cached,
        output_tokens=usage.completion_tokens,
    )


def client_for(model: str, **kwargs: Any) -> LLMClient:
    """The client for a pinned model; other endpoints build an OpenAICompatibleClient."""
    if model.startswith("gemini-"):
        return GeminiClient(**kwargs)
    if model.startswith("claude-"):
        return AnthropicClient(**kwargs)
    raise ValueError(f"no client for {model}: use OpenAICompatibleClient with its base_url")

"""One real call per pinned Gemini model, plain and streamed. Marked live: never part of
make check. Run with `uv run pytest -m live apps/api/tests/generation`; the keys come from
.env through plumbline.settings, and nothing is recorded (a live-mode cache in a temp dir)."""

import asyncio
from pathlib import Path

import pytest

from plumbline.cache import ResponseCache
from plumbline.core.types import CacheMode
from plumbline.generation.llm import (
    FAST_MODEL,
    STRONG_MODEL,
    LLMRequest,
    LLMResult,
    Message,
    client_for,
)
from plumbline.settings import Settings

pytestmark = pytest.mark.live


@pytest.mark.parametrize("model", [FAST_MODEL, STRONG_MODEL])
def test_a_pinned_model_answers_plain_and_streamed(model: str, tmp_path: Path) -> None:
    settings = Settings()
    if settings.gemini_api_key is None:
        pytest.skip(f"no key for {model}")
    client = client_for(model, cache=ResponseCache(CacheMode.LIVE, tmp_path), settings=settings)
    request = LLMRequest(
        model=model,
        system="Reply with one word.",
        messages=[Message(role="user", content="Say: ready")],
        max_output_tokens=256,
    )
    result = asyncio.run(client.complete(request))
    assert "ready" in result.text.lower()
    assert result.usage.output_tokens > 0
    assert result.cost_usd > 0

    async def streamed() -> list[str | LLMResult]:
        other = request.model_copy(update={"messages": [Message(role="user", content="Say: go")]})
        return [item async for item in client.stream(other)]

    *deltas, final = asyncio.run(streamed())
    assert isinstance(final, LLMResult)
    assert "".join(str(d) for d in deltas) == final.text

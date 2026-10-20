"""Contextual headers for indexing, on a fake client: each distinct text described once,
the law in force as the context, and the search text rebuilt."""

import asyncio
import json
import re
from collections.abc import AsyncIterator
from datetime import date

import pytest

from plumbline.core.types import Chunk, Jurisdiction, Language
from plumbline.generation.llm import LLMRequest, LLMResult, Usage
from plumbline.retrieval.contextualize import HEADER_MODEL, contextualize, law_text


class FakeClient:
    provider = "fake"

    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResult:
        self.requests.append(request)
        ids = re.findall(r'<passage id="(p\d+)">', request.messages[0].content)
        text = json.dumps({"headers": [{"id": i, "header": f"About {i}."} for i in ids]})
        return LLMResult(
            text=text,
            model=request.model,
            usage=Usage(),
            cost_usd=0.0,
            latency_ms=0,
            stop_reason="stop",
            cached=False,
            key="fake",
        )

    def stream(self, request: LLMRequest) -> AsyncIterator[str | LLMResult]:
        raise NotImplementedError


def chunk(
    n: int, text: str, *, start: date | None = None, end: date | None = None, law: str = "es-lau"
) -> Chunk:
    return Chunk(
        id=f"{law}:{n}",
        document_id=law,
        jurisdiction=Jurisdiction.SPAIN,
        law=law,
        language=Language.ES,
        edition="boe-2026-10-13",
        article="9",
        label="LAU, art. 9",
        text=text,
        text_for_search=text,
        context_header="[Spain | LAU | Artículo 9 | Plazo mínimo]",
        effective_from=start,
        effective_to=end,
    )


OLD = chunk(1, "Texto de 2019.", start=date(2019, 3, 6), end=date(2026, 10, 8))
NEW = chunk(2, "Texto de 2026.", start=date(2026, 10, 8))
REPEAT = chunk(3, "Texto de 2026.", start=date(2026, 10, 8))  # same label and text as NEW


def test_each_distinct_text_is_described_once_with_the_law_in_force_as_context() -> None:
    client = FakeClient()
    out = asyncio.run(
        contextualize([OLD, NEW, REPEAT], client, headers="both", as_of=date(2026, 10, 20))
    )
    (request,) = client.requests
    assert request.model == HEADER_MODEL == "claude-haiku-5-5"
    law = request.messages[0].content.split("</law>")[0]
    assert "Texto de 2026." in law
    assert "Texto de 2019." not in law  # the old version is a passage, not the context
    assert request.messages[0].content.count("<passage id=") == 2
    assert [c.context_header_llm for c in out] == ["About p1.", "About p2.", "About p2."]
    assert out[1].text_for_search == (
        "[Spain | LAU | Artículo 9 | Plazo mínimo]\nAbout p2.\nTexto de 2026."
    )
    llm_only = asyncio.run(
        contextualize([NEW], FakeClient(), headers="llm", as_of=date(2026, 10, 20))
    )
    assert llm_only[0].text_for_search == "About p1.\nTexto de 2026."


def test_the_context_is_the_law_on_the_day() -> None:
    assert law_text([OLD, NEW], date(2020, 1, 1)) == "LAU, art. 9\nTexto de 2019."


def test_a_setting_without_llm_headers_or_two_laws_are_refused() -> None:
    with pytest.raises(ValueError, match="no LLM header"):
        asyncio.run(contextualize([NEW], FakeClient(), headers="deterministic", as_of=date.today()))
    other = chunk(4, "Otro texto.", law="es-lph")
    with pytest.raises(ValueError, match="one law at a time"):
        asyncio.run(contextualize([NEW, other], FakeClient(), headers="both", as_of=date.today()))

"""GET /api/law/search: the served configuration's retrieval, with no model call, each hit
ready to cite, and nothing of a restricted source but its reference."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from plumbline.api.app import create_app
from plumbline.api.quota import SEARCH_SHARE, MemoryCounter
from plumbline.core.config import EvalConfig
from plumbline.core.types import CacheMode, Chunk, Jurisdiction, Language, Retrieved
from plumbline.db import make_engine, make_sessionmaker
from plumbline.generation.pipeline import ChunkSearch
from plumbline.settings import Settings

pytestmark = pytest.mark.anyio
NO_DATABASE = "postgresql+psycopg://nobody@127.0.0.1:1/none"


def _chunk(document_id: str, jurisdiction: Jurisdiction, article: str, text: str) -> Chunk:
    return Chunk(
        id=f"{document_id}:{article}",
        document_id=document_id,
        jurisdiction=jurisdiction,
        law=document_id,
        language=Language.EN,
        edition="2026",
        article=article,
        label=f"{document_id} art. {article}",
        heading="A heading",
        text=text,
        text_for_search=text,
    )


FLORIDA = _chunk("fl-stat-83-2026", Jurisdiction.FLORIDA, "83.49", "The landlord must return…")
DUBAI = _chunk("dubai-law-26-2007-dlp-2024-12-20", Jurisdiction.DUBAI, "25", "Text not ours.")


@dataclass
class Search:
    seen: list[dict[str, Any]] = field(default_factory=list)

    def search(
        self,
        question: str,
        *,
        k: int,
        jurisdictions: list[Jurisdiction] | None,
        as_of: date | None,
    ) -> list[Retrieved]:
        self.seen.append({"q": question, "k": k, "jurisdictions": jurisdictions, "as_of": as_of})
        hits = [FLORIDA, DUBAI] * k
        return [Retrieved(chunk=c, rank=n, score=1 / n) for n, c in enumerate(hits, start=1)]


@dataclass(frozen=True)
class Parts:
    search: ChunkSearch


def _app(search: Search | None, questions: int = 30) -> tuple[FastAPI, list[str]]:
    configs: list[str] = []

    def factory(config: EvalConfig, /) -> Parts:
        configs.append(config.name)
        assert search is not None
        return Parts(search=search)

    settings = Settings(
        _env_file=None, cache_mode=CacheMode.REPLAY, daily_questions_per_ip=questions
    )
    app = create_app(
        settings,
        sessions=make_sessionmaker(make_engine(NO_DATABASE)),
        counter=MemoryCounter(),
        retrieval=factory if search is not None else None,
    )
    if search is None:
        app.state.retrieval = None
    return app, configs


async def _get(app: FastAPI, **params: Any) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/law/search", params=params)


async def test_hits_are_ready_to_cite_and_restricted_ones_quote_nothing() -> None:
    search = Search()
    app, configs = _app(search)
    response = await _get(app, q="deposit", jurisdiction="florida", as_of="2026-03-01", k=2)
    assert response.status_code == 200
    body = response.json()
    assert configs == ["A2-claude"]  # the served twin's retrieval, as /api/ask
    assert body["config_name"] == "A2-claude"
    assert search.seen == [
        {"q": "deposit", "k": 2, "jurisdictions": [Jurisdiction.FLORIDA], "as_of": date(2026, 3, 1)}
    ]
    florida, dubai = body["hits"]
    assert (florida["rank"], florida["chunk_id"]) == (1, FLORIDA.id)
    assert florida["text"] == FLORIDA.text
    assert florida["heading"] == "A heading"
    assert florida["restricted"] is False
    assert florida["source"]["id"] == "fl-stat-83-2026"
    assert florida["ref"]["article"] == "83.49"
    # The licence rule: a reference and a link, never the text or the heading.
    assert (dubai["text"], dubai["heading"], dubai["restricted"]) == ("", None, True)
    assert dubai["label"] == DUBAI.label
    assert dubai["source"]["id"] == DUBAI.document_id


async def test_every_jurisdiction_when_none_is_named() -> None:
    search = Search()
    app, _ = _app(search)
    body = (await _get(app, q="deposit")).json()
    assert search.seen[0]["jurisdictions"] is None
    assert len(body["hits"]) == 5  # the default k
    assert (body["jurisdiction"], body["as_of"]) == (None, None)


async def test_bounds_on_the_query() -> None:
    app, _ = _app(Search())
    for params in ({}, {"q": ""}, {"q": "x" * 1001}, {"q": "x", "k": 0}, {"q": "x", "k": 11}):
        assert (await _get(app, **params)).status_code == 422
    assert (await _get(app, q="x", jurisdiction="mars")).status_code == 422


async def test_searches_have_a_daily_allowance_of_their_own() -> None:
    app, _ = _app(Search(), questions=1)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        codes = [
            (await client.get("/api/law/search", params={"q": "x"})).status_code
            for _ in range(SEARCH_SHARE + 1)
        ]
        usage = (await client.get("/api/usage")).json()
    assert codes == [200] * SEARCH_SHARE + [429]
    assert usage["used"] == 0  # searches never touch the question allowance


async def test_a_server_without_retrieval_says_so() -> None:
    app, _ = _app(None)
    response = await _get(app, q="deposit")
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")

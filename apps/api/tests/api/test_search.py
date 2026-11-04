"""GET /api/search: the admin's view of retrieval, built on the pipeline's protocols and
fakes of them, since the SQL retriever is Lane A's."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from plumbline.api import search as search_module
from plumbline.api.app import create_app
from plumbline.core.config import EvalConfig
from plumbline.core.types import (
    Chunk,
    Jurisdiction,
    Language,
    RetrievalScores,
    Retrieved,
)
from plumbline.generation.pipeline import ChunkSearch, Reranker
from plumbline.generation.router import utc_today
from plumbline.settings import Settings

AUTH = {"Authorization": "Bearer search-test-token"}


def _hit(rank: int, article: str, text: str) -> Retrieved:
    chunk = Chunk(
        id=f"fl:{article}",
        document_id="fl-stat-83-2026",
        jurisdiction=Jurisdiction.FLORIDA,
        law="fl-stat-83",
        language=Language.EN,
        edition="2026",
        article=article,
        label=f"Fla. Stat. § {article}",
        text=text,
        text_for_search=text,
    )
    scores = RetrievalScores(
        dense=0.9 - rank / 100,
        bm25=12.0 - rank,
        rrf=1 / (60 + rank),
        dense_rank=rank,
        bm25_rank=rank,
    )
    return Retrieved(chunk=chunk, rank=rank, score=scores.rrf or 0.0, scores=scores)


HITS = [
    _hit(1, "83.49", "Deposit money."),
    _hit(2, "83.50", "Disclosure of the landlord's address, in writing, to every tenant."),
    _hit(3, "83.51", "Obligation to maintain."),
]


class FakeSearch:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search(
        self,
        question: str,
        *,
        k: int,
        jurisdictions: Sequence[Jurisdiction] | None,
        as_of: date | None,
    ) -> list[Retrieved]:
        self.calls.append({"q": question, "k": k, "jurisdictions": jurisdictions, "as_of": as_of})
        return HITS[:k]


class LengthReranker:
    """Scores a text by its length: the longest passage wins."""

    model = "fake-length"

    def scores(self, query: str, texts: Sequence[str]) -> list[float]:
        return [float(len(text)) for text in texts]


class Fakes:
    def __init__(self) -> None:
        self.search_ = FakeSearch()
        self.reranker_: LengthReranker | None = LengthReranker()
        self.asked: list[str] = []

    def __call__(self, config: EvalConfig) -> Fakes:
        self.asked.append(config.name)
        self.reranker_ = LengthReranker() if config.retrieval.rerank != "none" else None
        return self

    @property
    def search(self) -> ChunkSearch:
        return self.search_

    @property
    def reranker(self) -> Reranker | None:
        return self.reranker_


@pytest.fixture
def fakes() -> Fakes:
    return Fakes()


@pytest.fixture
def client(fakes: Fakes) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None, admin_token=SecretStr("search-test-token"), answer_config="A2"
    )
    with TestClient(create_app(settings, retrieval=fakes)) as test_client:
        yield test_client


def test_it_wants_the_admin_token_and_a_retrieval() -> None:
    settings = Settings(_env_file=None, admin_token=SecretStr("search-test-token"))
    with TestClient(create_app(settings)) as bare:
        assert bare.get("/api/search", params={"q": "x"}).status_code == 401
        no_retrieval = bare.get("/api/search", params={"q": "x"}, headers=AUTH)
        assert no_retrieval.status_code == 503
    assert (
        TestClient(create_app(Settings(_env_file=None))).get("/api/search?q=x").status_code == 404
    )


def test_a_configuration_without_a_reranker_shows_retrievals_own_scores(
    client: TestClient, fakes: Fakes
) -> None:
    body = client.get(
        "/api/search",
        params={"q": "deposit", "jurisdictions": ["florida", "spain"], "as_of": "2026-05-01"},
        headers=AUTH,
    ).json()
    assert (body["config"], body["k"], body["candidates"]) == ("A2", 8, 3)
    assert (body["as_of"], body["as_of_filter"], body["law_date"]) == (
        "2026-05-01",
        True,
        "2026-05-01",
    )
    assert [hit["chunk"]["article"] for hit in body["hits"]] == ["83.49", "83.50", "83.51"]
    first = body["hits"][0]["scores"]
    assert first["dense"] == pytest.approx(0.89)
    assert first["bm25"] == 11.0
    assert first["rrf"] == pytest.approx(1 / 61)
    assert first["rerank"] is None
    assert list(body["timings_ms"]) == ["search"]
    assert fakes.search_.calls == [
        {
            "q": "deposit",
            "k": 8,  # A2's top_k
            "jurisdictions": [Jurisdiction.FLORIDA, Jurisdiction.SPAIN],
            "as_of": date(2026, 5, 1),
        }
    ]


def test_the_law_searched_is_of_one_day_as_the_pipeline_picks_it(
    client: TestClient, fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    today = client.get("/api/search", params={"q": "deposit"}, headers=AUTH).json()
    assert (today["as_of"], today["law_date"]) == (None, utc_today().isoformat())
    assert fakes.search_.calls[-1]["as_of"] is None  # the retriever reads today's law

    a2 = search_module._config("A2")
    retrieval = a2.retrieval.model_copy(update={"as_of_filter": False})
    unfiltered = a2.model_copy(update={"retrieval": retrieval})
    monkeypatch.setattr(search_module, "_config", lambda name: unfiltered)
    asked = client.get(
        "/api/search", params={"q": "deposit", "as_of": "2020-01-01"}, headers=AUTH
    ).json()
    # Not filtered by date, an answer would read today's law; the debug route shows the same.
    assert fakes.search_.calls[-1]["as_of"] is None
    assert (asked["as_of"], asked["as_of_filter"]) == ("2020-01-01", False)
    assert asked["law_date"] == utc_today().isoformat()


def test_a_reranking_configuration_asks_for_candidates_then_cuts_by_rerank_score(
    client: TestClient, fakes: Fakes
) -> None:
    body = client.get(
        "/api/search", params={"q": "address", "config": "A3", "k": 2}, headers=AUTH
    ).json()
    assert fakes.search_.calls[0]["k"] == 20  # A3's rerank_candidates, not k
    assert (body["candidates"], body["k"]) == (3, 2)
    # The longest passage first, ranked again from 1, with the retrieval scores kept.
    assert [(hit["rank"], hit["chunk"]["article"]) for hit in body["hits"]] == [
        (1, "83.50"),
        (2, "83.51"),
    ]
    assert body["hits"][0]["scores"]["rerank"] == float(len(HITS[1].chunk.text_for_search))
    assert body["hits"][0]["scores"]["rrf"] == pytest.approx(1 / 62)
    assert set(body["timings_ms"]) == {"search", "rerank"}


def test_an_unknown_or_escaping_configuration_is_a_404(client: TestClient) -> None:
    # "../configs/A2" names a real file by a path that is not the folder's own spelling.
    for name in ("Z9", "../A2", "../configs/A2", "A2/../A2", "..%2fA2", "."):
        assert (
            client.get("/api/search", params={"q": "x", "config": name}, headers=AUTH).status_code
            == 404
        )


def test_the_question_and_k_are_bounded(client: TestClient) -> None:
    assert client.get("/api/search", params={"q": ""}, headers=AUTH).status_code == 422
    assert client.get("/api/search", params={"q": "x", "k": 51}, headers=AUTH).status_code == 422

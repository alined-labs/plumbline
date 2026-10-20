import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from plumbline.cache import CacheMiss, ResponseCache
from plumbline.core.types import CacheMode
from plumbline.retrieval.rerank import (
    COHERE_USD_PER_SEARCH,
    CohereReranker,
    TeiReranker,
    reranker_for,
)

QUERY = "How long does a landlord have to return a deposit?"
TEXTS = ["(3)(a) within 15 days", "(9) interest once a year", "(5) seven days' notice"]


def score(text: str) -> float:
    return round(1 / (1 + len(text)), 6)


def tei(calls: list[dict[str, Any]]) -> httpx.Client:
    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        ranks = [{"index": i, "score": score(t)} for i, t in enumerate(body["texts"])]
        # Like TEI, answer in score order, not input order.
        return httpx.Response(200, json=sorted(ranks, key=lambda r: -r["score"]))

    return httpx.Client(transport=httpx.MockTransport(handle))


def offline() -> httpx.Client:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise AssertionError("replay must not reach the network")

    return httpx.Client(transport=httpx.MockTransport(refuse))


def test_tei_scores_follow_the_input_order_and_replay(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    recorder = TeiReranker(
        "http://tei", ResponseCache(CacheMode.RECORD, tmp_path), client=tei(calls)
    )
    assert recorder.scores(QUERY, TEXTS) == [score(t) for t in TEXTS]
    assert calls == [{"query": QUERY, "texts": TEXTS, "raw_scores": False}]
    replayer = TeiReranker(
        "http://tei", ResponseCache(CacheMode.REPLAY, tmp_path), client=offline()
    )
    assert replayer.scores(QUERY, list(reversed(TEXTS))) == [score(t) for t in reversed(TEXTS)]


def test_tei_sends_only_the_misses_in_batches_of_32(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    reranker = TeiReranker(
        "http://tei", ResponseCache(CacheMode.RECORD, tmp_path), client=tei(calls)
    )
    reranker.scores(QUERY, TEXTS[:2])
    texts = [*TEXTS[:2], *(f"paragraph {n} of a long article" for n in range(68))]
    assert reranker.scores(QUERY, texts) == [score(t) for t in texts]
    assert [len(c["texts"]) for c in calls] == [2, 32, 32, 4]


def test_replay_without_a_recording_fails_loudly(tmp_path: Path) -> None:
    reranker = TeiReranker(
        "http://tei", ResponseCache(CacheMode.REPLAY, tmp_path), client=offline()
    )
    with pytest.raises(CacheMiss, match="no rerank recording"):
        reranker.scores(QUERY, TEXTS)


def cohere(calls: list[httpx.Request], units: float) -> httpx.Client:
    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        documents = json.loads(request.content)["documents"]
        results = [{"index": i, "relevance_score": score(d)} for i, d in enumerate(documents)]
        meta = {"billed_units": {"search_units": units}}
        return httpx.Response(200, json={"results": results[::-1], "meta": meta})

    return httpx.Client(transport=httpx.MockTransport(handle))


def test_cohere_records_scores_and_shares_the_search_cost(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []
    cache = ResponseCache(CacheMode.RECORD, tmp_path)
    reranker = CohereReranker(cache, SecretStr("test-key"), client=cohere(calls, units=1))
    assert reranker.scores(QUERY, TEXTS) == [score(t) for t in TEXTS]
    request = calls[0]
    assert request.headers["authorization"] == "Bearer test-key"
    assert json.loads(request.content) == {
        "model": "rerank-v3.5",
        "query": QUERY,
        "documents": TEXTS,
    }
    costs = [
        cache.get("rerank", {"model": "rerank-v3.5", "query": QUERY, "text": t}) for t in TEXTS
    ]
    assert sum(c.cost_usd for c in costs if c) == pytest.approx(COHERE_USD_PER_SEARCH)
    # Replay needs no key.
    replay = CohereReranker(ResponseCache(CacheMode.REPLAY, tmp_path), None, client=offline())
    assert replay.scores(QUERY, TEXTS[:1]) == [score(TEXTS[0])]


def test_cohere_without_a_key_cannot_record(tmp_path: Path) -> None:
    reranker = CohereReranker(ResponseCache(CacheMode.RECORD, tmp_path), None, client=offline())
    with pytest.raises(RuntimeError, match="COHERE_API_KEY"):
        reranker.scores(QUERY, TEXTS)


def test_the_configuration_names_the_reranker(tmp_path: Path) -> None:
    cache = ResponseCache(CacheMode.REPLAY, tmp_path)
    assert reranker_for("none", cache) is None
    assert isinstance(reranker_for("local", cache), TeiReranker)
    assert isinstance(reranker_for("cohere", cache), CohereReranker)

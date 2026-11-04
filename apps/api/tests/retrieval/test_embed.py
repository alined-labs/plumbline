import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from plumbline.cache import ResponseCache
from plumbline.core.config import load_configs
from plumbline.core.types import CacheMode
from plumbline.retrieval.embed import DIMENSIONS, TeiEmbedder, batches, query_text
from plumbline.retrieval.index import variant_key
from plumbline.settings import ROOT


def vector(text: str, dims: int = DIMENSIONS) -> list[float]:
    # A deterministic vector per text: its length, then zeros (exact in float32).
    return [float(len(text))] + [0.0] * (dims - 1)


def tei(calls: list[dict[str, Any]], dims: int = DIMENSIONS) -> httpx.Client:
    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(200, json=[vector(t, dims) for t in body["inputs"]])

    return httpx.Client(transport=httpx.MockTransport(handle))


def offline() -> httpx.Client:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise AssertionError("replay must not reach the network")

    return httpx.Client(transport=httpx.MockTransport(refuse))


def test_the_query_format_is_the_model_cards() -> None:
    assert query_text("Who pays for repairs?") == (
        "Instruct: Given a web search query, retrieve relevant passages that answer the query"
        "\nQuery:Who pays for repairs?"
    )


def test_documents_go_bare_queries_instructed_and_both_replay(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    embedder = TeiEmbedder(
        "http://tei", ResponseCache(CacheMode.RECORD, tmp_path), client=tei(calls)
    )
    docs = embedder.embed_documents(["(3)(a) within 15 days", "fianza"])
    assert [v[0] for v in docs] == [21.0, 6.0]
    question = embedder.embed_query("Who pays for repairs?")
    assert calls[0] == {
        "inputs": ["(3)(a) within 15 days", "fianza"],
        "normalize": True,
        "truncate": True,
    }
    assert calls[1]["inputs"] == [query_text("Who pays for repairs?")]
    replay = TeiEmbedder("http://tei", ResponseCache(CacheMode.REPLAY, tmp_path), client=offline())
    assert replay.embed_documents(["fianza"]) == [docs[1]]
    assert replay.embed_query("Who pays for repairs?") == question


def test_only_misses_reach_the_server_in_batches_of_32(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    embedder = TeiEmbedder(
        "http://tei", ResponseCache(CacheMode.RECORD, tmp_path), client=tei(calls)
    )
    embedder.embed_documents(["a", "b"])
    texts = ["a", "b", *(f"text {n}" for n in range(66))]
    assert len(embedder.embed_documents(texts)) == 68
    assert [len(c["inputs"]) for c in calls] == [2, 32, 32, 2]


def test_a_vector_of_the_wrong_size_is_refused(tmp_path: Path) -> None:
    embedder = TeiEmbedder(
        "http://tei", ResponseCache(CacheMode.RECORD, tmp_path), client=tei([], dims=768)
    )
    with pytest.raises(ValueError, match="1024 floats"):
        embedder.embed_documents(["fianza"])


def test_configurations_share_a_variant_when_only_search_differs() -> None:
    keys = {name: variant_key(c) for name, c in load_configs(ROOT / "evals" / "configs").items()}
    assert all(len(k) == 12 and int(k, 16) >= 0 for k in keys.values())
    assert keys["A1"] == keys["A2"] == keys["A3"]  # article chunks, no header, Qwen3
    assert keys["A4"] == keys["R1"]  # the deterministic header; the reranker is search
    assert keys["A5"] == keys["A6"]  # both headers; the rewrite is search
    distinct = {keys[n] for n in ("A0", "A2", "A4", "A5", "E1")}
    assert len(distinct) == 5  # fixed chunks, headers and the embedding model all change rows


def test_a_request_stops_at_the_token_budget_as_well_as_the_count() -> None:
    long = "palabra " * 1_500  # 1,500 tokens
    assert [len(b) for b in batches([long] * 5)] == [2, 2, 1]  # 3,000 tokens a request
    assert [len(b) for b in batches(["corto"] * 70)] == [32, 32, 6]
    huge = "palabra " * 9_000
    assert [len(b) for b in batches(["corto", huge, "corto"])] == [1, 1, 1]  # alone
    assert batches([]) == []

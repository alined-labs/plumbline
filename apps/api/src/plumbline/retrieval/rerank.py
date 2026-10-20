"""Rerankers behind one interface: the local cross-encoder, bge-reranker-v2-m3 on TEI
(configurations A3 onwards), and Cohere Rerank (configuration R1).

A cross-encoder scores each (query, text) pair on its own, so batching changes nothing,
and each pair is one recording (kind "rerank"): two configurations whose candidates
overlap share their scores. Scores are relevance in 0..1 (TEI's sigmoid of the raw logit;
Cohere's normalized score), not comparable between the two models.

Truncation: MX3's TEI caps a pair at 4,096 tokens (max_input_length, auto_truncate on)
and cuts the end of the text. Children of the article-aware chunker stay under 800 regex
tokens (at most about 1,200 model tokens), so nothing is cut in practice; a fixed A0
window is 800 regex tokens too.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from typing import Final, Literal, Protocol

import httpx
from pydantic import SecretStr

from plumbline.cache import Fresh, Json, ResponseCache, get_cache
from plumbline.settings import get_settings

TEI_BATCH: Final = 32  # TEI's --max-client-batch-size, as MX3 serves it
COHERE_URL: Final = "https://api.cohere.com/v2/rerank"
COHERE_MODEL: Final = "rerank-v3.5"
# One search unit is one query with up to 100 documents (documents over 500 tokens count
# as several). Price from third-party guides on 2026-10-19, unconfirmed: Cohere's own
# pricing page lists no pay-as-you-go rate (brain block A7).
COHERE_USD_PER_SEARCH: Final = 2.00 / 1000


class Reranker(Protocol):
    @property
    def model(self) -> str: ...

    def scores(self, query: str, texts: Sequence[str]) -> list[float]:
        """One relevance score per text, in the order given."""
        ...


@dataclass(frozen=True)
class TeiReranker:
    url: str
    cache: ResponseCache
    model: str = "BAAI/bge-reranker-v2-m3"
    client: httpx.Client | None = None  # tests pass a client with a mock transport
    timeout_s: float = 60.0

    def scores(self, query: str, texts: Sequence[str]) -> list[float]:
        requests = [
            {"model": self.model, "query": query, "text": text, "raw_scores": False}
            for text in texts
        ]
        cached = self.cache.call_batch("rerank", requests, self._call)
        return [float(c.response["score"]) for c in cached]

    def _call(self, requests: Sequence[Mapping[str, Json]]) -> list[Fresh]:
        query = str(requests[0]["query"])
        texts = [str(r["text"]) for r in requests]
        found: dict[int, float] = {}
        with _session(self.client, self.timeout_s) as client:
            for start in range(0, len(texts), TEI_BATCH):
                batch = texts[start : start + TEI_BATCH]
                body = {"query": query, "texts": batch, "raw_scores": False}
                response = client.post(f"{self.url.rstrip('/')}/rerank", json=body)
                response.raise_for_status()
                # TEI returns ranks sorted by score; "index" points back into this batch.
                for rank in response.json():
                    found[start + int(rank["index"])] = float(rank["score"])
        return [Fresh(response={"score": found[i]}) for i in range(len(texts))]


@dataclass(frozen=True)
class CohereReranker:
    cache: ResponseCache
    api_key: SecretStr | None  # needed only on a cache miss: replay runs without it
    model: str = COHERE_MODEL
    client: httpx.Client | None = None
    timeout_s: float = 60.0

    def scores(self, query: str, texts: Sequence[str]) -> list[float]:
        requests = [{"model": self.model, "query": query, "text": text} for text in texts]
        cached = self.cache.call_batch("rerank", requests, self._call)
        return [float(c.response["score"]) for c in cached]

    def _call(self, requests: Sequence[Mapping[str, Json]]) -> list[Fresh]:
        if self.api_key is None:
            raise RuntimeError("Cohere reranking needs COHERE_API_KEY to record")
        body = {
            "model": self.model,
            "query": str(requests[0]["query"]),
            "documents": [str(r["text"]) for r in requests],
        }
        headers = {"Authorization": f"Bearer {self.api_key.get_secret_value()}"}
        with _session(self.client, self.timeout_s) as client:
            response = client.post(COHERE_URL, json=body, headers=headers)
            response.raise_for_status()
            data = response.json()
        found = {int(r["index"]): float(r["relevance_score"]) for r in data["results"]}
        # The bill is per search, not per document: each pair carries its share, and the
        # search units ride along so the cost can be recomputed at a confirmed price.
        units = float(data.get("meta", {}).get("billed_units", {}).get("search_units", 1))
        share = units / len(requests)
        return [
            Fresh(
                response={"score": found[i], "search_units": share},
                cost_usd=share * COHERE_USD_PER_SEARCH,
            )
            for i in range(len(requests))
        ]


def reranker_for(
    kind: Literal["none", "local", "cohere"], cache: ResponseCache | None = None
) -> Reranker | None:
    """The reranker a configuration's `retrieval.rerank` names, wired from the settings."""
    if kind == "none":
        return None
    settings = get_settings()
    cache = cache or get_cache()
    if kind == "local":
        return TeiReranker(settings.rerank_url, cache, settings.rerank_model)
    return CohereReranker(cache, settings.cohere_api_key)


def _session(client: httpx.Client | None, timeout_s: float) -> AbstractContextManager[httpx.Client]:
    # A client the caller passed stays open; one made here closes after the call.
    return nullcontext(client) if client is not None else httpx.Client(timeout=timeout_s)

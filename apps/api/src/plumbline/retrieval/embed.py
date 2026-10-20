"""Embeddings: a TEI client for Qwen3-Embedding-0.6B (configurations A0 to A6).

Queries carry the model card's instruction, in its exact format, and documents carry none,
as the card prescribes. The task description is the card's own example; the card reports
that a task-specific English instruction gains 1% to 5%, and since only queries carry it,
trying one costs re-embedding the questions alone.

Every call goes through the cache (kind "embed"), one recording per text with its vector
packed by encode_vector; only texts without a recording reach the server, 32 to a
request (TEI's --max-client-batch-size as MX3 serves it).

Truncation: MX3's TEI caps an input at 4,096 tokens and cuts the end of a longer one. The
texts embedded here are the dense leg's: chunker leaves (under 800 regex tokens, at most
about 1,200 model tokens) and A0's 800-token windows, so nothing is cut in practice. A
whole parent article can be longer, one more reason the dense leg searches leaves only
(proposed to Lane D for D4: such parents keep no vector).

Speed: on MX3's CPU (TEI 1.9.4, float32) the server embeds about 50 tokens a second
(measured 2026-10-20: 1, 8 and 32 texts of 82 tokens at 61, 55 and 45 tokens/s). A first
recording of a variant takes roughly an hour per 200,000 tokens; replays are free.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from typing import Final

import httpx

from plumbline.cache import Fresh, Json, ResponseCache, decode_vector, encode_vector

DIMENSIONS: Final = 1024
TEI_BATCH: Final = 32
# Qwen3-Embedding's model card: queries are f'Instruct: {task_description}\nQuery:{query}',
# with no space after "Query:", and this is its example task description.
QUERY_TASK: Final = "Given a web search query, retrieve relevant passages that answer the query"


def query_text(question: str) -> str:
    return f"Instruct: {QUERY_TASK}\nQuery:{question}"


@dataclass(frozen=True)
class TeiEmbedder:
    url: str
    cache: ResponseCache
    model: str = "Qwen/Qwen3-Embedding-0.6B"
    client: httpx.Client | None = None  # tests pass a client with a mock transport
    timeout_s: float = 600.0

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """One unit vector per text, in order, with no instruction."""
        return self._embed(texts)

    def embed_query(self, question: str) -> list[float]:
        return self._embed([query_text(question)])[0]

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        requests = [
            {"model": self.model, "input": text, "normalize": True, "truncate": True}
            for text in texts
        ]
        cached = self.cache.call_batch("embed", requests, self._call)
        return [decode_vector(str(c.response["vector"])) for c in cached]

    def _call(self, requests: Sequence[Mapping[str, Json]]) -> list[Fresh]:
        texts = [str(r["input"]) for r in requests]
        vectors: list[list[float]] = []
        session: AbstractContextManager[httpx.Client] = (
            nullcontext(self.client)
            if self.client is not None
            else httpx.Client(timeout=self.timeout_s)
        )
        with session as client:
            for start in range(0, len(texts), TEI_BATCH):
                body = {
                    "inputs": texts[start : start + TEI_BATCH],
                    "normalize": True,
                    "truncate": True,
                }
                response = client.post(f"{self.url.rstrip('/')}/embed", json=body)
                response.raise_for_status()
                vectors += response.json()
        if len(vectors) != len(texts) or any(len(v) != DIMENSIONS for v in vectors):
            raise ValueError(
                f"expected {len(texts)} vectors of {DIMENSIONS} floats from {self.model}"
            )
        return [Fresh(response={"vector": encode_vector(v)}) for v in vectors]

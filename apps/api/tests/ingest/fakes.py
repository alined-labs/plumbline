"""Stand-ins for the model servers, for the tests of the index stage."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from plumbline.ingest.index import EMBEDDING_DIM


class FakeEmbedder:
    """Deterministic one-hot vectors, and a record of what it was asked."""

    def __init__(self, fail: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.fail = fail

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if self.fail:
            raise ConnectionError("the embedding server is down")
        self.calls.append(list(texts))
        out = []
        for text_ in texts:
            at = int.from_bytes(hashlib.sha256(text_.encode()).digest()[:4], "big") % EMBEDDING_DIM
            out.append([1.0 if i == at else 0.0 for i in range(EMBEDDING_DIM)])
        return out

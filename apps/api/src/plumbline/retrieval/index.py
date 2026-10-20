"""The index's variants: one table holds several chunk sets, one per variant.

A variant is what changes a chunk row's content: the chunker settings (which cut the
text), the headers setting (which builds text_for_search) and the embedding model (which
makes the vector). Retrieval settings such as merge_parent, rrf_k or the reranker change
how rows are searched, not what they hold, so configurations that differ only there share
a variant: A1, A2 and A3 index the same rows, and so do A4 and R1.
"""

from __future__ import annotations

import hashlib

from plumbline.cache import canonical_json
from plumbline.core.config import EvalConfig


def variant_key(config: EvalConfig) -> str:
    """The first 12 hex digits of the sha256 of the variant's canonical JSON (agreed with
    Lane D for migration 0004)."""
    variant = {
        "chunker": config.chunker.model_dump(mode="json", exclude={"merge_parent"}),
        "headers": config.retrieval.headers,
        "embedding_model": config.retrieval.embedding_model,
    }
    return hashlib.sha256(canonical_json(variant).encode("utf-8")).hexdigest()[:12]

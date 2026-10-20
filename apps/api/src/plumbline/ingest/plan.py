"""What the index stage writes (Lane D, task D4): for each variant of the configurations
asked for and each parsed source, the chunks, which of them get a vector, and a hash of
exactly that content.

Configurations that differ only in how they search (A1, A2 and A3; A4 and R1) share a
variant, so they share rows: a unit is one source in one variant. Chunking is cheap and
deterministic, so planning does it up front; embedding is the slow part, and happens in
the job.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from plumbline.chunking.chunker import chunk_document
from plumbline.core.config import EvalConfig
from plumbline.core.types import Chunk, ParsedDocument
from plumbline.corpus.manifest import Source
from plumbline.ingest.laws import law_name
from plumbline.retrieval.index import variant_key


class UnsupportedConfig(ValueError):
    """A configuration the index stage cannot build yet."""


@dataclass(frozen=True)
class Unit:
    """One source in one variant: what a job writes."""

    source: Source
    document: ParsedDocument
    config: EvalConfig  # the first of the configurations that share the variant
    configs: tuple[str, ...]  # the names of all of them
    variant: str
    chunks: tuple[Chunk, ...]
    embedded: tuple[Chunk, ...]  # the chunks that get a vector
    content_hash: str

    @property
    def embedding_model(self) -> str:
        return self.config.retrieval.embedding_model


def leaves(chunks: Sequence[Chunk]) -> tuple[Chunk, ...]:
    """The chunks no other chunk names as its parent: what the dense leg searches."""
    parents = {chunk.parent_id for chunk in chunks if chunk.parent_id}
    return tuple(chunk for chunk in chunks if chunk.id not in parents)


def plan_unit(
    source: Source, document: ParsedDocument, config: EvalConfig, configs: Sequence[str]
) -> Unit:
    if config.retrieval.headers in {"llm", "both"}:
        raise UnsupportedConfig(
            f"{config.name} asks for LLM headers, which the chunker takes after A10's "
            "headers are written; index the configurations without them for now"
        )
    chunks = tuple(
        chunk_document(
            document,
            config.chunker,
            law_name=law_name(source.law),
            headers=config.retrieval.headers,
        )
    )
    embedded = leaves(chunks)
    variant = variant_key(config)
    return Unit(
        source=source,
        document=document,
        config=config,
        configs=tuple(configs),
        variant=variant,
        chunks=chunks,
        embedded=embedded,
        content_hash=_content_hash(document, variant, config.retrieval.embedding_model, chunks),
    )


def plan_units(
    sources: Sequence[Source],
    documents: Mapping[str, ParsedDocument],
    configs: Sequence[EvalConfig],
) -> list[Unit]:
    """A unit per parsed source and variant, sources in manifest order."""
    by_variant: dict[str, list[EvalConfig]] = {}
    for config in configs:
        by_variant.setdefault(variant_key(config), []).append(config)
    return [
        plan_unit(source, documents[source.id], group[0], [c.name for c in group])
        for group in by_variant.values()
        for source in sources
        if source.id in documents
    ]


def _content_hash(
    document: ParsedDocument, variant: str, embedding_model: str, chunks: Sequence[Chunk]
) -> str:
    """Everything a job writes: the source's text, the variant, the model and every field
    of every chunk, so a changed chunker, parser or header makes a new job."""
    digest = hashlib.sha256()
    for part in (document.sha256, document.parser, variant, embedding_model):
        digest.update(part.encode())
        digest.update(b"\x1f")
    for chunk in chunks:
        digest.update(chunk.model_dump_json().encode())
        digest.update(b"\x1e")
    return digest.hexdigest()

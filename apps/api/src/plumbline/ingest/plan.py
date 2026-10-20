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


@dataclass(frozen=True)
class Unplanned:
    """A source the chunker could not read in a variant, and why."""

    source: Source
    configs: tuple[str, ...]
    error: str


def plan_all(
    sources: Sequence[Source],
    documents: Mapping[str, ParsedDocument],
    configs: Sequence[EvalConfig],
) -> tuple[list[Unit], list[Unplanned]]:
    """A unit per parsed source and variant, sources in manifest order, and the ones that
    could not be planned. One source the chunker cannot read must not stop the others, and
    a source that chunks in one variant but not another still gets the one that works."""
    by_variant: dict[str, list[EvalConfig]] = {}
    for config in configs:
        by_variant.setdefault(variant_key(config), []).append(config)
    units: list[Unit] = []
    unplanned: list[Unplanned] = []
    for group in by_variant.values():
        names = [c.name for c in group]
        for source in sources:
            if source.id not in documents:
                continue
            try:
                units.append(plan_unit(source, documents[source.id], group[0], names))
            except UnsupportedConfig:
                raise  # a configuration the caller asked for that cannot be built yet
            except ValueError as exc:
                unplanned.append(Unplanned(source, tuple(names), str(exc)))
    return units, unplanned


def plan_units(
    sources: Sequence[Source],
    documents: Mapping[str, ParsedDocument],
    configs: Sequence[EvalConfig],
) -> list[Unit]:
    """plan_all for a caller that wants every unit or an error."""
    units, unplanned = plan_all(sources, documents, configs)
    if unplanned:
        raise ValueError(f"{unplanned[0].source.id}: {unplanned[0].error}")
    return units


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

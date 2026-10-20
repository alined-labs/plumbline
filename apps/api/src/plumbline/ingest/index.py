"""Writing a parsed, chunked and embedded statute into Postgres (Lane D, task D4).

One call writes one document's chunks for one variant (Lane A's variant_key: the chunker,
the header mode and the embedding model), in one transaction: the document's row, then
its chunks with their vectors, replacing that variant's earlier chunks of the document.
Other variants of the same document stay as they are. Articles go in before their
paragraphs, which the parent key requires.

A chunk may have no vector: the dense leg searches leaves only (paragraphs, and articles
without them), and a parent whose paragraphs are all embedded stays searchable by BM25
alone, so its vector would cost embedding time (about 50 tokens a second on CPU) for
nothing.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import delete, func, insert, select
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.core.types import Chunk, ParsedDocument
from plumbline.db.models import EMBEDDING_DIM, PUBLIC_TENANT, ChunkRow, Document
from plumbline.db.session import tenant_session


class Embedder(Protocol):
    """What indexing needs from Lane A's embedder: document vectors, in order."""

    model: str

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...


class IndexingError(ValueError):
    """The chunks or vectors do not belong to the document they are written for."""


@dataclass(frozen=True)
class Indexed:
    source_id: str
    variant: str
    chunks: int
    articles: int  # chunks with no parent: whole articles or sections


async def index_document(
    sessions: async_sessionmaker[AsyncSession],
    document: ParsedDocument,
    chunks: Sequence[Chunk],
    vectors: Sequence[Sequence[float] | None],
    *,
    variant: str,
    tenant_id: uuid.UUID = PUBLIC_TENANT,
) -> Indexed:
    if len(vectors) != len(chunks):
        raise IndexingError(f"{len(chunks)} chunks but {len(vectors)} vectors")
    if any(vector is not None and len(vector) != EMBEDDING_DIM for vector in vectors):
        raise IndexingError(f"every vector must have {EMBEDDING_DIM} dimensions")
    strangers = {c.document_id for c in chunks} - {document.source_id}
    if strangers:
        raise IndexingError(f"chunks of other documents: {', '.join(sorted(strangers))}")
    rows = [
        _row(chunk, None if vector is None else list(vector), variant, tenant_id)
        for chunk, vector in sorted(
            zip(chunks, vectors, strict=True), key=lambda pair: pair[0].parent_id is not None
        )
    ]
    async with tenant_session(sessions, tenant_id) as session:
        values = {
            "tenant_id": tenant_id,
            "law": document.law,
            "jurisdiction": document.jurisdiction.value,
            "language": document.language.value,
            "edition": document.edition,
            "sha256": document.sha256,
            "parser": document.parser,
            "page_count": len(document.pages),
        }
        await session.execute(
            upsert(Document)
            .values(id=document.source_id, **values)
            .on_conflict_do_update(index_elements=[Document.id], set_=values)
        )
        await session.execute(
            delete(ChunkRow).where(
                ChunkRow.variant == variant, ChunkRow.document_id == document.source_id
            )
        )
        if rows:
            await session.execute(insert(ChunkRow), rows)
    return Indexed(
        source_id=document.source_id,
        variant=variant,
        chunks=len(rows),
        articles=sum(1 for c in chunks if c.parent_id is None),
    )


async def stored_counts(
    sessions: async_sessionmaker[AsyncSession],
    variant: str,
    document_id: str,
    tenant_id: uuid.UUID = PUBLIC_TENANT,
) -> tuple[int, int]:
    """How many chunks, and how many of them with a vector, the index holds for one
    document in one variant."""
    async with tenant_session(sessions, tenant_id) as session:
        row = (
            await session.execute(
                select(func.count(), func.count(ChunkRow.embedding)).where(
                    ChunkRow.variant == variant, ChunkRow.document_id == document_id
                )
            )
        ).one()
    return int(row[0]), int(row[1])


def _row(
    chunk: Chunk, vector: list[float] | None, variant: str, tenant_id: uuid.UUID
) -> dict[str, object]:
    return {
        "variant": variant,
        "id": chunk.id,
        "tenant_id": tenant_id,
        "document_id": chunk.document_id,
        "parent_id": chunk.parent_id,
        "jurisdiction": chunk.jurisdiction.value,
        "law": chunk.law,
        "language": chunk.language.value,
        "edition": chunk.edition,
        "article": chunk.article,
        "path": list(chunk.path),
        "label": chunk.label,
        "heading": chunk.heading,
        "text": chunk.text,
        "text_for_search": chunk.text_for_search,
        "context_header": chunk.context_header,
        "context_header_llm": chunk.context_header_llm,
        "effective_from": chunk.effective_from,
        "effective_to": chunk.effective_to,
        "status": chunk.status.value,
        "validity_note": chunk.validity_note,
        "history": chunk.history,
        "page": chunk.page,
        "metadata_": dict(chunk.metadata),
        "embedding": vector,
    }

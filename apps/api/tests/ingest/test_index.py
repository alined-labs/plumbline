"""Writing a document's chunks and vectors: one transaction per document and variant,
replacing that variant's earlier chunks, and searchable by both indexes at once."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.core.types import (
    Chunk,
    Jurisdiction,
    Language,
    ParsedDocument,
    ParsedPage,
    ParseMethod,
)
from plumbline.db import make_engine, make_sessionmaker
from plumbline.db.models import EMBEDDING_DIM, PUBLIC_TENANT, ChunkRow
from plumbline.db.session import tenant_session
from plumbline.ingest.index import IndexingError, index_document, stored_counts

pytestmark = [pytest.mark.db, pytest.mark.anyio]
Sessions = async_sessionmaker[AsyncSession]


@pytest.fixture
async def sessions(database_url: str) -> AsyncIterator[Sessions]:
    engine = make_engine(database_url)
    yield make_sessionmaker(engine)
    await engine.dispose()


def _document(source_id: str) -> ParsedDocument:
    return ParsedDocument(
        source_id=source_id,
        law="fl-stat-83",
        jurisdiction=Jurisdiction.FLORIDA,
        language=Language.EN,
        edition="2026",
        sha256="0" * 64,
        parser="plumbline html 3",
        pages=[ParsedPage(number=1, method=ParseMethod.HTML, markdown="83.49 Deposit money.")],
    )


def _chunks(source_id: str) -> list[Chunk]:
    common = {
        "document_id": source_id,
        "jurisdiction": Jurisdiction.FLORIDA,
        "law": "fl-stat-83",
        "language": Language.EN,
        "edition": "2026",
        "article": "83.49",
    }
    article = "83.49 Deposit money or advance rent; duty of landlord and tenant."
    paragraph = "(3)(a) The landlord shall return the security deposit within 15 days."
    # The paragraph comes first: indexing must still write its article before it.
    return [
        Chunk(
            id=f"{source_id}:p3",
            parent_id=f"{source_id}:a",
            path=["(3)"],
            label="Fla. Stat. § 83.49(3)",
            text=paragraph,
            text_for_search=paragraph,
            **common,
        ),
        Chunk(
            id=f"{source_id}:a",
            label="Fla. Stat. § 83.49",
            text=article,
            text_for_search=article,
            metadata={"history": True},
            **common,
        ),
    ]


def _vector(seed: int) -> list[float]:
    return [1.0 if i == seed else 0.0 for i in range(EMBEDDING_DIM)]


async def _count(sessions: Sessions, source_id: str, variant: str | None = None) -> int:
    query = select(func.count()).select_from(ChunkRow).where(ChunkRow.document_id == source_id)
    if variant:
        query = query.where(ChunkRow.variant == variant)
    async with tenant_session(sessions, PUBLIC_TENANT) as session:
        return int(await session.scalar(query) or 0)


async def test_a_document_is_written_whole_and_replaced_not_doubled(sessions: Sessions) -> None:
    source_id = f"fl-{uuid.uuid4().hex[:8]}"
    chunks = _chunks(source_id)
    indexed = await index_document(
        sessions, _document(source_id), chunks, [_vector(1), _vector(2)], variant="v1"
    )
    assert (indexed.chunks, indexed.articles) == (2, 1)
    await index_document(
        sessions, _document(source_id), chunks, [_vector(1), _vector(2)], variant="v1"
    )
    await index_document(
        sessions, _document(source_id), chunks, [_vector(3), _vector(4)], variant="v2"
    )
    assert (await _count(sessions, source_id, "v1"), await _count(sessions, source_id)) == (2, 4)


async def test_a_parent_may_have_no_vector(sessions: Sessions) -> None:
    source_id = f"fl-{uuid.uuid4().hex[:8]}"
    await index_document(
        sessions, _document(source_id), _chunks(source_id), [_vector(1), None], variant="v"
    )
    assert await stored_counts(sessions, "v", source_id) == (2, 1)  # the paragraph only


async def test_the_written_chunks_are_found_by_both_indexes(sessions: Sessions) -> None:
    source_id = f"fl-{uuid.uuid4().hex[:8]}"
    variant = uuid.uuid4().hex[:12]
    await index_document(
        sessions,
        _document(source_id),
        _chunks(source_id),
        [_vector(7), _vector(8)],
        variant=variant,
    )
    async with tenant_session(sessions, PUBLIC_TENANT) as session:
        nearest = await session.scalar(
            select(ChunkRow.id)
            .where(ChunkRow.variant == variant)
            .order_by(ChunkRow.embedding.cosine_distance(_vector(7)))
            .limit(1)
        )
        keyword = await session.scalars(
            text(
                "SELECT id FROM chunks WHERE (CASE WHEN language = 'en' THEN text_for_search END)"
                "::pdb.alias('search_en') ||| 'security' AND variant = :variant"
            ),
            {"variant": variant},
        )
        exact = await session.scalars(
            select(ChunkRow.id).where(
                ChunkRow.variant == variant,
                ChunkRow.jurisdiction == "florida",
                ChunkRow.law == "fl-stat-83",
                ChunkRow.article == "83.49",
                ChunkRow.edition == "2026",
            )
        )
        row = await session.get_one(ChunkRow, (variant, f"{source_id}:a"))
    assert nearest == f"{source_id}:p3"
    assert list(keyword) == [f"{source_id}:p3"]
    assert set(exact) == {f"{source_id}:a", f"{source_id}:p3"}
    assert row.metadata_ == {"history": True}


@pytest.mark.parametrize(
    ("vectors", "error"),
    [([_vector(1)], "2 chunks but 1 vectors"), ([[0.0] * 3, _vector(1)], "1024 dimensions")],
)
async def test_vectors_that_do_not_fit_are_refused(
    sessions: Sessions, vectors: list[list[float]], error: str
) -> None:
    with pytest.raises(IndexingError, match=error):
        await index_document(sessions, _document("fl"), _chunks("fl"), vectors, variant="v")


async def test_chunks_of_another_document_are_refused(sessions: Sessions) -> None:
    with pytest.raises(IndexingError, match="chunks of other documents: other"):
        await index_document(
            sessions, _document("fl"), _chunks("other"), [_vector(1), _vector(2)], variant="v"
        )

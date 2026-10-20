"""The whole law from the index, for the long-context baseline (LC).

One SQL query reads every article-level chunk (no parent) of the jurisdictions asked for,
from the chunk set LC's chunker built (its variant: retrieval.index.variant_key of the LC
configuration, which LC shares with A1 and A2). The as-of filter and the order are applied
here, on a few hundred rows: an article is kept when Chunk.in_force_on the date, and
without a date when it is in force today, so the model never reads two versions of one
article side by side. The order is the law's own: by law, then by article, each number
compared as a number (Florida's 83.425 between 83.42 and 83.43; "9", "9 bis", then "10").
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from plumbline.core.types import Chunk, Jurisdiction, Language, ProvisionStatus
from plumbline.db.models import PUBLIC_TENANT, ChunkRow
from plumbline.db.session import tenant_session_sync

Key = tuple[tuple[str, Decimal], ...]


class SqlLawSource:
    """generation.pipeline.LawSource over Lane D's chunks table."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        variant: str,
        tenant_id: uuid.UUID = PUBLIC_TENANT,
    ) -> None:
        self.sessions = sessions
        self.variant = variant
        self.tenant_id = tenant_id

    def articles(
        self, jurisdictions: Sequence[Jurisdiction] | None, as_of: date | None
    ) -> list[Chunk]:
        query = select(ChunkRow).where(
            ChunkRow.variant == self.variant, ChunkRow.parent_id.is_(None)
        )
        if jurisdictions is not None:
            query = query.where(ChunkRow.jurisdiction.in_([j.value for j in jurisdictions]))
        with tenant_session_sync(self.sessions, self.tenant_id) as session:
            chunks = [to_chunk(row) for row in session.scalars(query)]
        day = as_of or datetime.now(UTC).date()
        return sorted((c for c in chunks if c.in_force_on(day)), key=law_order)

    def jurisdictions(self) -> frozenset[Jurisdiction]:
        """The jurisdictions this variant holds: the pipeline's `indexed`."""
        query = select(ChunkRow.jurisdiction).where(ChunkRow.variant == self.variant).distinct()
        with tenant_session_sync(self.sessions, self.tenant_id) as session:
            return frozenset(Jurisdiction(value) for value in session.scalars(query))


def to_chunk(row: ChunkRow) -> Chunk:
    return Chunk(
        id=row.id,
        document_id=row.document_id,
        parent_id=row.parent_id,
        jurisdiction=Jurisdiction(row.jurisdiction),
        law=row.law,
        language=Language(row.language),
        edition=row.edition,
        article=row.article,
        path=list(row.path),
        label=row.label,
        heading=row.heading,
        text=row.text,
        text_for_search=row.text_for_search,
        context_header=row.context_header,
        context_header_llm=row.context_header_llm,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        status=ProvisionStatus(row.status),
        validity_note=row.validity_note,
        history=row.history,
        page=row.page,
        metadata=row.metadata_,
    )


def law_order(chunk: Chunk) -> tuple[str, Key, Key, str]:
    """Laws by their numbers too: chapter 83 before chapter 718."""
    return (chunk.jurisdiction.value, article_key(chunk.law), article_key(chunk.article), chunk.id)


def article_key(article: str) -> Key:
    """An article number as (text, number) pairs. Numbers are decimals because Florida's
    are: s. 83.425 was inserted between ss. 83.42 and 83.43."""
    parts = re.split(r"(\d+(?:\.\d+)?)", article)
    parts.append("-1")  # pairs up the trailing text; real numbers are never negative
    return tuple((parts[i], Decimal(parts[i + 1])) for i in range(0, len(parts) - 1, 2))

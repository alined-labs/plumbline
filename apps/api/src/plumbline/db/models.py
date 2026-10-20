"""SQLAlchemy models of the schema in migrations/versions/0002_schema.py. The migration is
the source of truth (it also holds the checks and the row-level security policies);
tests/db/test_models.py fails when these models and the migrated database disagree."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, ClassVar, Final

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    Double,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import text as sql  # chunks has a column named text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIM: Final = 1024  # Qwen3-Embedding-0.6B
PUBLIC_TENANT: Final = uuid.UUID("00000000-0000-0000-0000-000000000000")

Json = dict[str, Any]
TextList = list[str]


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        str: Text(),
        int: Integer(),
        float: Double(),
        bool: Boolean(),
        date: Date(),
        datetime: DateTime(timezone=True),
        uuid.UUID: Uuid(),
        Json: JSONB(),
        TextList: ARRAY(Text()),
    }


def _now() -> Mapped[datetime]:
    return mapped_column(server_default=func.now())


def _tenant() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    slug: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    created_at: Mapped[datetime] = _now()


class Document(Base):
    """One parsed source: a statute edition from the manifest (or, later, an upload)."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(primary_key=True)  # the manifest's source id
    tenant_id: Mapped[uuid.UUID] = _tenant()
    law: Mapped[str]
    jurisdiction: Mapped[str]
    language: Mapped[str]
    edition: Mapped[str]
    sha256: Mapped[str]
    parser: Mapped[str]
    page_count: Mapped[int]
    metadata_: Mapped[Json] = mapped_column("metadata", server_default=sql("'{}'"))
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class ChunkRow(Base):
    """plumbline.core.types.Chunk, stored, with its embedding, in one chunk set (variant).
    The BM25 index of migration 0004 is not declared here: SQLAlchemy cannot express it."""

    __tablename__ = "chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["variant", "parent_id"],
            ["chunks.variant", "chunks.id"],
            ondelete="CASCADE",
            name="chunks_parent_fkey",
        ),
        UniqueConstraint("key", name="uq_chunks_key"),
        Index("ix_chunks_parent", "variant", "parent_id"),
        Index("ix_chunks_article_ref", "variant", "jurisdiction", "law", "article", "edition"),
    )

    variant: Mapped[str] = mapped_column(primary_key=True)  # Lane A's variant_key(config)
    id: Mapped[str] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(Computed("variant || ':' || id", persisted=True))
    tenant_id: Mapped[uuid.UUID] = _tenant()
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[str | None]
    jurisdiction: Mapped[str]
    law: Mapped[str]
    language: Mapped[str]
    edition: Mapped[str]
    article: Mapped[str]
    path: Mapped[TextList] = mapped_column(server_default=sql("'{}'"))
    label: Mapped[str]
    heading: Mapped[str | None]
    text: Mapped[str]
    text_for_search: Mapped[str]
    context_header: Mapped[str] = mapped_column(server_default=sql("''"))
    context_header_llm: Mapped[str | None]
    effective_from: Mapped[date | None]
    effective_to: Mapped[date | None]
    status: Mapped[str] = mapped_column(server_default=sql("'in_force'"))
    validity_note: Mapped[str | None]
    history: Mapped[str | None]
    page: Mapped[int | None]
    metadata_: Mapped[Json] = mapped_column("metadata", server_default=sql("'{}'"))
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR(EMBEDDING_DIM))
    created_at: Mapped[datetime] = _now()


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "kind", "content_hash", name="uq_ingestion_jobs_input"),
        Index("ix_ingestion_jobs_queued", "created_at", postgresql_where=sql("status = 'queued'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    kind: Mapped[str]
    source_id: Mapped[str]
    content_hash: Mapped[str]
    status: Mapped[str] = mapped_column(server_default=sql("'queued'"))
    attempts: Mapped[int] = mapped_column(server_default=sql("0"))
    payload: Mapped[Json] = mapped_column(server_default=sql("'{}'"))
    result: Mapped[Json | None]
    error: Mapped[str | None]
    worker: Mapped[str | None]
    created_at: Mapped[datetime] = _now()
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]


class IngestionJobEvent(Base):
    """One step of a job, appended as it happens: what its event stream sends."""

    __tablename__ = "ingestion_job_events"
    __table_args__ = (Index("ix_ingestion_job_events_job_id_id", "job_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion_jobs.id", ondelete="CASCADE"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    kind: Mapped[str]
    message: Mapped[str] = mapped_column(server_default=sql("''"))
    data: Mapped[Json] = mapped_column(server_default=sql("'{}'"))
    created_at: Mapped[datetime] = _now()


class QueryRow(Base):
    """One answered (or failed) request to /api/ask."""

    __tablename__ = "queries"
    __table_args__ = (Index("ix_queries_tenant_id_created_at", "tenant_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    request_id: Mapped[str] = mapped_column(unique=True)
    question: Mapped[str]
    as_of: Mapped[date | None]
    jurisdictions: Mapped[TextList] = mapped_column(server_default=sql("'{}'"))
    tier: Mapped[str]
    status: Mapped[str | None]
    route: Mapped[str | None]
    model: Mapped[str | None]
    config_name: Mapped[str | None]
    config_hash: Mapped[str | None]
    latency_ms: Mapped[float | None]
    input_tokens: Mapped[int] = mapped_column(server_default=sql("0"))
    output_tokens: Mapped[int] = mapped_column(server_default=sql("0"))
    cost_usd: Mapped[float] = mapped_column(server_default=sql("0"))
    cached: Mapped[bool] = mapped_column(server_default=sql("false"))
    trace_url: Mapped[str | None]
    error: Mapped[str | None]
    answer: Mapped[Json | None]
    trace: Mapped[Json | None]
    created_at: Mapped[datetime] = _now()


class EvalRunRow(Base):
    """rag_eval.schema.EvalRun without its results."""

    __tablename__ = "eval_runs"

    run_id: Mapped[str] = mapped_column(primary_key=True)
    schema_version: Mapped[int]
    config_name: Mapped[str]
    config_hash: Mapped[str]
    git_sha: Mapped[str]
    golden_file: Mapped[str]
    split: Mapped[str]
    judged: Mapped[bool]
    n_items: Mapped[int]
    summary: Mapped[Json] = mapped_column(server_default=sql("'{}'"))
    notes: Mapped[str | None]
    created_at: Mapped[datetime]


class EvalResultRow(Base):
    """rag_eval.schema.EvalResult, one per run and golden item."""

    __tablename__ = "eval_results"

    run_id: Mapped[str] = mapped_column(
        ForeignKey("eval_runs.run_id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[str] = mapped_column(primary_key=True)
    retrieved: Mapped[list[Json]] = mapped_column(JSONB(), server_default=sql("'[]'"))
    status: Mapped[str | None]
    answer: Mapped[str | None]
    cited: Mapped[TextList] = mapped_column(server_default=sql("'{}'"))
    invalid_citations: Mapped[int] = mapped_column(server_default=sql("0"))
    metrics: Mapped[Json] = mapped_column(server_default=sql("'{}'"))
    latency_ms: Mapped[float | None]
    cost_usd: Mapped[float | None]
    trace_id: Mapped[str | None]
    error: Mapped[str | None]


class Setting(Base):
    """A runtime switch, such as the demo tier, changed without a redeploy."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB())
    updated_at: Mapped[datetime] = _now()

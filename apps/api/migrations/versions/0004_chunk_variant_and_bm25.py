"""Chunk variants and the BM25 index, as agreed with Lane A (task A4).

One table holds several chunk sets: the chunker, its header mode and the embedding model
all change a chunk's text_for_search or its vector, though not always its id. So a chunk
is keyed by (variant, id), where Lane A's variant_key(config) is the first 12 hex of the
sha256 over those settings, and every query names its variant.

The BM25 index (pg_search) has one field per language, each holding only that language's
rows, so English and Spanish never share document frequencies; unicode_words keeps
"83.49" as one token, which the simple tokenizer splits. Its key is the unique `key`
column, as pg_search needs one unique column; variant, jurisdiction and language are
literal fields, so filters on them are pushed into the index.

The chunks table is empty until the first ingest (task D4), so the new NOT NULL column
needs no default. Downgrading deletes every chunk: the old key cannot hold one chunk in
several variants, and chunks are derived data that make ingest rebuilds.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _field(language: str, stemmer: str) -> str:
    return (
        f"((CASE WHEN language = '{language}' THEN text_for_search END)::pdb.unicode_words("
        f"'stemmer={stemmer}', 'ascii_folding=true', 'alias=search_{language}'))"
    )


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE chunks DROP CONSTRAINT chunks_parent_id_fkey;
        ALTER TABLE chunks DROP CONSTRAINT chunks_pkey;
        DROP INDEX ix_chunks_parent_id;
        DROP INDEX ix_chunks_article_ref;
        ALTER TABLE chunks ADD COLUMN variant text NOT NULL;
        ALTER TABLE chunks ADD PRIMARY KEY (variant, id);
        ALTER TABLE chunks ADD CONSTRAINT chunks_parent_fkey FOREIGN KEY (variant, parent_id)
            REFERENCES chunks (variant, id) ON DELETE CASCADE;
        ALTER TABLE chunks ADD COLUMN key text GENERATED ALWAYS AS (variant || ':' || id) STORED;
        ALTER TABLE chunks ADD CONSTRAINT uq_chunks_key UNIQUE (key);
        CREATE INDEX ix_chunks_parent ON chunks (variant, parent_id);
        -- An exact article reference finds its chunks within one variant.
        CREATE INDEX ix_chunks_article_ref ON chunks (variant, jurisdiction, law, article, edition);
        CREATE INDEX chunks_bm25 ON chunks USING bm25 (
            key,
            {_field("en", "english")},
            {_field("es", "spanish")},
            (variant::pdb.literal),
            (jurisdiction::pdb.literal),
            (language::pdb.literal)
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM chunks;
        DROP INDEX chunks_bm25;
        DROP INDEX ix_chunks_article_ref;
        DROP INDEX ix_chunks_parent;
        ALTER TABLE chunks DROP CONSTRAINT uq_chunks_key;
        ALTER TABLE chunks DROP COLUMN key;
        ALTER TABLE chunks DROP CONSTRAINT chunks_parent_fkey;
        ALTER TABLE chunks DROP CONSTRAINT chunks_pkey;
        ALTER TABLE chunks DROP COLUMN variant;
        ALTER TABLE chunks ADD PRIMARY KEY (id);
        ALTER TABLE chunks ADD CONSTRAINT chunks_parent_id_fkey FOREIGN KEY (parent_id)
            REFERENCES chunks (id) ON DELETE CASCADE;
        CREATE INDEX ix_chunks_parent_id ON chunks (parent_id);
        CREATE INDEX ix_chunks_article_ref ON chunks (jurisdiction, law, article, edition);
        """
    )

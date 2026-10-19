"""The schema: tenants, documents, chunks, ingestion jobs, queries, evaluation runs and
settings, with row-level security on tenant_id from the start.

Isolation works like this. The application never queries as the table owner (a superuser
bypasses row-level security, and FORCE below covers an owner that is not one): at the
start of each transaction it runs SET LOCAL ROLE plumbline_app and sets app.tenant_id
with set_config(..., true). The policies then show a tenant its own rows plus the public
corpus (the statutes, owned by the fixed public tenant), and let it write only its own
rows. With app.tenant_id unset, current_tenant() is NULL, so a forgotten setting reads
only the public corpus and writes nothing.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PUBLIC_TENANT = "00000000-0000-0000-0000-000000000000"
# The enumerations of plumbline.core.types, written out: a migration must not change when
# the code does. tests/db/test_schema.py checks that they still agree.
JURISDICTIONS = "('dubai', 'spain', 'colombia', 'florida')"
LANGUAGES = "('en', 'es')"
PROVISION_STATUSES = "('in_force', 'repealed', 'struck_down')"
JOB_STATUSES = "('queued', 'running', 'succeeded', 'failed')"
TIERS = "('full', 'free', 'static')"
ANSWER_STATUSES = "('answered', 'partial', 'abstained')"
TENANT_TABLES = ("documents", "chunks", "ingestion_jobs", "queries")
SHARED_TABLES = ("documents", "chunks")  # the public tenant's rows are readable by every tenant

UPGRADE = f"""
CREATE TABLE tenants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug text NOT NULL UNIQUE,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO tenants (id, slug, name) VALUES ('{PUBLIC_TENANT}', 'public', 'Public corpus');

CREATE TABLE documents (
    id text PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    law text NOT NULL,
    jurisdiction text NOT NULL CHECK (jurisdiction IN {JURISDICTIONS}),
    language text NOT NULL CHECK (language IN {LANGUAGES}),
    edition text NOT NULL,
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{{64}}$'),
    parser text NOT NULL,
    page_count integer NOT NULL CHECK (page_count >= 1),
    metadata jsonb NOT NULL DEFAULT '{{}}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_documents_tenant_id ON documents (tenant_id);

CREATE TABLE chunks (
    id text PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    document_id text NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    parent_id text REFERENCES chunks (id) ON DELETE CASCADE,
    jurisdiction text NOT NULL CHECK (jurisdiction IN {JURISDICTIONS}),
    law text NOT NULL,
    language text NOT NULL CHECK (language IN {LANGUAGES}),
    edition text NOT NULL,
    article text NOT NULL,
    path text[] NOT NULL DEFAULT '{{}}',
    label text NOT NULL,
    heading text,
    text text NOT NULL,
    text_for_search text NOT NULL,
    context_header text NOT NULL DEFAULT '',
    context_header_llm text,
    effective_from date,
    effective_to date,  -- exclusive; NULL while in force
    status text NOT NULL DEFAULT 'in_force' CHECK (status IN {PROVISION_STATUSES}),
    validity_note text,
    history text,
    page integer CHECK (page >= 1),
    metadata jsonb NOT NULL DEFAULT '{{}}',
    embedding vector(1024),  -- NULL until the embedder has run
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from)
);
CREATE INDEX ix_chunks_tenant_id ON chunks (tenant_id);
CREATE INDEX ix_chunks_document_id ON chunks (document_id);
CREATE INDEX ix_chunks_parent_id ON chunks (parent_id);
-- An exact article reference (jurisdiction, law, article, edition) finds its chunks.
CREATE INDEX ix_chunks_article_ref ON chunks (jurisdiction, law, article, edition);

CREATE TABLE ingestion_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    kind text NOT NULL,
    source_id text NOT NULL,
    content_hash text NOT NULL,
    status text NOT NULL DEFAULT 'queued' CHECK (status IN {JOB_STATUSES}),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    payload jsonb NOT NULL DEFAULT '{{}}',
    result jsonb,
    error text,
    worker text,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    -- Idempotency: one input is queued once, whatever happens to the job afterwards.
    CONSTRAINT uq_ingestion_jobs_input UNIQUE (tenant_id, kind, content_hash)
);
-- Workers claim the oldest queued job; the partial index keeps that scan small.
CREATE INDEX ix_ingestion_jobs_queued ON ingestion_jobs (created_at) WHERE status = 'queued';

CREATE TABLE queries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    request_id text NOT NULL UNIQUE,
    question text NOT NULL,
    as_of date,
    jurisdictions text[] NOT NULL DEFAULT '{{}}',
    tier text NOT NULL CHECK (tier IN {TIERS}),
    status text CHECK (status IN {ANSWER_STATUSES}),  -- NULL when the stream failed
    route text,
    model text,
    config_name text,
    config_hash text,
    latency_ms double precision CHECK (latency_ms >= 0),
    input_tokens integer NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens integer NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    cost_usd double precision NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),
    cached boolean NOT NULL DEFAULT false,
    trace_url text,
    error text,
    answer jsonb,  -- the Answer as streamed, for the nightly online evaluation
    trace jsonb,  -- the AnswerTrace
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_queries_tenant_id_created_at ON queries (tenant_id, created_at);

CREATE TABLE eval_runs (
    run_id text PRIMARY KEY,
    schema_version integer NOT NULL,
    config_name text NOT NULL,
    config_hash text NOT NULL,
    git_sha text NOT NULL,
    golden_file text NOT NULL,
    split text NOT NULL CHECK (split IN ('dev', 'test', 'all')),
    judged boolean NOT NULL,
    n_items integer NOT NULL CHECK (n_items >= 0),
    summary jsonb NOT NULL DEFAULT '{{}}',
    notes text,
    created_at timestamptz NOT NULL
);

CREATE TABLE eval_results (
    run_id text NOT NULL REFERENCES eval_runs (run_id) ON DELETE CASCADE,
    item_id text NOT NULL,
    retrieved jsonb NOT NULL DEFAULT '[]',
    status text CHECK (status IN {ANSWER_STATUSES}),
    answer text,
    cited text[] NOT NULL DEFAULT '{{}}',
    invalid_citations integer NOT NULL DEFAULT 0 CHECK (invalid_citations >= 0),
    metrics jsonb NOT NULL DEFAULT '{{}}',
    latency_ms double precision CHECK (latency_ms >= 0),
    cost_usd double precision CHECK (cost_usd >= 0),
    trace_id text,
    error text,
    PRIMARY KEY (run_id, item_id)
);

CREATE TABLE settings (
    key text PRIMARY KEY,
    value jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- The tenant a transaction acts for; NULL when unset or empty.
CREATE FUNCTION current_tenant() RETURNS uuid
LANGUAGE sql STABLE
AS $$ SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid $$;

-- Roles are cluster-wide and the lanes' test databases share the cluster and may migrate
-- at the same moment, so an existing role (or a concurrent creation) is not an error.
DO $$ BEGIN
    CREATE ROLE plumbline_app NOLOGIN;
EXCEPTION WHEN duplicate_object OR unique_violation THEN NULL;
END $$;
GRANT plumbline_app TO CURRENT_USER;
GRANT USAGE ON SCHEMA public TO plumbline_app;
GRANT SELECT ON tenants TO plumbline_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON documents, chunks, ingestion_jobs, queries,
    eval_runs, eval_results, settings TO plumbline_app;
GRANT EXECUTE ON FUNCTION current_tenant() TO plumbline_app;
"""  # noqa: S608 (built from the constants above, never from input)


def upgrade() -> None:
    op.execute(UPGRADE)
    for table in TENANT_TABLES:
        # FORCE applies the policies to the table owner too; only superusers bypass them.
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        readable = "tenant_id = current_tenant()"
        if table in SHARED_TABLES:
            readable += f" OR tenant_id = '{PUBLIC_TENANT}'"
        op.execute(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING ({readable})")
        op.execute(
            f"CREATE POLICY {table}_write ON {table} FOR ALL"
            " USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant())"
        )


def downgrade() -> None:
    # Dropping the tables and the function drops their grants; the schema grant stays.
    op.execute(
        "DROP TABLE settings, eval_results, eval_runs, queries, ingestion_jobs, chunks,"
        " documents, tenants"
    )
    op.execute("DROP FUNCTION current_tenant()")
    op.execute("REVOKE USAGE ON SCHEMA public FROM plumbline_app")
    # Other databases on the cluster (the lanes' test databases) may still use the role.
    op.execute(
        """
        DO $$ BEGIN
            DROP ROLE plumbline_app;
        EXCEPTION WHEN dependent_objects_still_exist THEN NULL;
        END $$
        """
    )

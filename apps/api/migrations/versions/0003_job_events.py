"""Ingestion job events: the progress log a job's event stream reads, one row per step.

The application may only read and append (no UPDATE or DELETE grant), so the log of what
a job did cannot be rewritten afterwards. Row-level security matches ingestion_jobs.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EVENT_KINDS = "('queued', 'requeued', 'started', 'progress', 'succeeded', 'failed')"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE ingestion_job_events (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            job_id uuid NOT NULL REFERENCES ingestion_jobs (id) ON DELETE CASCADE,
            tenant_id uuid NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            kind text NOT NULL CHECK (kind IN {EVENT_KINDS}),
            message text NOT NULL DEFAULT '',
            data jsonb NOT NULL DEFAULT '{{}}',
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_ingestion_job_events_job_id_id ON ingestion_job_events (job_id, id);
        ALTER TABLE ingestion_job_events ENABLE ROW LEVEL SECURITY;
        ALTER TABLE ingestion_job_events FORCE ROW LEVEL SECURITY;
        CREATE POLICY ingestion_job_events_read ON ingestion_job_events FOR SELECT
            USING (tenant_id = current_tenant());
        CREATE POLICY ingestion_job_events_append ON ingestion_job_events FOR INSERT
            WITH CHECK (tenant_id = current_tenant());
        GRANT SELECT, INSERT ON ingestion_job_events TO plumbline_app;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE ingestion_job_events")

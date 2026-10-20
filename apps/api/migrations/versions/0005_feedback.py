"""Feedback on answers: helpful or not, why, and an optional note, tied to the answer by
the request_id its trace carries. The application may only read and append it.

The note is free text, so it may hold personal data: it is stored, never sent to a model,
and never logged.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REASONS = "'wrong_citation', 'missed_statute', 'outdated_law', 'hard_to_follow', 'something_else'"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE feedback (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            request_id text NOT NULL CHECK (char_length(request_id) BETWEEN 1 AND 64),
            helpful boolean NOT NULL,
            reasons text[] NOT NULL DEFAULT '{{}}' CHECK (reasons <@ ARRAY[{REASONS}]),
            note text CHECK (char_length(note) <= 1000),
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_feedback_request_id ON feedback (request_id);
        ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;
        ALTER TABLE feedback FORCE ROW LEVEL SECURITY;
        CREATE POLICY feedback_read ON feedback FOR SELECT USING (tenant_id = current_tenant());
        CREATE POLICY feedback_append ON feedback FOR INSERT
            WITH CHECK (tenant_id = current_tenant());
        GRANT SELECT, INSERT ON feedback TO plumbline_app;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE feedback")

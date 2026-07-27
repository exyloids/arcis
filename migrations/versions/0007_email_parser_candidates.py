"""Store parsed email transaction candidates for review.

Revision ID: 0007_email_parser_candidates
Revises: 0006_gmail_source_artifacts
"""

from alembic import op

revision = "0007_email_parser_candidates"
down_revision = "0006_gmail_source_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE parser_candidates (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            artifact_id UUID NOT NULL REFERENCES source_artifacts(id),
            financial_account_id UUID REFERENCES financial_accounts(id),
            parser_name TEXT NOT NULL,
            state TEXT NOT NULL CHECK (state IN ('ready', 'needs_review', 'unsupported', 'accepted', 'rejected')),
            review_reason TEXT,
            normalized JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (artifact_id, parser_name)
        );
        CREATE INDEX ix_parser_candidates_user_state ON parser_candidates(user_id, state, created_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE parser_candidates;")

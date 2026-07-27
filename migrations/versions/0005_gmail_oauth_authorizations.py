"""Persist single-use Gmail OAuth authorization state.

Revision ID: 0005_gmail_oauth_authorizations
Revises: 0004_import_row_review
"""

from alembic import op

revision = "0005_gmail_oauth_authorizations"
down_revision = "0004_import_row_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE oauth_authorizations (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            provider TEXT NOT NULL CHECK (provider = 'gmail'),
            state_sha256 CHAR(64) NOT NULL UNIQUE,
            code_verifier TEXT NOT NULL,
            redirect_uri TEXT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_oauth_authorizations_active ON oauth_authorizations (provider, expires_at)
            WHERE consumed_at IS NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_oauth_authorizations_active; DROP TABLE oauth_authorizations;")

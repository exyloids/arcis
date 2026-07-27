"""Persist row-level import validation results for review.

Revision ID: 0004_import_row_review
Revises: 0003_import_artifact_lifecycle
"""

from alembic import op

revision = "0004_import_row_review"
down_revision = "0003_import_artifact_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE imports ADD COLUMN valid_row_count INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE imports ADD COLUMN invalid_row_count INTEGER NOT NULL DEFAULT 0;
        UPDATE imports SET valid_row_count = row_count;

        CREATE TABLE import_row_errors (
            id UUID PRIMARY KEY,
            import_id UUID NOT NULL REFERENCES imports(id) ON DELETE CASCADE,
            ordinal INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (import_id, ordinal)
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE import_row_errors;
        ALTER TABLE imports DROP COLUMN invalid_row_count;
        ALTER TABLE imports DROP COLUMN valid_row_count;
        """
    )

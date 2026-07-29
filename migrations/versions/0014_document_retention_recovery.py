"""Add recoverable source-document deletion metadata.

Revision ID: 0014_document_retention_recovery
Revises: 0013_everyday_finance_controls
"""

from alembic import op

revision = "0014_document_retention_recovery"
down_revision = "0013_everyday_finance_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE source_artifacts
            ADD COLUMN original_object_key TEXT,
            ADD COLUMN recovery_object_key TEXT,
            ADD COLUMN deleted_at TIMESTAMPTZ,
            ADD COLUMN purge_after TIMESTAMPTZ;
        CREATE INDEX ix_source_artifacts_recovery
            ON source_artifacts(user_id, lifecycle_state, purge_after)
            WHERE recovery_object_key IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX ix_source_artifacts_recovery;
        ALTER TABLE source_artifacts
            DROP COLUMN purge_after,
            DROP COLUMN deleted_at,
            DROP COLUMN recovery_object_key,
            DROP COLUMN original_object_key;
        """
    )

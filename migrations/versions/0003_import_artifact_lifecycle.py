"""Persist import artifact metadata and lifecycle details.

Revision ID: 0003_import_artifact_lifecycle
Revises: 0002_manual_ledger
"""

from alembic import op

revision = "0003_import_artifact_lifecycle"
down_revision = "0002_manual_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE imports ADD COLUMN object_key TEXT;
        ALTER TABLE imports ADD COLUMN detected_mime_type TEXT;
        ALTER TABLE imports ADD COLUMN byte_size BIGINT;
        ALTER TABLE imports ADD COLUMN error_code TEXT;
        ALTER TABLE imports ADD COLUMN cancelled_at TIMESTAMPTZ;
        CREATE UNIQUE INDEX ux_imports_object_key ON imports(object_key) WHERE object_key IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX ux_imports_object_key;
        ALTER TABLE imports DROP COLUMN cancelled_at;
        ALTER TABLE imports DROP COLUMN error_code;
        ALTER TABLE imports DROP COLUMN byte_size;
        ALTER TABLE imports DROP COLUMN detected_mime_type;
        ALTER TABLE imports DROP COLUMN object_key;
        """
    )

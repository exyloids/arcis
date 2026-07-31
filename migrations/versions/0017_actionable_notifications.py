"""Add safe action metadata to notifications.

Revision ID: 0017_actionable_notifications
Revises: 0016_transaction_subcategories
"""

from alembic import op

revision = "0017_actionable_notifications"
down_revision = "0016_transaction_subcategories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE notifications
            ADD COLUMN action_kind TEXT,
            ADD COLUMN action_payload JSONB NOT NULL DEFAULT '{}'::jsonb;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE notifications
            DROP COLUMN action_payload,
            DROP COLUMN action_kind;
        """
    )

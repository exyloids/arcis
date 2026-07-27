"""Associate source artifacts with Gmail messages.

Revision ID: 0006_gmail_source_artifacts
Revises: 0005_gmail_oauth_authorizations
"""

from alembic import op

revision = "0006_gmail_source_artifacts"
down_revision = "0005_gmail_oauth_authorizations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE source_artifacts ADD COLUMN mailbox_id UUID REFERENCES mailboxes(id);
        ALTER TABLE source_artifacts ADD COLUMN provider_message_id TEXT;
        CREATE UNIQUE INDEX ux_source_artifacts_mailbox_message
            ON source_artifacts(mailbox_id, provider_message_id)
            WHERE mailbox_id IS NOT NULL AND provider_message_id IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX ux_source_artifacts_mailbox_message;
        ALTER TABLE source_artifacts DROP COLUMN provider_message_id;
        ALTER TABLE source_artifacts DROP COLUMN mailbox_id;
        """
    )

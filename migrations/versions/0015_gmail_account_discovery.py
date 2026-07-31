"""Add user-confirmed financial-account discovery from Gmail alerts.

Revision ID: 0015_gmail_account_discovery
Revises: 0014_document_retention_recovery
"""

from alembic import op

revision = "0015_gmail_account_discovery"
down_revision = "0014_document_retention_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE discovered_financial_accounts (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            mailbox_id UUID REFERENCES mailboxes(id),
            fingerprint TEXT NOT NULL,
            institution_code TEXT NOT NULL,
            account_type TEXT NOT NULL
                CHECK (account_type IN ('bank_account', 'credit_card')),
            masked_identifier TEXT NOT NULL,
            suggested_product_name TEXT NOT NULL,
            suggested_display_name TEXT NOT NULL,
            currency CHAR(3) NOT NULL DEFAULT 'INR',
            state TEXT NOT NULL DEFAULT 'pending'
                CHECK (state IN ('pending', 'confirmed', 'rejected')),
            financial_account_id UUID REFERENCES financial_accounts(id),
            first_detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            decided_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, fingerprint),
            CHECK (
                (state = 'confirmed' AND financial_account_id IS NOT NULL)
                OR state <> 'confirmed'
            )
        );

        CREATE INDEX ix_discovered_accounts_user_state
            ON discovered_financial_accounts(user_id, state, last_detected_at DESC);

        ALTER TABLE parser_candidates
            ADD COLUMN discovered_account_id UUID
                REFERENCES discovered_financial_accounts(id);

        CREATE INDEX ix_parser_candidates_discovered_account
            ON parser_candidates(discovered_account_id, state);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX ix_parser_candidates_discovered_account;
        ALTER TABLE parser_candidates DROP COLUMN discovered_account_id;
        DROP TABLE discovered_financial_accounts;
        """
    )

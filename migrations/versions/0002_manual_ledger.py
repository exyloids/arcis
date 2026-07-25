"""Add manual-ledger imports, categories, mailbox metadata, and evidence links.

Revision ID: 0002_manual_ledger
Revises: 0001_initial
"""

from alembic import op

revision = "0002_manual_ledger"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE categories (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            is_system BOOLEAN NOT NULL DEFAULT false,
            archived_at TIMESTAMPTZ,
            version INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, code)
        );

        CREATE TABLE mailboxes (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            provider TEXT NOT NULL DEFAULT 'gmail',
            provider_subject TEXT NOT NULL,
            display_email TEXT NOT NULL,
            connection_status TEXT NOT NULL DEFAULT 'disconnected',
            granted_scopes JSONB NOT NULL DEFAULT '[]'::jsonb,
            history_cursor TEXT,
            last_successful_sync_at TIMESTAMPTZ,
            version INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, provider, provider_subject)
        );

        CREATE TABLE oauth_credentials (
            mailbox_id UUID PRIMARY KEY REFERENCES mailboxes(id),
            encrypted_secret TEXT NOT NULL,
            key_version TEXT NOT NULL,
            rotated_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE imports (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            financial_account_id UUID NOT NULL REFERENCES financial_accounts(id),
            filename TEXT NOT NULL,
            content_sha256 CHAR(64) NOT NULL,
            state TEXT NOT NULL CHECK (state IN ('preview_ready', 'confirmed', 'cancelled', 'failed')),
            row_count INTEGER NOT NULL DEFAULT 0,
            duplicate_count INTEGER NOT NULL DEFAULT 0,
            confirmed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, financial_account_id, content_sha256)
        );
        CREATE INDEX ix_imports_user_created ON imports(user_id, created_at DESC);

        CREATE TABLE import_rows (
            id UUID PRIMARY KEY,
            import_id UUID NOT NULL REFERENCES imports(id) ON DELETE CASCADE,
            ordinal INTEGER NOT NULL,
            transaction_date DATE NOT NULL,
            posted_date DATE,
            narration TEXT NOT NULL,
            amount NUMERIC(20, 4) NOT NULL CHECK (amount > 0),
            currency CHAR(3) NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('debit', 'credit')),
            provider_reference TEXT,
            raw_columns JSONB NOT NULL,
            UNIQUE (import_id, ordinal)
        );

        ALTER TABLE source_artifacts ADD COLUMN import_id UUID REFERENCES imports(id);
        ALTER TABLE source_records ADD COLUMN financial_account_id UUID REFERENCES financial_accounts(id);
        ALTER TABLE transactions ADD COLUMN category_id UUID REFERENCES categories(id);
        ALTER TABLE transactions ADD COLUMN source_record_id UUID REFERENCES source_records(id);
        ALTER TABLE transactions ADD COLUMN provider_reference TEXT;
        ALTER TABLE transactions ADD COLUMN category_source TEXT NOT NULL DEFAULT 'uncategorized';
        ALTER TABLE transactions ADD COLUMN merchant_normalized TEXT;
        CREATE UNIQUE INDEX ux_transactions_source_record ON transactions(source_record_id)
            WHERE source_record_id IS NOT NULL;
        CREATE INDEX ix_transactions_user_month ON transactions(user_id, transaction_date DESC);

        CREATE TABLE transaction_relations (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            left_transaction_id UUID NOT NULL REFERENCES transactions(id),
            right_transaction_id UUID NOT NULL REFERENCES transactions(id),
            relation_type TEXT NOT NULL CHECK (relation_type IN ('potential_duplicate', 'transfer_pair', 'card_payment_pair')),
            confidence NUMERIC(5, 4) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (left_transaction_id, right_transaction_id, relation_type),
            CHECK (left_transaction_id <> right_transaction_id)
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE transaction_relations;
        DROP INDEX ix_transactions_user_month;
        DROP INDEX ux_transactions_source_record;
        ALTER TABLE transactions DROP COLUMN merchant_normalized;
        ALTER TABLE transactions DROP COLUMN category_source;
        ALTER TABLE transactions DROP COLUMN provider_reference;
        ALTER TABLE transactions DROP COLUMN source_record_id;
        ALTER TABLE transactions DROP COLUMN category_id;
        ALTER TABLE source_records DROP COLUMN financial_account_id;
        ALTER TABLE source_artifacts DROP COLUMN import_id;
        DROP TABLE import_rows;
        DROP TABLE imports;
        DROP TABLE oauth_credentials;
        DROP TABLE mailboxes;
        DROP TABLE categories;
        """
    )

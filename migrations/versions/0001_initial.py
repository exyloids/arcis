"""Create the initial evidence and ledger tables.

Revision ID: 0001_initial
Revises:
"""

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE users (
            id UUID PRIMARY KEY,
            email_normalized TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            default_currency CHAR(3) NOT NULL DEFAULT 'INR',
            timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'locked', 'deleting', 'deleted')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE financial_accounts (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            account_type TEXT NOT NULL
                CHECK (account_type IN ('bank_account', 'credit_card')),
            institution_code TEXT NOT NULL,
            product_name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            masked_identifier TEXT,
            currency CHAR(3) NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'archived')),
            version INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_financial_accounts_user ON financial_accounts(user_id);

        CREATE TABLE source_artifacts (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            kind TEXT NOT NULL,
            content_sha256 CHAR(64) NOT NULL,
            object_key TEXT,
            detected_mime_type TEXT,
            byte_size BIGINT,
            lifecycle_state TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, kind, content_sha256)
        );
        CREATE INDEX ix_source_artifacts_user ON source_artifacts(user_id);

        CREATE TABLE source_records (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            artifact_id UUID NOT NULL REFERENCES source_artifacts(id),
            source_record_key TEXT NOT NULL,
            transaction_date DATE NOT NULL,
            posted_date DATE,
            narration TEXT NOT NULL,
            amount NUMERIC(20, 4) NOT NULL CHECK (amount > 0),
            currency CHAR(3) NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('debit', 'credit')),
            provider_reference TEXT,
            confidence NUMERIC(5, 4),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (artifact_id, source_record_key)
        );
        CREATE INDEX ix_source_records_user_date ON source_records(user_id, transaction_date);

        CREATE TABLE transactions (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            financial_account_id UUID NOT NULL REFERENCES financial_accounts(id),
            transaction_date DATE NOT NULL,
            posted_date DATE,
            narration TEXT NOT NULL,
            amount NUMERIC(20, 4) NOT NULL CHECK (amount > 0),
            currency CHAR(3) NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('debit', 'credit')),
            transaction_kind TEXT NOT NULL DEFAULT 'unknown',
            reconciliation_state TEXT NOT NULL DEFAULT 'email_only',
            version INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_transactions_user_date ON transactions(user_id, transaction_date DESC);
        CREATE INDEX ix_transactions_account_date
            ON transactions(financial_account_id, transaction_date DESC);

        CREATE TABLE transaction_evidence (
            transaction_id UUID NOT NULL REFERENCES transactions(id),
            source_record_id UUID NOT NULL REFERENCES source_records(id),
            relationship TEXT NOT NULL DEFAULT 'primary',
            match_method TEXT NOT NULL,
            match_score NUMERIC(5, 4),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (transaction_id, source_record_id),
            UNIQUE (source_record_id)
        );

        CREATE TABLE jobs (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            job_kind TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'queued',
            idempotency_key TEXT NOT NULL,
            phase TEXT,
            progress JSONB NOT NULL DEFAULT '{}'::jsonb,
            error_code TEXT,
            attempt INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, job_kind, idempotency_key)
        );
        CREATE INDEX ix_jobs_user_state ON jobs(user_id, state);

        CREATE TABLE audit_events (
            id UUID PRIMARY KEY,
            user_id UUID REFERENCES users(id),
            actor_type TEXT NOT NULL,
            actor_id UUID,
            action TEXT NOT NULL,
            target_type TEXT,
            target_id UUID,
            request_id TEXT,
            result TEXT NOT NULL,
            safe_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_audit_events_user_time ON audit_events(user_id, created_at DESC);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE audit_events;
        DROP TABLE jobs;
        DROP TABLE transaction_evidence;
        DROP TABLE transactions;
        DROP TABLE source_records;
        DROP TABLE source_artifacts;
        DROP TABLE financial_accounts;
        DROP TABLE users;
        """
    )

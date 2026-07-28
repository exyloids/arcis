"""Add statement metadata and reconciliation review records.

Revision ID: 0008_statements_reconciliation
Revises: 0007_email_parser_candidates
"""

from alembic import op

revision = "0008_statements_reconciliation"
down_revision = "0007_email_parser_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE statements (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            financial_account_id UUID NOT NULL REFERENCES financial_accounts(id),
            import_id UUID NOT NULL UNIQUE REFERENCES imports(id),
            parser_name TEXT NOT NULL,
            parser_version TEXT NOT NULL,
            period_start DATE,
            period_end DATE,
            opening_balance NUMERIC(20, 4),
            closing_balance NUMERIC(20, 4),
            statement_amount NUMERIC(20, 4),
            minimum_due NUMERIC(20, 4),
            due_date DATE,
            total_limit NUMERIC(20, 4),
            available_limit NUMERIC(20, 4),
            state TEXT NOT NULL CHECK (state IN ('preview_ready', 'confirmed', 'reconciled', 'failed')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            confirmed_at TIMESTAMPTZ
        );
        CREATE INDEX ix_statements_account_period ON statements(financial_account_id, period_end DESC);

        CREATE TABLE reconciliation_reviews (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            statement_id UUID NOT NULL REFERENCES statements(id) ON DELETE CASCADE,
            import_row_id UUID NOT NULL REFERENCES import_rows(id) ON DELETE CASCADE,
            transaction_id UUID REFERENCES transactions(id),
            state TEXT NOT NULL CHECK (state IN ('needs_review', 'accepted', 'rejected')),
            match_method TEXT NOT NULL,
            match_score NUMERIC(5, 4),
            reason TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            reviewed_at TIMESTAMPTZ,
            UNIQUE (statement_id, import_row_id, transaction_id)
        );
        CREATE INDEX ix_reconciliation_reviews_user_state
            ON reconciliation_reviews(user_id, state, created_at DESC);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX ix_reconciliation_reviews_user_state;
        DROP TABLE reconciliation_reviews;
        DROP INDEX ix_statements_account_period;
        DROP TABLE statements;
        """
    )

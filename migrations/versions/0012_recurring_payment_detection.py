"""Add reviewable recurring-payment detections.

Revision ID: 0012_recurring_payment_detection
Revises: 0011_category_rules
"""

from alembic import op

revision = "0012_recurring_payment_detection"
down_revision = "0011_category_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE recurring_payment_detections (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            financial_account_id UUID NOT NULL REFERENCES financial_accounts(id),
            merchant_key TEXT NOT NULL,
            display_name TEXT NOT NULL,
            category_id UUID REFERENCES categories(id),
            cadence TEXT NOT NULL CHECK (cadence IN ('weekly', 'monthly', 'quarterly', 'yearly')),
            cadence_days INTEGER NOT NULL,
            typical_amount NUMERIC(18, 4) NOT NULL,
            amount_tolerance NUMERIC(18, 4) NOT NULL,
            occurrence_count INTEGER NOT NULL,
            first_observed_on DATE NOT NULL,
            last_observed_on DATE NOT NULL,
            next_expected_on DATE NOT NULL,
            confidence NUMERIC(5, 4) NOT NULL,
            state TEXT NOT NULL DEFAULT 'detected' CHECK (state IN ('detected', 'confirmed', 'dismissed')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, financial_account_id, merchant_key, cadence)
        );
        CREATE INDEX ix_recurring_payment_detections_user_state_next
            ON recurring_payment_detections (user_id, state, next_expected_on);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE recurring_payment_detections;")

"""Add user preferences, budgets, card payment state, and notifications.

Revision ID: 0013_everyday_finance_controls
Revises: 0012_recurring_payment_detection
"""

from alembic import op

revision = "0013_everyday_finance_controls"
down_revision = "0012_recurring_payment_detection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE user_preferences (
            user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            reporting_period TEXT NOT NULL DEFAULT 'this_month'
                CHECK (reporting_period IN (
                    'all_time', 'this_month', 'last_month',
                    'last_3_months', 'last_6_months', 'this_year'
                )),
            retention_policy JSONB NOT NULL DEFAULT
                jsonb_build_object(
                    'source_artifacts_days', 365,
                    'statement_files_days', 730
                ),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE budgets (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            category_id UUID NOT NULL REFERENCES categories(id),
            monthly_limit NUMERIC(20, 4) NOT NULL CHECK (monthly_limit > 0),
            active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, category_id)
        );
        CREATE INDEX ix_budgets_user_active ON budgets(user_id, active);

        CREATE TABLE card_statement_payments (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            statement_id UUID NOT NULL UNIQUE REFERENCES statements(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'unpaid'
                CHECK (status IN ('unpaid', 'partial', 'paid')),
            paid_amount NUMERIC(20, 4) NOT NULL DEFAULT 0 CHECK (paid_amount >= 0),
            paid_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_card_statement_payments_user
            ON card_statement_payments(user_id, status);

        CREATE TABLE notifications (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            notification_kind TEXT NOT NULL,
            deduplication_key TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'unread'
                CHECK (state IN ('unread', 'read', 'dismissed')),
            due_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, notification_kind, deduplication_key)
        );
        CREATE INDEX ix_notifications_user_state
            ON notifications(user_id, state, created_at DESC);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE notifications;
        DROP TABLE card_statement_payments;
        DROP TABLE budgets;
        DROP TABLE user_preferences;
        """
    )

"""Add user-owned merchant and category rules.

Revision ID: 0009_merchant_category_rules
Revises: 0008_statements_reconciliation
"""

from alembic import op

revision = "0009_merchant_category_rules"
down_revision = "0008_statements_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE merchant_rules (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            match_pattern TEXT NOT NULL,
            merchant_normalized TEXT NOT NULL,
            category_id UUID REFERENCES categories(id),
            priority INTEGER NOT NULL DEFAULT 100,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, match_pattern)
        );
        CREATE INDEX ix_merchant_rules_user_priority ON merchant_rules(user_id, priority, created_at);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE merchant_rules;")

"""Add deterministic categorization rule metadata.

Revision ID: 0011_category_rules
Revises: 0010_category_hierarchy
"""

from alembic import op

revision = "0011_category_rules"
down_revision = "0010_category_hierarchy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE merchant_rules ADD COLUMN rule_type TEXT NOT NULL DEFAULT 'keyword'
            CHECK (rule_type IN ('user_override', 'exact_merchant', 'mcc', 'keyword'));
        ALTER TABLE merchant_rules ADD COLUMN confidence NUMERIC(5,4) NOT NULL DEFAULT 0.8000;
        ALTER TABLE transactions ADD COLUMN category_rule_id UUID REFERENCES merchant_rules(id);
        ALTER TABLE transactions ADD COLUMN category_confidence NUMERIC(5,4);
        ALTER TABLE transactions ADD COLUMN merchant_mcc TEXT;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE transactions DROP COLUMN merchant_mcc;
        ALTER TABLE transactions DROP COLUMN category_confidence;
        ALTER TABLE transactions DROP COLUMN category_rule_id;
        ALTER TABLE merchant_rules DROP COLUMN confidence;
        ALTER TABLE merchant_rules DROP COLUMN rule_type;
    """)

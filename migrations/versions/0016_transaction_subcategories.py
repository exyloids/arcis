"""Store transaction categories and subcategories independently.

Revision ID: 0016_transaction_subcategories
Revises: 0015_gmail_account_discovery
"""

from alembic import op

revision = "0016_transaction_subcategories"
down_revision = "0015_gmail_account_discovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE transactions
            ADD COLUMN subcategory_id UUID REFERENCES categories(id);
        ALTER TABLE merchant_rules
            ADD COLUMN subcategory_id UUID REFERENCES categories(id);

        UPDATE transactions transaction
        SET subcategory_id = transaction.category_id,
            category_id = category.parent_id
        FROM categories category
        WHERE transaction.category_id = category.id
          AND category.parent_id IS NOT NULL;

        UPDATE merchant_rules rule
        SET subcategory_id = rule.category_id,
            category_id = category.parent_id
        FROM categories category
        WHERE rule.category_id = category.id
          AND category.parent_id IS NOT NULL;

        CREATE INDEX ix_transactions_user_subcategory
            ON transactions(user_id, subcategory_id, transaction_date DESC);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE transactions
        SET category_id = subcategory_id
        WHERE subcategory_id IS NOT NULL;

        UPDATE merchant_rules
        SET category_id = subcategory_id
        WHERE subcategory_id IS NOT NULL;

        DROP INDEX ix_transactions_user_subcategory;
        ALTER TABLE merchant_rules DROP COLUMN subcategory_id;
        ALTER TABLE transactions DROP COLUMN subcategory_id;
        """
    )

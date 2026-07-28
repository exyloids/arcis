"""Add category hierarchy and expanded personal-finance taxonomy.

Revision ID: 0010_category_hierarchy
Revises: 0009_merchant_category_rules
"""

from alembic import op

revision = "0010_category_hierarchy"
down_revision = "0009_merchant_category_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE categories ADD COLUMN parent_id UUID REFERENCES categories(id);")
    op.execute("CREATE INDEX ix_categories_user_parent ON categories(user_id, parent_id, name);")


def downgrade() -> None:
    op.execute("DROP INDEX ix_categories_user_parent;")
    op.execute("ALTER TABLE categories DROP COLUMN parent_id;")

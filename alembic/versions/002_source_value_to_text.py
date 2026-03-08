"""change source_value from varchar(500) to text

Revision ID: 002
Revises: 001
Create Date: 2026-03-08
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "campaigns",
        "source_value",
        existing_type=sa.String(500),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "campaigns",
        "source_value",
        existing_type=sa.Text(),
        type_=sa.String(500),
        existing_nullable=False,
    )

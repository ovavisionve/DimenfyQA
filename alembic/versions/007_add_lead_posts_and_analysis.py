"""add lead posts and content analysis fields

Revision ID: 007
Revises: 006
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("ig_posts", JSONB, nullable=True))
    op.add_column("leads", sa.Column("ig_post_analysis", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "ig_post_analysis")
    op.drop_column("leads", "ig_posts")

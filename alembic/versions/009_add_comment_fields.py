"""add comment fields to leads

Revision ID: 009
Revises: 008
Create Date: 2026-03-25
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("comment_message", sa.Text, nullable=True))
    op.add_column("leads", sa.Column("comment_variant_b", sa.Text, nullable=True))
    op.add_column("leads", sa.Column("comment_status", sa.String(50), nullable=True))
    op.add_column("leads", sa.Column("comment_variant_used", sa.String(10), nullable=True))
    op.add_column("leads", sa.Column("commented_post_shortcode", sa.String(100), nullable=True))
    op.add_column("leads", sa.Column("comment_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leads", sa.Column("comment_error", sa.Text, nullable=True))
    op.add_column("leads", sa.Column("comment_attempts", sa.Integer, server_default="0", nullable=False))
    op.create_index("idx_leads_comment_status", "leads", ["comment_status"])


def downgrade() -> None:
    op.drop_index("idx_leads_comment_status")
    op.drop_column("leads", "comment_attempts")
    op.drop_column("leads", "comment_error")
    op.drop_column("leads", "comment_sent_at")
    op.drop_column("leads", "commented_post_shortcode")
    op.drop_column("leads", "comment_variant_used")
    op.drop_column("leads", "comment_status")
    op.drop_column("leads", "comment_variant_b")
    op.drop_column("leads", "comment_message")

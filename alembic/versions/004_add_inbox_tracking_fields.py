"""add inbox tracking fields to leads

Revision ID: 004
Revises: 003
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leads", sa.Column("reply_text", sa.Text(), nullable=True))
    op.add_column("leads", sa.Column("reply_classification", sa.String(50), nullable=True))
    op.add_column("leads", sa.Column(
        "conversation_status", sa.String(50), server_default="pending", nullable=False
    ))

    op.create_index("idx_leads_conversation_status", "leads", ["conversation_status"])


def downgrade() -> None:
    op.drop_index("idx_leads_conversation_status", table_name="leads")

    op.drop_column("leads", "conversation_status")
    op.drop_column("leads", "reply_classification")
    op.drop_column("leads", "reply_text")
    op.drop_column("leads", "replied_at")

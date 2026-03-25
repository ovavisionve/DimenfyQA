"""Add conversation_messages and reply_suggestions tables for Unibox feature

Revision ID: 011
Revises: 010
Create Date: 2026-03-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("message_type", sa.String(30), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("ig_account_used", sa.String(255), nullable=True),
        sa.Column("variant_used", sa.String(10), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_convmsg_lead", "conversation_messages", ["lead_id"])
    op.create_index("idx_convmsg_campaign", "conversation_messages", ["campaign_id"])
    op.create_index("idx_convmsg_sent_at", "conversation_messages", ["sent_at"])

    op.create_table(
        "reply_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("suggestions", postgresql.JSONB, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("was_used", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_replysugg_lead", "reply_suggestions", ["lead_id"])


def downgrade() -> None:
    op.drop_index("idx_replysugg_lead", table_name="reply_suggestions")
    op.drop_table("reply_suggestions")
    op.drop_index("idx_convmsg_sent_at", table_name="conversation_messages")
    op.drop_index("idx_convmsg_campaign", table_name="conversation_messages")
    op.drop_index("idx_convmsg_lead", table_name="conversation_messages")
    op.drop_table("conversation_messages")

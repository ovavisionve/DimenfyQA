"""add follow-up automation system

Revision ID: 005
Revises: 004
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create follow_up_rules table
    op.create_table(
        "follow_up_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", UUID(as_uuid=True), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("delay_days", sa.Integer(), nullable=False),
        sa.Column("template_prompt", sa.Text(), nullable=True),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("campaign_id", "step_number", name="uq_followup_campaign_step"),
    )
    op.create_index("idx_followup_campaign", "follow_up_rules", ["campaign_id"])
    op.create_index("idx_followup_client", "follow_up_rules", ["client_id"])

    # Add follow-up tracking fields to leads
    op.add_column("leads", sa.Column("follow_up_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("leads", sa.Column("last_follow_up_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leads", sa.Column("next_follow_up_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("idx_leads_next_follow_up_at", "leads", ["next_follow_up_at"])


def downgrade() -> None:
    op.drop_index("idx_leads_next_follow_up_at", table_name="leads")

    op.drop_column("leads", "next_follow_up_at")
    op.drop_column("leads", "last_follow_up_at")
    op.drop_column("leads", "follow_up_count")

    op.drop_index("idx_followup_client", table_name="follow_up_rules")
    op.drop_index("idx_followup_campaign", table_name="follow_up_rules")
    op.drop_table("follow_up_rules")

"""Add CRM tables (lead_notes, score_history) and crm_stage field on leads

Revision ID: 012
Revises: 011
Create Date: 2026-03-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add crm_stage to leads
    op.add_column("leads", sa.Column("crm_stage", sa.String(50), server_default="new", nullable=False))
    op.create_index("idx_leads_crm_stage", "leads", ["crm_stage"])

    # Create lead_notes table
    op.create_table(
        "lead_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_leadnotes_lead", "lead_notes", ["lead_id"])

    # Create score_history table
    op.create_table(
        "score_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("old_score", sa.Integer, nullable=False),
        sa.Column("new_score", sa.Integer, nullable=False),
        sa.Column("delta", sa.Integer, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_scorehist_lead", "score_history", ["lead_id"])
    op.create_index("idx_scorehist_created", "score_history", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_scorehist_created", table_name="score_history")
    op.drop_index("idx_scorehist_lead", table_name="score_history")
    op.drop_table("score_history")
    op.drop_index("idx_leadnotes_lead", table_name="lead_notes")
    op.drop_table("lead_notes")
    op.drop_index("idx_leads_crm_stage", table_name="leads")
    op.drop_column("leads", "crm_stage")

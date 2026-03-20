"""add phase 2 DM sending fields to leads

Revision ID: 003
Revises: 002
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("send_attempts", sa.Integer(), server_default="0", nullable=False))
    op.add_column("leads", sa.Column("send_error", sa.Text(), nullable=True))
    op.add_column("leads", sa.Column("delivery_status", sa.String(50), nullable=True))
    op.add_column("leads", sa.Column("dm_variant_used", sa.String(10), nullable=True))

    op.create_index("idx_leads_delivery_status", "leads", ["delivery_status"])
    op.create_index("idx_leads_send_attempts", "leads", ["send_attempts"])


def downgrade() -> None:
    op.drop_index("idx_leads_send_attempts", table_name="leads")
    op.drop_index("idx_leads_delivery_status", table_name="leads")

    op.drop_column("leads", "dm_variant_used")
    op.drop_column("leads", "delivery_status")
    op.drop_column("leads", "send_error")
    op.drop_column("leads", "send_attempts")

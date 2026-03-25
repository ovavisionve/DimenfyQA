"""add celery_task_id and last_phase to campaigns for recovery

Revision ID: 010
Revises: 009
Create Date: 2026-03-25
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("campaigns", sa.Column("celery_task_id", sa.String(255), nullable=True))
    op.add_column("campaigns", sa.Column("last_phase", sa.String(50), nullable=True))
    op.create_index("ix_campaigns_celery_task_id", "campaigns", ["celery_task_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_campaigns_celery_task_id", table_name="campaigns")
    op.drop_column("campaigns", "last_phase")
    op.drop_column("campaigns", "celery_task_id")

"""create all tables

Revision ID: 001
Revises:
Create Date: 2026-03-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # clients
    op.create_table(
        "clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("business_type", sa.String(100), nullable=True),
        sa.Column("ig_accounts", postgresql.JSONB(), server_default="[]", nullable=True),
        sa.Column("settings", postgresql.JSONB(), server_default="{}", nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # campaigns
    op.create_table(
        "campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_value", sa.String(500), nullable=False),
        sa.Column("status", sa.String(50), server_default="pending", nullable=True),
        sa.Column("settings", postgresql.JSONB(), server_default="{}", nullable=True),
        sa.Column("stats", postgresql.JSONB(), server_default="{}", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # leads
    op.create_table(
        "leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("ig_username", sa.String(255), nullable=False),
        sa.Column("ig_full_name", sa.String(500), nullable=True),
        sa.Column("ig_bio", sa.Text(), nullable=True),
        sa.Column("ig_bio_clean", sa.Text(), nullable=True),
        sa.Column("ig_website", sa.String(500), nullable=True),
        sa.Column("ig_category", sa.String(255), nullable=True),
        sa.Column("ig_follower_count", sa.Integer(), nullable=True),
        sa.Column("ig_following_count", sa.Integer(), nullable=True),
        sa.Column("ig_is_private", sa.Boolean(), nullable=True),
        sa.Column("ig_profile_pic_url", sa.Text(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("score_reason", sa.Text(), nullable=True),
        sa.Column("lead_category", sa.String(100), nullable=True),
        sa.Column("research_data", sa.Text(), nullable=True),
        sa.Column("research_summary", sa.Text(), nullable=True),
        sa.Column("dm_message", sa.Text(), nullable=True),
        sa.Column("dm_variant_b", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), server_default="scraped", nullable=True),
        sa.Column("is_duplicate", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("researched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dm_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("client_id", "ig_username", name="uq_leads_client_username"),
    )
    op.create_index("idx_leads_campaign", "leads", ["campaign_id"])
    op.create_index("idx_leads_client", "leads", ["client_id"])
    op.create_index("idx_leads_status", "leads", ["status"])
    op.create_index("idx_leads_score", "leads", ["score"])
    op.create_index("idx_leads_username", "leads", ["ig_username"])

    # messages
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("variant", sa.String(10), server_default="A", nullable=True),
        sa.Column("status", sa.String(50), server_default="generated", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # scrape_jobs
    op.create_table(
        "scrape_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("apify_run_id", sa.String(255), nullable=True),
        sa.Column("apify_dataset_id", sa.String(255), nullable=True),
        sa.Column("actor_type", sa.String(100), nullable=True),
        sa.Column("status", sa.String(50), server_default="pending", nullable=True),
        sa.Column("items_found", sa.Integer(), server_default="0", nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("scrape_jobs")
    op.drop_table("messages")
    op.drop_index("idx_leads_username", "leads")
    op.drop_index("idx_leads_score", "leads")
    op.drop_index("idx_leads_status", "leads")
    op.drop_index("idx_leads_client", "leads")
    op.drop_index("idx_leads_campaign", "leads")
    op.drop_table("leads")
    op.drop_table("campaigns")
    op.drop_table("clients")

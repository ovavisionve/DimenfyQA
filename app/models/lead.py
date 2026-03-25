import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Lead(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("client_id", "ig_username", name="uq_leads_client_username"),
        Index("idx_leads_campaign", "campaign_id"),
        Index("idx_leads_client", "client_id"),
        Index("idx_leads_status", "status"),
        Index("idx_leads_score", "score"),
        Index("idx_leads_username", "ig_username"),
        Index("idx_leads_conversation_status", "conversation_status"),
        Index("idx_leads_next_follow_up_at", "next_follow_up_at"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )

    # Instagram data
    ig_username: Mapped[str] = mapped_column(String(255), nullable=False)
    ig_full_name: Mapped[Optional[str]] = mapped_column(String(500))
    ig_bio: Mapped[Optional[str]] = mapped_column(Text)
    ig_bio_clean: Mapped[Optional[str]] = mapped_column(Text)
    ig_website: Mapped[Optional[str]] = mapped_column(String(500))
    ig_category: Mapped[Optional[str]] = mapped_column(String(255))
    ig_follower_count: Mapped[Optional[int]] = mapped_column(Integer)
    ig_following_count: Mapped[Optional[int]] = mapped_column(Integer)
    ig_is_private: Mapped[Optional[bool]] = mapped_column(Boolean)
    ig_profile_pic_url: Mapped[Optional[str]] = mapped_column(Text)
    ig_posts: Mapped[Optional[dict]] = mapped_column(JSONB)  # Latest posts/reels from Apify
    ig_post_analysis: Mapped[Optional[dict]] = mapped_column(JSONB)  # Gemini analysis of posts

    # Scoring
    score: Mapped[Optional[int]] = mapped_column(Integer)
    score_reason: Mapped[Optional[str]] = mapped_column(Text)
    lead_category: Mapped[Optional[str]] = mapped_column(String(100))

    # Research (only if score >= 60)
    research_data: Mapped[Optional[str]] = mapped_column(Text)
    research_summary: Mapped[Optional[str]] = mapped_column(Text)

    # Generated DM (only if score >= 70)
    dm_message: Mapped[Optional[str]] = mapped_column(Text)
    dm_variant_b: Mapped[Optional[str]] = mapped_column(Text)

    # Status
    status: Mapped[str] = mapped_column(String(50), default="scraped", server_default="scraped")
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # Phase 2 — DM Sending
    send_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    send_error: Mapped[Optional[str]] = mapped_column(Text)
    delivery_status: Mapped[Optional[str]] = mapped_column(String(50))
    dm_variant_used: Mapped[Optional[str]] = mapped_column(String(10))

    # Phase 3 — Inbox Monitoring & Reply Tracking
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reply_text: Mapped[Optional[str]] = mapped_column(Text)
    reply_classification: Mapped[Optional[str]] = mapped_column(String(50))
    conversation_status: Mapped[str] = mapped_column(
        String(50), default="pending", server_default="pending"
    )

    # Phase 3 — Follow-up Automation
    follow_up_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_follow_up_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_follow_up_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Phase 6 — CRM Stage
    crm_stage: Mapped[str] = mapped_column(
        String(50), default="new", server_default="new"
    )

    # Phase 5 — Post Commenting
    comment_message: Mapped[Optional[str]] = mapped_column(Text)  # Comment variant A
    comment_variant_b: Mapped[Optional[str]] = mapped_column(Text)  # Comment variant B
    comment_status: Mapped[Optional[str]] = mapped_column(String(50))  # pending, sent, failed, skipped
    comment_variant_used: Mapped[Optional[str]] = mapped_column(String(10))  # A or B
    commented_post_shortcode: Mapped[Optional[str]] = mapped_column(String(100))  # shortCode of commented post
    comment_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    comment_error: Mapped[Optional[str]] = mapped_column(Text)
    comment_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Timestamps
    scraped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    scored_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    researched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    dm_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    campaign = relationship("Campaign", back_populates="leads")
    client = relationship("Client", back_populates="leads")

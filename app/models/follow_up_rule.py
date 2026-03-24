import uuid
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class FollowUpRule(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "follow_up_rules"
    __table_args__ = (
        UniqueConstraint("campaign_id", "step_number", name="uq_followup_campaign_step"),
        Index("idx_followup_campaign", "campaign_id"),
        Index("idx_followup_client", "client_id"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )

    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    delay_days: Mapped[int] = mapped_column(Integer, nullable=False)
    template_prompt: Mapped[Optional[str]] = mapped_column(Text)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    # Relationships
    campaign = relationship("Campaign", back_populates="follow_up_rules")
    client = relationship("Client", back_populates="follow_up_rules")

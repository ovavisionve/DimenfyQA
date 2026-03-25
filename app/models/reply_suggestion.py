import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ReplySuggestion(Base, UUIDMixin, TimestampMixin):
    """AI-generated reply suggestions for a lead conversation."""

    __tablename__ = "reply_suggestions"
    __table_args__ = (
        Index("idx_replysugg_lead", "lead_id"),
    )

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False
    )

    # JSON array of suggestion objects:
    # [{"intent": "close", "message": "..."}, {"intent": "nurture", "message": "..."}, {"intent": "qualify", "message": "..."}]
    suggestions: Mapped[dict] = mapped_column(JSONB, nullable=False)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    was_used: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # Relationships
    lead = relationship("Lead", backref="reply_suggestions")

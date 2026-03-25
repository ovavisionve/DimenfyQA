import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class LeadNote(Base, UUIDMixin, TimestampMixin):
    """Manual notes added by team members to a lead."""

    __tablename__ = "lead_notes"
    __table_args__ = (
        Index("idx_leadnotes_lead", "lead_id"),
    )

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    lead = relationship("Lead", backref="notes")


class ScoreHistory(Base, UUIDMixin):
    """Tracks score changes over time for dynamic scoring."""

    __tablename__ = "score_history"
    __table_args__ = (
        Index("idx_scorehist_lead", "lead_id"),
        Index("idx_scorehist_created", "created_at"),
    )

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False
    )
    old_score: Mapped[int] = mapped_column(Integer, nullable=False)
    new_score: Mapped[int] = mapped_column(Integer, nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False
    )

    # Relationships
    lead = relationship("Lead", backref="score_history")

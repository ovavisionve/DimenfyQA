import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ConversationMessage(Base, UUIDMixin, TimestampMixin):
    """Stores every message in a conversation thread (sent DMs, replies, follow-ups, manual replies)."""

    __tablename__ = "conversation_messages"
    __table_args__ = (
        Index("idx_convmsg_lead", "lead_id"),
        Index("idx_convmsg_campaign", "campaign_id"),
        Index("idx_convmsg_sent_at", "sent_at"),
    )

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )

    # Direction: "outbound" (we sent) or "inbound" (lead replied)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)

    # Message type: "dm", "follow_up", "reply", "manual_reply"
    message_type: Mapped[str] = mapped_column(String(30), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Which IG account was used to send (outbound only)
    ig_account_used: Mapped[Optional[str]] = mapped_column(String(255))

    # Variant used for outbound DMs
    variant_used: Mapped[Optional[str]] = mapped_column(String(10))

    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationships
    lead = relationship("Lead", backref="conversation_messages")

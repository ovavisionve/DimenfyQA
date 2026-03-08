import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Campaign(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "campaigns"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_value: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", server_default="pending")
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    stats: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")

    # Relationships
    client = relationship("Client", back_populates="campaigns")
    leads = relationship("Lead", back_populates="campaign", lazy="selectin")
    scrape_jobs = relationship("ScrapeJob", back_populates="campaign", lazy="selectin")

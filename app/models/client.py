import uuid
from typing import Optional

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Client(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "clients"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_type: Mapped[Optional[str]] = mapped_column(String(100))
    ig_accounts: Mapped[dict] = mapped_column(JSONB, default=list, server_default="[]")
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    # Relationships
    campaigns = relationship("Campaign", back_populates="client", lazy="selectin")
    leads = relationship("Lead", back_populates="client", lazy="selectin")
    follow_up_rules = relationship("FollowUpRule", back_populates="client", lazy="selectin")
    webhooks = relationship("Webhook", back_populates="client", lazy="selectin")

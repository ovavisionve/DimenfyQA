"""System-level key-value configuration stored in the database."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SystemConfig(Base, TimestampMixin):
    __tablename__ = "system_config"
    __table_args__ = {"schema": "public"}

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

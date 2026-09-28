import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TenantScopedMixin, TimestampMixin


class Notification(IdMixin, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key", name="uq_notification_dedupe"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(500))
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    dedupe_key: Mapped[str | None] = mapped_column(String(200))
    read_at: Mapped[datetime | None]


class DevicePushToken(IdMixin, TimestampMixin, Base):
    __tablename__ = "device_push_tokens"
    __table_args__ = (UniqueConstraint("token", name="uq_push_token"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String(500))
    platform: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(20), default="expo")
    revoked_at: Mapped[datetime | None]

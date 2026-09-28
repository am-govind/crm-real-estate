import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, utcnow


class AuditEvent(IdMixin, Base):
    """Append-only audit log. Rows are never updated or deleted by the application."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_entity", "tenant_id", "entity_type", "entity_id"),)

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    changes: Mapped[dict] = mapped_column(default=dict)
    metadata_: Mapped[dict] = mapped_column("metadata", default=dict)
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)

import uuid
from datetime import date, datetime

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import ActorMixin, Base, IdMixin, TenantScopedMixin, TimestampMixin, uuid_fk

TASK_STATUSES = ("open", "in_progress", "blocked", "done", "cancelled")
PRIORITIES = ("low", "medium", "high", "urgent")


class Task(IdMixin, TimestampMixin, TenantScopedMixin, ActorMixin, Base):
    __tablename__ = "tasks"

    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    due_date: Mapped[date | None] = mapped_column(index=True)
    assignee_id: Mapped[uuid.UUID | None] = uuid_fk("users.id")
    property_id: Mapped[uuid.UUID | None] = uuid_fk("properties.id")
    deal_id: Mapped[uuid.UUID | None] = uuid_fk("deals.id")
    deal_stage_id: Mapped[uuid.UUID | None] = uuid_fk("deal_stages.id", index=False)
    site_visit_id: Mapped[uuid.UUID | None] = uuid_fk("site_visits.id")
    completed_at: Mapped[datetime | None]
    completed_by_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)
    client_ref: Mapped[str | None] = mapped_column(String(64), index=True)

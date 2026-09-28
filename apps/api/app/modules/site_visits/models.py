import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import ActorMixin, Base, IdMixin, TenantScopedMixin, TimestampMixin, utcnow, uuid_fk

VISIT_STATUSES = ("scheduled", "in_progress", "completed", "cancelled", "missed")


class SiteVisit(IdMixin, TimestampMixin, TenantScopedMixin, ActorMixin, Base):
    __tablename__ = "site_visits"
    __table_args__ = (UniqueConstraint("tenant_id", "client_ref", name="uq_site_visit_client_ref"),)

    property_id: Mapped[uuid.UUID | None] = uuid_fk("properties.id")
    deal_id: Mapped[uuid.UUID | None] = uuid_fk("deals.id")
    title: Mapped[str] = mapped_column(String(300))
    purpose: Mapped[str | None] = mapped_column(Text)
    scheduled_start: Mapped[datetime] = mapped_column(index=True)
    scheduled_end: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(String(20), default="scheduled", index=True)
    outcome: Mapped[str | None] = mapped_column(Text)
    meeting_point: Mapped[str | None] = mapped_column(String(500))

    check_in_at: Mapped[datetime | None]
    check_in_lat: Mapped[float | None] = mapped_column(Float)
    check_in_lng: Mapped[float | None] = mapped_column(Float)
    check_in_accuracy_m: Mapped[float | None] = mapped_column(Float)
    check_out_at: Mapped[datetime | None]
    check_out_lat: Mapped[float | None] = mapped_column(Float)
    check_out_lng: Mapped[float | None] = mapped_column(Float)
    track: Mapped[list] = mapped_column(default=list)

    calendar_provider: Mapped[str | None] = mapped_column(String(30))
    calendar_external_ref: Mapped[str | None] = mapped_column(String(300))
    client_ref: Mapped[str | None] = mapped_column(String(64))

    attendees: Mapped[list["SiteVisitAttendee"]] = relationship(cascade="all, delete-orphan")
    notes: Mapped[list["SiteVisitNote"]] = relationship(order_by="SiteVisitNote.created_at", cascade="all, delete-orphan")


class SiteVisitAttendee(IdMixin, Base):
    __tablename__ = "site_visit_attendees"

    visit_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("site_visits.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID | None] = uuid_fk("users.id")
    owner_id: Mapped[uuid.UUID | None] = uuid_fk("owners.id", index=False)
    name: Mapped[str | None] = mapped_column(String(200))
    contact: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(40), default="attendee")
    is_assigned: Mapped[bool] = mapped_column(Boolean, default=False)
    attended: Mapped[bool | None] = mapped_column(Boolean)


class SiteVisitNote(IdMixin, Base):
    __tablename__ = "site_visit_notes"
    __table_args__ = (UniqueConstraint("visit_id", "client_ref", name="uq_visit_note_client_ref"),)

    visit_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("site_visits.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)
    author_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    client_ref: Mapped[str | None] = mapped_column(String(64))
    recorded_at: Mapped[datetime] = mapped_column(default=utcnow)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class SiteVisitMedia(IdMixin, TenantScopedMixin, Base):
    __tablename__ = "site_visit_media"
    __table_args__ = (UniqueConstraint("visit_id", "client_ref", name="uq_visit_media_client_ref"),)

    visit_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("site_visits.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    storage_key: Mapped[str] = mapped_column(String(600))
    filename: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(150))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    caption: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    captured_at: Mapped[datetime | None]
    uploaded_by_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)
    uploaded_at: Mapped[datetime] = mapped_column(default=utcnow)
    client_ref: Mapped[str | None] = mapped_column(String(64))

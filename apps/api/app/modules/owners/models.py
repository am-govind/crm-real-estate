import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import ActorMixin, Base, IdMixin, TenantScopedMixin, TimestampMixin, uuid_fk

OWNER_TYPES = ("individual", "organization", "trust", "huf", "government", "other")
VERIFICATION_STATUSES = ("unverified", "pending", "verified", "rejected")
READINESS = ("unknown", "not_interested", "considering", "ready_to_sell")


class Owner(IdMixin, TimestampMixin, TenantScopedMixin, ActorMixin, Base):
    __tablename__ = "owners"

    code: Mapped[str] = mapped_column(String(20), index=True)
    owner_type: Mapped[str] = mapped_column(String(20), default="individual")
    full_name: Mapped[str] = mapped_column(String(300), index=True)
    local_name: Mapped[str | None] = mapped_column(String(300))
    relation_name: Mapped[str | None] = mapped_column(String(300))
    date_of_birth: Mapped[date | None]
    verification_status: Mapped[str] = mapped_column(String(20), default="unverified", index=True)
    verified_by_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)
    verified_at: Mapped[datetime | None]
    verification_note: Mapped[str | None] = mapped_column(Text)
    readiness: Mapped[str] = mapped_column(String(20), default="unknown")
    notes: Mapped[str | None] = mapped_column(Text)
    custom_fields: Mapped[dict] = mapped_column(default=dict)

    contacts: Mapped[list["OwnerContact"]] = relationship(cascade="all, delete-orphan", back_populates="owner")


class OwnerContact(IdMixin, TimestampMixin, Base):
    __tablename__ = "owner_contacts"

    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    value: Mapped[str] = mapped_column(String(500))
    label: Mapped[str | None] = mapped_column(String(100))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    owner: Mapped[Owner] = relationship(back_populates="contacts")

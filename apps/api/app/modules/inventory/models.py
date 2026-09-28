import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import ActorMixin, Base, IdMixin, MeasureType, TenantScopedMixin, TimestampMixin, utcnow, uuid_fk

PROPERTY_TYPES = ("land_plot", "apartment", "studio_flat", "commercial_unit")
INVENTORY_STATUSES = ("available", "reserved", "blocked", "sold", "under_acquisition", "not_for_sale")
APPROVAL_STATES = ("pending", "approved", "rejected")


class SiteRecord(IdMixin, TimestampMixin, TenantScopedMixin, ActorMixin, Base):
    """Registry identity. ``site_code`` is immutable. Search columns mirror the active approved revision."""

    __tablename__ = "site_records"
    __table_args__ = (UniqueConstraint("tenant_id", "site_code", name="uq_site_code"),)

    site_code: Mapped[str] = mapped_column(String(20))
    property_type: Mapped[str] = mapped_column(String(20), index=True)
    approval_state: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    active_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("site_record_revisions.id", use_alter=True, name="fk_site_active_revision"), nullable=True
    )
    pending_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("site_record_revisions.id", use_alter=True, name="fk_site_pending_revision"), nullable=True
    )

    # Denormalized from the active approved revision for deterministic filtering.
    status: Mapped[str | None] = mapped_column(String(30), index=True)
    property_id: Mapped[uuid.UUID | None] = uuid_fk("properties.id")
    source_document_id: Mapped[uuid.UUID | None] = uuid_fk("documents.id")
    source_map_upload_id: Mapped[uuid.UUID | None] = uuid_fk("map_uploads.id")
    plot_label: Mapped[str | None] = mapped_column(String(100), index=True)
    unit_number: Mapped[str | None] = mapped_column(String(50), index=True)
    project_name: Mapped[str | None] = mapped_column(String(200))
    village_id: Mapped[uuid.UUID | None] = uuid_fk("geo_units.id")
    district_id: Mapped[uuid.UUID | None] = uuid_fk("geo_units.id")
    location_text: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    area_value: Mapped[Decimal | None] = mapped_column(MeasureType)
    area_unit: Mapped[str | None] = mapped_column(String(20))
    area_sqm_derived: Mapped[Decimal | None] = mapped_column(MeasureType, index=True)
    length_m_derived: Mapped[Decimal | None] = mapped_column(MeasureType)
    width_m_derived: Mapped[Decimal | None] = mapped_column(MeasureType)
    rooms: Mapped[int | None] = mapped_column(Integer)
    bathrooms: Mapped[int | None] = mapped_column(Integer)
    floor: Mapped[str | None] = mapped_column(String(20))
    usage_type: Mapped[str | None] = mapped_column(String(60))


class SiteRecordRevision(IdMixin, Base):
    """Full snapshot of a create/edit. Saved as pending; an administrator approves or rejects it."""

    __tablename__ = "site_record_revisions"
    __table_args__ = (UniqueConstraint("site_record_id", "revision_no", name="uq_site_revision"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    site_record_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("site_records.id"), index=True)
    revision_no: Mapped[int] = mapped_column(Integer)
    change_type: Mapped[str] = mapped_column(String(10))
    data: Mapped[dict] = mapped_column()
    derived: Mapped[dict] = mapped_column(default=dict)
    match_decision: Mapped[dict] = mapped_column(default=dict)
    change_note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    submitted_by_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    submitted_at: Mapped[datetime] = mapped_column(default=utcnow)
    reviewed_by_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)
    reviewed_at: Mapped[datetime | None]
    review_note: Mapped[str | None] = mapped_column(Text)

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import ActorMixin, Base, IdMixin, MeasureType, TenantScopedMixin, TimestampMixin, uuid_fk

LAND_TYPES = ("agricultural", "non_agricultural", "residential", "commercial", "industrial", "mixed", "other")
PROPERTY_STATUSES = ("prospect", "in_pipeline", "acquired", "dropped", "on_hold")
ROAD_ACCESS = ("unknown", "none", "kaccha", "pakka", "highway_frontage")
TITLE_STATUSES = ("unknown", "under_review", "clear", "encumbered", "disputed")
OWNERSHIP_TYPES = ("sole", "joint", "co_owner", "legal_heir", "poa_holder", "lessee", "other")


class Property(IdMixin, TimestampMixin, TenantScopedMixin, ActorMixin, Base):
    """The land parcel: the centre of the product."""

    __tablename__ = "properties"

    code: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(300))
    land_type: Mapped[str] = mapped_column(String(30), default="agricultural", index=True)
    status: Mapped[str] = mapped_column(String(20), default="prospect", index=True)

    state_id: Mapped[uuid.UUID | None] = uuid_fk("geo_units.id")
    district_id: Mapped[uuid.UUID | None] = uuid_fk("geo_units.id")
    tehsil_id: Mapped[uuid.UUID | None] = uuid_fk("geo_units.id")
    village_id: Mapped[uuid.UUID | None] = uuid_fk("geo_units.id")
    survey_number: Mapped[str | None] = mapped_column(String(100), index=True)
    khasra_number: Mapped[str | None] = mapped_column(String(100), index=True)
    khata_number: Mapped[str | None] = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(Text)
    pincode: Mapped[str | None] = mapped_column(String(12))

    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    active_geometry_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("geometry_versions.id", use_alter=True, name="fk_property_active_geometry"), nullable=True
    )

    area_value: Mapped[Decimal | None] = mapped_column(MeasureType)
    area_unit: Mapped[str | None] = mapped_column(String(20))
    area_sqm_derived: Mapped[Decimal | None] = mapped_column(MeasureType, index=True)
    land_use: Mapped[str | None] = mapped_column(String(60))
    road_access: Mapped[str] = mapped_column(String(20), default="unknown")
    road_frontage_value: Mapped[Decimal | None] = mapped_column(MeasureType)
    road_frontage_unit: Mapped[str | None] = mapped_column(String(20))
    title_status: Mapped[str] = mapped_column(String(20), default="unknown")

    notes: Mapped[str | None] = mapped_column(Text)
    custom_fields: Mapped[dict] = mapped_column(default=dict)

    owners: Mapped[list["PropertyOwner"]] = relationship(back_populates="property", order_by="PropertyOwner.created_at")
    assignments: Mapped[list["PropertyAssignment"]] = relationship(cascade="all, delete-orphan")


class PropertyAssignment(IdMixin, TimestampMixin, Base):
    __tablename__ = "property_assignments"
    __table_args__ = (UniqueConstraint("property_id", "user_id", name="uq_property_assignment"),)

    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(40), default="member")


class PropertyOwner(IdMixin, TimestampMixin, ActorMixin, Base):
    """Ownership lives on the relationship. Rows are closed (valid_to) rather than overwritten."""

    __tablename__ = "property_owners"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("owners.id"), index=True)
    ownership_type: Mapped[str] = mapped_column(String(20), default="sole")
    share_percent: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    record_reference: Mapped[str | None] = mapped_column(String(300))
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("documents.id", use_alter=True, name="fk_property_owner_source_doc"), nullable=True
    )
    valid_from: Mapped[date | None]
    valid_to: Mapped[date | None]
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    ended_reason: Mapped[str | None] = mapped_column(Text)
    verification_status: Mapped[str] = mapped_column(String(20), default="unverified")
    verified_by_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)
    verified_at: Mapped[datetime | None]
    supersedes_id: Mapped[uuid.UUID | None] = uuid_fk("property_owners.id", index=False)

    property: Mapped[Property] = relationship(back_populates="owners")
    owner: Mapped["Owner"] = relationship("Owner")  # noqa: F821

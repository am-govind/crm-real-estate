import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import ActorMixin, Base, IdMixin, TenantScopedMixin, TimestampMixin, utcnow, uuid_fk

MAP_FILE_KINDS = ("geojson", "kml", "pdf", "image")
GEOMETRY_STATUSES = ("draft", "submitted", "approved", "rejected", "superseded")


class MapUpload(IdMixin, TenantScopedMixin, Base):
    """Immutable original map upload. There are no update paths for these rows or their objects."""

    __tablename__ = "map_uploads"

    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    deal_id: Mapped[uuid.UUID | None] = uuid_fk("deals.id")
    file_kind: Mapped[str] = mapped_column(String(10))
    storage_key: Mapped[str] = mapped_column(String(600))
    filename: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(150))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    source_document_id: Mapped[uuid.UUID | None] = uuid_fk("documents.id", index=False)
    uploaded_by_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)
    uploaded_at: Mapped[datetime] = mapped_column(default=utcnow)


class MapProcessingRun(IdMixin, TimestampMixin, Base):
    """Processing state for an upload. Separate from the upload so the original stays immutable."""

    __tablename__ = "map_processing_runs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    upload_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("map_uploads.id"), index=True)
    background_job_id: Mapped[uuid.UUID | None] = uuid_fk("background_jobs.id", index=False)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    message: Mapped[str | None] = mapped_column(Text)
    extracted_geometry_ids: Mapped[list] = mapped_column(default=list)


class GeometryVersion(IdMixin, TimestampMixin, TenantScopedMixin, ActorMixin, Base):
    """Versioned GeoJSON geometry for a property. Only one approved version is active at a time."""

    __tablename__ = "geometry_versions"
    __table_args__ = (UniqueConstraint("property_id", "version_no", name="uq_geometry_version"),)

    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    geojson: Mapped[dict] = mapped_column()
    source: Mapped[str] = mapped_column(String(30))
    source_upload_id: Mapped[uuid.UUID | None] = uuid_fk("map_uploads.id")
    source_page: Mapped[int | None] = mapped_column(Integer)
    georeference: Mapped[dict] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    area_sqm: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    perimeter_m: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    calc_method: Mapped[str | None] = mapped_column(String(60))
    validation: Mapped[dict] = mapped_column(default=dict)
    confidence: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None]
    reviewed_by_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)
    reviewed_at: Mapped[datetime | None]
    review_note: Mapped[str | None] = mapped_column(Text)
    superseded_by_id: Mapped[uuid.UUID | None] = uuid_fk("geometry_versions.id", index=False)


class NearbyFeature(IdMixin, TenantScopedMixin, Base):
    """Derived, informational context from a map provider. Always carries source and confidence."""

    __tablename__ = "nearby_features"

    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str | None] = mapped_column(String(300))
    ref: Mapped[str | None] = mapped_column(String(60))
    distance_m: Mapped[float] = mapped_column(Float)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(60))
    confidence: Mapped[str] = mapped_column(String(20), default="medium")
    fetched_at: Mapped[datetime] = mapped_column(default=utcnow)
    raw: Mapped[dict] = mapped_column(default=dict)

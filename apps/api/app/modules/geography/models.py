import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin

GEO_LEVELS = ("state", "district", "tehsil", "village")


class GeoUnit(IdMixin, TimestampMixin, Base):
    """Administrative hierarchy. ``tenant_id`` null means a shared gazetteer entry.

    Level keys are fixed (state/district/tehsil/village); display labels are per-tenant terminology.
    """

    __tablename__ = "geo_units"
    __table_args__ = (UniqueConstraint("tenant_id", "parent_id", "level", "name", name="uq_geo_unit"),)

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("geo_units.id"), index=True)
    level: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(200))
    local_name: Mapped[str | None] = mapped_column(String(200))
    code: Mapped[str | None] = mapped_column(String(40))

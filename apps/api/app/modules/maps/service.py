import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.db import utcnow
from app.core.errors import Conflict, Forbidden, ValidationFailed
from app.core.permissions import P
from app.modules.audit import service as audit
from app.modules.maps.geometry import engine
from app.modules.maps.models import GeometryVersion
from app.modules.properties.models import Property

INFORMATIONAL_NOTICE = (
    "Map-derived information is informational until approved by a qualified reviewer "
    "and does not by itself prove legal title."
)


def _next_version(session: Session, property_id: uuid.UUID) -> int:
    return (session.scalar(select(func.max(GeometryVersion.version_no)).where(GeometryVersion.property_id == property_id)) or 0) + 1


def create_draft(
    session: Session,
    ctx: RequestContext | None,
    *,
    tenant_id: uuid.UUID,
    prop: Property,
    geometry: dict,
    source: str,
    source_upload_id: uuid.UUID | None = None,
    source_page: int | None = None,
    georeference: dict | None = None,
    confidence: str | None = None,
    notes: str | None = None,
) -> GeometryVersion:
    """Creates a new draft version. Never changes the active approved geometry."""
    result = engine.validate(geometry)
    area = perimeter = None
    if result.valid:
        area = Decimal(str(round(engine.area_sqm(geometry), 4)))
        perimeter = Decimal(str(round(engine.perimeter_m(geometry), 4)))
    gv = GeometryVersion(
        tenant_id=tenant_id, property_id=prop.id, version_no=_next_version(session, prop.id), geojson=geometry,
        source=source, source_upload_id=source_upload_id, source_page=source_page, georeference=georeference or {},
        status="draft", area_sqm=area, perimeter_m=perimeter, calc_method=engine.method,
        validation=result.as_dict(), confidence=confidence, notes=notes,
        created_by_id=ctx.user_id if ctx else None,
    )
    session.add(gv)
    session.flush()
    audit.record(
        session, ctx, "geometry.drafted", "property", prop.id, tenant_id=tenant_id,
        metadata={"geometry_id": str(gv.id), "version": gv.version_no, "source": source, "valid": result.valid,
                  "upload_id": str(source_upload_id) if source_upload_id else None},
    )
    return gv


def submit(session: Session, ctx: RequestContext, gv: GeometryVersion) -> GeometryVersion:
    if gv.status not in ("draft", "rejected"):
        raise Conflict(f"Geometry is {gv.status}")
    if not gv.validation.get("valid"):
        raise ValidationFailed("Fix validation errors before submitting", details=gv.validation)
    gv.status = "submitted"
    gv.submitted_at = utcnow()
    audit.record(session, ctx, "geometry.submitted", "property", gv.property_id, metadata={"geometry_id": str(gv.id)})
    return gv


def approve(session: Session, ctx: RequestContext, gv: GeometryVersion, prop: Property, *, note: str | None) -> GeometryVersion:
    ctx.require(P.GEOMETRY_APPROVE)
    if gv.status != "submitted":
        raise Conflict("Only submitted geometry can be approved")
    if gv.created_by_id == ctx.user_id and not ctx.is_system_admin:
        raise Forbidden("Reviewers cannot approve geometry they created")
    now = utcnow()
    previous = session.get(GeometryVersion, prop.active_geometry_id) if prop.active_geometry_id else None
    if previous and previous.status == "approved":
        previous.status = "superseded"
        previous.superseded_by_id = gv.id
    gv.status = "approved"
    gv.reviewed_by_id = ctx.user_id
    gv.reviewed_at = now
    gv.review_note = note
    prop.active_geometry_id = gv.id
    if prop.latitude is None or prop.longitude is None:
        lng, lat = engine.centroid(gv.geojson)
        prop.latitude = Decimal(str(round(lat, 6)))
        prop.longitude = Decimal(str(round(lng, 6)))
        audit.record(session, ctx, "property.location_from_geometry", "property", prop.id, metadata={"geometry_id": str(gv.id)})
    audit.record(
        session, ctx, "geometry.approved", "property", prop.id,
        metadata={"geometry_id": str(gv.id), "superseded": str(previous.id) if previous else None, "note": note},
    )
    return gv


def reject(session: Session, ctx: RequestContext, gv: GeometryVersion, *, note: str) -> GeometryVersion:
    ctx.require(P.GEOMETRY_APPROVE)
    if gv.status != "submitted":
        raise Conflict("Only submitted geometry can be rejected")
    gv.status = "rejected"
    gv.reviewed_by_id = ctx.user_id
    gv.reviewed_at = utcnow()
    gv.review_note = note
    audit.record(session, ctx, "geometry.rejected", "property", gv.property_id, metadata={"geometry_id": str(gv.id), "note": note})
    return gv

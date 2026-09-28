import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.core.db import utcnow
from app.core.deps import DB, requires
from app.core.errors import NotFound
from app.core.pagination import Page, PageParams, paginate
from app.core.permissions import P
from app.core.sequences import take
from app.core.tenancy import get_scoped, scoped
from app.modules.audit import service as audit
from app.modules.geography.models import GeoUnit
from app.modules.identity.models import TenantMembership
from app.modules.properties import service
from app.modules.properties.access import get_visible_property, visible_clause
from app.modules.properties.models import Property, PropertyAssignment, PropertyOwner
from app.modules.properties.schemas import (
    AssignmentIn,
    AssignmentOut,
    MapPin,
    OwnershipSummary,
    PropertyCreate,
    PropertyOut,
    PropertyOwnerCreate,
    PropertyOwnerEnd,
    PropertyOwnerOut,
    PropertyOwnerVerify,
    PropertyUpdate,
)

router = APIRouter(prefix="/properties", tags=["properties"])

STATUS_COLORS = {
    "prospect": "#6b7280",
    "in_pipeline": "#2563eb",
    "acquired": "#16a34a",
    "dropped": "#dc2626",
    "on_hold": "#d97706",
}


@router.get("", response_model=Page[PropertyOut])
def list_properties(
    db: DB,
    q: str | None = None,
    status: list[str] | None = Query(None),
    land_type: list[str] | None = Query(None),
    state_id: uuid.UUID | None = None,
    district_id: uuid.UUID | None = None,
    tehsil_id: uuid.UUID | None = None,
    village_id: uuid.UUID | None = None,
    title_status: str | None = None,
    road_access: str | None = None,
    owner_id: uuid.UUID | None = None,
    min_area_sqm: Decimal | None = None,
    max_area_sqm: Decimal | None = None,
    assigned_to_me: bool = False,
    page: PageParams = Depends(),
    ctx=requires(P.PROPERTY_READ),
):
    stmt = scoped(Property, ctx).where(visible_clause(ctx))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Property.name.ilike(like),
                Property.code.ilike(like),
                Property.survey_number.ilike(like),
                Property.khasra_number.ilike(like),
                Property.khata_number.ilike(like),
                Property.address.ilike(like),
                Property.village_id.in_(select(GeoUnit.id).where(GeoUnit.name.ilike(like))),
            )
        )
    if status:
        stmt = stmt.where(Property.status.in_(status))
    if land_type:
        stmt = stmt.where(Property.land_type.in_(land_type))
    for col, val in (
        (Property.state_id, state_id), (Property.district_id, district_id),
        (Property.tehsil_id, tehsil_id), (Property.village_id, village_id),
        (Property.title_status, title_status), (Property.road_access, road_access),
    ):
        if val is not None:
            stmt = stmt.where(col == val)
    if owner_id:
        stmt = stmt.where(
            Property.id.in_(select(PropertyOwner.property_id).where(PropertyOwner.owner_id == owner_id, PropertyOwner.is_current.is_(True)))
        )
    if min_area_sqm is not None:
        stmt = stmt.where(Property.area_sqm_derived >= min_area_sqm)
    if max_area_sqm is not None:
        stmt = stmt.where(Property.area_sqm_derived <= max_area_sqm)
    if assigned_to_me:
        stmt = stmt.where(Property.id.in_(select(PropertyAssignment.property_id).where(PropertyAssignment.user_id == ctx.user_id)))
    items, total = paginate(db, stmt.order_by(Property.updated_at.desc()), page)
    return {"items": items, "total": total, "limit": page.limit, "offset": page.offset}


@router.post("", response_model=PropertyOut, status_code=201)
def create_property(body: PropertyCreate, db: DB, ctx=requires(P.PROPERTY_WRITE)):
    prop = Property(tenant_id=ctx.tenant_id, code=take(db, ctx.tenant_id, "property"), created_by_id=ctx.user_id, **body.model_dump())
    service.validate_geography(db, ctx, prop)
    service.refresh_derived(prop)
    db.add(prop)
    db.flush()
    db.add(PropertyAssignment(property_id=prop.id, user_id=ctx.user_id, role="creator"))
    audit.record(db, ctx, "property.created", "property", prop.id, changes=audit.snapshot(prop))
    return prop


@router.get("/map-pins", response_model=list[MapPin])
def map_pins(
    db: DB,
    min_lat: Decimal | None = None,
    min_lng: Decimal | None = None,
    max_lat: Decimal | None = None,
    max_lng: Decimal | None = None,
    status: list[str] | None = Query(None),
    ctx=requires(P.PROPERTY_READ),
):
    from app.modules.deals.models import Deal
    from app.modules.workflows.models import StageDefinition

    stmt = scoped(Property, ctx).where(
        visible_clause(ctx), Property.latitude.is_not(None), Property.longitude.is_not(None)
    )
    if None not in (min_lat, min_lng, max_lat, max_lng):
        stmt = stmt.where(
            Property.latitude.between(min_lat, max_lat), Property.longitude.between(min_lng, max_lng)
        )
    if status:
        stmt = stmt.where(Property.status.in_(status))
    props = list(db.scalars(stmt.limit(5000)))
    deals = {
        d.property_id: (d, s)
        for d, s in db.execute(
            select(Deal, StageDefinition)
            .join(StageDefinition, StageDefinition.id == Deal.current_stage_id, isouter=True)
            .where(Deal.tenant_id == ctx.tenant_id, Deal.is_active.is_(True), Deal.property_id.in_([p.id for p in props]))
        ).all()
    }
    pins = []
    for p in props:
        deal, stage = deals.get(p.id, (None, None))
        color = (stage.color if stage and stage.color else None) or STATUS_COLORS.get(p.status, "#6b7280")
        pins.append(
            MapPin(
                property_id=p.id, code=p.code, name=p.name, latitude=p.latitude, longitude=p.longitude, status=p.status,
                deal_id=deal.id if deal else None, deal_stage_key=stage.key if stage else None,
                deal_stage_name=stage.name if stage else None, color=color, has_geometry=p.active_geometry_id is not None,
            )
        )
    return pins


@router.get("/{property_id}", response_model=PropertyOut)
def get_property(property_id: uuid.UUID, db: DB, ctx=requires(P.PROPERTY_READ)):
    return get_visible_property(db, property_id, ctx)


@router.patch("/{property_id}", response_model=PropertyOut)
def update_property(property_id: uuid.UUID, body: PropertyUpdate, db: DB, ctx=requires(P.PROPERTY_WRITE)):
    prop = get_visible_property(db, property_id, ctx)
    before = audit.snapshot(prop)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(prop, k, v)
    service.validate_geography(db, ctx, prop)
    service.refresh_derived(prop)
    db.flush()
    audit.record_update(db, ctx, "property", prop, before)
    return prop


# ---- Ownership ----


@router.get("/{property_id}/owners", response_model=list[PropertyOwnerOut])
def list_property_owners(property_id: uuid.UUID, db: DB, include_history: bool = False, ctx=requires(P.PROPERTY_READ)):
    prop = get_visible_property(db, property_id, ctx)
    stmt = (
        select(PropertyOwner)
        .where(PropertyOwner.property_id == prop.id)
        .options(selectinload(PropertyOwner.owner))
        .order_by(PropertyOwner.created_at)
    )
    if not include_history:
        stmt = stmt.where(PropertyOwner.is_current.is_(True))
    return list(db.scalars(stmt))


@router.get("/{property_id}/ownership-summary", response_model=OwnershipSummary)
def get_ownership_summary(property_id: uuid.UUID, db: DB, ctx=requires(P.PROPERTY_READ)):
    return service.ownership_summary(db, get_visible_property(db, property_id, ctx))


@router.post("/{property_id}/owners", response_model=PropertyOwnerOut, status_code=201)
def add_property_owner(property_id: uuid.UUID, body: PropertyOwnerCreate, db: DB, ctx=requires(P.PROPERTY_WRITE)):
    prop = get_visible_property(db, property_id, ctx)
    return service.add_owner(db, ctx, prop, body)


def _get_po(db, prop: Property, po_id: uuid.UUID) -> PropertyOwner:
    po = db.get(PropertyOwner, po_id)
    if po is None or po.property_id != prop.id:
        raise NotFound("Ownership record not found")
    return po


@router.post("/{property_id}/owners/{po_id}/end", response_model=PropertyOwnerOut)
def end_property_owner(property_id: uuid.UUID, po_id: uuid.UUID, body: PropertyOwnerEnd, db: DB, ctx=requires(P.PROPERTY_WRITE)):
    prop = get_visible_property(db, property_id, ctx)
    return service.end_ownership(db, ctx, prop, _get_po(db, prop, po_id), reason=body.reason, valid_to=body.valid_to)


@router.post("/{property_id}/owners/{po_id}/verification", response_model=PropertyOwnerOut)
def verify_property_owner(
    property_id: uuid.UUID, po_id: uuid.UUID, body: PropertyOwnerVerify, db: DB, ctx=requires(P.OWNER_VERIFY)
):
    prop = get_visible_property(db, property_id, ctx)
    po = _get_po(db, prop, po_id)
    before = po.verification_status
    po.verification_status = body.status
    po.verified_by_id = ctx.user_id if body.status != "pending" else None
    po.verified_at = utcnow() if body.status != "pending" else None
    audit.record(
        db, ctx, "property.ownership_verification_changed", "property", prop.id,
        changes={"verification_status": {"from": before, "to": body.status}},
        metadata={"property_owner_id": str(po.id), "note": body.note},
    )
    return po


# ---- Assignments ----


@router.get("/{property_id}/assignments", response_model=list[AssignmentOut])
def list_assignments(property_id: uuid.UUID, db: DB, ctx=requires(P.PROPERTY_READ)):
    return get_visible_property(db, property_id, ctx).assignments


@router.post("/{property_id}/assignments", response_model=AssignmentOut, status_code=201)
def add_assignment(property_id: uuid.UUID, body: AssignmentIn, db: DB, ctx=requires(P.PROPERTY_ASSIGN)):
    prop = get_scoped(db, Property, property_id, ctx)
    member = db.scalar(
        select(TenantMembership).where(TenantMembership.tenant_id == ctx.tenant_id, TenantMembership.user_id == body.user_id)
    )
    if member is None:
        raise NotFound("User is not a member of this tenant")
    existing = next((a for a in prop.assignments if a.user_id == body.user_id), None)
    if existing:
        existing.role = body.role
        return existing
    a = PropertyAssignment(property_id=prop.id, user_id=body.user_id, role=body.role)
    db.add(a)
    db.flush()
    audit.record(db, ctx, "property.assigned", "property", prop.id, metadata=body.model_dump(mode="json"))
    return a


@router.delete("/{property_id}/assignments/{user_id}", status_code=204)
def remove_assignment(property_id: uuid.UUID, user_id: uuid.UUID, db: DB, ctx=requires(P.PROPERTY_ASSIGN)):
    prop = get_scoped(db, Property, property_id, ctx)
    a = next((a for a in prop.assignments if a.user_id == user_id), None)
    if a is None:
        raise NotFound("Assignment not found")
    db.delete(a)
    audit.record(db, ctx, "property.unassigned", "property", prop.id, metadata={"user_id": str(user_id)})

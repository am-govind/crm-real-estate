import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.core.deps import DB, TenantCtx, requires
from app.core.errors import NotFound, ValidationFailed
from app.core.permissions import P
from app.core.schemas import ORMModel
from app.modules.audit import service as audit
from app.modules.geography.models import GEO_LEVELS, GeoUnit

router = APIRouter(prefix="/geo-units", tags=["geography"])


class GeoUnitIn(BaseModel):
    level: str
    name: str = Field(min_length=1, max_length=200)
    local_name: str | None = None
    code: str | None = None
    parent_id: uuid.UUID | None = None


class GeoUnitOut(ORMModel):
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    parent_id: uuid.UUID | None
    level: str
    name: str
    local_name: str | None
    code: str | None


@router.get("", response_model=list[GeoUnitOut])
def list_units(ctx: TenantCtx, db: DB, level: str | None = None, parent_id: uuid.UUID | None = None, q: str | None = None):
    stmt = select(GeoUnit).where(or_(GeoUnit.tenant_id.is_(None), GeoUnit.tenant_id == ctx.tenant_id))
    if level:
        stmt = stmt.where(GeoUnit.level == level)
    if parent_id:
        stmt = stmt.where(GeoUnit.parent_id == parent_id)
    if q:
        stmt = stmt.where(GeoUnit.name.ilike(f"%{q}%"))
    return list(db.scalars(stmt.order_by(GeoUnit.name).limit(500)))


@router.post("", response_model=GeoUnitOut, status_code=201)
def create_unit(body: GeoUnitIn, db: DB, ctx=requires(P.GEOGRAPHY_MANAGE)):
    if body.level not in GEO_LEVELS:
        raise ValidationFailed("Unknown level", details={"allowed": list(GEO_LEVELS)})
    idx = GEO_LEVELS.index(body.level)
    if idx > 0:
        if body.parent_id is None:
            raise ValidationFailed(f"A {body.level} requires a parent {GEO_LEVELS[idx - 1]}")
        parent = db.get(GeoUnit, body.parent_id)
        if parent is None or parent.tenant_id not in (None, ctx.tenant_id):
            raise NotFound("Parent not found")
        if parent.level != GEO_LEVELS[idx - 1]:
            raise ValidationFailed(f"Parent must be a {GEO_LEVELS[idx - 1]}")
    unit = GeoUnit(tenant_id=ctx.tenant_id, **body.model_dump())
    db.add(unit)
    db.flush()
    audit.record(db, ctx, "geo_unit.created", "geo_unit", unit.id, metadata=body.model_dump(mode="json"))
    return unit

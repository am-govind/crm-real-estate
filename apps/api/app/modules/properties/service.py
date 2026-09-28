from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.measure import derive_area_sqm, derived_decimal
from app.core.tenancy import get_scoped
from app.modules.audit import service as audit
from app.modules.geography.models import GEO_LEVELS, GeoUnit
from app.modules.owners.models import Owner
from app.modules.properties.models import Property, PropertyOwner
from app.modules.properties.schemas import OwnershipSummary, PropertyOwnerCreate

HUNDRED = Decimal("100")


def refresh_derived(prop: Property) -> None:
    prop.area_sqm_derived = derived_decimal(derive_area_sqm(prop.area_value, prop.area_unit))


def validate_geography(session: Session, ctx: RequestContext, prop: Property) -> None:
    chain = [prop.state_id, prop.district_id, prop.tehsil_id, prop.village_id]
    previous = None
    for level, unit_id in zip(GEO_LEVELS, chain, strict=True):
        if unit_id is None:
            previous = None
            continue
        unit = session.get(GeoUnit, unit_id)
        if unit is None or unit.tenant_id not in (None, ctx.tenant_id):
            raise NotFound(f"Unknown {level}")
        if unit.level != level:
            raise ValidationFailed(f"{level}_id must reference a {level}")
        if previous is not None and unit.parent_id != previous:
            raise ValidationFailed(f"{level} does not belong to the selected parent")
        previous = unit.id


def current_owners(session: Session, prop: Property) -> list[PropertyOwner]:
    return list(
        session.scalars(select(PropertyOwner).where(PropertyOwner.property_id == prop.id, PropertyOwner.is_current.is_(True)))
    )


def ownership_summary(session: Session, prop: Property) -> OwnershipSummary:
    rows = current_owners(session, prop)
    total = sum((r.share_percent or Decimal("0") for r in rows), Decimal("0"))
    warnings: list[str] = []
    if not rows:
        warnings.append("No current owners recorded")
    sole_without_share = len(rows) == 1 and rows[0].share_percent is None and rows[0].ownership_type == "sole"
    missing_shares = [r for r in rows if r.share_percent is None]
    if missing_shares and not sole_without_share:
        warnings.append(f"{len(missing_shares)} owner(s) have no share recorded")
    if total > HUNDRED:
        warnings.append(f"Shares total {total}% which exceeds 100%")
    elif rows and not sole_without_share and total < HUNDRED:
        warnings.append(f"Shares total {total}%; {HUNDRED - total}% unaccounted for")
    verified = sum(1 for r in rows if r.verification_status == "verified")
    if rows and verified < len(rows):
        warnings.append(f"{len(rows) - verified} ownership record(s) not verified")
    complete = bool(rows) and (sole_without_share or (total == HUNDRED and not missing_shares))
    return OwnershipSummary(
        total_share_percent=total if not sole_without_share else HUNDRED,
        current_owner_count=len(rows),
        verified_owner_count=verified,
        is_complete=complete,
        warnings=warnings,
    )


def add_owner(session: Session, ctx: RequestContext, prop: Property, body: PropertyOwnerCreate) -> PropertyOwner:
    owner = get_scoped(session, Owner, body.owner_id, ctx, label="Owner")
    current = current_owners(session, prop)

    superseded: PropertyOwner | None = None
    if body.supersedes_id:
        superseded = next((r for r in current if r.id == body.supersedes_id), None)
        if superseded is None:
            raise NotFound("Superseded ownership record not found or not current")

    if any(r.owner_id == owner.id and r is not superseded for r in current):
        raise Conflict("Owner already holds a current ownership record on this property")

    remaining = [r for r in current if r is not superseded]
    total = sum((r.share_percent or Decimal("0") for r in remaining), Decimal("0")) + (body.share_percent or Decimal("0"))
    if total > HUNDRED:
        raise ValidationFailed("Total ownership would exceed 100%", details={"total": str(total)})

    if superseded is not None:
        superseded.is_current = False
        superseded.valid_to = body.valid_from or date.today()
        superseded.ended_reason = "Superseded by new ownership record"

    po = PropertyOwner(
        tenant_id=ctx.tenant_id,
        property_id=prop.id,
        created_by_id=ctx.user_id,
        **body.model_dump(),
    )
    session.add(po)
    session.flush()
    audit.record(
        session, ctx, "property.owner_added", "property", prop.id,
        changes={"ownership": audit.snapshot(po)},
        metadata={"supersedes": str(superseded.id) if superseded else None},
    )
    return po


def end_ownership(
    session: Session, ctx: RequestContext, prop: Property, po: PropertyOwner, *, reason: str, valid_to: date | None
) -> PropertyOwner:
    if not po.is_current:
        raise Conflict("Ownership record is already ended")
    po.is_current = False
    po.valid_to = valid_to or date.today()
    po.ended_reason = reason
    audit.record(
        session, ctx, "property.owner_ended", "property", prop.id,
        metadata={"property_owner_id": str(po.id), "reason": reason, "valid_to": po.valid_to},
    )
    return po

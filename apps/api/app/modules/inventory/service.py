import uuid
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.db import utcnow
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.measure import derive_area_sqm, derive_length_m, derived_decimal
from app.core.permissions import P
from app.core.sequences import peek, take
from app.core.tenancy import get_scoped, scoped
from app.modules.audit import service as audit
from app.modules.documents.models import Document
from app.modules.inventory.models import SiteRecord, SiteRecordRevision
from app.modules.maps.geometry import haversine_m
from app.modules.maps.models import MapUpload
from app.modules.properties.models import Property


def _uuid(value) -> uuid.UUID | None:
    return uuid.UUID(str(value)) if value else None


def _primary_area(data: dict) -> dict | None:
    return data.get("area") if data["property_type"] == "land_plot" else data.get("total_area")


def compute_derived(data: dict) -> dict:
    """Explicitly derived values; the original measurements in ``data`` are never modified."""
    derived: dict = {}
    area = _primary_area(data)
    if area:
        d = derive_area_sqm(Decimal(area["value"]), area["unit"])
        if d:
            derived["area_sqm"] = d
    if data["property_type"] == "land_plot":
        length, width = data.get("length"), data.get("width")
        for name, m in (("length_m", length), ("width_m", width)):
            if m:
                d = derive_length_m(Decimal(m["value"]), m["unit"])
                if d:
                    derived[name] = d
        if not area and length and width and length["unit"] == width["unit"]:
            product = Decimal(length["value"]) * Decimal(width["value"])
            derived["area_from_dimensions"] = {
                "value": format(product, "f"), "unit": f"sq{length['unit']}", "derived": True,
                "formula": "length * width (rectangular approximation)",
                "sources": {"length": length, "width": width},
            }
            as_sqm = derive_area_sqm(product, {"ft": "sqft", "m": "sqm", "yd": "sqyd"}.get(length["unit"], ""))
            if as_sqm:
                as_sqm["formula"] = f"(length * width) then {as_sqm['formula']}"
                derived["area_sqm"] = as_sqm
    return derived


def _validate_refs(session: Session, ctx: RequestContext, data: dict) -> None:
    src, loc = data.get("source") or {}, data.get("location") or {}
    if src.get("document_id"):
        get_scoped(session, Document, _uuid(src["document_id"]), ctx, label="Source document")
    if src.get("map_upload_id"):
        get_scoped(session, MapUpload, _uuid(src["map_upload_id"]), ctx, label="Source map")
    if loc.get("property_id"):
        get_scoped(session, Property, _uuid(loc["property_id"]), ctx, label="Property")


def suggest_matches(session: Session, ctx: RequestContext, data: dict, *, exclude_id=None, limit: int = 10) -> list[dict]:
    """Suggestions only. The user decides whether an entry is new or an update; nothing is merged."""
    src, loc = data.get("source") or {}, data.get("location") or {}
    label = data.get("plot_label") or data.get("unit_number")
    stmt = scoped(SiteRecord, ctx).where(SiteRecord.property_type == data["property_type"])
    if exclude_id:
        stmt = stmt.where(SiteRecord.id != exclude_id)
    clauses = []
    if src.get("document_id"):
        clauses.append(SiteRecord.source_document_id == _uuid(src["document_id"]))
    if src.get("map_upload_id"):
        clauses.append(SiteRecord.source_map_upload_id == _uuid(src["map_upload_id"]))
    if label:
        clauses.append(func.lower(SiteRecord.plot_label) == label.lower())
        clauses.append(func.lower(SiteRecord.unit_number) == label.lower())
    if loc.get("property_id"):
        clauses.append(SiteRecord.property_id == _uuid(loc["property_id"]))
    if loc.get("latitude") is not None and loc.get("longitude") is not None:
        lat, lng = loc["latitude"], loc["longitude"]
        clauses.append(SiteRecord.latitude.between(lat - 0.01, lat + 0.01) & SiteRecord.longitude.between(lng - 0.01, lng + 0.01))
    if not clauses:
        return []
    candidates = session.scalars(stmt.where(or_(*clauses)).limit(200)).all()

    area_sqm = derived_decimal(compute_derived(data).get("area_sqm"))
    results = []
    for c in candidates:
        score, reasons = 0.0, []
        same_source = (src.get("document_id") and str(c.source_document_id) == str(src["document_id"])) or (
            src.get("map_upload_id") and str(c.source_map_upload_id) == str(src["map_upload_id"])
        )
        if same_source:
            score += 0.3
            reasons.append("Same source map/document")
        if label and label.lower() in ((c.plot_label or "").lower(), (c.unit_number or "").lower()):
            score += 0.35
            reasons.append(f"Same label '{label}'")
        if loc.get("property_id") and str(c.property_id) == str(loc["property_id"]):
            score += 0.1
            reasons.append("Same property")
        if loc.get("latitude") is not None and c.latitude is not None:
            dist = haversine_m(loc["longitude"], loc["latitude"], c.longitude, c.latitude)
            if dist < 50:
                score += 0.15
                reasons.append(f"Within {dist:.0f} m")
        if area_sqm and c.area_sqm_derived:
            diff = abs(area_sqm - c.area_sqm_derived) / max(area_sqm, Decimal("1"))
            if diff <= Decimal("0.02"):
                score += 0.1
                reasons.append("Area within 2%")
        if score > 0:
            results.append({"site_id": c.id, "site_code": c.site_code, "score": round(min(score, 1.0), 2),
                            "reasons": reasons, "approval_state": c.approval_state})
    return sorted(results, key=lambda r: -r["score"])[:limit]


def create_site(session: Session, ctx: RequestContext, *, confirmed_code: str, data: dict, considered: list, note: str | None) -> SiteRecord:
    ctx.require(P.INVENTORY_WRITE)
    tenant_id = ctx.require_tenant()
    expected = peek(session, tenant_id, "site")
    if confirmed_code != expected:
        raise Conflict("The prefilled Site ID is no longer available; confirm the new suggestion", details={"suggested_site_code": expected})
    _validate_refs(session, ctx, data)
    code = take(session, tenant_id, "site")
    record = SiteRecord(tenant_id=tenant_id, site_code=code, property_type=data["property_type"], approval_state="pending", created_by_id=ctx.user_id)
    session.add(record)
    session.flush()
    rev = SiteRecordRevision(
        tenant_id=tenant_id, site_record_id=record.id, revision_no=1, change_type="create", data=data,
        derived=compute_derived(data), change_note=note, submitted_by_id=ctx.user_id,
        match_decision={"decision": "new", "considered_candidates": [str(c) for c in considered]},
    )
    session.add(rev)
    session.flush()
    record.pending_revision_id = rev.id
    audit.record(session, ctx, "inventory.site_created", "site_record", record.id,
                 metadata={"site_code": code, "revision_id": str(rev.id), "considered_candidates": [str(c) for c in considered]})
    return record


def propose_revision(session: Session, ctx: RequestContext, record: SiteRecord, *, data: dict, note: str, considered: list) -> SiteRecordRevision:
    ctx.require(P.INVENTORY_WRITE)
    if record.pending_revision_id:
        raise Conflict("This site already has a pending change awaiting approval")
    if data["property_type"] != record.property_type:
        raise Conflict("Property type cannot change; register a new site instead")
    _validate_refs(session, ctx, data)
    next_no = (session.scalar(select(func.max(SiteRecordRevision.revision_no)).where(SiteRecordRevision.site_record_id == record.id)) or 0) + 1
    rev = SiteRecordRevision(
        tenant_id=record.tenant_id, site_record_id=record.id, revision_no=next_no, change_type="update", data=data,
        derived=compute_derived(data), change_note=note, submitted_by_id=ctx.user_id,
        match_decision={"decision": "update", "considered_candidates": [str(c) for c in considered]},
    )
    session.add(rev)
    session.flush()
    record.pending_revision_id = rev.id
    audit.record(session, ctx, "inventory.revision_proposed", "site_record", record.id, metadata={"revision_id": str(rev.id), "note": note})
    return rev


def _apply(record: SiteRecord, rev: SiteRecordRevision) -> None:
    d, loc, src = rev.data, rev.data.get("location") or {}, rev.data.get("source") or {}
    area = _primary_area(d)
    record.status = d.get("status")
    record.property_id = _uuid(loc.get("property_id"))
    record.project_name = loc.get("project_name")
    record.village_id = _uuid(loc.get("village_id"))
    record.district_id = _uuid(loc.get("district_id"))
    record.location_text = loc.get("address") or loc.get("description")
    record.latitude = loc.get("latitude")
    record.longitude = loc.get("longitude")
    record.source_document_id = _uuid(src.get("document_id"))
    record.source_map_upload_id = _uuid(src.get("map_upload_id"))
    record.plot_label = d.get("plot_label")
    record.unit_number = d.get("unit_number")
    record.area_value = Decimal(area["value"]) if area else None
    record.area_unit = area["unit"] if area else None
    record.area_sqm_derived = derived_decimal(rev.derived.get("area_sqm"))
    record.length_m_derived = derived_decimal(rev.derived.get("length_m"))
    record.width_m_derived = derived_decimal(rev.derived.get("width_m"))
    record.rooms = d.get("rooms")
    record.bathrooms = d.get("bathrooms")
    record.floor = d.get("floor")
    record.usage_type = d.get("usage_type")


def get_revision(session: Session, ctx: RequestContext, revision_id) -> tuple[SiteRecord, SiteRecordRevision]:
    rev = session.get(SiteRecordRevision, revision_id)
    if rev is None or rev.tenant_id != ctx.require_tenant():
        raise NotFound("Revision not found")
    return session.get(SiteRecord, rev.site_record_id), rev


def approve(session: Session, ctx: RequestContext, record: SiteRecord, rev: SiteRecordRevision, note: str | None) -> SiteRecord:
    ctx.require(P.INVENTORY_APPROVE)
    if rev.status != "pending" or record.pending_revision_id != rev.id:
        raise Conflict("Only the pending revision can be approved")
    if rev.submitted_by_id == ctx.user_id and not ctx.is_system_admin:
        raise Forbidden("Changes must be approved by someone other than the submitter")
    now = utcnow()
    if record.active_revision_id:
        previous = session.get(SiteRecordRevision, record.active_revision_id)
        if previous:
            previous.status = "superseded"
    rev.status = "approved"
    rev.reviewed_by_id = ctx.user_id
    rev.reviewed_at = now
    rev.review_note = note
    record.active_revision_id = rev.id
    record.pending_revision_id = None
    record.approval_state = "approved"
    _apply(record, rev)
    audit.record(session, ctx, "inventory.revision_approved", "site_record", record.id, metadata={"revision_id": str(rev.id), "note": note})
    return record


def reject(session: Session, ctx: RequestContext, record: SiteRecord, rev: SiteRecordRevision, note: str) -> SiteRecord:
    ctx.require(P.INVENTORY_APPROVE)
    if rev.status != "pending" or record.pending_revision_id != rev.id:
        raise Conflict("Only the pending revision can be rejected")
    rev.status = "rejected"
    rev.reviewed_by_id = ctx.user_id
    rev.reviewed_at = utcnow()
    rev.review_note = note
    record.pending_revision_id = None
    if record.active_revision_id is None:
        record.approval_state = "rejected"
    audit.record(session, ctx, "inventory.revision_rejected", "site_record", record.id, metadata={"revision_id": str(rev.id), "note": note})
    return record

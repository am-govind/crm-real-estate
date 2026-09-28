import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select

from app.core.deps import DB, requires
from app.core.pagination import Page, PageParams, paginate
from app.core.permissions import P
from app.core.sequences import peek
from app.core.tenancy import get_scoped, scoped
from app.modules.inventory import service
from app.modules.inventory.models import SiteRecord, SiteRecordRevision
from app.modules.inventory.schemas import (
    MatchCandidate,
    MatchQuery,
    RejectIn,
    RevisionCreate,
    RevisionOut,
    ReviewIn,
    SiteCreate,
    SiteDetail,
    SiteOut,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _detail(db, record: SiteRecord) -> SiteDetail:
    history = db.scalars(
        select(SiteRecordRevision).where(SiteRecordRevision.site_record_id == record.id).order_by(SiteRecordRevision.revision_no.desc())
    ).all()
    by_id = {r.id: r for r in history}
    out = SiteDetail.model_validate(record)
    out.history = [RevisionOut.model_validate(r) for r in history]
    if record.active_revision_id in by_id:
        out.active_revision = RevisionOut.model_validate(by_id[record.active_revision_id])
    if record.pending_revision_id in by_id:
        out.pending_revision = RevisionOut.model_validate(by_id[record.pending_revision_id])
    return out


@router.get("/next-site-id")
def next_site_id(db: DB, ctx=requires(P.INVENTORY_WRITE)):
    return {"site_code": peek(db, ctx.tenant_id, "site")}


@router.post("/match-suggestions", response_model=list[MatchCandidate])
def match_suggestions(body: MatchQuery, db: DB, ctx=requires(P.INVENTORY_READ)):
    return service.suggest_matches(db, ctx, body.data.model_dump(mode="json"), exclude_id=body.exclude_site_id)


@router.get("/sites", response_model=Page[SiteOut])
def search_sites(
    db: DB,
    q: str | None = None,
    site_code: str | None = None,
    property_type: list[str] | None = Query(None),
    status: list[str] | None = Query(None),
    approval_state: list[str] | None = Query(None),
    include_unapproved: bool = False,
    property_id: uuid.UUID | None = None,
    source_document_id: uuid.UUID | None = None,
    source_map_upload_id: uuid.UUID | None = None,
    plot_label: str | None = None,
    village_id: uuid.UUID | None = None,
    district_id: uuid.UUID | None = None,
    min_area_sqm: Decimal | None = None,
    max_area_sqm: Decimal | None = None,
    min_length_m: Decimal | None = None,
    min_width_m: Decimal | None = None,
    rooms: int | None = None,
    min_rooms: int | None = None,
    floor: str | None = None,
    page: PageParams = Depends(),
    ctx=requires(P.INVENTORY_READ),
):
    stmt = scoped(SiteRecord, ctx)
    if approval_state and (include_unapproved or ctx.has(P.INVENTORY_APPROVE)):
        stmt = stmt.where(SiteRecord.approval_state.in_(approval_state))
    elif not include_unapproved:
        stmt = stmt.where(SiteRecord.approval_state == "approved")
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(SiteRecord.site_code.ilike(like), SiteRecord.plot_label.ilike(like), SiteRecord.unit_number.ilike(like),
                              SiteRecord.project_name.ilike(like), SiteRecord.location_text.ilike(like)))
    if site_code:
        stmt = stmt.where(SiteRecord.site_code == site_code.upper())
    if property_type:
        stmt = stmt.where(SiteRecord.property_type.in_(property_type))
    if status:
        stmt = stmt.where(SiteRecord.status.in_(status))
    for col, val in (
        (SiteRecord.property_id, property_id), (SiteRecord.source_document_id, source_document_id),
        (SiteRecord.source_map_upload_id, source_map_upload_id), (SiteRecord.village_id, village_id),
        (SiteRecord.district_id, district_id), (SiteRecord.rooms, rooms), (SiteRecord.floor, floor),
    ):
        if val is not None:
            stmt = stmt.where(col == val)
    if plot_label:
        stmt = stmt.where(SiteRecord.plot_label.ilike(plot_label))
    if min_area_sqm is not None:
        stmt = stmt.where(SiteRecord.area_sqm_derived >= min_area_sqm)
    if max_area_sqm is not None:
        stmt = stmt.where(SiteRecord.area_sqm_derived <= max_area_sqm)
    if min_length_m is not None:
        stmt = stmt.where(SiteRecord.length_m_derived >= min_length_m)
    if min_width_m is not None:
        stmt = stmt.where(SiteRecord.width_m_derived >= min_width_m)
    if min_rooms is not None:
        stmt = stmt.where(SiteRecord.rooms >= min_rooms)
    items, total = paginate(db, stmt.order_by(SiteRecord.site_code), page)
    return {"items": items, "total": total, "limit": page.limit, "offset": page.offset}


@router.post("/sites", response_model=SiteDetail, status_code=201)
def create_site(body: SiteCreate, db: DB, ctx=requires(P.INVENTORY_WRITE)):
    record = service.create_site(
        db, ctx, confirmed_code=body.confirmed_site_code, data=body.data.model_dump(mode="json"),
        considered=body.considered_candidates, note=body.change_note,
    )
    return _detail(db, record)


@router.get("/sites/{site_id}", response_model=SiteDetail)
def get_site(site_id: uuid.UUID, db: DB, ctx=requires(P.INVENTORY_READ)):
    return _detail(db, get_scoped(db, SiteRecord, site_id, ctx, label="Site"))


@router.post("/sites/{site_id}/revisions", response_model=SiteDetail, status_code=201)
def propose_revision(site_id: uuid.UUID, body: RevisionCreate, db: DB, ctx=requires(P.INVENTORY_WRITE)):
    record = get_scoped(db, SiteRecord, site_id, ctx, label="Site")
    service.propose_revision(db, ctx, record, data=body.data.model_dump(mode="json"), note=body.change_note, considered=body.considered_candidates)
    return _detail(db, record)


@router.get("/revisions", response_model=list[RevisionOut])
def approval_queue(db: DB, status: str = "pending", ctx=requires(P.INVENTORY_READ)):
    return list(db.scalars(
        select(SiteRecordRevision)
        .where(SiteRecordRevision.tenant_id == ctx.tenant_id, SiteRecordRevision.status == status)
        .order_by(SiteRecordRevision.submitted_at)
        .limit(500)
    ))


@router.post("/revisions/{revision_id}/approve", response_model=SiteDetail)
def approve_revision(revision_id: uuid.UUID, body: ReviewIn, db: DB, ctx=requires(P.INVENTORY_APPROVE)):
    record, rev = service.get_revision(db, ctx, revision_id)
    return _detail(db, service.approve(db, ctx, record, rev, body.note))


@router.post("/revisions/{revision_id}/reject", response_model=SiteDetail)
def reject_revision(revision_id: uuid.UUID, body: RejectIn, db: DB, ctx=requires(P.INVENTORY_APPROVE)):
    record, rev = service.get_revision(db, ctx, revision_id)
    return _detail(db, service.reject(db, ctx, record, rev, body.note))

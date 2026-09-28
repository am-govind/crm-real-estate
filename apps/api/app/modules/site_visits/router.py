import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import select

from app.core.deps import DB, requires
from app.core.errors import NotFound
from app.core.pagination import Page, PageParams, paginate
from app.core.permissions import P
from app.core.storage import get_storage, safe_filename
from app.core.tenancy import scoped
from app.modules.audit import service as audit
from app.modules.integrations.calendar import calendar_provider
from app.modules.site_visits import service
from app.modules.site_visits.models import SiteVisit, SiteVisitAttendee, SiteVisitMedia
from app.modules.site_visits.schemas import (
    CheckOutIn,
    GeoPoint,
    MediaOut,
    NoteIn,
    NoteOut,
    VisitCreate,
    VisitDetail,
    VisitOut,
    VisitUpdate,
)
from app.modules.tasks.router import TaskCreate, TaskOut, create_task

router = APIRouter(prefix="/site-visits", tags=["site-visits"])


def _detail(db, ctx, visit: SiteVisit) -> VisitDetail:
    media = db.scalars(select(SiteVisitMedia).where(SiteVisitMedia.visit_id == visit.id).order_by(SiteVisitMedia.uploaded_at)).all()
    out = VisitDetail.model_validate(visit)
    out.media = [MediaOut.model_validate(m) for m in media]
    out.conflicts = service.conflicts(db, ctx, visit)
    return out


@router.get("", response_model=Page[VisitOut])
def list_visits(
    db: DB,
    starts_after: datetime | None = None,
    starts_before: datetime | None = None,
    status: list[str] | None = Query(None),
    property_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
    mine: bool = False,
    page: PageParams = Depends(),
    ctx=requires(P.SITE_VISIT_READ),
):
    stmt = scoped(SiteVisit, ctx).where(service.visible_clause(ctx))
    if starts_after:
        stmt = stmt.where(SiteVisit.scheduled_start >= starts_after)
    if starts_before:
        stmt = stmt.where(SiteVisit.scheduled_start <= starts_before)
    if status:
        stmt = stmt.where(SiteVisit.status.in_(status))
    if property_id:
        stmt = stmt.where(SiteVisit.property_id == property_id)
    if deal_id:
        stmt = stmt.where(SiteVisit.deal_id == deal_id)
    if mine:
        stmt = stmt.where(SiteVisit.id.in_(select(SiteVisitAttendee.visit_id).where(SiteVisitAttendee.user_id == ctx.user_id)))
    items, total = paginate(db, stmt.order_by(SiteVisit.scheduled_start), page)
    return {"items": items, "total": total, "limit": page.limit, "offset": page.offset}


@router.post("", response_model=VisitDetail, status_code=201)
def create_visit(body: VisitCreate, db: DB, ctx=requires(P.SITE_VISIT_WRITE)):
    return _detail(db, ctx, service.create_visit(db, ctx, body))


@router.get("/{visit_id}", response_model=VisitDetail)
def get_visit(visit_id: uuid.UUID, db: DB, ctx=requires(P.SITE_VISIT_READ)):
    return _detail(db, ctx, service.get_visible_visit(db, visit_id, ctx))


@router.patch("/{visit_id}", response_model=VisitDetail)
def update_visit(visit_id: uuid.UUID, body: VisitUpdate, db: DB, ctx=requires(P.SITE_VISIT_WRITE)):
    visit = service.get_visible_visit(db, visit_id, ctx)
    before = audit.snapshot(visit)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(visit, k, v)
    db.flush()
    if changes.get("status") == "cancelled" and visit.calendar_external_ref:
        calendar_provider.cancel(external_ref=visit.calendar_external_ref)
    elif {"scheduled_start", "scheduled_end", "title", "meeting_point"} & changes.keys():
        service._sync_calendar(db, visit)
    audit.record_update(db, ctx, "site_visit", visit, before)
    return _detail(db, ctx, visit)


@router.post("/{visit_id}/check-in", response_model=VisitDetail)
def check_in(visit_id: uuid.UUID, body: GeoPoint, db: DB, ctx=requires(P.SITE_VISIT_WRITE)):
    visit = service.get_visible_visit(db, visit_id, ctx)
    return _detail(db, ctx, service.check_in(db, ctx, visit, body))


@router.post("/{visit_id}/check-out", response_model=VisitDetail)
def check_out(visit_id: uuid.UUID, body: CheckOutIn, db: DB, ctx=requires(P.SITE_VISIT_WRITE)):
    visit = service.get_visible_visit(db, visit_id, ctx)
    return _detail(db, ctx, service.check_out(db, ctx, visit, body))


@router.post("/{visit_id}/notes", response_model=NoteOut, status_code=201)
def add_note(visit_id: uuid.UUID, body: NoteIn, db: DB, ctx=requires(P.SITE_VISIT_WRITE)):
    return service.add_note(db, ctx, service.get_visible_visit(db, visit_id, ctx), body)


@router.post("/{visit_id}/media", response_model=MediaOut, status_code=201)
def upload_media(
    visit_id: uuid.UUID,
    db: DB,
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    captured_at: datetime | None = Form(None),
    client_ref: str | None = Form(None),
    ctx=requires(P.SITE_VISIT_WRITE),
):
    visit = service.get_visible_visit(db, visit_id, ctx)
    return service.add_media(
        db, ctx, visit, stream=file.file, filename=safe_filename(file.filename or "media"),
        content_type=file.content_type or "application/octet-stream", caption=caption, latitude=latitude,
        longitude=longitude, captured_at=captured_at, client_ref=client_ref,
    )


@router.get("/{visit_id}/media/{media_id}/file")
def download_media(visit_id: uuid.UUID, media_id: uuid.UUID, db: DB, ctx=requires(P.SITE_VISIT_READ)):
    visit = service.get_visible_visit(db, visit_id, ctx)
    media = db.get(SiteVisitMedia, media_id)
    if media is None or media.visit_id != visit.id:
        raise NotFound("Media not found")
    storage = get_storage()
    url = storage.presigned_get(media.storage_key, filename=media.filename, content_type=media.content_type)
    if url:
        return RedirectResponse(url, status_code=302)
    return StreamingResponse(storage.open(media.storage_key), media_type=media.content_type,
                             headers={"Cache-Control": "private, no-store"})


@router.post("/{visit_id}/follow-up-tasks", response_model=TaskOut, status_code=201)
def create_follow_up(visit_id: uuid.UUID, body: TaskCreate, db: DB, ctx=requires(P.TASK_WRITE)):
    visit = service.get_visible_visit(db, visit_id, ctx)
    body = body.model_copy(update={"site_visit_id": visit.id, "property_id": body.property_id or visit.property_id, "deal_id": body.deal_id or visit.deal_id})
    return create_task(db, ctx, body)

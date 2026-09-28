import uuid
from datetime import timedelta
from typing import BinaryIO

from sqlalchemy import ColumnElement, or_, select, true
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.db import utcnow
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.permissions import P
from app.core.storage import build_key, get_storage
from app.core.tenancy import get_scoped, scoped
from app.modules.audit import service as audit
from app.modules.deals.access import get_visible_deal
from app.modules.deals.access import visible_clause as deal_visible
from app.modules.deals.models import Deal
from app.modules.identity.models import TenantMembership, User
from app.modules.integrations.calendar import CalendarEvent, calendar_provider
from app.modules.properties.access import get_visible_property
from app.modules.properties.access import visible_clause as property_visible
from app.modules.properties.models import Property
from app.modules.site_visits.models import SiteVisit, SiteVisitAttendee, SiteVisitMedia, SiteVisitNote
from app.modules.site_visits.schemas import CheckOutIn, GeoPoint, NoteIn, VisitCreate


def visible_clause(ctx: RequestContext) -> ColumnElement[bool]:
    if ctx.has(P.DEAL_READ_ALL) and ctx.has(P.PROPERTY_READ_ALL):
        return true()
    return or_(
        SiteVisit.created_by_id == ctx.user_id,
        SiteVisit.id.in_(select(SiteVisitAttendee.visit_id).where(SiteVisitAttendee.user_id == ctx.user_id)),
        SiteVisit.property_id.in_(select(Property.id).where(property_visible(ctx))),
        SiteVisit.deal_id.in_(select(Deal.id).where(deal_visible(ctx))),
    )


def get_visible_visit(session: Session, visit_id: uuid.UUID, ctx: RequestContext) -> SiteVisit:
    visit = get_scoped(session, SiteVisit, visit_id, ctx, label="Site visit")
    if session.scalar(select(SiteVisit.id).where(SiteVisit.id == visit.id, visible_clause(ctx))) is None:
        raise NotFound("Site visit not found")
    return visit


def find_by_client_ref(session: Session, ctx: RequestContext, client_ref: str | None) -> SiteVisit | None:
    if not client_ref:
        return None
    return session.scalar(scoped(SiteVisit, ctx).where(SiteVisit.client_ref == client_ref))


def conflicts(session: Session, ctx: RequestContext, visit: SiteVisit) -> list[dict]:
    user_ids = [a.user_id for a in visit.attendees if a.user_id and a.is_assigned]
    if not user_ids:
        return []
    start = visit.scheduled_start
    end = visit.scheduled_end or start + timedelta(hours=2)
    others = session.scalars(
        scoped(SiteVisit, ctx)
        .join(SiteVisitAttendee, SiteVisitAttendee.visit_id == SiteVisit.id)
        .where(
            SiteVisit.id != visit.id,
            SiteVisit.status.in_(("scheduled", "in_progress")),
            SiteVisitAttendee.user_id.in_(user_ids),
            SiteVisit.scheduled_start < end,
            SiteVisit.scheduled_start > start - timedelta(hours=2),
        )
    ).unique().all()
    return [
        {"visit_id": str(o.id), "title": o.title, "scheduled_start": o.scheduled_start.isoformat()} for o in others
    ]


def _sync_calendar(session: Session, visit: SiteVisit) -> None:
    emails = [
        e for e in session.scalars(
            select(User.email).where(User.id.in_([a.user_id for a in visit.attendees if a.user_id]))
        ) if e
    ]
    ref = calendar_provider.upsert(
        CalendarEvent(
            internal_id=str(visit.id), title=visit.title, starts_at=visit.scheduled_start, ends_at=visit.scheduled_end,
            location=visit.meeting_point, attendee_emails=emails, description=visit.purpose,
        ),
        external_ref=visit.calendar_external_ref,
    )
    if ref:
        visit.calendar_provider = calendar_provider.name
        visit.calendar_external_ref = ref


def create_visit(session: Session, ctx: RequestContext, body: VisitCreate) -> SiteVisit:
    existing = find_by_client_ref(session, ctx, body.client_ref)
    if existing:
        return existing
    property_id = body.property_id
    if body.deal_id:
        deal = get_visible_deal(session, body.deal_id, ctx)
        if property_id and property_id != deal.property_id:
            raise ValidationFailed("Deal belongs to a different property")
        property_id = deal.property_id
    if property_id:
        get_visible_property(session, property_id, ctx)

    user_ids = {a.user_id for a in body.attendees if a.user_id}
    if user_ids:
        members = set(session.scalars(
            select(TenantMembership.user_id).where(TenantMembership.tenant_id == ctx.tenant_id, TenantMembership.user_id.in_(user_ids))
        ))
        if user_ids - members:
            raise NotFound("Some attendees are not members of this tenant")

    visit = SiteVisit(
        tenant_id=ctx.tenant_id, property_id=property_id, deal_id=body.deal_id, title=body.title, purpose=body.purpose,
        scheduled_start=body.scheduled_start, scheduled_end=body.scheduled_end, meeting_point=body.meeting_point,
        client_ref=body.client_ref, created_by_id=ctx.user_id,
    )
    visit.attendees = [SiteVisitAttendee(**a.model_dump()) for a in body.attendees]
    if not any(a.user_id == ctx.user_id for a in visit.attendees):
        visit.attendees.append(SiteVisitAttendee(user_id=ctx.user_id, role="organizer", is_assigned=True))
    session.add(visit)
    session.flush()
    _sync_calendar(session, visit)
    audit.record(session, ctx, "site_visit.scheduled", "site_visit", visit.id, changes=audit.snapshot(visit),
                 metadata={"attendees": [a.model_dump(mode="json") for a in body.attendees]})
    return visit


def check_in(session: Session, ctx: RequestContext, visit: SiteVisit, point: GeoPoint) -> SiteVisit:
    if visit.status not in ("scheduled", "in_progress"):
        raise Conflict(f"Visit is {visit.status}")
    if visit.check_in_at is None:
        visit.check_in_at = point.recorded_at or utcnow()
        visit.check_in_lat, visit.check_in_lng, visit.check_in_accuracy_m = point.latitude, point.longitude, point.accuracy_m
    visit.status = "in_progress"
    audit.record(session, ctx, "site_visit.checked_in", "site_visit", visit.id, metadata=point.model_dump(mode="json"))
    return visit


def check_out(session: Session, ctx: RequestContext, visit: SiteVisit, body: CheckOutIn) -> SiteVisit:
    if visit.status == "completed":
        return visit
    if visit.status != "in_progress":
        raise Conflict("Check in before checking out")
    visit.check_out_at = body.recorded_at or utcnow()
    visit.check_out_lat, visit.check_out_lng = body.latitude, body.longitude
    visit.track = [p.model_dump(mode="json") for p in body.track][:5000]
    if body.outcome:
        visit.outcome = body.outcome
    visit.status = "completed"
    audit.record(session, ctx, "site_visit.checked_out", "site_visit", visit.id,
                 metadata={"latitude": body.latitude, "longitude": body.longitude, "track_points": len(body.track)})
    return visit


def add_note(session: Session, ctx: RequestContext, visit: SiteVisit, body: NoteIn) -> SiteVisitNote:
    if body.client_ref:
        existing = session.scalar(select(SiteVisitNote).where(SiteVisitNote.visit_id == visit.id, SiteVisitNote.client_ref == body.client_ref))
        if existing:
            return existing
    note = SiteVisitNote(
        visit_id=visit.id, body=body.body, author_id=ctx.user_id, latitude=body.latitude, longitude=body.longitude,
        client_ref=body.client_ref, recorded_at=body.recorded_at or utcnow(),
    )
    session.add(note)
    session.flush()
    audit.record(session, ctx, "site_visit.note_added", "site_visit", visit.id, metadata={"note_id": str(note.id)})
    return note


def add_media(
    session: Session, ctx: RequestContext, visit: SiteVisit, *, stream: BinaryIO, filename: str, content_type: str,
    caption: str | None, latitude: float | None, longitude: float | None, captured_at, client_ref: str | None,
) -> SiteVisitMedia:
    if client_ref:
        existing = session.scalar(select(SiteVisitMedia).where(SiteVisitMedia.visit_id == visit.id, SiteVisitMedia.client_ref == client_ref))
        if existing:
            return existing
    if content_type.startswith("image/"):
        kind = "photo"
    elif content_type.startswith("video/"):
        kind = "video"
    elif content_type.startswith("audio/"):
        kind = "audio"
    else:
        raise ValidationFailed("Only photos, videos and audio can be attached to site visits")
    stored = get_storage().put(build_key(visit.tenant_id, "site-visits", visit.id, filename), stream, content_type)
    media = SiteVisitMedia(
        tenant_id=visit.tenant_id, visit_id=visit.id, kind=kind, storage_key=stored.key, filename=filename,
        content_type=content_type, size_bytes=stored.size_bytes, sha256=stored.sha256, caption=caption,
        latitude=latitude, longitude=longitude, captured_at=captured_at, uploaded_by_id=ctx.user_id, client_ref=client_ref,
    )
    session.add(media)
    session.flush()
    audit.record(session, ctx, "site_visit.media_added", "site_visit", visit.id,
                 metadata={"media_id": str(media.id), "kind": kind, "sha256": stored.sha256})
    return media

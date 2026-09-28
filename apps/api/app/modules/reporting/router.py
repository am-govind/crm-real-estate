import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.db import utcnow
from app.core.deps import DB, requires
from app.core.errors import ValidationFailed
from app.core.permissions import P
from app.modules.deals import service as deal_service
from app.modules.deals.access import get_visible_deal
from app.modules.deals.access import visible_clause as deal_visible
from app.modules.deals.models import Deal, DealAssignment
from app.modules.documents import service as document_service
from app.modules.documents.models import Document
from app.modules.geography.models import GeoUnit
from app.modules.identity.models import User
from app.modules.inventory.models import SiteRecord
from app.modules.maps.models import GeometryVersion
from app.modules.payments import service as payment_service
from app.modules.payments.models import PaymentMilestone
from app.modules.properties import service as property_service
from app.modules.properties.access import visible_clause as property_visible
from app.modules.properties.models import Property, PropertyOwner
from app.modules.properties.router import STATUS_COLORS
from app.modules.scoring import service as scoring_service
from app.modules.site_visits.models import SiteVisit
from app.modules.tasks.models import Task
from app.modules.workflows.models import StageDefinition
from app.modules.workflows.service import load_version, resolve_activation

router = APIRouter(prefix="/reports", tags=["reporting"])

OPEN_TASK = ("open", "in_progress", "blocked")


def _s(v: Decimal | None) -> str | None:
    return format(v, "f") if v is not None else None


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.get("/deals/{deal_id}/control-center")
def control_center(deal_id: uuid.UUID, db: DB, ctx=requires(P.DEAL_READ)):
    deal = get_visible_deal(db, deal_id, ctx)
    prop = db.get(Property, deal.property_id)
    geo = {u.id: u.name for u in db.scalars(select(GeoUnit).where(GeoUnit.id.in_(
        [i for i in (prop.state_id, prop.district_id, prop.tehsil_id, prop.village_id) if i])))}
    stages = deal_service.stage_views(db, deal)
    current = next((s for s in stages if s.stage_definition_id == deal.current_stage_id), None)
    progress = deal_service.stage_progress(db, deal)

    owners = db.scalars(
        select(PropertyOwner).where(PropertyOwner.property_id == prop.id, PropertyOwner.is_current.is_(True))
        .options(selectinload(PropertyOwner.owner))
    ).all()
    dd = deal_service.due_diligence_summary(db, deal)
    docs = document_service.completeness(db, ctx, deal_id=deal.id) if ctx.has(P.DOCUMENT_READ) else None
    fin = payment_service.financial_summary(db, deal) if ctx.has(P.PAYMENT_READ) else None
    score = scoring_service.latest_score(db, deal)

    tasks = db.scalars(
        select(Task).where(Task.deal_id == deal.id, Task.status.in_(OPEN_TASK))
        .order_by(Task.due_date.is_(None), Task.due_date).limit(10)
    ).all()
    visits = db.scalars(
        select(SiteVisit).where(SiteVisit.deal_id == deal.id, SiteVisit.status.in_(("scheduled", "in_progress")))
        .order_by(SiteVisit.scheduled_start).limit(5)
    ).all()
    assignee = db.get(User, deal.next_action_assignee_id) if deal.next_action_assignee_id else None
    geometry = db.get(GeometryVersion, prop.active_geometry_id) if prop.active_geometry_id else None
    sla_days = current.sla_days if current else None
    days_in_stage = (utcnow() - _aware(deal.stage_entered_at)).days if deal.stage_entered_at else None

    return {
        "deal": {
            "id": str(deal.id), "code": deal.code, "title": deal.title, "status": deal.status, "priority": deal.priority,
            "is_active": deal.is_active, "started_at": deal.started_at.isoformat(), "active_override_reason": deal.active_override_reason,
        },
        "property": {
            "id": str(prop.id), "code": prop.code, "name": prop.name, "land_type": prop.land_type, "status": prop.status,
            "survey_number": prop.survey_number, "khasra_number": prop.khasra_number,
            "location": {k: geo.get(getattr(prop, f"{k}_id")) for k in ("state", "district", "tehsil", "village")},
            "area": {"value": _s(prop.area_value), "unit": prop.area_unit,
                     "sqm_derived": _s(prop.area_sqm_derived)},
            "latitude": _s(prop.latitude), "longitude": _s(prop.longitude),
            "road_access": prop.road_access, "title_status": prop.title_status, "land_use": prop.land_use,
            "geometry": None if geometry is None else {
                "id": str(geometry.id), "version": geometry.version_no, "area_sqm": _s(geometry.area_sqm),
                "perimeter_m": _s(geometry.perimeter_m), "derived": True, "reviewed_at": geometry.reviewed_at.isoformat() if geometry.reviewed_at else None,
            },
        },
        "stage": {
            "current": None if current is None else {"key": current.key, "name": current.name, "category": current.category, "color": current.color},
            "days_in_stage": days_in_stage,
            "sla_days": sla_days,
            "is_overdue": bool(sla_days is not None and days_in_stage is not None and days_in_stage > sla_days),
            "progress": progress,
            "stages": [{"key": s.key, "name": s.name, "status": s.status, "color": s.color} for s in stages],
        },
        "owners": {
            "summary": property_service.ownership_summary(db, prop).model_dump(mode="json"),
            "items": [
                {"owner_id": str(po.owner_id), "name": po.owner.full_name, "share_percent": _s(po.share_percent),
                 "ownership_type": po.ownership_type, "ownership_verification": po.verification_status,
                 "identity_verification": po.owner.verification_status, "readiness": po.owner.readiness}
                for po in owners
            ],
        },
        "documents": docs,
        "due_diligence": {d.category: d.model_dump() for d in dd},
        "financials": fin,
        "next_action": {
            "action": deal.next_action, "due_date": deal.next_action_due.isoformat() if deal.next_action_due else None,
            "assignee": None if assignee is None else {"id": str(assignee.id), "name": assignee.display_name or assignee.email},
            "is_overdue": bool(deal.next_action_due and deal.next_action_due < date.today()),
        },
        "open_tasks": [
            {"id": str(t.id), "title": t.title, "priority": t.priority, "status": t.status,
             "due_date": t.due_date.isoformat() if t.due_date else None, "assignee_id": str(t.assignee_id) if t.assignee_id else None}
            for t in tasks
        ],
        "upcoming_visits": [
            {"id": str(v.id), "title": v.title, "scheduled_start": v.scheduled_start.isoformat(), "status": v.status} for v in visits
        ],
        "score": None if score is None else {"total": score.total, "coverage": score.coverage, "computed_at": score.computed_at.isoformat(), "breakdown": score.breakdown},
    }


@router.get("/pipeline")
def pipeline(db: DB, activation_id: uuid.UUID | None = None, assignee_id: uuid.UUID | None = None, ctx=requires(P.DEAL_READ)):
    try:
        act = resolve_activation(db, ctx.tenant_id, land_type=None, activation_id=activation_id)
    except ValidationFailed:
        return {"activation_id": None, "stages": [], "totals": {}}
    version = load_version(db, act.template_version_id)
    labels = (act.config or {}).get("stage_labels") or {}
    slas = (act.config or {}).get("sla_days") or {}

    stmt = (
        select(Deal, Property)
        .join(Property, Property.id == Deal.property_id)
        .where(Deal.tenant_id == ctx.tenant_id, Deal.template_version_id == version.id, Deal.is_active.is_(True), deal_visible(ctx))
    )
    if assignee_id:
        stmt = stmt.where(Deal.id.in_(select(DealAssignment.deal_id).where(DealAssignment.user_id == assignee_id)))
    rows = db.execute(stmt).all()
    now = utcnow()

    columns = []
    total_value = Decimal("0")
    for sd in version.stages:
        cards = []
        value = Decimal("0")
        sla = slas.get(sd.key, sd.sla_days)
        for d, p in rows:
            if d.current_stage_id != sd.id:
                continue
            amount = d.negotiated_price or d.expected_price or d.asking_price
            value += amount or 0
            days = (now - _aware(d.stage_entered_at)).days if d.stage_entered_at else None
            cards.append({
                "deal_id": str(d.id), "code": d.code, "title": d.title, "priority": d.priority,
                "property_id": str(p.id), "property_name": p.name, "amount": _s(amount), "currency": d.currency,
                "days_in_stage": days, "is_stuck": bool(sla is not None and days is not None and days > sla),
                "next_action": d.next_action, "next_action_due": d.next_action_due.isoformat() if d.next_action_due else None,
            })
        total_value += value
        columns.append({
            "key": sd.key, "name": labels.get(sd.key, sd.name), "color": sd.color, "category": sd.category,
            "sla_days": sla, "count": len(cards), "value": _s(value), "deals": cards,
        })
    return {
        "activation_id": str(act.id), "template_version_id": str(version.id), "stages": columns,
        "totals": {"deals": len(rows), "value": _s(total_value)},
    }


@router.get("/dashboard")
def dashboard(db: DB, ctx=requires(P.REPORT_READ)):
    tid = ctx.tenant_id
    today = date.today()
    month_start = today.replace(day=1)
    in_30 = today + timedelta(days=30)

    status_counts = dict(db.execute(
        select(Deal.status, func.count()).where(Deal.tenant_id == tid, deal_visible(ctx)).group_by(Deal.status)
    ).all())
    active = db.scalars(select(Deal).where(Deal.tenant_id == tid, Deal.is_active.is_(True), deal_visible(ctx))).all()
    pipeline_value = sum(((d.negotiated_price or d.expected_price or d.asking_price or Decimal("0")) for d in active), Decimal("0"))
    won_this_month = db.scalar(select(func.count()).select_from(Deal).where(
        Deal.tenant_id == tid, Deal.status == "won", Deal.closed_at >= datetime.combine(month_start, datetime.min.time(), tzinfo=timezone.utc), deal_visible(ctx)
    )) or 0

    stage_counts = db.execute(
        select(StageDefinition.name, StageDefinition.color, func.count())
        .join(Deal, Deal.current_stage_id == StageDefinition.id)
        .where(Deal.tenant_id == tid, Deal.is_active.is_(True), deal_visible(ctx))
        .group_by(StageDefinition.name, StageDefinition.color, StageDefinition.position)
        .order_by(StageDefinition.position)
    ).all()

    due_soon = db.scalars(select(PaymentMilestone).where(
        PaymentMilestone.tenant_id == tid, PaymentMilestone.status.in_(("planned", "partially_paid")),
        PaymentMilestone.due_date.between(today, in_30),
    )).all()
    overdue_payments = db.scalar(select(func.count()).select_from(PaymentMilestone).where(
        PaymentMilestone.tenant_id == tid, PaymentMilestone.status.in_(("planned", "partially_paid", "overdue")), PaymentMilestone.due_date < today
    )) or 0

    def count(model, *where) -> int:
        return db.scalar(select(func.count()).select_from(model).where(model.tenant_id == tid, *where)) or 0

    return {
        "deals": {
            "by_status": status_counts,
            "active": len(active),
            "pipeline_value": _s(pipeline_value),
            "won_this_month": won_this_month,
            "by_stage": [{"stage": n, "color": c, "count": k} for n, c, k in stage_counts],
        },
        "properties": {
            "total": db.scalar(select(func.count()).select_from(Property).where(Property.tenant_id == tid, property_visible(ctx))) or 0,
        },
        "payments": {
            "due_next_30_days": len(due_soon),
            "due_next_30_days_amount": _s(sum((m.planned_amount for m in due_soon), Decimal("0"))),
            "overdue_milestones": overdue_payments,
        },
        "tasks": {
            "overdue": count(Task, Task.status.in_(OPEN_TASK), Task.due_date < today),
            "mine_open": count(Task, Task.status.in_(OPEN_TASK), Task.assignee_id == ctx.user_id),
        },
        "documents": {
            "pending_review": count(Document, Document.review_status == "pending_review", Document.is_archived.is_(False)),
            "expiring_30_days": count(Document, Document.expiry_date.between(today, in_30), Document.is_archived.is_(False)),
            "expired": count(Document, Document.expiry_date < today, Document.is_archived.is_(False)),
        },
        "geometry": {"awaiting_review": count(GeometryVersion, GeometryVersion.status == "submitted")},
        "inventory": {
            "approved": count(SiteRecord, SiteRecord.approval_state == "approved"),
            "pending_approval": count(SiteRecord, SiteRecord.pending_revision_id.is_not(None)),
        },
        "site_visits": {
            "upcoming_7_days": count(SiteVisit, SiteVisit.status == "scheduled",
                                     SiteVisit.scheduled_start.between(utcnow(), utcnow() + timedelta(days=7))),
        },
    }


@router.get("/map-layers")
def map_layers(db: DB, ctx=requires(P.PROPERTY_READ)):
    """Active approved parcel boundaries as a GeoJSON FeatureCollection coloured by status."""
    rows = db.execute(
        select(Property, GeometryVersion)
        .join(GeometryVersion, GeometryVersion.id == Property.active_geometry_id)
        .where(Property.tenant_id == ctx.tenant_id, property_visible(ctx))
        .limit(5000)
    ).all()
    stage_by_property = dict(db.execute(
        select(Deal.property_id, StageDefinition.color)
        .join(StageDefinition, StageDefinition.id == Deal.current_stage_id)
        .where(Deal.tenant_id == ctx.tenant_id, Deal.is_active.is_(True))
    ).all())
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": g.geojson,
                "properties": {
                    "property_id": str(p.id), "code": p.code, "name": p.name, "status": p.status,
                    "color": stage_by_property.get(p.id) or STATUS_COLORS.get(p.status, "#6b7280"),
                    "area_sqm": _s(g.area_sqm), "derived": True,
                },
            }
            for p, g in rows
        ],
    }

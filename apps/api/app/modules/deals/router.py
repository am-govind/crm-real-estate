import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.core.db import utcnow
from app.core.deps import DB, requires
from app.core.errors import NotFound
from app.core.pagination import Page, PageParams
from app.core.permissions import P
from app.core.tenancy import scoped
from app.modules.audit import service as audit
from app.modules.deals import service
from app.modules.deals.access import get_visible_deal, visible_clause
from app.modules.deals.models import (
    Agreement,
    Deal,
    DealAssignment,
    DealOwnershipSnapshot,
    DealStageTransition,
    DueDiligenceItem,
    NegotiationEntry,
)
from app.modules.deals.schemas import (
    AgreementIn,
    AgreementOut,
    AgreementUpdate,
    AssignmentIn,
    ChecklistBypassIn,
    ChecklistUpdate,
    DDItemIn,
    DDItemOut,
    DDItemUpdate,
    DDSummary,
    DealAssignmentOut,
    DealCloseIn,
    DealCreate,
    DealListItem,
    DealOut,
    DealReopenIn,
    DealStageOut,
    DealUpdate,
    NegotiationIn,
    NegotiationOut,
    SnapshotIn,
    SnapshotOut,
    StageTransitionIn,
    TransitionOut,
)
from app.modules.identity.models import TenantMembership
from app.modules.properties.models import Property
from app.modules.workflows.models import StageDefinition

router = APIRouter(prefix="/deals", tags=["deals"])


def _list_item(deal: Deal, prop: Property, stage: StageDefinition | None) -> DealListItem:
    return DealListItem(
        **DealOut.model_validate(deal).model_dump(),
        property_name=prop.name,
        property_code=prop.code,
        current_stage_key=stage.key if stage else None,
        current_stage_name=stage.name if stage else None,
    )


@router.get("", response_model=Page[DealListItem])
def list_deals(
    db: DB,
    q: str | None = None,
    status: list[str] | None = Query(None),
    stage_key: list[str] | None = Query(None),
    property_id: uuid.UUID | None = None,
    assignee_id: uuid.UUID | None = None,
    active_only: bool = False,
    priority: str | None = None,
    page: PageParams = Depends(),
    ctx=requires(P.DEAL_READ),
):
    stmt = (
        select(Deal, Property, StageDefinition)
        .join(Property, Property.id == Deal.property_id)
        .join(StageDefinition, StageDefinition.id == Deal.current_stage_id, isouter=True)
        .where(Deal.tenant_id == ctx.tenant_id, visible_clause(ctx))
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Deal.title.ilike(like), Deal.code.ilike(like), Property.name.ilike(like), Property.code.ilike(like)))
    if status:
        stmt = stmt.where(Deal.status.in_(status))
    if stage_key:
        stmt = stmt.where(StageDefinition.key.in_(stage_key))
    if property_id:
        stmt = stmt.where(Deal.property_id == property_id)
    if assignee_id:
        stmt = stmt.where(Deal.id.in_(select(DealAssignment.deal_id).where(DealAssignment.user_id == assignee_id)))
    if active_only:
        stmt = stmt.where(Deal.is_active.is_(True))
    if priority:
        stmt = stmt.where(Deal.priority == priority)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Deal.updated_at.desc()).limit(page.limit).offset(page.offset)).all()
    return {"items": [_list_item(d, p, s) for d, p, s in rows], "total": total, "limit": page.limit, "offset": page.offset}


@router.post("", response_model=DealOut, status_code=201)
def create_deal(body: DealCreate, db: DB, ctx=requires(P.DEAL_WRITE)):
    return service.create_deal(db, ctx, body)


@router.get("/{deal_id}", response_model=DealOut)
def get_deal(deal_id: uuid.UUID, db: DB, ctx=requires(P.DEAL_READ)):
    return get_visible_deal(db, deal_id, ctx)


@router.patch("/{deal_id}", response_model=DealOut)
def update_deal(deal_id: uuid.UUID, body: DealUpdate, db: DB, ctx=requires(P.DEAL_WRITE)):
    deal = get_visible_deal(db, deal_id, ctx)
    before = audit.snapshot(deal)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("next_action_assignee_id"):
        _require_member(db, ctx.tenant_id, changes["next_action_assignee_id"])
    for k, v in changes.items():
        setattr(deal, k, v)
    db.flush()
    audit.record_update(db, ctx, "deal", deal, before)
    return deal


def _require_member(db, tenant_id, user_id):
    if db.scalar(select(TenantMembership.id).where(TenantMembership.tenant_id == tenant_id, TenantMembership.user_id == user_id)) is None:
        raise NotFound("User is not a member of this tenant")


# ---- Stages ----


@router.get("/{deal_id}/stages", response_model=list[DealStageOut])
def get_stages(deal_id: uuid.UUID, db: DB, ctx=requires(P.DEAL_READ)):
    return service.stage_views(db, get_visible_deal(db, deal_id, ctx))


@router.post("/{deal_id}/transitions", response_model=DealOut)
def move_stage(deal_id: uuid.UUID, body: StageTransitionIn, db: DB, ctx=requires(P.DEAL_READ)):
    deal = get_visible_deal(db, deal_id, ctx)
    return service.transition(
        db, ctx, deal, target_key=body.target_stage_key, reason=body.reason, bypass_checklist=body.bypass_incomplete_checklist
    )


@router.get("/{deal_id}/transitions", response_model=list[TransitionOut])
def list_transitions(deal_id: uuid.UUID, db: DB, ctx=requires(P.DEAL_READ)):
    deal = get_visible_deal(db, deal_id, ctx)
    return list(db.scalars(select(DealStageTransition).where(DealStageTransition.deal_id == deal.id).order_by(DealStageTransition.occurred_at)))


@router.post("/{deal_id}/close", response_model=DealOut)
def close_deal(deal_id: uuid.UUID, body: DealCloseIn, db: DB, ctx=requires(P.DEAL_WRITE)):
    return service.close_deal(db, ctx, get_visible_deal(db, deal_id, ctx), outcome=body.outcome, reason=body.reason)


@router.post("/{deal_id}/reopen", response_model=DealOut)
def reopen_deal(deal_id: uuid.UUID, body: DealReopenIn, db: DB, ctx=requires(P.DEAL_WRITE)):
    return service.reopen_deal(db, ctx, get_visible_deal(db, deal_id, ctx), reason=body.reason, override=body.override_active_deal)


@router.patch("/{deal_id}/checklist/{item_id}", response_model=list[DealStageOut])
def update_checklist(deal_id: uuid.UUID, item_id: uuid.UUID, body: ChecklistUpdate, db: DB, ctx=requires(P.DEAL_WRITE)):
    deal = get_visible_deal(db, deal_id, ctx)
    item = service.get_checklist_item(db, deal, item_id)
    service.update_checklist_item(db, ctx, deal, item, status=body.status, note=body.note, document_id=body.document_id)
    db.flush()
    return service.stage_views(db, deal)


@router.post("/{deal_id}/checklist/{item_id}/bypass", response_model=list[DealStageOut])
def bypass_checklist(deal_id: uuid.UUID, item_id: uuid.UUID, body: ChecklistBypassIn, db: DB, ctx=requires(P.DEAL_CHECKLIST_BYPASS)):
    deal = get_visible_deal(db, deal_id, ctx)
    service.bypass_checklist_item(db, ctx, deal, service.get_checklist_item(db, deal, item_id), body.reason)
    db.flush()
    return service.stage_views(db, deal)


# ---- Assignments ----


@router.get("/{deal_id}/assignments", response_model=list[DealAssignmentOut])
def list_assignments(deal_id: uuid.UUID, db: DB, ctx=requires(P.DEAL_READ)):
    return get_visible_deal(db, deal_id, ctx).assignments


@router.post("/{deal_id}/assignments", response_model=DealAssignmentOut, status_code=201)
def add_assignment(deal_id: uuid.UUID, body: AssignmentIn, db: DB, ctx=requires(P.DEAL_ASSIGN)):
    deal = get_visible_deal(db, deal_id, ctx)
    _require_member(db, ctx.tenant_id, body.user_id)
    existing = next((a for a in deal.assignments if a.user_id == body.user_id), None)
    if existing:
        existing.role = body.role
        return existing
    a = DealAssignment(deal_id=deal.id, user_id=body.user_id, role=body.role)
    db.add(a)
    db.flush()
    audit.record(db, ctx, "deal.assigned", "deal", deal.id, metadata=body.model_dump(mode="json"))
    return a


@router.delete("/{deal_id}/assignments/{user_id}", status_code=204)
def remove_assignment(deal_id: uuid.UUID, user_id: uuid.UUID, db: DB, ctx=requires(P.DEAL_ASSIGN)):
    deal = get_visible_deal(db, deal_id, ctx)
    a = next((a for a in deal.assignments if a.user_id == user_id), None)
    if a is None:
        raise NotFound("Assignment not found")
    db.delete(a)
    audit.record(db, ctx, "deal.unassigned", "deal", deal.id, metadata={"user_id": str(user_id)})


# ---- Ownership snapshots ----


@router.get("/{deal_id}/ownership-snapshots", response_model=list[SnapshotOut])
def list_snapshots(deal_id: uuid.UUID, db: DB, ctx=requires(P.DEAL_READ)):
    deal = get_visible_deal(db, deal_id, ctx)
    return list(db.scalars(select(DealOwnershipSnapshot).where(DealOwnershipSnapshot.deal_id == deal.id).order_by(DealOwnershipSnapshot.taken_at)))


@router.post("/{deal_id}/ownership-snapshots", response_model=SnapshotOut, status_code=201)
def confirm_ownership(deal_id: uuid.UUID, body: SnapshotIn, db: DB, ctx=requires(P.OWNER_VERIFY)):
    deal = get_visible_deal(db, deal_id, ctx)
    prop = db.get(Property, deal.property_id)
    return service.snapshot_ownership(db, ctx, deal, prop, reason="ownership_confirmed", note=body.note)


# ---- Due diligence ----


@router.get("/{deal_id}/due-diligence", response_model=list[DDItemOut])
def list_dd(deal_id: uuid.UUID, db: DB, category: str | None = None, ctx=requires(P.DEAL_READ)):
    deal = get_visible_deal(db, deal_id, ctx)
    stmt = select(DueDiligenceItem).where(DueDiligenceItem.deal_id == deal.id)
    if category:
        stmt = stmt.where(DueDiligenceItem.category == category)
    return list(db.scalars(stmt.order_by(DueDiligenceItem.category, DueDiligenceItem.created_at)))


@router.get("/{deal_id}/due-diligence/summary", response_model=list[DDSummary])
def dd_summary(deal_id: uuid.UUID, db: DB, ctx=requires(P.DEAL_READ)):
    return service.due_diligence_summary(db, get_visible_deal(db, deal_id, ctx))


@router.post("/{deal_id}/due-diligence", response_model=DDItemOut, status_code=201)
def create_dd(deal_id: uuid.UUID, body: DDItemIn, db: DB, ctx=requires(P.DEAL_WRITE)):
    deal = get_visible_deal(db, deal_id, ctx)
    if body.assignee_id:
        _require_member(db, ctx.tenant_id, body.assignee_id)
    item = DueDiligenceItem(tenant_id=ctx.tenant_id, deal_id=deal.id, created_by_id=ctx.user_id, **body.model_dump())
    db.add(item)
    db.flush()
    audit.record(db, ctx, "due_diligence.created", "deal", deal.id, metadata={"item_id": str(item.id), **body.model_dump(mode="json")})
    return item


@router.patch("/{deal_id}/due-diligence/{item_id}", response_model=DDItemOut)
def update_dd(deal_id: uuid.UUID, item_id: uuid.UUID, body: DDItemUpdate, db: DB, ctx=requires(P.DEAL_READ)):
    deal = get_visible_deal(db, deal_id, ctx)
    item = db.get(DueDiligenceItem, item_id)
    if item is None or item.deal_id != deal.id:
        raise NotFound("Due-diligence item not found")
    changes = body.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] in ("clear", "issue_found", "waived"):
        ctx.require(P.DUE_DILIGENCE_REVIEW)
        item.reviewer_id = ctx.user_id
        item.reviewed_at = utcnow()
    else:
        ctx.require(P.DEAL_WRITE)
    if changes.get("document_ids") is not None:
        changes["document_ids"] = [str(d) for d in changes["document_ids"]]
    before = audit.snapshot(item)
    for k, v in changes.items():
        setattr(item, k, v)
    db.flush()
    audit.record_update(db, ctx, "due_diligence", item, before, metadata={"deal_id": str(deal.id)})
    return item


# ---- Negotiation and agreements ----


@router.get("/{deal_id}/negotiations", response_model=list[NegotiationOut])
def list_negotiations(deal_id: uuid.UUID, db: DB, ctx=requires(P.DEAL_READ)):
    deal = get_visible_deal(db, deal_id, ctx)
    return list(db.scalars(select(NegotiationEntry).where(NegotiationEntry.deal_id == deal.id).order_by(NegotiationEntry.occurred_at)))


@router.post("/{deal_id}/negotiations", response_model=NegotiationOut, status_code=201)
def add_negotiation(deal_id: uuid.UUID, body: NegotiationIn, db: DB, ctx=requires(P.DEAL_WRITE)):
    deal = get_visible_deal(db, deal_id, ctx)
    data = body.model_dump()
    if data["occurred_at"] is None:
        data.pop("occurred_at")
    entry = NegotiationEntry(tenant_id=ctx.tenant_id, deal_id=deal.id, recorded_by_id=ctx.user_id, **data)
    db.add(entry)
    if body.kind == "accepted" and body.amount is not None:
        before = deal.negotiated_price
        deal.negotiated_price = body.amount
        audit.record(db, ctx, "deal.negotiated_price_set", "deal", deal.id, changes={"negotiated_price": {"from": before, "to": body.amount}})
    db.flush()
    audit.record(db, ctx, "deal.negotiation_recorded", "deal", deal.id, metadata=body.model_dump(mode="json"))
    return entry


@router.get("/{deal_id}/agreements", response_model=list[AgreementOut])
def list_agreements(deal_id: uuid.UUID, db: DB, ctx=requires(P.DEAL_READ)):
    deal = get_visible_deal(db, deal_id, ctx)
    return list(db.scalars(select(Agreement).where(Agreement.deal_id == deal.id).order_by(Agreement.created_at)))


@router.post("/{deal_id}/agreements", response_model=AgreementOut, status_code=201)
def create_agreement(deal_id: uuid.UUID, body: AgreementIn, db: DB, ctx=requires(P.DEAL_WRITE)):
    deal = get_visible_deal(db, deal_id, ctx)
    a = Agreement(tenant_id=ctx.tenant_id, deal_id=deal.id, created_by_id=ctx.user_id, **body.model_dump())
    db.add(a)
    db.flush()
    audit.record(db, ctx, "agreement.created", "agreement", a.id, changes=audit.snapshot(a), metadata={"deal_id": str(deal.id)})
    return a


@router.patch("/{deal_id}/agreements/{agreement_id}", response_model=AgreementOut)
def update_agreement(deal_id: uuid.UUID, agreement_id: uuid.UUID, body: AgreementUpdate, db: DB, ctx=requires(P.DEAL_WRITE)):
    deal = get_visible_deal(db, deal_id, ctx)
    a = db.get(Agreement, agreement_id)
    if a is None or a.deal_id != deal.id:
        raise NotFound("Agreement not found")
    before = audit.snapshot(a)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    db.flush()
    audit.record_update(db, ctx, "agreement", a, before, metadata={"deal_id": str(deal.id)})
    return a


@router.get("/{deal_id}/audit", response_model=list[dict])
def deal_audit(deal_id: uuid.UUID, db: DB, ctx=requires(P.DEAL_READ)):
    from app.modules.audit.models import AuditEvent

    deal = get_visible_deal(db, deal_id, ctx)
    rows = db.scalars(
        scoped(AuditEvent, ctx)
        .where(AuditEvent.entity_type == "deal", AuditEvent.entity_id == str(deal.id))
        .order_by(AuditEvent.occurred_at.desc())
        .limit(500)
    )
    return [
        {"id": str(e.id), "action": e.action, "actor_id": str(e.actor_id) if e.actor_id else None,
         "changes": e.changes, "metadata": e.metadata_, "occurred_at": e.occurred_at.isoformat()}
        for e in rows
    ]

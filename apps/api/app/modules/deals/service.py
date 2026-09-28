import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.context import RequestContext
from app.core.db import utcnow
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.permissions import P
from app.core.sequences import take
from app.modules.audit import service as audit
from app.modules.deals.models import (
    ACTIVE_STATUSES,
    Deal,
    DealAssignment,
    DealChecklistItem,
    DealOwnershipSnapshot,
    DealStage,
    DealStageTransition,
    DueDiligenceItem,
)
from app.modules.deals.schemas import ChecklistItemOut, DDSummary, DealCreate, DealStageOut
from app.modules.identity.models import Tenant, TenantMembership
from app.modules.properties import service as property_service
from app.modules.properties.access import get_visible_property
from app.modules.properties.models import Property, PropertyOwner
from app.modules.workflows import service as workflow_service
from app.modules.workflows.models import StageDefinition, TenantWorkflowActivation

DONE_STATES = {"done", "not_applicable", "bypassed"}


def load_stages(session: Session, deal: Deal) -> list[DealStage]:
    return list(
        session.scalars(
            select(DealStage)
            .where(DealStage.deal_id == deal.id)
            .options(
                selectinload(DealStage.definition),
                selectinload(DealStage.checklist).selectinload(DealChecklistItem.definition),
            )
            .order_by(DealStage.position)
        )
    )


def active_deals_for_property(session: Session, property_id: uuid.UUID) -> list[Deal]:
    return list(session.scalars(select(Deal).where(Deal.property_id == property_id, Deal.is_active.is_(True))))


def _check_active_rule(session: Session, ctx: RequestContext, prop: Property, *, override: bool, reason: str | None, exclude: uuid.UUID | None = None) -> None:
    active = [d for d in active_deals_for_property(session, prop.id) if d.id != exclude]
    if not active:
        return
    if not override:
        raise Conflict(
            "This property already has an active acquisition deal",
            details={"active_deal_ids": [str(d.id) for d in active]},
        )
    if not ctx.has(P.DEAL_ACTIVE_OVERRIDE):
        raise Forbidden("Only authorized administrators can override the active-deal rule")
    if not reason:
        raise ValidationFailed("An override reason is required")


def snapshot_ownership(session: Session, ctx: RequestContext | None, deal: Deal, prop: Property, *, reason: str, note: str | None = None) -> DealOwnershipSnapshot:
    rows = session.scalars(
        select(PropertyOwner)
        .where(PropertyOwner.property_id == prop.id, PropertyOwner.is_current.is_(True))
        .options(selectinload(PropertyOwner.owner))
    ).all()
    owners = [
        {
            "property_owner_id": str(r.id),
            "owner_id": str(r.owner_id),
            "owner_code": r.owner.code,
            "full_name": r.owner.full_name,
            "ownership_type": r.ownership_type,
            "share_percent": format(r.share_percent, "f") if r.share_percent is not None else None,
            "record_reference": r.record_reference,
            "verification_status": r.verification_status,
            "owner_verification_status": r.owner.verification_status,
        }
        for r in rows
    ]
    summary = property_service.ownership_summary(session, prop).model_dump(mode="json")
    snap = DealOwnershipSnapshot(
        deal_id=deal.id, reason=reason, owners=owners, summary=summary, note=note, taken_by_id=ctx.user_id if ctx else None
    )
    session.add(snap)
    session.flush()
    audit.record(session, ctx, "deal.ownership_snapshot", "deal", deal.id, metadata={"reason": reason, "snapshot_id": str(snap.id)})
    return snap


def create_deal(session: Session, ctx: RequestContext, body: DealCreate) -> Deal:
    tenant_id = ctx.require_tenant()
    prop = get_visible_property(session, body.property_id, ctx)
    _check_active_rule(session, ctx, prop, override=body.override_active_deal, reason=body.override_reason)

    activation = workflow_service.resolve_activation(session, tenant_id, land_type=prop.land_type, activation_id=body.activation_id)
    version = workflow_service.load_version(session, activation.template_version_id)
    tenant = session.get(Tenant, tenant_id)
    hidden = set(activation.config.get("hidden_optional_items") or [])

    now = utcnow()
    deal = Deal(
        tenant_id=tenant_id,
        code=take(session, tenant_id, "deal"),
        property_id=prop.id,
        title=body.title or f"Acquisition of {prop.name}",
        priority=body.priority,
        source=body.source,
        currency=body.currency or (tenant.default_currency if tenant else "INR"),
        asking_price=body.asking_price,
        expected_price=body.expected_price,
        notes=body.notes,
        template_version_id=version.id,
        activation_id=activation.id,
        current_stage_id=version.stages[0].id,
        stage_entered_at=now,
        created_by_id=ctx.user_id,
        active_override_reason=body.override_reason if body.override_active_deal else None,
        active_override_by_id=ctx.user_id if body.override_active_deal else None,
    )
    session.add(deal)
    session.flush()

    for sd in version.stages:
        ds = DealStage(
            deal_id=deal.id, stage_definition_id=sd.id, position=sd.position,
            status="active" if sd.position == 0 else "pending", entered_at=now if sd.position == 0 else None,
        )
        ds.checklist = [
            DealChecklistItem(
                deal_id=deal.id, item_definition_id=c.id, position=c.position, is_required=c.is_required,
                is_hidden=f"{sd.key}.{c.key}" in hidden,
            )
            for c in sd.checklist
        ]
        session.add(ds)

    assignee_ids = {ctx.user_id, *body.assignee_ids}
    members = set(
        session.scalars(
            select(TenantMembership.user_id).where(TenantMembership.tenant_id == tenant_id, TenantMembership.user_id.in_(assignee_ids))
        )
    )
    for uid in assignee_ids:
        if uid not in members and uid != ctx.user_id:
            raise NotFound("Assignee is not a member of this tenant", details={"user_id": str(uid)})
        session.add(DealAssignment(deal_id=deal.id, user_id=uid, role="lead" if uid == ctx.user_id else "member"))

    session.add(DealStageTransition(deal_id=deal.id, to_stage_id=version.stages[0].id, direction="start", actor_id=ctx.user_id))
    if prop.status in ("prospect", "on_hold", "dropped"):
        prop.status = "in_pipeline"
    session.flush()

    audit.record(
        session, ctx, "deal.created", "deal", deal.id,
        changes=audit.snapshot(deal),
        metadata={"override_active_deal": body.override_active_deal, "override_reason": body.override_reason},
    )
    if body.override_active_deal:
        audit.record(session, ctx, "deal.active_rule_overridden", "property", prop.id, metadata={"deal_id": str(deal.id), "reason": body.override_reason})
    snapshot_ownership(session, ctx, deal, prop, reason="deal_start")
    return deal


def _activation_config(session: Session, deal: Deal) -> dict:
    if deal.activation_id is None:
        return {}
    act = session.get(TenantWorkflowActivation, deal.activation_id)
    return act.config if act else {}


def stage_views(session: Session, deal: Deal) -> list[DealStageOut]:
    config = _activation_config(session, deal)
    labels = config.get("stage_labels") or {}
    slas = config.get("sla_days") or {}
    out = []
    for ds in load_stages(session, deal):
        sd = ds.definition
        out.append(
            DealStageOut(
                id=ds.id, stage_definition_id=sd.id, key=sd.key, name=labels.get(sd.key, sd.name), category=sd.category,
                color=sd.color, position=ds.position, status=ds.status, is_terminal=sd.is_terminal,
                is_skippable=sd.is_skippable, sla_days=slas.get(sd.key, sd.sla_days), entered_at=ds.entered_at,
                completed_at=ds.completed_at, bypass_reason=ds.bypass_reason,
                checklist=[
                    ChecklistItemOut(
                        id=c.id, key=c.definition.key, label=c.definition.label, is_required=c.is_required,
                        is_hidden=c.is_hidden, status=c.status, note=c.note, document_id=c.document_id,
                        document_class_key=c.definition.document_class_key, completed_by_id=c.completed_by_id,
                        completed_at=c.completed_at,
                    )
                    for c in ds.checklist
                ],
            )
        )
    return out


def _require_open(deal: Deal) -> None:
    if deal.status != "open":
        raise Conflict(f"Deal is {deal.status}; reopen it before changing stages")


def transition(
    session: Session, ctx: RequestContext, deal: Deal, *, target_key: str, reason: str | None, bypass_checklist: bool
) -> Deal:
    ctx.require(P.DEAL_STAGE_MOVE)
    _require_open(deal)
    stages = load_stages(session, deal)
    by_key = {s.definition.key: s for s in stages}
    target = by_key.get(target_key)
    if target is None:
        raise NotFound(f"Stage {target_key!r} is not part of this deal's workflow")
    current = next((s for s in stages if s.stage_definition_id == deal.current_stage_id), None)
    if current is None:
        raise Conflict("Deal has no current stage")
    if target.id == current.id:
        raise ValidationFailed("Deal is already in this stage")

    reason = (reason or "").strip() or None
    now = utcnow()
    bypassed_stage_ids: list[str] = []
    bypassed_items: list[str] = []

    if target.position < current.position:
        if not reason or len(reason) < 3:
            raise ValidationFailed("A reason is required to move a deal backward")
        direction = "backward"
        current.status = "pending"
        current.entered_at = None
        for s in stages:
            if target.position < s.position < current.position and s.status == "completed":
                s.status = "pending"
                s.completed_at = None
    else:
        skipping = [s for s in stages if current.position < s.position < target.position]
        direction = "skip" if skipping else "forward"
        if skipping:
            if not ctx.has(P.DEAL_STAGE_SKIP):
                raise Forbidden("Only authorized users can skip stages")
            if not reason or len(reason) < 3:
                raise ValidationFailed("A reason is required to skip stages")
            locked = [s.definition.key for s in skipping if not s.definition.is_skippable]
            if locked:
                raise ValidationFailed("Some stages cannot be skipped", details={"stages": locked})

        incomplete = [c for c in current.checklist if c.is_required and not c.is_hidden and c.status not in DONE_STATES]
        if incomplete:
            if not bypass_checklist:
                raise ValidationFailed(
                    "Required checklist items are incomplete",
                    details={"items": [c.definition.key for c in incomplete]},
                )
            if not ctx.has(P.DEAL_CHECKLIST_BYPASS):
                raise Forbidden("Only authorized users can bypass checklist items")
            if not reason:
                raise ValidationFailed("A reason is required to bypass checklist items")
            for c in incomplete:
                _bypass_item(c, ctx, reason, now)
                bypassed_items.append(str(c.id))

        current.status = "completed"
        current.completed_at = now
        for s in skipping:
            s.status = "bypassed"
            s.bypassed_at = now
            s.bypassed_by_id = ctx.user_id
            s.bypass_reason = reason
            bypassed_stage_ids.append(str(s.stage_definition_id))
            for c in s.checklist:
                if c.status not in DONE_STATES:
                    _bypass_item(c, ctx, reason, now)
                    bypassed_items.append(str(c.id))

    target.status = "active"
    target.entered_at = now
    target.completed_at = None
    deal.current_stage_id = target.stage_definition_id
    deal.stage_entered_at = now

    session.add(
        DealStageTransition(
            deal_id=deal.id, from_stage_id=current.stage_definition_id, to_stage_id=target.stage_definition_id,
            direction=direction, reason=reason, bypassed_stage_ids=bypassed_stage_ids,
            bypassed_checklist_item_ids=bypassed_items, actor_id=ctx.user_id,
        )
    )

    if target.definition.is_terminal:
        target.status = "completed"
        target.completed_at = now
        deal.status = "won"
        deal.is_active = False
        deal.closed_at = now
        prop = session.get(Property, deal.property_id)
        if prop:
            prop.status = "acquired"

    audit.record(
        session, ctx, f"deal.stage_{direction}", "deal", deal.id,
        changes={"stage": {"from": current.definition.key, "to": target.definition.key}},
        metadata={"reason": reason, "bypassed_stages": bypassed_stage_ids, "bypassed_checklist_items": bypassed_items},
    )
    session.flush()
    return deal


def _bypass_item(item: DealChecklistItem, ctx: RequestContext, reason: str, now) -> None:
    item.status = "bypassed"
    item.note = f"Bypassed: {reason}"
    item.completed_by_id = ctx.user_id
    item.completed_at = now


def close_deal(session: Session, ctx: RequestContext, deal: Deal, *, outcome: str, reason: str) -> Deal:
    if deal.status in ("won", "lost", "cancelled"):
        raise Conflict(f"Deal is already {deal.status}")
    before = deal.status
    deal.status = outcome
    deal.close_reason = reason
    if outcome in ("lost", "cancelled"):
        deal.is_active = False
        deal.closed_at = utcnow()
        prop = session.get(Property, deal.property_id)
        if prop and not [d for d in active_deals_for_property(session, prop.id) if d.id != deal.id]:
            prop.status = "dropped" if outcome == "lost" else "prospect"
    audit.record(session, ctx, "deal.status_changed", "deal", deal.id, changes={"status": {"from": before, "to": outcome}}, metadata={"reason": reason})
    return deal


def reopen_deal(session: Session, ctx: RequestContext, deal: Deal, *, reason: str, override: bool) -> Deal:
    if deal.status not in ("on_hold", "lost", "cancelled"):
        raise Conflict("Only on-hold, lost or cancelled deals can be reopened")
    prop = session.get(Property, deal.property_id)
    assert prop is not None
    if not deal.is_active:
        _check_active_rule(session, ctx, prop, override=override, reason=reason, exclude=deal.id)
    before = deal.status
    deal.status = "open"
    deal.is_active = True
    deal.closed_at = None
    prop.status = "in_pipeline"
    audit.record(session, ctx, "deal.reopened", "deal", deal.id, changes={"status": {"from": before, "to": "open"}}, metadata={"reason": reason, "override": override})
    return deal


def get_checklist_item(session: Session, deal: Deal, item_id: uuid.UUID) -> DealChecklistItem:
    item = session.get(DealChecklistItem, item_id)
    if item is None or item.deal_id != deal.id:
        raise NotFound("Checklist item not found")
    return item


def update_checklist_item(session: Session, ctx: RequestContext, deal: Deal, item: DealChecklistItem, *, status: str, note: str | None, document_id: uuid.UUID | None) -> DealChecklistItem:
    if item.status == "bypassed" and status != "pending":
        raise Conflict("Bypassed items must be reset to pending before being completed")
    if document_id is not None:
        from app.modules.documents.models import Document

        doc = session.get(Document, document_id)
        if doc is None or doc.tenant_id != deal.tenant_id:
            raise NotFound("Document not found")
    before = {"status": item.status, "note": item.note, "document_id": item.document_id}
    item.status = status
    item.note = note
    if document_id is not None:
        item.document_id = document_id
    item.completed_by_id = ctx.user_id if status != "pending" else None
    item.completed_at = utcnow() if status != "pending" else None
    audit.record(
        session, ctx, "deal.checklist_updated", "deal", deal.id,
        changes={"from": before, "to": {"status": status, "note": note, "document_id": item.document_id}},
        metadata={"checklist_item_id": str(item.id)},
    )
    return item


def bypass_checklist_item(session: Session, ctx: RequestContext, deal: Deal, item: DealChecklistItem, reason: str) -> DealChecklistItem:
    ctx.require(P.DEAL_CHECKLIST_BYPASS)
    if item.status in DONE_STATES:
        raise Conflict(f"Item is already {item.status}")
    _bypass_item(item, ctx, reason, utcnow())
    audit.record(session, ctx, "deal.checklist_bypassed", "deal", deal.id, metadata={"checklist_item_id": str(item.id), "reason": reason})
    return item


def stage_progress(session: Session, deal: Deal) -> dict:
    stages = load_stages(session, deal)
    total = len(stages)
    done = sum(1 for s in stages if s.status in ("completed", "bypassed"))
    current = next((s for s in stages if s.stage_definition_id == deal.current_stage_id), None)
    return {
        "total_stages": total,
        "completed_stages": done,
        "bypassed_stages": sum(1 for s in stages if s.status == "bypassed"),
        "percent": round(100 * done / total) if total else 0,
        "current_position": current.position if current else None,
    }


def due_diligence_summary(session: Session, deal: Deal) -> list[DDSummary]:
    items = session.scalars(select(DueDiligenceItem).where(DueDiligenceItem.deal_id == deal.id)).all()
    out = []
    for category in ("legal", "technical", "revenue", "survey"):
        rows = [i for i in items if i.category == category]
        clear = sum(1 for i in rows if i.status in ("clear", "waived"))
        issues = sum(1 for i in rows if i.status == "issue_found")
        open_ = len(rows) - clear - issues
        if not rows:
            status = "not_started"
        elif issues:
            status = "issue_found"
        elif open_ == 0:
            status = "clear"
        elif any(i.status == "in_progress" for i in rows) or clear:
            status = "in_progress"
        else:
            status = "not_started"
        out.append(DDSummary(category=category, status=status, total=len(rows), clear=clear, issues=issues, open=open_))
    return out


def current_stage_def(session: Session, deal: Deal) -> StageDefinition | None:
    return session.get(StageDefinition, deal.current_stage_id) if deal.current_stage_id else None

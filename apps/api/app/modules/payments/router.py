import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.db import utcnow
from app.core.deps import DB, requires
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.money import Money
from app.core.permissions import P
from app.core.schemas import ORMModel
from app.core.tenancy import get_scoped
from app.modules.audit import service as audit
from app.modules.deals.access import get_visible_deal
from app.modules.documents.models import Document
from app.modules.payments import service
from app.modules.payments.models import Payment, PaymentMilestone

router = APIRouter(tags=["payments"])

Kind = Literal["token", "advance", "installment", "final", "other"]
Mode = Literal["bank_transfer", "cheque", "demand_draft", "upi", "cash", "other"]


class MilestoneIn(BaseModel):
    kind: Kind
    label: str = Field(min_length=1, max_length=200)
    planned_amount: Money = Field(gt=0)
    due_date: date | None = None
    position: int = 0
    payee_owner_id: uuid.UUID | None = None
    notes: str | None = None


class MilestoneUpdate(BaseModel):
    label: str | None = None
    planned_amount: Money | None = Field(default=None, gt=0)
    due_date: date | None = None
    position: int | None = None
    notes: str | None = None
    reason: str = Field(min_length=3)


class MilestoneOut(ORMModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    kind: str
    label: str
    position: int
    planned_amount: Money
    currency: str
    due_date: date | None
    status: str
    approval_status: str
    approved_by_id: uuid.UUID | None
    approved_at: datetime | None
    approval_note: str | None
    payee_owner_id: uuid.UUID | None
    notes: str | None
    created_by_id: uuid.UUID | None
    created_at: datetime


class PaymentIn(BaseModel):
    milestone_id: uuid.UUID | None = None
    amount: Money = Field(gt=0)
    paid_on: date
    mode: Mode
    reference: str | None = None
    payee_owner_id: uuid.UUID | None = None
    receipt_document_id: uuid.UUID | None = None
    notes: str | None = None


class PaymentOut(ORMModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    milestone_id: uuid.UUID | None
    amount: Money
    currency: str
    paid_on: date
    mode: str
    reference: str | None
    payee_owner_id: uuid.UUID | None
    receipt_document_id: uuid.UUID | None
    status: str
    recorded_by_id: uuid.UUID
    approved_by_id: uuid.UUID | None
    approved_at: datetime | None
    decision_note: str | None
    reversal_reason: str | None
    reversed_at: datetime | None
    notes: str | None
    created_at: datetime


class DecisionIn(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = None


class ReverseIn(BaseModel):
    reason: str = Field(min_length=3)


def _milestone(db, ctx, deal, milestone_id) -> PaymentMilestone:
    m = get_scoped(db, PaymentMilestone, milestone_id, ctx, label="Milestone")
    if m.deal_id != deal.id:
        raise NotFound("Milestone not found")
    return m


@router.get("/deals/{deal_id}/financials")
def deal_financials(deal_id: uuid.UUID, db: DB, ctx=requires(P.PAYMENT_READ)):
    return service.financial_summary(db, get_visible_deal(db, deal_id, ctx))


@router.get("/deals/{deal_id}/payment-milestones", response_model=list[MilestoneOut])
def list_milestones(deal_id: uuid.UUID, db: DB, ctx=requires(P.PAYMENT_READ)):
    deal = get_visible_deal(db, deal_id, ctx)
    return list(db.scalars(select(PaymentMilestone).where(PaymentMilestone.deal_id == deal.id).order_by(PaymentMilestone.position, PaymentMilestone.due_date)))


@router.post("/deals/{deal_id}/payment-milestones", response_model=MilestoneOut, status_code=201)
def create_milestone(deal_id: uuid.UUID, body: MilestoneIn, db: DB, ctx=requires(P.PAYMENT_WRITE)):
    deal = get_visible_deal(db, deal_id, ctx)
    m = PaymentMilestone(tenant_id=ctx.tenant_id, deal_id=deal.id, currency=deal.currency, created_by_id=ctx.user_id, **body.model_dump())
    db.add(m)
    db.flush()
    service.refresh_milestone_status(db, m)
    audit.record(db, ctx, "payment_milestone.created", "deal", deal.id, changes={"milestone": audit.snapshot(m)})
    return m


@router.patch("/deals/{deal_id}/payment-milestones/{milestone_id}", response_model=MilestoneOut)
def update_milestone(deal_id: uuid.UUID, milestone_id: uuid.UUID, body: MilestoneUpdate, db: DB, ctx=requires(P.PAYMENT_WRITE)):
    deal = get_visible_deal(db, deal_id, ctx)
    m = _milestone(db, ctx, deal, milestone_id)
    if m.status in ("paid", "cancelled"):
        raise Conflict(f"Milestone is {m.status}")
    before = audit.snapshot(m)
    changes = body.model_dump(exclude_unset=True, exclude={"reason"})
    for k, v in changes.items():
        setattr(m, k, v)
    if "planned_amount" in changes or "due_date" in changes:
        m.approval_status = "pending_approval"
        m.approved_by_id = None
        m.approved_at = None
    service.refresh_milestone_status(db, m)
    db.flush()
    audit.record_update(db, ctx, "payment_milestone", m, before, metadata={"deal_id": str(deal.id), "reason": body.reason})
    return m


@router.post("/deals/{deal_id}/payment-milestones/{milestone_id}/decision", response_model=MilestoneOut)
def decide_milestone(deal_id: uuid.UUID, milestone_id: uuid.UUID, body: DecisionIn, db: DB, ctx=requires(P.PAYMENT_APPROVE)):
    deal = get_visible_deal(db, deal_id, ctx)
    m = _milestone(db, ctx, deal, milestone_id)
    if m.created_by_id == ctx.user_id and not ctx.is_system_admin:
        raise Forbidden("Milestones must be approved by someone other than their creator")
    before = m.approval_status
    m.approval_status = body.decision
    m.approved_by_id = ctx.user_id
    m.approved_at = utcnow()
    m.approval_note = body.note
    audit.record(db, ctx, "payment_milestone.decided", "deal", deal.id,
                 changes={"approval_status": {"from": before, "to": body.decision}}, metadata={"milestone_id": str(m.id), "note": body.note})
    return m


@router.post("/deals/{deal_id}/payment-milestones/{milestone_id}/cancel", response_model=MilestoneOut)
def cancel_milestone(deal_id: uuid.UUID, milestone_id: uuid.UUID, body: ReverseIn, db: DB, ctx=requires(P.PAYMENT_APPROVE)):
    deal = get_visible_deal(db, deal_id, ctx)
    m = _milestone(db, ctx, deal, milestone_id)
    approved, pending = service.milestone_paid(db, m)
    if approved or pending:
        raise Conflict("Milestones with payments cannot be cancelled; reverse the payments first")
    m.status = "cancelled"
    audit.record(db, ctx, "payment_milestone.cancelled", "deal", deal.id, metadata={"milestone_id": str(m.id), "reason": body.reason})
    return m


@router.get("/deals/{deal_id}/payments", response_model=list[PaymentOut])
def list_payments(deal_id: uuid.UUID, db: DB, ctx=requires(P.PAYMENT_READ)):
    deal = get_visible_deal(db, deal_id, ctx)
    return list(db.scalars(select(Payment).where(Payment.deal_id == deal.id).order_by(Payment.paid_on, Payment.created_at)))


@router.post("/deals/{deal_id}/payments", response_model=PaymentOut, status_code=201)
def record_payment(deal_id: uuid.UUID, body: PaymentIn, db: DB, ctx=requires(P.PAYMENT_WRITE)):
    deal = get_visible_deal(db, deal_id, ctx)
    if body.milestone_id:
        m = _milestone(db, ctx, deal, body.milestone_id)
        if m.status == "cancelled":
            raise Conflict("Cannot pay against a cancelled milestone")
        if m.approval_status != "approved":
            raise ValidationFailed("Milestone must be approved before payments are recorded against it")
    if body.receipt_document_id:
        doc = db.get(Document, body.receipt_document_id)
        if doc is None or doc.tenant_id != ctx.tenant_id or doc.deal_id != deal.id:
            raise NotFound("Receipt document not found on this deal")
    p = Payment(tenant_id=ctx.tenant_id, deal_id=deal.id, currency=deal.currency, recorded_by_id=ctx.user_id, **body.model_dump())
    db.add(p)
    db.flush()
    audit.record(db, ctx, "payment.recorded", "deal", deal.id, changes={"payment": audit.snapshot(p)})
    return p


@router.post("/deals/{deal_id}/payments/{payment_id}/decision", response_model=PaymentOut)
def decide_payment(deal_id: uuid.UUID, payment_id: uuid.UUID, body: DecisionIn, db: DB, ctx=requires(P.PAYMENT_APPROVE)):
    deal = get_visible_deal(db, deal_id, ctx)
    p = get_scoped(db, Payment, payment_id, ctx, label="Payment")
    if p.deal_id != deal.id:
        raise NotFound("Payment not found")
    if p.status != "recorded":
        raise Conflict(f"Payment is {p.status}")
    if p.recorded_by_id == ctx.user_id and not ctx.is_system_admin:
        raise Forbidden("Payments must be approved by someone other than the recorder")
    if body.decision == "rejected" and not body.note:
        raise ValidationFailed("A note is required when rejecting a payment")
    p.status = body.decision
    p.approved_by_id = ctx.user_id
    p.approved_at = utcnow()
    p.decision_note = body.note
    if p.milestone_id:
        service.refresh_milestone_status(db, db.get(PaymentMilestone, p.milestone_id))
    audit.record(db, ctx, "payment.decided", "deal", deal.id, changes={"status": {"from": "recorded", "to": body.decision}},
                 metadata={"payment_id": str(p.id), "note": body.note})
    return p


@router.post("/deals/{deal_id}/payments/{payment_id}/reverse", response_model=PaymentOut)
def reverse_payment(deal_id: uuid.UUID, payment_id: uuid.UUID, body: ReverseIn, db: DB, ctx=requires(P.PAYMENT_APPROVE)):
    deal = get_visible_deal(db, deal_id, ctx)
    p = get_scoped(db, Payment, payment_id, ctx, label="Payment")
    if p.deal_id != deal.id:
        raise NotFound("Payment not found")
    if p.status == "reversed":
        raise Conflict("Payment is already reversed")
    before = p.status
    p.status = "reversed"
    p.reversal_reason = body.reason
    p.reversed_at = utcnow()
    p.reversed_by_id = ctx.user_id
    if p.milestone_id:
        service.refresh_milestone_status(db, db.get(PaymentMilestone, p.milestone_id))
    audit.record(db, ctx, "payment.reversed", "deal", deal.id, changes={"status": {"from": before, "to": "reversed"}},
                 metadata={"payment_id": str(p.id), "reason": body.reason})
    return p

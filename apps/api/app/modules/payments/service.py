from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.money import zero
from app.modules.deals.models import Deal
from app.modules.payments.models import Payment, PaymentMilestone

ADVANCE_KINDS = ("token", "advance")


def milestone_paid(session: Session, milestone: PaymentMilestone) -> tuple[Decimal, Decimal]:
    """Returns (approved paid, pending approval) totals for a milestone."""
    rows = session.scalars(select(Payment).where(Payment.milestone_id == milestone.id)).all()
    approved = sum((p.amount for p in rows if p.status == "approved"), zero())
    pending = sum((p.amount for p in rows if p.status == "recorded"), zero())
    return approved, pending


def refresh_milestone_status(session: Session, milestone: PaymentMilestone) -> None:
    if milestone.status == "cancelled":
        return
    approved, _ = milestone_paid(session, milestone)
    if approved >= milestone.planned_amount:
        milestone.status = "paid"
    elif approved > 0:
        milestone.status = "partially_paid"
    elif milestone.due_date and milestone.due_date < date.today():
        milestone.status = "overdue"
    else:
        milestone.status = "planned"


def financial_summary(session: Session, deal: Deal) -> dict:
    milestones = session.scalars(
        select(PaymentMilestone).where(PaymentMilestone.deal_id == deal.id).order_by(PaymentMilestone.position, PaymentMilestone.due_date)
    ).all()
    payments = session.scalars(select(Payment).where(Payment.deal_id == deal.id)).all()
    live = [m for m in milestones if m.status != "cancelled"]
    by_milestone = {m.id: m for m in milestones}

    paid = sum((p.amount for p in payments if p.status == "approved"), zero())
    pending = sum((p.amount for p in payments if p.status == "recorded"), zero())
    advance_planned = sum((m.planned_amount for m in live if m.kind in ADVANCE_KINDS), zero())
    advance_paid = sum(
        (p.amount for p in payments if p.status == "approved" and p.milestone_id and by_milestone[p.milestone_id].kind in ADVANCE_KINDS),
        zero(),
    )
    planned_total = sum((m.planned_amount for m in live), zero())
    basis = deal.negotiated_price if deal.negotiated_price is not None else deal.expected_price
    balance = (basis - paid) if basis is not None else None
    overdue = [m for m in live if m.status == "overdue" or (m.status in ("planned", "partially_paid") and m.due_date and m.due_date < date.today())]
    upcoming = sorted((m for m in live if m.status in ("planned", "partially_paid", "overdue") and m.due_date), key=lambda m: m.due_date)

    def s(v: Decimal | None) -> str | None:
        return format(v, "f") if v is not None else None

    return {
        "currency": deal.currency,
        "asking_price": s(deal.asking_price),
        "expected_price": s(deal.expected_price),
        "negotiated_price": s(deal.negotiated_price),
        "balance_basis": "negotiated_price" if deal.negotiated_price is not None else ("expected_price" if basis is not None else None),
        "planned_total": s(planned_total),
        "unplanned_amount": s(basis - planned_total) if basis is not None else None,
        "advance_planned": s(advance_planned),
        "advance_paid": s(advance_paid),
        "paid_total": s(paid),
        "pending_approval_total": s(pending),
        "balance_amount": s(balance),
        "overdue_milestones": len(overdue),
        "next_due": (
            {"milestone_id": str(upcoming[0].id), "label": upcoming[0].label, "due_date": upcoming[0].due_date.isoformat(),
             "planned_amount": s(upcoming[0].planned_amount)}
            if upcoming else None
        ),
    }

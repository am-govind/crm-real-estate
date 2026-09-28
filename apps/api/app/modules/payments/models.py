import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import ActorMixin, Base, IdMixin, TenantScopedMixin, TimestampMixin, uuid_fk

MILESTONE_KINDS = ("token", "advance", "installment", "final", "other")
MILESTONE_STATUSES = ("planned", "partially_paid", "paid", "overdue", "cancelled")
APPROVAL_STATUSES = ("pending_approval", "approved", "rejected")
PAYMENT_MODES = ("bank_transfer", "cheque", "demand_draft", "upi", "cash", "other")
PAYMENT_STATUSES = ("recorded", "approved", "rejected", "reversed")


class PaymentMilestone(IdMixin, TimestampMixin, TenantScopedMixin, ActorMixin, Base):
    __tablename__ = "payment_milestones"

    deal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("deals.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer, default=0)
    planned_amount: Mapped[Decimal]
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    due_date: Mapped[date | None] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(20), default="planned", index=True)
    approval_status: Mapped[str] = mapped_column(String(20), default="pending_approval")
    approved_by_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)
    approved_at: Mapped[datetime | None]
    approval_note: Mapped[str | None] = mapped_column(Text)
    payee_owner_id: Mapped[uuid.UUID | None] = uuid_fk("owners.id", index=False)
    notes: Mapped[str | None] = mapped_column(Text)


class Payment(IdMixin, TimestampMixin, TenantScopedMixin, Base):
    """An actual payment. Never deleted or edited in amount; corrections are reversals."""

    __tablename__ = "payments"

    deal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("deals.id"), index=True)
    milestone_id: Mapped[uuid.UUID | None] = uuid_fk("payment_milestones.id")
    amount: Mapped[Decimal]
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    paid_on: Mapped[date]
    mode: Mapped[str] = mapped_column(String(20))
    reference: Mapped[str | None] = mapped_column(String(200))
    payee_owner_id: Mapped[uuid.UUID | None] = uuid_fk("owners.id", index=False)
    receipt_document_id: Mapped[uuid.UUID | None] = uuid_fk("documents.id", index=False)
    status: Mapped[str] = mapped_column(String(20), default="recorded", index=True)
    recorded_by_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)
    approved_at: Mapped[datetime | None]
    decision_note: Mapped[str | None] = mapped_column(Text)
    reversal_reason: Mapped[str | None] = mapped_column(Text)
    reversed_at: Mapped[datetime | None]
    reversed_by_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)
    notes: Mapped[str | None] = mapped_column(Text)

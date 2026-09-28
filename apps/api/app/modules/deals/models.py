import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import ActorMixin, Base, IdMixin, TenantScopedMixin, TimestampMixin, utcnow, uuid_fk

DEAL_STATUSES = ("open", "on_hold", "won", "lost", "cancelled")
ACTIVE_STATUSES = ("open", "on_hold")
STAGE_STATES = ("pending", "active", "completed", "bypassed")
CHECKLIST_STATES = ("pending", "done", "not_applicable", "bypassed")
DD_CATEGORIES = ("legal", "technical", "revenue", "survey")
DD_STATUSES = ("not_started", "in_progress", "clear", "issue_found", "waived")


class Deal(IdMixin, TimestampMixin, TenantScopedMixin, ActorMixin, Base):
    """An acquisition attempt on a property. A property may have many historical deals."""

    __tablename__ = "deals"

    code: Mapped[str] = mapped_column(String(20), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("properties.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    source: Mapped[str | None] = mapped_column(String(100))

    template_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("workflow_template_versions.id"))
    activation_id: Mapped[uuid.UUID | None] = uuid_fk("tenant_workflow_activations.id", index=False)
    current_stage_id: Mapped[uuid.UUID | None] = uuid_fk("stage_definitions.id")
    stage_entered_at: Mapped[datetime | None]

    active_override_reason: Mapped[str | None] = mapped_column(Text)
    active_override_by_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)

    currency: Mapped[str] = mapped_column(String(3), default="INR")
    asking_price: Mapped[Decimal | None]
    expected_price: Mapped[Decimal | None]
    negotiated_price: Mapped[Decimal | None]

    next_action: Mapped[str | None] = mapped_column(String(500))
    next_action_due: Mapped[date | None]
    next_action_assignee_id: Mapped[uuid.UUID | None] = uuid_fk("users.id")

    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    closed_at: Mapped[datetime | None]
    close_reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    custom_fields: Mapped[dict] = mapped_column(default=dict)

    stages: Mapped[list["DealStage"]] = relationship(back_populates="deal", order_by="DealStage.position", cascade="all, delete-orphan")
    assignments: Mapped[list["DealAssignment"]] = relationship(cascade="all, delete-orphan")


class DealAssignment(IdMixin, TimestampMixin, Base):
    __tablename__ = "deal_assignments"
    __table_args__ = (UniqueConstraint("deal_id", "user_id", name="uq_deal_assignment"),)

    deal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(40), default="member")


class DealStage(IdMixin, Base):
    """Per-deal state of each stage in the deal's pinned workflow version."""

    __tablename__ = "deal_stages"
    __table_args__ = (UniqueConstraint("deal_id", "stage_definition_id", name="uq_deal_stage"),)

    deal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    stage_definition_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("stage_definitions.id"))
    position: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    entered_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    bypassed_at: Mapped[datetime | None]
    bypassed_by_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)
    bypass_reason: Mapped[str | None] = mapped_column(Text)

    deal: Mapped[Deal] = relationship(back_populates="stages")
    definition: Mapped["StageDefinition"] = relationship("StageDefinition")  # noqa: F821
    checklist: Mapped[list["DealChecklistItem"]] = relationship(
        back_populates="deal_stage", order_by="DealChecklistItem.position", cascade="all, delete-orphan"
    )


class DealChecklistItem(IdMixin, TimestampMixin, Base):
    __tablename__ = "deal_checklist_items"

    deal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    deal_stage_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("deal_stages.id", ondelete="CASCADE"), index=True)
    item_definition_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("checklist_item_definitions.id"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    note: Mapped[str | None] = mapped_column(Text)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("documents.id", use_alter=True, name="fk_checklist_document"), nullable=True
    )
    completed_by_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)
    completed_at: Mapped[datetime | None]

    deal_stage: Mapped[DealStage] = relationship(back_populates="checklist")
    definition: Mapped["ChecklistItemDefinition"] = relationship("ChecklistItemDefinition")  # noqa: F821


class DealStageTransition(IdMixin, Base):
    __tablename__ = "deal_stage_transitions"

    deal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    from_stage_id: Mapped[uuid.UUID | None] = uuid_fk("stage_definitions.id", index=False)
    to_stage_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("stage_definitions.id"))
    direction: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(Text)
    bypassed_stage_ids: Mapped[list] = mapped_column(default=list)
    bypassed_checklist_item_ids: Mapped[list] = mapped_column(default=list)
    actor_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)
    occurred_at: Mapped[datetime] = mapped_column(default=utcnow)


class DealOwnershipSnapshot(IdMixin, Base):
    """Frozen copy of property ownership at deal start or when ownership is confirmed."""

    __tablename__ = "deal_ownership_snapshots"

    deal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(30))
    owners: Mapped[list] = mapped_column(default=list)
    summary: Mapped[dict] = mapped_column(default=dict)
    note: Mapped[str | None] = mapped_column(Text)
    taken_by_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)
    taken_at: Mapped[datetime] = mapped_column(default=utcnow)


class DueDiligenceItem(IdMixin, TimestampMixin, ActorMixin, Base):
    __tablename__ = "due_diligence_items"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    deal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="not_started")
    severity: Mapped[str | None] = mapped_column(String(10))
    findings: Mapped[str | None] = mapped_column(Text)
    assignee_id: Mapped[uuid.UUID | None] = uuid_fk("users.id")
    reviewer_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)
    reviewed_at: Mapped[datetime | None]
    document_ids: Mapped[list] = mapped_column(default=list)
    due_date: Mapped[date | None]


class NegotiationEntry(IdMixin, Base):
    __tablename__ = "negotiation_entries"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    deal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    party: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal | None]
    terms: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(default=utcnow)
    recorded_by_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)


class Agreement(IdMixin, TimestampMixin, ActorMixin, Base):
    __tablename__ = "agreements"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    deal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    reference_number: Mapped[str | None] = mapped_column(String(200))
    amount: Mapped[Decimal | None]
    signed_on: Mapped[date | None]
    registered_on: Mapped[date | None]
    valid_until: Mapped[date | None]
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("documents.id", use_alter=True, name="fk_agreement_document"), nullable=True
    )
    key_terms: Mapped[dict] = mapped_column(default=dict)
    notes: Mapped[str | None] = mapped_column(Text)

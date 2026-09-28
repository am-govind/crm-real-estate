import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.money import Money
from app.core.schemas import ORMModel

Priority = Literal["low", "medium", "high", "urgent"]
DDCategory = Literal["legal", "technical", "revenue", "survey"]
DDStatus = Literal["not_started", "in_progress", "clear", "issue_found", "waived"]


class DealCreate(BaseModel):
    property_id: uuid.UUID
    title: str | None = None
    activation_id: uuid.UUID | None = None
    priority: Priority = "medium"
    source: str | None = None
    currency: str | None = None
    asking_price: Money | None = None
    expected_price: Money | None = None
    notes: str | None = None
    assignee_ids: list[uuid.UUID] = Field(default_factory=list)
    override_active_deal: bool = False
    override_reason: str | None = None

    @model_validator(mode="after")
    def _override_reason(self):
        if self.override_active_deal and not (self.override_reason and len(self.override_reason.strip()) >= 3):
            raise ValueError("override_reason is required when overriding the active-deal rule")
        return self


class DealUpdate(BaseModel):
    title: str | None = None
    priority: Priority | None = None
    source: str | None = None
    asking_price: Money | None = None
    expected_price: Money | None = None
    negotiated_price: Money | None = None
    next_action: str | None = None
    next_action_due: date | None = None
    next_action_assignee_id: uuid.UUID | None = None
    notes: str | None = None
    custom_fields: dict | None = None


class StageTransitionIn(BaseModel):
    target_stage_key: str
    reason: str | None = None
    bypass_incomplete_checklist: bool = False


class DealCloseIn(BaseModel):
    outcome: Literal["lost", "cancelled", "on_hold"]
    reason: str = Field(min_length=3)


class DealReopenIn(BaseModel):
    reason: str = Field(min_length=3)
    override_active_deal: bool = False


class ChecklistUpdate(BaseModel):
    status: Literal["pending", "done", "not_applicable"]
    note: str | None = None
    document_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _na_note(self):
        if self.status == "not_applicable" and not self.note:
            raise ValueError("A note is required when marking an item not applicable")
        return self


class ChecklistBypassIn(BaseModel):
    reason: str = Field(min_length=3)


class AssignmentIn(BaseModel):
    user_id: uuid.UUID
    role: str = "member"


class SnapshotIn(BaseModel):
    note: str | None = None


class DDItemIn(BaseModel):
    category: DDCategory
    title: str
    assignee_id: uuid.UUID | None = None
    due_date: date | None = None


class DDItemUpdate(BaseModel):
    title: str | None = None
    status: DDStatus | None = None
    severity: Literal["low", "medium", "high", "critical"] | None = None
    findings: str | None = None
    assignee_id: uuid.UUID | None = None
    document_ids: list[uuid.UUID] | None = None
    due_date: date | None = None


class NegotiationIn(BaseModel):
    party: Literal["buyer", "seller", "broker", "other"]
    kind: Literal["offer", "counter_offer", "accepted", "rejected", "note"]
    amount: Money | None = None
    terms: str | None = None
    occurred_at: datetime | None = None


class AgreementIn(BaseModel):
    kind: Literal["loi", "mou", "agreement_to_sell", "sale_deed", "power_of_attorney", "other"]
    status: Literal["draft", "under_review", "signed", "registered", "cancelled"] = "draft"
    reference_number: str | None = None
    amount: Money | None = None
    signed_on: date | None = None
    registered_on: date | None = None
    valid_until: date | None = None
    document_id: uuid.UUID | None = None
    key_terms: dict = Field(default_factory=dict)
    notes: str | None = None


class AgreementUpdate(BaseModel):
    status: Literal["draft", "under_review", "signed", "registered", "cancelled"] | None = None
    reference_number: str | None = None
    amount: Money | None = None
    signed_on: date | None = None
    registered_on: date | None = None
    valid_until: date | None = None
    document_id: uuid.UUID | None = None
    key_terms: dict | None = None
    notes: str | None = None


# ---- Outputs ----


class DealOut(ORMModel):
    id: uuid.UUID
    code: str
    property_id: uuid.UUID
    title: str
    status: str
    is_active: bool
    priority: str
    source: str | None
    template_version_id: uuid.UUID
    activation_id: uuid.UUID | None
    current_stage_id: uuid.UUID | None
    stage_entered_at: datetime | None
    active_override_reason: str | None
    currency: str
    asking_price: Money | None
    expected_price: Money | None
    negotiated_price: Money | None
    next_action: str | None
    next_action_due: date | None
    next_action_assignee_id: uuid.UUID | None
    started_at: datetime
    closed_at: datetime | None
    close_reason: str | None
    notes: str | None
    custom_fields: dict
    created_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class DealListItem(DealOut):
    property_name: str
    property_code: str
    current_stage_key: str | None
    current_stage_name: str | None


class ChecklistItemOut(ORMModel):
    id: uuid.UUID
    key: str
    label: str
    is_required: bool
    is_hidden: bool
    status: str
    note: str | None
    document_id: uuid.UUID | None
    document_class_key: str | None
    completed_by_id: uuid.UUID | None
    completed_at: datetime | None


class DealStageOut(BaseModel):
    id: uuid.UUID
    stage_definition_id: uuid.UUID
    key: str
    name: str
    category: str
    color: str | None
    position: int
    status: str
    is_terminal: bool
    is_skippable: bool
    sla_days: int | None
    entered_at: datetime | None
    completed_at: datetime | None
    bypass_reason: str | None
    checklist: list[ChecklistItemOut]


class TransitionOut(ORMModel):
    id: uuid.UUID
    from_stage_id: uuid.UUID | None
    to_stage_id: uuid.UUID
    direction: str
    reason: str | None
    bypassed_stage_ids: list
    bypassed_checklist_item_ids: list
    actor_id: uuid.UUID | None
    occurred_at: datetime


class SnapshotOut(ORMModel):
    id: uuid.UUID
    reason: str
    owners: list
    summary: dict
    note: str | None
    taken_by_id: uuid.UUID | None
    taken_at: datetime


class DealAssignmentOut(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    role: str
    created_at: datetime


class DDItemOut(ORMModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    category: str
    title: str
    status: str
    severity: str | None
    findings: str | None
    assignee_id: uuid.UUID | None
    reviewer_id: uuid.UUID | None
    reviewed_at: datetime | None
    document_ids: list
    due_date: date | None
    created_at: datetime
    updated_at: datetime


class DDSummary(BaseModel):
    category: str
    status: str
    total: int
    clear: int
    issues: int
    open: int


class NegotiationOut(ORMModel):
    id: uuid.UUID
    party: str
    kind: str
    amount: Money | None
    terms: str | None
    occurred_at: datetime
    recorded_by_id: uuid.UUID | None


class AgreementOut(ORMModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    kind: str
    status: str
    reference_number: str | None
    amount: Money | None
    signed_on: date | None
    registered_on: date | None
    valid_until: date | None
    document_id: uuid.UUID | None
    key_terms: dict
    notes: str | None
    created_at: datetime
    updated_at: datetime

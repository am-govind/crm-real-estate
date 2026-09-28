import uuid

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.context import RequestContext
from app.core.db import utcnow
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.modules.audit import service as audit
from app.modules.workflows.models import (
    STAGE_CATEGORIES,
    ChecklistItemDefinition,
    StageDefinition,
    TenantTemplatePermission,
    TenantWorkflowActivation,
    WorkflowTemplate,
    WorkflowTemplateVersion,
)
from app.modules.workflows.schemas import StageIn, VersionDraftIn

ALLOWED_CONFIG_KEYS = {"stage_labels", "sla_days", "hidden_optional_items"}


def require_system_admin(ctx: RequestContext) -> None:
    if not ctx.is_system_admin:
        raise Forbidden("Workflow templates are published by system administrators")


def _validate_stages(stages: list[StageIn]) -> None:
    keys = [s.key for s in stages]
    if len(keys) != len(set(keys)):
        raise ValidationFailed("Stage keys must be unique")
    for s in stages:
        if s.category not in STAGE_CATEGORIES:
            raise ValidationFailed(f"Unknown category {s.category!r}", details={"allowed": list(STAGE_CATEGORIES)})
        item_keys = [c.key for c in s.checklist]
        if len(item_keys) != len(set(item_keys)):
            raise ValidationFailed(f"Checklist keys must be unique within stage {s.key}")
    if not stages[-1].is_terminal:
        raise ValidationFailed("The last stage must be terminal")
    if any(s.is_terminal for s in stages[:-1]):
        raise ValidationFailed("Only the last stage may be terminal")


def _build_stages(stages: list[StageIn]) -> list[StageDefinition]:
    out = []
    for pos, s in enumerate(stages):
        stage = StageDefinition(
            key=s.key, name=s.name, description=s.description, position=pos, category=s.category,
            color=s.color, is_terminal=s.is_terminal, is_skippable=s.is_skippable, sla_days=s.sla_days,
        )
        stage.checklist = [
            ChecklistItemDefinition(
                key=c.key, label=c.label, description=c.description, position=i,
                is_required=c.is_required, document_class_key=c.document_class_key,
            )
            for i, c in enumerate(s.checklist)
        ]
        out.append(stage)
    return out


def load_version(session: Session, version_id: uuid.UUID) -> WorkflowTemplateVersion:
    v = session.scalar(
        select(WorkflowTemplateVersion)
        .where(WorkflowTemplateVersion.id == version_id)
        .options(selectinload(WorkflowTemplateVersion.stages).selectinload(StageDefinition.checklist))
    )
    if v is None:
        raise NotFound("Workflow version not found")
    return v


def create_template(session: Session, ctx: RequestContext | None, *, key: str, name: str, description: str | None, land_types: list[str]) -> WorkflowTemplate:
    if session.scalar(select(WorkflowTemplate).where(WorkflowTemplate.key == key)):
        raise Conflict("Template key already exists")
    t = WorkflowTemplate(key=key, name=name, description=description, land_types=land_types)
    session.add(t)
    session.flush()
    audit.record(session, ctx, "workflow_template.created", "workflow_template", t.id, metadata={"key": key})
    return t


def create_draft(session: Session, ctx: RequestContext | None, template: WorkflowTemplate, body: VersionDraftIn) -> WorkflowTemplateVersion:
    _validate_stages(body.stages)
    next_version = (session.scalar(select(func.max(WorkflowTemplateVersion.version)).where(WorkflowTemplateVersion.template_id == template.id)) or 0) + 1
    v = WorkflowTemplateVersion(template_id=template.id, version=next_version, status="draft", notes=body.notes)
    v.stages = _build_stages(body.stages)
    session.add(v)
    session.flush()
    audit.record(session, ctx, "workflow_version.drafted", "workflow_template_version", v.id, metadata={"version": next_version})
    return v


def replace_draft(session: Session, ctx: RequestContext, version: WorkflowTemplateVersion, body: VersionDraftIn) -> WorkflowTemplateVersion:
    if version.status != "draft":
        raise Conflict("Published versions are immutable; create a new draft instead")
    _validate_stages(body.stages)
    version.stages = []
    session.flush()
    version.stages = _build_stages(body.stages)
    version.notes = body.notes
    session.flush()
    audit.record(session, ctx, "workflow_version.draft_updated", "workflow_template_version", version.id)
    return version


def publish(session: Session, ctx: RequestContext | None, version: WorkflowTemplateVersion) -> WorkflowTemplateVersion:
    if version.status != "draft":
        raise Conflict("Only drafts can be published")
    if len(version.stages) < 2:
        raise ValidationFailed("A workflow requires at least two stages")
    version.status = "published"
    version.published_at = utcnow()
    version.published_by_id = ctx.user_id if ctx else None
    audit.record(session, ctx, "workflow_version.published", "workflow_template_version", version.id)
    return version


def retire(session: Session, ctx: RequestContext, version: WorkflowTemplateVersion) -> WorkflowTemplateVersion:
    """Retired versions cannot be newly activated; existing deals keep using them."""
    if version.status != "published":
        raise Conflict("Only published versions can be retired")
    version.status = "retired"
    audit.record(session, ctx, "workflow_version.retired", "workflow_template_version", version.id)
    return version


def validate_activation_config(version: WorkflowTemplateVersion, config: dict) -> None:
    unknown = set(config) - ALLOWED_CONFIG_KEYS
    if unknown:
        raise ValidationFailed("Unsupported workflow configuration", details={"keys": sorted(unknown), "allowed": sorted(ALLOWED_CONFIG_KEYS)})
    stage_keys = {s.key for s in version.stages}
    for k in (config.get("stage_labels") or {}):
        if k not in stage_keys:
            raise ValidationFailed(f"Unknown stage {k!r} in stage_labels")
    for k, v in (config.get("sla_days") or {}).items():
        if k not in stage_keys or not isinstance(v, int) or v < 0:
            raise ValidationFailed(f"Invalid SLA override for {k!r}")
    items = {f"{s.key}.{c.key}": c for s in version.stages for c in s.checklist}
    for ref in config.get("hidden_optional_items") or []:
        item = items.get(ref)
        if item is None:
            raise ValidationFailed(f"Unknown checklist item {ref!r}")
        if item.is_required:
            raise ValidationFailed(f"Required checklist item {ref!r} cannot be hidden")


def is_template_permitted(session: Session, tenant_id: uuid.UUID, template_id: uuid.UUID) -> bool:
    rows = session.scalars(select(TenantTemplatePermission.template_id).where(TenantTemplatePermission.tenant_id == tenant_id)).all()
    return not rows or template_id in rows


def activate(session: Session, ctx: RequestContext, *, version_id: uuid.UUID, is_default: bool, land_types: list[str], config: dict) -> TenantWorkflowActivation:
    tenant_id = ctx.require_tenant()
    version = load_version(session, version_id)
    if version.status != "published":
        raise ValidationFailed("Only published workflow versions can be activated")
    if not is_template_permitted(session, tenant_id, version.template_id):
        raise Forbidden("This workflow template is not permitted for your tenant")
    validate_activation_config(version, config)
    existing = session.scalar(
        select(TenantWorkflowActivation).where(
            TenantWorkflowActivation.tenant_id == tenant_id, TenantWorkflowActivation.template_version_id == version_id
        )
    )
    if existing:
        raise Conflict("This version is already activated")
    if is_default:
        _clear_default(session, tenant_id)
    act = TenantWorkflowActivation(
        tenant_id=tenant_id, template_version_id=version.id, is_default=is_default,
        land_types=land_types, config=config, activated_by_id=ctx.user_id,
    )
    session.add(act)
    session.flush()
    audit.record(session, ctx, "workflow.activated", "tenant_workflow_activation", act.id, metadata={"version_id": str(version.id), "config": config})
    return act


def _clear_default(session: Session, tenant_id: uuid.UUID) -> None:
    session.execute(
        update(TenantWorkflowActivation).where(TenantWorkflowActivation.tenant_id == tenant_id).values(is_default=False)
    )


def update_activation(session: Session, ctx: RequestContext, act: TenantWorkflowActivation, changes: dict) -> TenantWorkflowActivation:
    before = audit.snapshot(act)
    if "config" in changes and changes["config"] is not None:
        validate_activation_config(load_version(session, act.template_version_id), changes["config"])
    if changes.get("is_default"):
        _clear_default(session, act.tenant_id)
    for k, v in changes.items():
        if v is not None:
            setattr(act, k, v)
    session.flush()
    audit.record_update(session, ctx, "tenant_workflow_activation", act, before)
    return act


def resolve_activation(session: Session, tenant_id: uuid.UUID, *, land_type: str | None, activation_id: uuid.UUID | None) -> TenantWorkflowActivation:
    if activation_id:
        act = session.get(TenantWorkflowActivation, activation_id)
        if act is None or act.tenant_id != tenant_id or not act.is_active:
            raise NotFound("Workflow activation not found")
        return act
    acts = session.scalars(
        select(TenantWorkflowActivation).where(
            TenantWorkflowActivation.tenant_id == tenant_id, TenantWorkflowActivation.is_active.is_(True)
        )
    ).all()
    if land_type:
        for a in acts:
            if land_type in (a.land_types or []):
                return a
    for a in acts:
        if a.is_default:
            return a
    if len(acts) == 1:
        return acts[0]
    raise ValidationFailed("No workflow is activated for this tenant; ask a tenant administrator to activate one")


# ---- Default template ----

DEFAULT_TEMPLATE_KEY = "india_land_acquisition"


def _stage(key, name, category, color, checklist=(), skippable=True, terminal=False, sla=None):
    return StageIn(
        key=key, name=name, category=category, color=color, is_skippable=skippable, is_terminal=terminal, sla_days=sla,
        checklist=[
            {"key": c[0], "label": c[1], "is_required": c[2] if len(c) > 2 else True, "document_class_key": c[3] if len(c) > 3 else None}
            for c in checklist
        ],
    )


DEFAULT_STAGES: list[StageIn] = [
    _stage("new_lead", "New Lead", "lead", "#64748b", [("source_recorded", "Lead source recorded"), ("basic_location", "Basic location captured")]),
    _stage("initial_screening", "Initial Screening", "screening", "#0ea5e9", [("fit_assessment", "Fit against acquisition criteria"), ("asking_price_known", "Asking price captured", False)], sla=7),
    _stage("site_visit", "Site Visit", "screening", "#06b6d4", [("visit_completed", "Site visit completed"), ("photos_uploaded", "Site photos uploaded", False)], sla=14),
    _stage("owner_verification", "Owner Verification", "diligence", "#8b5cf6", [("owners_identified", "All owners identified"), ("identity_docs", "Owner identity documents collected", True, "owner_identity")], skippable=False),
    _stage("document_collection", "Document Collection", "diligence", "#a855f7", [
        ("sale_deed", "Sale deed collected", True, "sale_deed"),
        ("khatauni", "Khatauni / record of rights collected", True, "khatauni"),
        ("mutation", "Mutation record collected", True, "mutation"),
        ("encumbrance", "Encumbrance certificate collected", True, "encumbrance"),
        ("tax_receipts", "Property tax receipts", False, "property_tax"),
    ], sla=21),
    _stage("legal_due_diligence", "Legal Due Diligence", "diligence", "#d946ef", [("title_search", "Title search completed"), ("legal_opinion", "Legal opinion recorded", True, "legal_opinion")], skippable=False),
    _stage("technical_survey", "Technical / Land Survey", "diligence", "#ec4899", [("demarcation", "Demarcation completed", True, "demarcation"), ("survey_report", "Survey report uploaded", True, "survey_report")]),
    _stage("valuation", "Valuation", "valuation", "#f43f5e", [("valuation_report", "Valuation report", False, "valuation_report"), ("target_price_set", "Target price set")]),
    _stage("negotiation", "Negotiation", "negotiation", "#f97316", [("terms_agreed", "Commercial terms agreed")]),
    _stage("loi_mou", "LOI / MOU", "agreement", "#f59e0b", [("loi_signed", "LOI / MOU signed", True, "loi_mou")]),
    _stage("agreement_to_sell", "Agreement to Sell", "agreement", "#eab308", [("ats_signed", "Agreement to sell signed", True, "agreement_to_sell")], skippable=False),
    _stage("advance_payment", "Advance Payment", "payment", "#84cc16", [("advance_paid", "Advance paid"), ("advance_receipt", "Advance receipt uploaded", True, "payment_receipt")], skippable=False),
    _stage("registration", "Registration", "closing", "#22c55e", [("registered", "Sale deed registered", True, "registration")], skippable=False),
    _stage("final_payment", "Final Payment", "payment", "#10b981", [("final_paid", "Final payment made"), ("final_receipt", "Final receipt uploaded", True, "payment_receipt")], skippable=False),
    _stage("closed", "Closed", "closed", "#15803d", terminal=True, skippable=False),
]


def ensure_default_template(session: Session) -> WorkflowTemplateVersion:
    t = session.scalar(select(WorkflowTemplate).where(WorkflowTemplate.key == DEFAULT_TEMPLATE_KEY))
    if t is None:
        t = create_template(
            session, None, key=DEFAULT_TEMPLATE_KEY, name="India land acquisition",
            description="Default acquisition journey for land parcels in India", land_types=[],
        )
    published = session.scalar(
        select(WorkflowTemplateVersion).where(
            WorkflowTemplateVersion.template_id == t.id, WorkflowTemplateVersion.status == "published"
        ).order_by(WorkflowTemplateVersion.version.desc())
    )
    if published:
        return published
    v = create_draft(session, None, t, VersionDraftIn(notes="Initial version", stages=DEFAULT_STAGES))
    return publish(session, None, v)

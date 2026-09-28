import uuid

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.deps import DB, Ctx, TenantCtx, requires
from app.core.errors import NotFound
from app.core.permissions import P
from app.modules.workflows import service
from app.modules.workflows.models import (
    StageDefinition,
    TenantWorkflowActivation,
    WorkflowTemplate,
    WorkflowTemplateVersion,
)
from app.modules.workflows.schemas import (
    ActivationIn,
    ActivationOut,
    ActivationUpdate,
    TemplateCreate,
    TemplateOut,
    VersionDraftIn,
    VersionOut,
)

router = APIRouter(tags=["workflows"])


def _template(db, template_id: uuid.UUID) -> WorkflowTemplate:
    t = db.get(WorkflowTemplate, template_id)
    if t is None:
        raise NotFound("Template not found")
    return t


# ---- System administration: templates are centrally published ----


@router.post("/admin/workflow-templates", response_model=TemplateOut, status_code=201)
def create_template(body: TemplateCreate, ctx: Ctx, db: DB):
    service.require_system_admin(ctx)
    return service.create_template(db, ctx, **body.model_dump())


@router.post("/admin/workflow-templates/{template_id}/versions", response_model=VersionOut, status_code=201)
def create_version(template_id: uuid.UUID, body: VersionDraftIn, ctx: Ctx, db: DB):
    service.require_system_admin(ctx)
    return service.create_draft(db, ctx, _template(db, template_id), body)


@router.put("/admin/workflow-versions/{version_id}", response_model=VersionOut)
def update_draft(version_id: uuid.UUID, body: VersionDraftIn, ctx: Ctx, db: DB):
    service.require_system_admin(ctx)
    return service.replace_draft(db, ctx, service.load_version(db, version_id), body)


@router.post("/admin/workflow-versions/{version_id}/publish", response_model=VersionOut)
def publish_version(version_id: uuid.UUID, ctx: Ctx, db: DB):
    service.require_system_admin(ctx)
    return service.publish(db, ctx, service.load_version(db, version_id))


@router.post("/admin/workflow-versions/{version_id}/retire", response_model=VersionOut)
def retire_version(version_id: uuid.UUID, ctx: Ctx, db: DB):
    service.require_system_admin(ctx)
    return service.retire(db, ctx, service.load_version(db, version_id))


# ---- Tenant view ----


@router.get("/workflow-templates", response_model=list[TemplateOut])
def list_templates(ctx: TenantCtx, db: DB):
    templates = db.scalars(
        select(WorkflowTemplate).where(WorkflowTemplate.is_archived.is_(False)).options(selectinload(WorkflowTemplate.versions))
    ).all()
    return [t for t in templates if ctx.is_system_admin or service.is_template_permitted(db, ctx.tenant_id, t.id)]


@router.get("/workflow-versions/{version_id}", response_model=VersionOut)
def get_version(version_id: uuid.UUID, _: TenantCtx, db: DB):
    return service.load_version(db, version_id)


def _activation_query(tenant_id):
    return (
        select(TenantWorkflowActivation)
        .where(TenantWorkflowActivation.tenant_id == tenant_id)
        .options(
            selectinload(TenantWorkflowActivation.template_version)
            .selectinload(WorkflowTemplateVersion.stages)
            .selectinload(StageDefinition.checklist)
        )
    )


@router.get("/workflow-activations", response_model=list[ActivationOut])
def list_activations(ctx: TenantCtx, db: DB):
    return list(db.scalars(_activation_query(ctx.tenant_id)))


@router.post("/workflow-activations", response_model=ActivationOut, status_code=201)
def activate(body: ActivationIn, db: DB, ctx=requires(P.WORKFLOW_CONFIGURE)):
    act = service.activate(
        db, ctx, version_id=body.template_version_id, is_default=body.is_default, land_types=body.land_types, config=body.config
    )
    return db.scalar(_activation_query(ctx.tenant_id).where(TenantWorkflowActivation.id == act.id))


@router.patch("/workflow-activations/{activation_id}", response_model=ActivationOut)
def update_activation(activation_id: uuid.UUID, body: ActivationUpdate, db: DB, ctx=requires(P.WORKFLOW_CONFIGURE)):
    act = db.scalar(_activation_query(ctx.tenant_id).where(TenantWorkflowActivation.id == activation_id))
    if act is None:
        raise NotFound("Activation not found")
    return service.update_activation(db, ctx, act, body.model_dump(exclude_unset=True))

import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.core.db import utcnow
from app.core.deps import DB, requires
from app.core.errors import NotFound
from app.core.pagination import Page, PageParams, paginate
from app.core.permissions import P
from app.core.schemas import ORMModel
from app.core.tenancy import get_scoped, scoped
from app.modules.audit import service as audit
from app.modules.deals.access import get_visible_deal
from app.modules.deals.access import visible_clause as deal_visible
from app.modules.deals.models import Deal
from app.modules.identity.models import TenantMembership
from app.modules.properties.access import get_visible_property
from app.modules.properties.access import visible_clause as prop_visible
from app.modules.properties.models import Property
from app.modules.tasks.models import Task

router = APIRouter(prefix="/tasks", tags=["tasks"])

Status = Literal["open", "in_progress", "blocked", "done", "cancelled"]
Priority = Literal["low", "medium", "high", "urgent"]


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    priority: Priority = "medium"
    due_date: date | None = None
    assignee_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    deal_stage_id: uuid.UUID | None = None
    site_visit_id: uuid.UUID | None = None
    client_ref: str | None = Field(default=None, max_length=64)


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: Status | None = None
    priority: Priority | None = None
    due_date: date | None = None
    assignee_id: uuid.UUID | None = None


class TaskOut(ORMModel):
    id: uuid.UUID
    title: str
    description: str | None
    status: str
    priority: str
    due_date: date | None
    assignee_id: uuid.UUID | None
    property_id: uuid.UUID | None
    deal_id: uuid.UUID | None
    deal_stage_id: uuid.UUID | None
    site_visit_id: uuid.UUID | None
    completed_at: datetime | None
    created_by_id: uuid.UUID | None
    client_ref: str | None
    created_at: datetime
    updated_at: datetime


def _require_member(db, tenant_id, user_id):
    if user_id and db.scalar(
        select(TenantMembership.id).where(TenantMembership.tenant_id == tenant_id, TenantMembership.user_id == user_id)
    ) is None:
        raise NotFound("Assignee is not a member of this tenant")


def create_task(db, ctx, body: TaskCreate) -> Task:
    if body.client_ref:
        existing = db.scalar(scoped(Task, ctx).where(Task.client_ref == body.client_ref))
        if existing:
            return existing
    _require_member(db, ctx.tenant_id, body.assignee_id)
    property_id = body.property_id
    if body.deal_id:
        deal = get_visible_deal(db, body.deal_id, ctx)
        property_id = property_id or deal.property_id
    if property_id:
        get_visible_property(db, property_id, ctx)
    if body.site_visit_id:
        from app.modules.site_visits.models import SiteVisit

        get_scoped(db, SiteVisit, body.site_visit_id, ctx, label="Site visit")
    task = Task(tenant_id=ctx.tenant_id, created_by_id=ctx.user_id, **{**body.model_dump(), "property_id": property_id})
    db.add(task)
    db.flush()
    audit.record(db, ctx, "task.created", "task", task.id, changes=audit.snapshot(task))
    return task


@router.get("", response_model=Page[TaskOut])
def list_tasks(
    db: DB,
    status: list[str] | None = Query(None),
    assignee_id: uuid.UUID | None = None,
    mine: bool = False,
    property_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
    site_visit_id: uuid.UUID | None = None,
    overdue: bool = False,
    due_before: date | None = None,
    page: PageParams = Depends(),
    ctx=requires(P.TASK_READ),
):
    stmt = scoped(Task, ctx)
    if status:
        stmt = stmt.where(Task.status.in_(status))
    if mine:
        stmt = stmt.where(Task.assignee_id == ctx.user_id)
    elif assignee_id:
        stmt = stmt.where(Task.assignee_id == assignee_id)
    for col, val in ((Task.property_id, property_id), (Task.deal_id, deal_id), (Task.site_visit_id, site_visit_id)):
        if val:
            stmt = stmt.where(col == val)
    if overdue:
        stmt = stmt.where(Task.due_date < date.today(), Task.status.in_(("open", "in_progress", "blocked")))
    if due_before:
        stmt = stmt.where(Task.due_date <= due_before)
    if not (ctx.has(P.DEAL_READ_ALL) or mine or assignee_id == ctx.user_id):
        stmt = stmt.where(
            or_(
                Task.assignee_id == ctx.user_id,
                Task.created_by_id == ctx.user_id,
                Task.deal_id.in_(select(Deal.id).where(deal_visible(ctx))),
                Task.property_id.in_(select(Property.id).where(prop_visible(ctx))),
            )
        )
    items, total = paginate(db, stmt.order_by(Task.due_date.is_(None), Task.due_date, Task.created_at.desc()), page)
    return {"items": items, "total": total, "limit": page.limit, "offset": page.offset}


@router.post("", response_model=TaskOut, status_code=201)
def create(body: TaskCreate, db: DB, ctx=requires(P.TASK_WRITE)):
    return create_task(db, ctx, body)


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: uuid.UUID, db: DB, ctx=requires(P.TASK_READ)):
    return get_scoped(db, Task, task_id, ctx, label="Task")


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(task_id: uuid.UUID, body: TaskUpdate, db: DB, ctx=requires(P.TASK_WRITE)):
    task = get_scoped(db, Task, task_id, ctx, label="Task")
    changes = body.model_dump(exclude_unset=True)
    if "assignee_id" in changes:
        _require_member(db, ctx.tenant_id, changes["assignee_id"])
    before = audit.snapshot(task)
    for k, v in changes.items():
        setattr(task, k, v)
    if changes.get("status") == "done" and task.completed_at is None:
        task.completed_at = utcnow()
        task.completed_by_id = ctx.user_id
    elif "status" in changes and changes["status"] != "done":
        task.completed_at = None
        task.completed_by_id = None
    db.flush()
    audit.record_update(db, ctx, "task", task, before)
    return task

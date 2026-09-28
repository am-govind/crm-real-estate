"""Offline mobile synchronization. Clients queue operations with stable ``client_ref`` values and
push them when online; every operation is idempotent and isolated in its own savepoint."""

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import or_, select

from app.core.db import utcnow
from app.core.deps import DB, requires
from app.core.errors import DomainError, NotFound
from app.core.permissions import P
from app.core.tenancy import get_scoped, scoped
from app.modules.properties.access import visible_clause as property_visible
from app.modules.properties.models import Property, PropertyAssignment
from app.modules.site_visits import service as visits
from app.modules.site_visits.models import SiteVisit, SiteVisitAttendee
from app.modules.site_visits.schemas import CheckOutIn, GeoPoint, NoteIn, VisitCreate, VisitOut
from app.modules.tasks.models import Task
from app.modules.tasks.router import TaskCreate, TaskOut, TaskUpdate, create_task

router = APIRouter(prefix="/sync", tags=["sync"])

OpKind = Literal[
    "site_visit.create", "site_visit.check_in", "site_visit.check_out", "site_visit.note", "task.create", "task.update"
]


class SyncOp(BaseModel):
    op: OpKind
    client_ref: str = Field(min_length=1, max_length=64)
    visit_id: uuid.UUID | None = None
    visit_client_ref: str | None = None
    task_id: uuid.UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SyncPush(BaseModel):
    ops: list[SyncOp] = Field(max_length=500)


class SyncResult(BaseModel):
    client_ref: str
    status: Literal["applied", "error"]
    id: uuid.UUID | None = None
    error: str | None = None


def _visit(db, ctx, op: SyncOp) -> SiteVisit:
    if op.visit_id:
        return visits.get_visible_visit(db, op.visit_id, ctx)
    found = visits.find_by_client_ref(db, ctx, op.visit_client_ref)
    if found is None:
        raise NotFound("Visit not found for this operation")
    return found


def _apply(db, ctx, op: SyncOp) -> uuid.UUID:
    if op.op == "site_visit.create":
        ctx.require(P.SITE_VISIT_WRITE)
        return visits.create_visit(db, ctx, VisitCreate(**{**op.payload, "client_ref": op.client_ref})).id
    if op.op == "site_visit.check_in":
        ctx.require(P.SITE_VISIT_WRITE)
        return visits.check_in(db, ctx, _visit(db, ctx, op), GeoPoint(**op.payload)).id
    if op.op == "site_visit.check_out":
        ctx.require(P.SITE_VISIT_WRITE)
        return visits.check_out(db, ctx, _visit(db, ctx, op), CheckOutIn(**op.payload)).id
    if op.op == "site_visit.note":
        ctx.require(P.SITE_VISIT_WRITE)
        return visits.add_note(db, ctx, _visit(db, ctx, op), NoteIn(**{**op.payload, "client_ref": op.client_ref})).id
    if op.op == "task.create":
        ctx.require(P.TASK_WRITE)
        payload = dict(op.payload)
        if op.visit_client_ref and not payload.get("site_visit_id"):
            payload["site_visit_id"] = _visit(db, ctx, op).id
        return create_task(db, ctx, TaskCreate(**{**payload, "client_ref": op.client_ref})).id
    if op.op == "task.update":
        ctx.require(P.TASK_WRITE)
        task = get_scoped(db, Task, op.task_id, ctx, label="Task")
        changes = TaskUpdate(**op.payload).model_dump(exclude_unset=True)
        for k, v in changes.items():
            setattr(task, k, v)
        if changes.get("status") == "done" and task.completed_at is None:
            task.completed_at, task.completed_by_id = utcnow(), ctx.user_id
        return task.id
    raise NotFound(f"Unknown operation {op.op}")


@router.post("/push", response_model=list[SyncResult])
def push(body: SyncPush, db: DB, ctx=requires(P.SITE_VISIT_READ)):
    results = []
    for op in body.ops:
        sp = db.begin_nested()
        try:
            obj_id = _apply(db, ctx, op)
            sp.commit()
            results.append(SyncResult(client_ref=op.client_ref, status="applied", id=obj_id))
        except (DomainError, ValidationError, ValueError) as exc:
            sp.rollback()
            message = exc.message if isinstance(exc, DomainError) else str(exc)
            results.append(SyncResult(client_ref=op.client_ref, status="error", error=message[:500]))
    return results


@router.get("/pull")
def pull(db: DB, since: datetime | None = None, ctx=requires(P.SITE_VISIT_READ)):
    server_time = utcnow()
    visit_stmt = scoped(SiteVisit, ctx).where(
        SiteVisit.id.in_(select(SiteVisitAttendee.visit_id).where(SiteVisitAttendee.user_id == ctx.user_id))
    )
    task_stmt = scoped(Task, ctx).where(or_(Task.assignee_id == ctx.user_id, Task.created_by_id == ctx.user_id))
    prop_stmt = scoped(Property, ctx).where(
        property_visible(ctx),
        Property.id.in_(select(PropertyAssignment.property_id).where(PropertyAssignment.user_id == ctx.user_id)),
    )
    if since:
        visit_stmt = visit_stmt.where(SiteVisit.updated_at > since)
        task_stmt = task_stmt.where(Task.updated_at > since)
        prop_stmt = prop_stmt.where(Property.updated_at > since)
    return {
        "server_time": server_time.isoformat(),
        "site_visits": [VisitOut.model_validate(v).model_dump(mode="json") for v in db.scalars(visit_stmt.limit(1000))],
        "tasks": [TaskOut.model_validate(t).model_dump(mode="json") for t in db.scalars(task_stmt.limit(2000))],
        "properties": [
            {"id": str(p.id), "code": p.code, "name": p.name, "status": p.status, "latitude": str(p.latitude) if p.latitude is not None else None,
             "longitude": str(p.longitude) if p.longitude is not None else None, "survey_number": p.survey_number,
             "address": p.address, "updated_at": p.updated_at.isoformat()}
            for p in db.scalars(prop_stmt.limit(1000))
        ],
    }

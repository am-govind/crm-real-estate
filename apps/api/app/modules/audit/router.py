import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.deps import DB, requires
from app.core.pagination import Page, PageParams, paginate
from app.core.permissions import P
from app.core.schemas import ORMModel
from app.core.tenancy import scoped
from app.modules.audit.models import AuditEvent

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEventOut(ORMModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    changes: dict
    metadata_: dict
    request_id: str | None
    occurred_at: datetime


class _Filters(BaseModel):
    entity_type: str | None = None
    entity_id: str | None = None
    actor_id: uuid.UUID | None = None
    action: str | None = None


@router.get("", response_model=Page[AuditEventOut])
def list_events(
    db: DB,
    filters: _Filters = Depends(),
    page: PageParams = Depends(),
    ctx=requires(P.AUDIT_READ),
) -> dict:
    stmt = scoped(AuditEvent, ctx)
    if filters.entity_type:
        stmt = stmt.where(AuditEvent.entity_type == filters.entity_type)
    if filters.entity_id:
        stmt = stmt.where(AuditEvent.entity_id == filters.entity_id)
    if filters.actor_id:
        stmt = stmt.where(AuditEvent.actor_id == filters.actor_id)
    if filters.action:
        stmt = stmt.where(AuditEvent.action.startswith(filters.action))
    items, total = paginate(db, stmt.order_by(AuditEvent.occurred_at.desc()), page)
    return {"items": items, "total": total, "limit": page.limit, "offset": page.offset}

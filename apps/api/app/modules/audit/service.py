import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.modules.audit.models import AuditEvent


def _jsonable(value: Any) -> Any:
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    return value


def snapshot(obj: Any, fields: list[str] | None = None) -> dict[str, Any]:
    mapper = inspect(obj).mapper
    names = fields or [c.key for c in mapper.column_attrs]
    return {n: _jsonable(getattr(obj, n)) for n in names}


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    keys = set(before) | set(after)
    return {
        k: {"from": before.get(k), "to": after.get(k)}
        for k in sorted(keys)
        if before.get(k) != after.get(k) and k not in ("updated_at",)
    }


def record(
    session: Session,
    ctx: RequestContext | None,
    action: str,
    entity_type: str,
    entity_id: Any = None,
    *,
    changes: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    tenant_id: uuid.UUID | None = None,
) -> AuditEvent:
    event = AuditEvent(
        tenant_id=tenant_id or (ctx.tenant_id if ctx else None),
        actor_id=ctx.user_id if ctx else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        changes=_jsonable(changes or {}),
        metadata_=_jsonable(metadata or {}),
        request_id=ctx.request_id if ctx else None,
        ip_address=ctx.ip_address if ctx else None,
    )
    session.add(event)
    return event


def record_update(
    session: Session, ctx: RequestContext, entity_type: str, obj: Any, before: dict[str, Any], **kwargs: Any
) -> AuditEvent | None:
    changes = diff(before, snapshot(obj))
    if not changes:
        return None
    return record(session, ctx, f"{entity_type}.updated", entity_type, obj.id, changes=changes, **kwargs)

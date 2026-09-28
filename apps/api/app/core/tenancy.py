"""Service-layer tenant enforcement. All tenant-owned reads must go through these helpers."""

import uuid
from typing import TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.errors import NotFound

M = TypeVar("M")


def scoped(model: type[M], ctx: RequestContext) -> Select:
    return select(model).where(model.tenant_id == ctx.require_tenant())  # type: ignore[attr-defined]


def get_scoped(session: Session, model: type[M], obj_id: uuid.UUID, ctx: RequestContext, *, label: str | None = None) -> M:
    obj = session.get(model, obj_id)
    if obj is None or getattr(obj, "tenant_id", None) != ctx.require_tenant():
        raise NotFound(f"{label or model.__name__} not found")
    return obj


def ensure_same_tenant(ctx: RequestContext, *objs: object) -> None:
    tid = ctx.require_tenant()
    for obj in objs:
        if obj is not None and getattr(obj, "tenant_id", None) != tid:
            raise NotFound("Related record not found")

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, update

from app.core.db import utcnow
from app.core.deps import DB, Ctx, TenantCtx
from app.core.errors import NotFound
from app.core.pagination import Page, PageParams, paginate
from app.core.schemas import ORMModel
from app.core.tenancy import scoped
from app.modules.notifications.models import DevicePushToken, Notification

router = APIRouter(tags=["notifications"])


class NotificationOut(ORMModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str | None
    link: str | None
    entity_type: str | None
    entity_id: str | None
    read_at: datetime | None
    created_at: datetime


class DeviceIn(BaseModel):
    token: str
    platform: Literal["ios", "android", "web"]


@router.get("/notifications", response_model=Page[NotificationOut])
def list_notifications(ctx: TenantCtx, db: DB, unread_only: bool = False, page: PageParams = Depends()):
    stmt = scoped(Notification, ctx).where(Notification.user_id == ctx.user_id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    items, total = paginate(db, stmt.order_by(Notification.created_at.desc()), page)
    return {"items": items, "total": total, "limit": page.limit, "offset": page.offset}


@router.post("/notifications/{notification_id}/read", status_code=204)
def mark_read(notification_id: uuid.UUID, ctx: TenantCtx, db: DB):
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != ctx.user_id:
        raise NotFound("Notification not found")
    n.read_at = n.read_at or utcnow()


@router.post("/notifications/read-all", status_code=204)
def mark_all_read(ctx: TenantCtx, db: DB):
    db.execute(
        update(Notification)
        .where(Notification.user_id == ctx.user_id, Notification.tenant_id == ctx.tenant_id, Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )


@router.post("/devices", status_code=204)
def register_device(body: DeviceIn, ctx: Ctx, db: DB):
    existing = db.scalar(select(DevicePushToken).where(DevicePushToken.token == body.token))
    if existing:
        existing.user_id = ctx.user_id
        existing.platform = body.platform
        existing.revoked_at = None
    else:
        db.add(DevicePushToken(user_id=ctx.user_id, token=body.token, platform=body.platform))


@router.delete("/devices/{token}", status_code=204)
def unregister_device(token: str, ctx: Ctx, db: DB):
    existing = db.scalar(select(DevicePushToken).where(DevicePushToken.token == token, DevicePushToken.user_id == ctx.user_id))
    if existing:
        existing.revoked_at = utcnow()

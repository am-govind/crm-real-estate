import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.notifications import channels
from app.modules.notifications.models import DevicePushToken, Notification


def notify(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    user_ids: Iterable[uuid.UUID | None],
    kind: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    dedupe_key: str | None = None,
    push: bool = False,
) -> list[Notification]:
    created: list[Notification] = []
    for uid in {u for u in user_ids if u}:
        if dedupe_key and session.scalar(
            select(Notification.id).where(Notification.user_id == uid, Notification.dedupe_key == dedupe_key)
        ):
            continue
        n = Notification(
            tenant_id=tenant_id, user_id=uid, kind=kind, title=title, body=body, link=link,
            entity_type=entity_type, entity_id=entity_id, dedupe_key=dedupe_key,
        )
        session.add(n)
        created.append(n)
    session.flush()
    if push and created:
        tokens = list(
            session.scalars(
                select(DevicePushToken.token).where(
                    DevicePushToken.user_id.in_([n.user_id for n in created]), DevicePushToken.revoked_at.is_(None)
                )
            )
        )
        channels.push_channel.send(tokens, title=title, body=body, data={"link": link, "kind": kind})
    return created

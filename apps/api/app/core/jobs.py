"""Transactional-outbox background jobs.

``enqueue`` writes a job row inside the caller's transaction. Only after that transaction
commits is the job dispatched: inline (a thread, for local development) or to a Redis list
consumed by the worker deployment. The worker also sweeps queued rows whose dispatch was lost.
"""

import logging
import threading
import traceback
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text, Uuid, event, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.config import get_settings
from app.core.db import Base, IdMixin, SessionLocal, TimestampMixin, utcnow

log = logging.getLogger("landcrm.jobs")

REDIS_QUEUE_KEY = "landcrm:jobs"

Handler = Callable[[Session, "BackgroundJob"], dict | None]
_HANDLERS: dict[str, Handler] = {}


class BackgroundJob(IdMixin, TimestampMixin, Base):
    __tablename__ = "background_jobs"

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    kind: Mapped[str] = mapped_column(String(80), index=True)
    payload: Mapped[dict] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime] = mapped_column(default=utcnow)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict] = mapped_column(default=dict)


def job_handler(kind: str) -> Callable[[Handler], Handler]:
    def _register(fn: Handler) -> Handler:
        _HANDLERS[kind] = fn
        return fn

    return _register


def enqueue(session: Session, kind: str, payload: dict[str, Any], *, tenant_id: uuid.UUID | None = None, max_attempts: int = 3) -> BackgroundJob:
    job = BackgroundJob(kind=kind, payload=payload, tenant_id=tenant_id, max_attempts=max_attempts)
    session.add(job)
    session.flush()
    session.info.setdefault("pending_jobs", []).append(job.id)
    return job


@event.listens_for(Session, "after_commit")
def _dispatch_after_commit(session: Session) -> None:
    ids = session.info.pop("pending_jobs", [])
    for job_id in ids:
        dispatch(job_id)


@event.listens_for(Session, "after_rollback")
def _discard_after_rollback(session: Session) -> None:
    session.info.pop("pending_jobs", None)


def dispatch(job_id: uuid.UUID) -> None:
    if get_settings().queue_backend == "redis":
        try:
            _redis().rpush(REDIS_QUEUE_KEY, str(job_id))
        except Exception:  # noqa: BLE001 - the worker sweeper will pick it up
            log.exception("Failed to push job %s to Redis", job_id)
        return
    threading.Thread(target=run_job, args=(job_id,), daemon=True).start()


_redis_client = None


def _redis():
    global _redis_client
    if _redis_client is None:
        import redis

        _redis_client = redis.Redis.from_url(get_settings().redis_url)
    return _redis_client


def load_handlers() -> None:
    """Imports modules that register job handlers."""
    import app.modules.documents.jobs  # noqa: F401
    import app.modules.maps.jobs  # noqa: F401
    import app.modules.payments.jobs  # noqa: F401


def run_job(job_id: uuid.UUID) -> None:
    load_handlers()
    with SessionLocal() as session:
        job = session.scalar(select(BackgroundJob).where(BackgroundJob.id == job_id).with_for_update(skip_locked=True))
        if job is None or job.status not in ("queued", "retrying"):
            return
        handler = _HANDLERS.get(job.kind)
        if handler is None:
            job.status = "failed"
            job.last_error = f"No handler registered for {job.kind}"
            session.commit()
            return
        job.status = "running"
        job.attempts += 1
        job.started_at = utcnow()
        session.commit()

        try:
            result = handler(session, job) or {}
            job.status = "succeeded"
            job.result = result
            job.finished_at = utcnow()
            session.commit()
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            job = session.get(BackgroundJob, job_id)
            assert job is not None
            job.last_error = "".join(traceback.format_exception_only(type(exc), exc))[-4000:]
            if job.attempts >= job.max_attempts:
                job.status = "failed"
                job.finished_at = utcnow()
            else:
                job.status = "retrying"
                job.run_after = utcnow() + timedelta(seconds=30 * (2 ** job.attempts))
            session.commit()
            log.exception("Job %s (%s) failed", job_id, job.kind)


def due_job_ids(session: Session, *, stale_after_seconds: int = 60, limit: int = 100) -> list[uuid.UUID]:
    now = utcnow()
    rows = session.scalars(
        select(BackgroundJob.id)
        .where(
            BackgroundJob.status.in_(("queued", "retrying")),
            BackgroundJob.run_after <= now,
            BackgroundJob.created_at <= now - timedelta(seconds=stale_after_seconds),
        )
        .limit(limit)
    )
    return list(rows)

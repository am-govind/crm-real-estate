"""Worker deployment: consumes the Redis job queue, sweeps missed jobs and runs periodic schedules.

Run with ``LANDCRM_QUEUE_BACKEND=redis python -m landcrm_worker.main``.
"""

import logging
import signal
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import select

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.core.jobs import REDIS_QUEUE_KEY, BackgroundJob, due_job_ids, enqueue, load_handlers, run_job

log = logging.getLogger("landcrm.worker")


@dataclass
class Schedule:
    kind: str
    every_seconds: int
    last_run: float = 0.0


SCHEDULES = [
    Schedule("documents.expiry_reminders", every_seconds=6 * 3600),
    Schedule("payments.overdue_check", every_seconds=3600),
]

_running = True


def _stop(*_):
    global _running
    _running = False


def _enqueue_periodic(now: float) -> None:
    for sched in SCHEDULES:
        if now - sched.last_run < sched.every_seconds:
            continue
        with SessionLocal() as s:
            pending = s.scalar(
                select(BackgroundJob.id).where(
                    BackgroundJob.kind == sched.kind, BackgroundJob.status.in_(("queued", "running", "retrying"))
                )
            )
            if pending is None:
                enqueue(s, sched.kind, {"scheduled_at": utcnow().isoformat()})
                s.commit()
                log.info("scheduled %s", sched.kind)
        sched.last_run = now


def _sweep() -> None:
    with SessionLocal() as s:
        ids = due_job_ids(s)
    for job_id in ids:
        run_job(job_id)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    load_handlers()

    settings = get_settings()
    redis_client = None
    if settings.queue_backend == "redis":
        import redis

        redis_client = redis.Redis.from_url(settings.redis_url)
    log.info("worker started (queue=%s)", settings.queue_backend)

    last_sweep = 0.0
    while _running:
        now = time.time()
        _enqueue_periodic(now)
        if now - last_sweep > 30:
            _sweep()
            last_sweep = now

        if redis_client is not None:
            item = redis_client.blpop([REDIS_QUEUE_KEY], timeout=5)
            if item:
                try:
                    run_job(uuid.UUID(item[1].decode()))
                except Exception:  # noqa: BLE001
                    log.exception("job crashed")
        else:
            time.sleep(5)
    log.info("worker stopped")


if __name__ == "__main__":
    main()

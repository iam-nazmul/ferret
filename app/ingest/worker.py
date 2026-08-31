"""Celery app and beat schedule.

Beat must run at exactly ONE replica — duplicate schedulers double-crawl every source.
"""

import asyncio
import uuid

from celery import Celery
from celery.schedules import crontab

from app.config import settings
from app.logging import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)

celery_app = Celery("ferret", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=3600,
    task_routes={"ferret.ingest_ocr": {"queue": "ocr"}},
    beat_schedule={
        "crawl-web-sources": {
            "task": "ferret.crawl_sources",
            "schedule": crontab(minute=0, hour="*/24"),
            "args": ("web_sitemap",),
        },
        "crawl-pdf-buckets": {
            "task": "ferret.crawl_sources",
            "schedule": crontab(minute=0, hour="*/6"),
            "args": ("pdf_bucket",),
        },
        "expire-threads": {
            "task": "ferret.expire_threads",
            "schedule": crontab(minute=30, hour=3),
        },
    },
)


@celery_app.task(name="ferret.crawl_sources")
def crawl_sources(kind: str) -> dict:
    return asyncio.run(_crawl_sources(kind))


@celery_app.task(name="ferret.ingest_source", bind=True, max_retries=3)
def ingest_source_task(self, source_id: str) -> dict:
    try:
        return asyncio.run(_ingest_one(uuid.UUID(source_id)))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries)) from exc


@celery_app.task(name="ferret.expire_threads")
def expire_threads_task() -> int:
    return asyncio.run(_expire_threads())


async def _crawl_sources(kind: str) -> dict:
    from sqlalchemy import select

    from app.models import Source
    from app.models.base import session_factory

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Source.id).where(Source.kind == kind, Source.enabled.is_(True))
            )
        ).scalars().all()

    for source_id in rows:
        # Per-source lock: two overlapping crawls duplicate work and deadlock on upsert.
        ingest_source_task.apply_async(args=[str(source_id)], task_id=f"ingest-{source_id}")
    return {"scheduled": len(rows)}


async def _ingest_one(source_id: uuid.UUID) -> dict:
    from app.ingest.pipeline import ingest_source
    from app.models.base import session_factory

    async with session_factory() as session:
        stats = await ingest_source(session, source_id)
    log.info("ingest_complete", source_id=str(source_id), **stats)
    return stats


async def _expire_threads() -> int:
    from app.memory.retention import expire_threads
    from app.models.base import session_factory

    async with session_factory() as session:
        return await expire_threads(session)

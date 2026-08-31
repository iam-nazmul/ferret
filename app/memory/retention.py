"""Thread retention. Checkpoint tables grow monotonically; this is not optional in prod."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logging import get_logger

log = get_logger(__name__)

# LangGraph owns these tables (public schema, its own setup()). No created_at column —
# the timestamp is inside the checkpoint payload.
_EXPIRED_THREADS_SQL = """
SELECT thread_id FROM checkpoints
GROUP BY thread_id
HAVING max((checkpoint->>'ts')::timestamptz) < :cutoff
"""

# checkpoint_writes and checkpoint_blobs have no FK to checkpoints, so deleting only
# from checkpoints would orphan them and the tables would still grow without bound.
_CHECKPOINT_TABLES = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")


async def expire_threads(session: AsyncSession, days: int | None = None) -> int:
    """Delete threads whose newest checkpoint is older than the retention window."""
    cutoff = datetime.now(UTC) - timedelta(days=days or settings.thread_retention_days)

    thread_ids = (
        (await session.execute(sql_text(_EXPIRED_THREADS_SQL), {"cutoff": cutoff}))
        .scalars()
        .all()
    )
    if not thread_ids:
        return 0

    for table in _CHECKPOINT_TABLES:
        await session.execute(
            sql_text(f"DELETE FROM {table} WHERE thread_id = ANY(:ids)"),  # noqa: S608
            {"ids": list(thread_ids)},
        )
    await session.commit()

    log.info("threads_expired", count=len(thread_ids), cutoff=cutoff.isoformat())
    return len(thread_ids)

"""Thread retention against LangGraph's real checkpoint tables.

These tables are created by LangGraph's setup(), not our migrations, and carry no
created_at column — the timestamp is inside checkpoint->>'ts'. That is exactly the kind
of assumption that rots silently, so it is asserted here.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.memory.retention import expire_threads


async def _insert_checkpoint(session, thread_id: str, ts: datetime) -> None:
    await session.execute(
        text(
            "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, checkpoint, metadata) "
            "VALUES (:tid, '', :cid, CAST(:cp AS jsonb), '{}'::jsonb)"
        ),
        {
            "tid": thread_id,
            "cid": f"cp-{thread_id}",
            "cp": f'{{"ts": "{ts.isoformat()}", "channel_values": {{}}}}',
        },
    )
    await session.commit()


async def test_expires_only_old_threads(clean_session):
    # Mirror the shape LangGraph's setup() produces, on the test's own engine.
    await clean_session.execute(
        text(
            "CREATE TABLE IF NOT EXISTS checkpoints ("
            "thread_id text NOT NULL, checkpoint_ns text NOT NULL DEFAULT '', "
            "checkpoint_id text NOT NULL, checkpoint jsonb NOT NULL, metadata jsonb NOT NULL DEFAULT '{}', "
            "PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id))"
        )
    )
    for table in ("checkpoint_writes", "checkpoint_blobs"):
        await clean_session.execute(
            text(f"CREATE TABLE IF NOT EXISTS {table} (thread_id text NOT NULL)")
        )
    await clean_session.commit()

    now = datetime.now(UTC)
    await _insert_checkpoint(clean_session, "old-thread", now - timedelta(days=120))
    await _insert_checkpoint(clean_session, "fresh-thread", now - timedelta(days=2))

    deleted = await expire_threads(clean_session, days=90)
    assert deleted == 1

    remaining = (
        await clean_session.execute(text("SELECT thread_id FROM checkpoints"))
    ).scalars().all()
    assert remaining == ["fresh-thread"]

    await clean_session.execute(text("DROP TABLE checkpoints, checkpoint_writes, checkpoint_blobs"))
    await clean_session.commit()


async def test_no_expired_threads_is_a_no_op(clean_session):
    await clean_session.execute(
        text(
            "CREATE TABLE IF NOT EXISTS checkpoints ("
            "thread_id text NOT NULL, checkpoint_ns text NOT NULL DEFAULT '', "
            "checkpoint_id text NOT NULL, checkpoint jsonb NOT NULL, metadata jsonb NOT NULL DEFAULT '{}', "
            "PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id))"
        )
    )
    await clean_session.commit()

    assert await expire_threads(clean_session, days=90) == 0

    await clean_session.execute(text("DROP TABLE checkpoints"))
    await clean_session.commit()

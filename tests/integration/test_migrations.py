"""Migrations must round-trip: rollback is 'previous image + alembic downgrade -1',
which only works if downgrade actually runs.
"""

import os
import subprocess
import sys

from sqlalchemy import text

from tests.integration.conftest import REPO_ROOT


def _alembic(command: list[str], url: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *command],
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )


async def test_schema_creates_expected_tables(engine):
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        tables = {r[0] for r in rows}

    assert {"sources", "documents", "chunks", "feedback"} <= tables


async def test_tsv_is_a_generated_column(engine):
    """BM25 can't fall out of sync because there's no way to forget to update it."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT is_generated FROM information_schema.columns "
                "WHERE table_name = 'chunks' AND column_name = 'tsv'"
            )
        )
        assert result.scalar() == "ALWAYS"


async def test_acl_groups_has_a_gin_index(engine):
    """Retrieval filters with && on every query; without the index it seq-scans."""
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT indexdef FROM pg_indexes WHERE tablename = 'documents'")
        )
        defs = " ".join(r[0] for r in rows).lower()

    assert "gin" in defs and "acl_groups" in defs


async def test_embedding_index_is_hnsw_cosine(engine):
    """<=> is cosine distance; an L2 index here silently degrades every result."""
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT indexdef FROM pg_indexes WHERE tablename = 'chunks'")
        )
        defs = " ".join(r[0] for r in rows).lower()

    assert "hnsw" in defs and "vector_cosine_ops" in defs


def test_downgrade_and_upgrade_round_trip(migrated):
    """Runs last-ish and restores head, so other tests still see the schema."""
    down = _alembic(["downgrade", "-1"], migrated)
    assert down.returncode == 0, f"downgrade failed:\n{down.stderr}"

    up = _alembic(["upgrade", "head"], migrated)
    assert up.returncode == 0, f"re-upgrade failed:\n{up.stderr}"

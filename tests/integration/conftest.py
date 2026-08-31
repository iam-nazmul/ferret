"""Integration fixtures: one real Postgres for the session, schema built by Alembic.

pgvector needs the extension, so the image is pgvector/pgvector:pg16, not stock postgres.

The container and schema are session-scoped (sync, so they can't collide with per-test
event loops); the async engine is function-scoped, because an asyncpg pool bound to one
loop cannot be reused from another.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytest.importorskip("testcontainers", reason="testcontainers not installed")

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def postgres_container():
    from testcontainers.postgres import PostgresContainer

    try:
        container = PostgresContainer("pgvector/pgvector:pg16", driver="asyncpg")
        container.start()
    except Exception as exc:  # no Docker socket available
        pytest.skip(f"Docker unavailable: {exc}")
    yield container
    container.stop()


@pytest.fixture(scope="session")
def async_url(postgres_container) -> str:
    return postgres_container.get_connection_url()


@pytest.fixture(scope="session")
def sync_url(async_url: str) -> str:
    return async_url.replace("+asyncpg", "")


@pytest.fixture(scope="session")
def migrated(async_url: str, sync_url: str) -> str:
    """Build the schema with Alembic — the same path production uses."""
    env = {**os.environ, "DATABASE_URL": async_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}")
    return async_url


@pytest_asyncio.fixture
async def engine(migrated: str):
    eng = create_async_engine(migrated)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    """A session rolled back after the test."""
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()


@pytest_asyncio.fixture
async def clean_session(engine):
    """A session for tests that must commit; its data is truncated afterwards."""
    from sqlalchemy import text

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()
        await s.execute(text("TRUNCATE sources, documents, chunks, feedback CASCADE"))
        await s.commit()

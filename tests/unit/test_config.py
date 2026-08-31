"""Database URL forms. Three consumers, three formats — mixing them fails at connect time."""

from app.config import Settings


def _s(url: str) -> Settings:
    return Settings(database_url=url)


def test_async_url_is_used_as_given():
    s = _s("postgresql+asyncpg://u:p@h:5432/db")
    assert s.database_url.startswith("postgresql+asyncpg://")


def test_sync_url_targets_psycopg3_not_psycopg2():
    """Bare postgresql:// makes SQLAlchemy import psycopg2, which is not a dependency."""
    assert _s("postgresql+asyncpg://u:p@h/db").sync_database_url == "postgresql+psycopg://u:p@h/db"


def test_conninfo_has_no_driver_suffix():
    """LangGraph's checkpointer and store take libpq conninfo, not a SQLAlchemy URL."""
    for url in (
        "postgresql+asyncpg://u:p@h/db",
        "postgresql+psycopg://u:p@h/db",
        "postgresql://u:p@h/db",
    ):
        assert _s(url).pg_conninfo == "postgresql://u:p@h/db"

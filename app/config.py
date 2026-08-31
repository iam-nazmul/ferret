"""Single source of configuration. Everything reads from here, nothing reads os.environ directly."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM + embeddings
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Observability
    langsmith_api_key: str = ""
    langsmith_project: str = "ferret"
    langsmith_tracing: bool = False

    # Data
    database_url: str = "postgresql+asyncpg://ferret:ferret@localhost:5432/ferret"
    redis_url: str = "redis://localhost:6379/0"
    reranker_url: str = "http://localhost:8081"

    # Auth
    oidc_issuer: str = ""
    oidc_audience: str = "ferret"
    oidc_group_claim: str = "groups"
    oidc_admin_group: str = "ferret-admins"
    auth_disabled: bool = False

    # Storage
    s3_endpoint_url: str = ""
    aws_region: str = "us-east-1"

    # API
    api_base_url: str = "http://localhost:8000"

    # --- Retrieval parameters (SPEC §8; changing these requires the eval gate) ---
    dense_candidates: int = 50
    sparse_candidates: int = 50
    rrf_k: int = 60
    fusion_limit: int = 30
    top_k: int = 8
    hnsw_ef_search: int = 100

    # --- Embedding (must match between ingestion, retrieval, and memory) ---
    embedding_model: str = "text-embedding-3-large"
    embedding_dims: int = 1024

    # --- Chunking (SPEC §7) ---
    chunk_tokens: int = 700
    chunk_overlap_tokens: int = 100
    scanned_pdf_chars_per_page: int = 100

    # --- Graph ---
    max_retries: int = 1
    thread_summarize_after: int = 40
    memory_search_limit: int = 5

    # --- Limits ---
    rate_limit_per_minute: int = 20
    rate_limit_concurrent: int = 5
    thread_retention_days: int = 90

    @property
    def sync_database_url(self) -> str:
        """SQLAlchemy sync URL (Alembic). psycopg3 — psycopg2 is not a dependency."""
        return self.database_url.replace("+asyncpg", "+psycopg")

    @property
    def pg_conninfo(self) -> str:
        """Raw libpq conninfo for LangGraph's psycopg-based checkpointer and store.

        These take a connection string, not a SQLAlchemy URL — a '+driver' suffix here
        fails at connect time, not at import time.
        """
        url = self.database_url
        for driver in ("+asyncpg", "+psycopg", "+psycopg2"):
            url = url.replace(driver, "")
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

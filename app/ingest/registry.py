"""Source kind -> (discoverer, fetcher)."""

from collections.abc import Awaitable, Callable

from app.ingest.discover import s3 as discover_s3
from app.ingest.discover import sitemap as discover_sitemap
from app.ingest.fetch import http as fetch_http
from app.ingest.fetch import s3 as fetch_s3
from app.ingest.types import Discovered, Fetched
from app.models import SourceKind

Discoverer = Callable[[str, dict], Awaitable[list[Discovered]]]
Fetcher = Callable[..., Awaitable[Fetched]]


async def _no_discovery(uri: str, config: dict) -> list[Discovered]:
    """Uploads are pushed in through the admin API, never discovered."""
    return []


REGISTRY: dict[str, tuple[Discoverer, Fetcher]] = {
    SourceKind.PDF_BUCKET.value: (discover_s3.discover, fetch_s3.fetch),
    SourceKind.WEB_SITEMAP.value: (discover_sitemap.discover, fetch_http.fetch),
    SourceKind.UPLOAD.value: (_no_discovery, fetch_http.fetch),
}


def get_handlers(kind: str) -> tuple[Discoverer, Fetcher]:
    if kind not in REGISTRY:
        raise ValueError(f"unknown source kind: {kind!r} (known: {sorted(REGISTRY)})")
    return REGISTRY[kind]

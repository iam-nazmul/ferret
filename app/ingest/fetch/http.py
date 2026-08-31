"""Conditional HTTP fetch."""

import httpx

from app.ingest.types import Fetched
from app.logging import get_logger

log = get_logger(__name__)


async def fetch(uri: str, etag: str | None = None) -> Fetched:
    headers = {"If-None-Match": etag} if etag else {}
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(uri, headers=headers)

    if resp.status_code == 304:
        return Fetched(uri=uri, content=b"", content_type="", etag=etag, unchanged=True)

    resp.raise_for_status()
    return Fetched(
        uri=uri,
        content=resp.content,
        content_type=resp.headers.get("content-type", "").split(";")[0],
        etag=resp.headers.get("etag", "").strip('"') or None,
    )

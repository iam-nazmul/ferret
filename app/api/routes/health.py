"""Liveness and readiness.

/healthz must NOT touch the database — pointing liveness at a DB check turns a slow
database into a restart loop.
"""

import httpx
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import DbSession
from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(db: DbSession, response: Response) -> dict:
    checks = {"database": False, "reranker": False}

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        pass

    try:
        async with httpx.AsyncClient(timeout=2) as client:
            r = await client.get(f"{settings.reranker_url.rstrip('/')}/healthz")
            checks["reranker"] = r.status_code == 200
    except Exception:
        pass

    # The reranker degrades gracefully (RRF fallback), so it doesn't gate readiness.
    if not checks["database"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if checks["database"] else "not ready", "checks": checks}

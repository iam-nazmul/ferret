"""FastAPI dependencies. Routes work with Principal, never with raw claims or request input."""

from collections.abc import AsyncIterator
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import DEV_PRINCIPAL, Principal, verify_token
from app.config import settings
from app.models.base import session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


async def get_principal(authorization: Annotated[str | None, Header()] = None) -> Principal:
    if settings.auth_disabled:
        return DEV_PRINCIPAL

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")

    try:
        return await verify_token(authorization.split(" ", 1)[1])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {exc}") from exc


async def require_admin(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
    if not principal.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin role required")
    return principal


def get_graph(request: Request):
    """The compiled graph, built once at startup."""
    return request.app.state.graph


def get_store(request: Request):
    return request.app.state.store


DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[Principal, Depends(get_principal)]
AdminUser = Annotated[Principal, Depends(require_admin)]

"""OIDC authentication."""

import time
from dataclasses import dataclass

import httpx
import jwt
from jwt import PyJWKClient

from app.config import settings
from app.logging import get_logger

log = get_logger(__name__)

_JWKS_TTL = 3600


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    groups: frozenset[str]
    is_admin: bool


class _JWKSCache:
    def __init__(self) -> None:
        self._client: PyJWKClient | None = None
        self._fetched_at = 0.0
        self._jwks_uri: str | None = None

    async def client(self) -> PyJWKClient:
        now = time.monotonic()
        if self._client is not None and now - self._fetched_at < _JWKS_TTL:
            return self._client

        if self._jwks_uri is None:
            async with httpx.AsyncClient(timeout=10) as http:
                resp = await http.get(f"{settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration")
                resp.raise_for_status()
                self._jwks_uri = resp.json()["jwks_uri"]

        self._client = PyJWKClient(self._jwks_uri, cache_keys=True)
        self._fetched_at = now
        return self._client


_jwks = _JWKSCache()


async def verify_token(token: str) -> Principal:
    """Verify a bearer token and derive the principal. Raises jwt exceptions on failure."""
    jwks_client = await _jwks.client()
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256", "ES256"],
        audience=settings.oidc_audience,
        issuer=settings.oidc_issuer or None,
        options={"require": ["exp", "sub"]},
    )
    return principal_from_claims(claims)


def principal_from_claims(claims: dict) -> Principal:
    raw_groups = claims.get(settings.oidc_group_claim) or []
    if isinstance(raw_groups, str):
        raw_groups = [g.strip() for g in raw_groups.split(",") if g.strip()]
    groups = frozenset(str(g) for g in raw_groups)
    return Principal(
        user_id=str(claims["sub"]),
        groups=groups,
        is_admin=settings.oidc_admin_group in groups,
    )


DEV_PRINCIPAL = Principal(user_id="dev", groups=frozenset({"all"}), is_admin=True)

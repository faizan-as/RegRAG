"""Supabase JWT authentication and role-based authorization."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, Request

from apps.api.errors import AuthenticationError, AuthorizationError
from apps.api.settings import AppEnv, Settings, get_settings


@dataclass(frozen=True)
class AuthenticatedUser:
    """The authenticated caller extracted from a validated Supabase JWT."""

    user_id: str
    email: str | None = None
    organization_id: str | None = None
    roles: list[str] = field(default_factory=lambda: ["researcher"])


DEV_BYPASS_USER = AuthenticatedUser(user_id="dev-user", email=None, roles=["admin"])


def _claim_value(payload: dict[str, Any], claim_path: str) -> Any:
    value: Any = payload
    for segment in claim_path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(segment)
    return value


def _extract_roles(payload: dict[str, Any], claim_path: str) -> list[str]:
    roles = _claim_value(payload, claim_path) or ["researcher"]
    if isinstance(roles, str):
        return [roles]
    if isinstance(roles, list) and all(isinstance(role, str) for role in roles):
        return roles or ["researcher"]
    return ["researcher"]


@lru_cache
def _jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_url, cache_keys=True)


def decode_bearer_token(token: str, settings: Settings) -> AuthenticatedUser:
    """Validate a Supabase-issued bearer token and extract the user context."""
    algorithms = settings.supabase_jwt_algorithms_list
    if not algorithms:
        raise AuthenticationError("Authentication algorithms are not configured.")
    if settings.supabase_jwks_url:
        try:
            signing_key = (
                _jwks_client(settings.supabase_jwks_url).get_signing_key_from_jwt(token).key
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Invalid or expired authentication token.") from exc
    elif settings.supabase_jwt_secret:
        if any(algorithm != "HS256" for algorithm in algorithms):
            raise AuthenticationError("Authentication is misconfigured.")
        signing_key = settings.supabase_jwt_secret
    else:
        raise AuthenticationError("Authentication is not configured.")

    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=algorithms,
            audience=settings.supabase_jwt_audience,
            issuer=settings.supabase_jwt_issuer,
            leeway=settings.supabase_jwt_leeway_seconds,
            options={
                "verify_aud": bool(settings.supabase_jwt_audience),
                "verify_iss": bool(settings.supabase_jwt_issuer),
                "require": ["exp", "sub"],
            },
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired authentication token.") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Authentication token is missing a subject claim.")
    app_metadata = payload.get("app_metadata") or {}
    return AuthenticatedUser(
        user_id=user_id,
        email=payload.get("email"),
        organization_id=app_metadata.get("organization_id") or app_metadata.get("tenant_id"),
        roles=_extract_roles(payload, settings.supabase_app_roles_claim),
    )


async def get_current_user(request: Request) -> AuthenticatedUser:
    """FastAPI dependency resolving the authenticated caller."""
    settings = get_settings()
    if settings.auth_dev_bypass and settings.app_env == AppEnv.DEVELOPMENT:
        return DEV_BYPASS_USER

    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise AuthenticationError("Missing bearer token.")
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise AuthenticationError("Missing bearer token.")
    return decode_bearer_token(token, settings)


def require_roles(*allowed_roles: str) -> Callable[..., Awaitable[AuthenticatedUser]]:
    """Build a dependency that authorizes only the given roles."""

    async def dependency(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if not set(allowed_roles) & set(user.roles):
            raise AuthorizationError("Insufficient role for this operation.")
        return user

    return dependency

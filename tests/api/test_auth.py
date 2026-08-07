"""Tests for Supabase authentication and application role mapping."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import ValidationError

from apps.api.errors import AuthenticationError
from apps.api.security import decode_bearer_token
from apps.api.settings import Settings


def _settings(**overrides) -> Settings:
    values = {
        "SUPABASE_JWT_SECRET": "test-secret",
        "SUPABASE_JWT_ALGORITHMS": "HS256",
        "SUPABASE_JWT_AUDIENCE": "authenticated",
        "SUPABASE_JWT_ISSUER": "https://example.supabase.co/auth/v1",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _token(**claims) -> str:
    payload = {
        "sub": "user-1",
        "aud": "authenticated",
        "iss": "https://example.supabase.co/auth/v1",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    payload.update(claims)
    return jwt.encode(payload, "test-secret", algorithm="HS256")


def test_platform_role_does_not_become_application_role() -> None:
    user = decode_bearer_token(_token(role="authenticated"), _settings())

    assert user.roles == ["researcher"]


def test_roles_are_read_from_application_metadata() -> None:
    user = decode_bearer_token(
        _token(app_metadata={"roles": ["admin"], "organization_id": "org-1"}),
        _settings(),
    )

    assert user.roles == ["admin"]
    assert user.organization_id == "org-1"


def test_wrong_issuer_is_rejected() -> None:
    with pytest.raises(AuthenticationError):
        decode_bearer_token(_token(iss="https://wrong.example"), _settings())


def test_development_bypass_is_rejected_outside_development() -> None:
    with pytest.raises(ValidationError, match="AUTH_DEV_BYPASS"):
        Settings(_env_file=None, APP_ENV="pilot", AUTH_DEV_BYPASS=True)

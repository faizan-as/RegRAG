"""Tests for audit inspection safety behavior."""

from __future__ import annotations

from apps.api.routes.audit import _redact


def test_audit_redaction_recurses_through_nested_payloads() -> None:
    payload = {
        "authorization": "Bearer secret",
        "nested": {"api_key": "secret", "result": "allowed"},
        "items": [{"password": "secret"}, {"status": "ok"}],
    }

    assert _redact(payload) == {
        "authorization": "[REDACTED]",
        "nested": {"api_key": "[REDACTED]", "result": "allowed"},
        "items": [{"password": "[REDACTED]"}, {"status": "ok"}],
    }

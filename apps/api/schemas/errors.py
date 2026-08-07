"""Structured error response schema for the API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    """Sanitized error detail returned to API clients."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable, secret-free error message.")
    request_id: str | None = Field(
        default=None, description="Correlation id for support/debugging."
    )
    details: list[dict[str, Any]] | None = Field(
        default=None, description="Optional field-level validation details."
    )


class ErrorResponse(BaseModel):
    """Envelope for all structured API error responses."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail

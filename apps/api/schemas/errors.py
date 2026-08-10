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


API_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status_code: {"model": ErrorResponse, "description": description}
    for status_code, description in {
        401: "Authentication required or token invalid.",
        403: "Caller is not authorized for this operation.",
        404: "Resource not found or not visible to the caller.",
        422: "Request validation failed.",
        429: "Rate limit exceeded.",
        500: "Unexpected internal error.",
        503: "A required service is unavailable.",
    }.items()
}

"""Liveness and readiness response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Cheap, dependency-free liveness payload."""

    model_config = ConfigDict(extra="forbid")

    status: str
    env: str


class DependencyStatus(BaseModel):
    """Health of a single downstream dependency."""

    model_config = ConfigDict(extra="forbid")

    name: str
    healthy: bool
    detail: str | None = Field(
        default=None, description="Sanitized detail; never a raw provider error."
    )


class ReadinessResponse(BaseModel):
    """Dependency-aware readiness payload."""

    model_config = ConfigDict(extra="forbid")

    status: str
    dependencies: list[DependencyStatus]

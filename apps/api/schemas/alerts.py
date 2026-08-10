"""Update-monitoring alert API schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from apps.api.schemas.audit import AlertType
from apps.api.schemas.documents import DocumentStatus


class AlertStatus(str, Enum):
    """Lifecycle status of an update-monitoring alert."""

    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertResponse(BaseModel):
    """A single update-monitoring alert record."""

    model_config = ConfigDict(extra="forbid")

    alert_id: str
    alert_type: AlertType
    document_id: str
    title: str
    previous_status: DocumentStatus | None = None
    current_status: DocumentStatus | None = None
    previous_version_hash: str | None = None
    current_version_hash: str | None = None
    summary: str | None = None
    status: AlertStatus = Field(default=AlertStatus.OPEN)
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    detected_at: datetime


class AlertListResponse(BaseModel):
    """A page of update-monitoring alerts."""

    model_config = ConfigDict(extra="forbid")

    alerts: list[AlertResponse] = Field(default_factory=list)
    limit: int
    offset: int


class AlertUpdateRequest(BaseModel):
    """A request to acknowledge or resolve an alert."""

    model_config = ConfigDict(extra="forbid")

    status: AlertStatus

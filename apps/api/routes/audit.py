"""Admin-only audit trail inspection route."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_db_session
from apps.api.security import AuthenticatedUser, require_roles
from src.db.models import AuditEventRecord

router = APIRouter(prefix="/api/audit", tags=["audit"])
_SECRET_KEYS = {"authorization", "token", "api_key", "secret", "password", "connection_string"}


class AuditResponse(BaseModel):
    """Redacted audit event returned to administrators."""

    model_config = ConfigDict(extra="forbid")
    event_id: str
    event_type: str
    user_id: str | None
    session_id: str | None
    route: str | None
    request_id: str | None
    payload: dict[str, Any]
    created_at: datetime


class AuditListResponse(BaseModel):
    """Bounded page of redacted audit events."""

    model_config = ConfigDict(extra="forbid")
    events: list[AuditResponse] = Field(default_factory=list)
    limit: int
    offset: int


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in _SECRET_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


@router.get("", response_model=AuditListResponse)
async def get_audit_events(
    event_type: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    route: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(require_roles("admin")),
) -> AuditListResponse:
    """Filter and page indexed audit columns with payload redaction."""
    del user
    statement = select(AuditEventRecord)
    if event_type:
        statement = statement.where(AuditEventRecord.event_type == event_type)
    if user_id:
        statement = statement.where(AuditEventRecord.user_id == user_id)
    if session_id:
        statement = statement.where(AuditEventRecord.session_id == session_id)
    if route:
        statement = statement.where(AuditEventRecord.route == route)
    if created_from:
        statement = statement.where(AuditEventRecord.created_at >= created_from)
    if created_to:
        statement = statement.where(AuditEventRecord.created_at <= created_to)
    records = await db.scalars(
        statement.order_by(AuditEventRecord.created_at.desc()).offset(offset).limit(limit)
    )
    return AuditListResponse(
        events=[
            AuditResponse(
                event_id=str(record.id),
                event_type=record.event_type,
                user_id=record.user_id,
                session_id=record.session_id,
                route=record.route,
                request_id=record.request_id,
                payload=_redact(record.payload),
                created_at=record.created_at,
            )
            for record in records
        ],
        limit=limit,
        offset=offset,
    )

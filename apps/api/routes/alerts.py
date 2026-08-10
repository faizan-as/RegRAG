"""Update-monitoring alert routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.audit import add_audit_event
from apps.api.deps import get_db_session
from apps.api.errors import NotFoundAPIError, ValidationAPIError
from apps.api.schemas.alerts import (
    AlertListResponse,
    AlertResponse,
    AlertStatus,
    AlertUpdateRequest,
)
from apps.api.security import AuthenticatedUser, require_roles
from src.db.models import AlertRecordORM
from src.db.models import AlertStatus as ORMAlertStatus
from src.monitoring.alerts import list_alerts, update_alert_status

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _response(record: AlertRecordORM) -> AlertResponse:
    return AlertResponse(
        alert_id=str(record.id),
        alert_type=record.alert_type,
        document_id=record.document_slug or "withdrawn-document",
        title=record.title,
        previous_status=record.previous_status,
        current_status=record.current_status,
        previous_version_hash=record.previous_version_hash,
        current_version_hash=record.current_version_hash,
        summary=record.summary,
        status=record.status,
        acknowledged_by=record.acknowledged_by,
        acknowledged_at=record.acknowledged_at,
        resolved_at=record.resolved_at,
        detected_at=record.detected_at,
    )


@router.get("", response_model=AlertListResponse)
async def get_alerts(
    status: AlertStatus | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(require_roles("researcher", "admin")),
) -> AlertListResponse:
    """List recent update alerts for authenticated researchers."""
    del user
    records = await list_alerts(
        db,
        status=ORMAlertStatus(status.value) if status is not None else None,
        limit=limit,
        offset=offset,
    )
    return AlertListResponse(
        alerts=[_response(record) for record in records], limit=limit, offset=offset
    )


@router.patch("/{alert_id}", response_model=AlertResponse)
async def patch_alert(
    alert_id: UUID,
    payload: AlertUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(require_roles("admin", "service")),
) -> AlertResponse:
    """Acknowledge or resolve an alert and audit the mutation transactionally."""
    try:
        record = await update_alert_status(
            db,
            alert_id,
            status=ORMAlertStatus(payload.status.value),
            acknowledged_by=user.user_id,
        )
    except ValueError as exc:
        raise ValidationAPIError(str(exc)) from exc
    if record is None:
        raise NotFoundAPIError("Alert was not found.")
    add_audit_event(
        db,
        event_type="alert_state_changed",
        user_id=user.user_id,
        session_id=None,
        route="/api/alerts/{alert_id}",
        request_id=request.state.request_id,
        payload={"alert_id": str(alert_id), "status": record.status},
    )
    await db.commit()
    return _response(record)

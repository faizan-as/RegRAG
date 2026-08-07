"""Audit trail persistence helper shared across API routes."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.common.logging import get_logger
from src.db.models import AuditEventRecord

logger = get_logger(__name__)


def add_audit_event(
    session: AsyncSession,
    *,
    event_type: str,
    user_id: str | None,
    session_id: str | None,
    route: str,
    request_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> AuditEventRecord:
    """Add a critical audit row to the caller-owned transaction."""
    record = AuditEventRecord(
        event_type=event_type,
        user_id=user_id,
        session_id=session_id,
        route=route,
        request_id=request_id,
        payload=payload or {},
    )
    session.add(record)
    return record


async def record_audit_event(
    session: AsyncSession,
    *,
    event_type: str,
    user_id: str | None,
    session_id: str | None,
    route: str,
    request_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Best-effort persistence for an operational event without a domain mutation."""
    try:
        add_audit_event(
            session,
            event_type=event_type,
            user_id=user_id,
            session_id=session_id,
            route=route,
            request_id=request_id,
            payload=payload,
        )
        await session.commit()
    except Exception as exc:  # pragma: no cover - defensive audit path
        logger.error("audit_persist_failed", event_type=event_type, route=route, error=str(exc))
        await session.rollback()

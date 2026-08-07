"""Server-owned chat session routes."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_db_session
from apps.api.errors import NotFoundAPIError
from apps.api.schemas.answer import Answer
from apps.api.schemas.evidence import EvidenceCard
from apps.api.schemas.sessions import (
    SessionCreateRequest,
    SessionHistoryResponse,
    SessionResponse,
    TurnResponse,
)
from apps.api.security import AuthenticatedUser, require_roles
from src.db.models import ChatSessionRecord, ChatTurnRecord

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


async def get_owned_session(
    session: AsyncSession, session_id: str, user_id: str
) -> ChatSessionRecord:
    """Load a session only when it belongs to the authenticated user."""
    record = await session.get(ChatSessionRecord, session_id)
    if record is None or record.owner_user_id != user_id:
        raise NotFoundAPIError("Chat session was not found.")
    return record


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    request: SessionCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(require_roles("researcher", "admin")),
) -> SessionResponse:
    """Create a server-owned session for the current user."""
    record = ChatSessionRecord(
        id=str(uuid4()), owner_user_id=user.user_id, title=request.title, status="active"
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return SessionResponse(
        session_id=record.id,
        title=record.title,
        status=record.status,
        created_at=record.created_at,
    )


@router.get("/{session_id}/turns", response_model=SessionHistoryResponse)
async def list_session_turns(
    session_id: str,
    session: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(require_roles("researcher", "admin")),
) -> SessionHistoryResponse:
    """Return final turns for an authorized session in chronological order."""
    await get_owned_session(session, session_id, user.user_id)
    result = await session.scalars(
        select(ChatTurnRecord)
        .where(ChatTurnRecord.session_id == session_id)
        .order_by(ChatTurnRecord.created_at, ChatTurnRecord.id)
    )
    turns = [
        TurnResponse(
            turn_id=str(turn.id),
            query=turn.query,
            answer=Answer(
                text=turn.answer_text,
                evidence=[EvidenceCard.model_validate(card) for card in turn.evidence],
                confidence=turn.confidence,
                refused=turn.refused,
                refusal_reason=turn.refusal_reason,
                session_id=session_id,
                generated_at=turn.created_at,
            ),
            created_at=turn.created_at,
        )
        for turn in result
    ]
    return SessionHistoryResponse(session_id=session_id, turns=turns)

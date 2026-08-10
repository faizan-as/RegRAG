"""Citation-first non-streaming and node-boundary SSE chat routes."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from apps.api.audit import add_audit_event, record_audit_event
from apps.api.deps import get_agent_graph, get_db_session, get_settings_dep
from apps.api.ratelimit import acquire_stream_lease, enforce_chat_rate_limit
from apps.api.routes.sessions import get_owned_session
from apps.api.schemas.answer import Answer, AnswerRequest
from apps.api.schemas.chat import ChatResponse, ChatStreamEvent
from apps.api.schemas.common import TransparencyMetadata
from apps.api.security import AuthenticatedUser, require_roles
from apps.api.settings import Settings
from src.agents.state import AgentState, ExecutionTraceEntry, initial_agent_state
from src.db.models import ChatSessionRecord, ChatTurnRecord

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _safe_trace(entry: ExecutionTraceEntry) -> dict[str, Any]:
    return {
        "node": entry.node,
        "started_at": entry.started_at.isoformat(),
        "completed_at": entry.completed_at.isoformat() if entry.completed_at else None,
        "status": entry.status,
        "provider": entry.provider,
        "evidence_count": entry.evidence_count,
        "confidence": entry.confidence,
        "retry_count": entry.retry_count,
        "diagnostics": entry.diagnostics,
    }


def _transparency(state: AgentState) -> TransparencyMetadata:
    return TransparencyMetadata(
        execution_trace=[_safe_trace(entry) for entry in state.get("execution_trace", [])],
        retrieval_diagnostics=state.get("retrieval_diagnostics", {}),
        provider_fallback_trace=state.get("provider_fallback_trace", []),
        ignored_filter_keys=state.get("ignored_filter_keys", []),
        guardrail_errors=state.get("guardrail_errors", []),
    )


async def _resolve_session(
    db: AsyncSession, user: AuthenticatedUser, requested_session_id: str | None
) -> ChatSessionRecord:
    if requested_session_id:
        return await get_owned_session(db, requested_session_id, user.user_id)
    record = ChatSessionRecord(id=str(uuid4()), owner_user_id=user.user_id, status="active")
    db.add(record)
    await db.flush()
    return record


async def _persist_final_turn(
    db: AsyncSession,
    *,
    session_id: str,
    request_id: str | None,
    query: str,
    state: AgentState,
    user_id: str,
) -> UUID:
    answer = state["answer"]
    turn_id = uuid4()
    db.add(
        ChatTurnRecord(
            id=turn_id,
            session_id=session_id,
            request_id=request_id,
            query=query,
            answer_text=answer.text,
            evidence=[card.model_dump(mode="json") for card in answer.evidence],
            confidence=answer.confidence,
            refused=answer.refused,
            refusal_reason=answer.refusal_reason,
            guardrail_metadata={
                "citation_bound": bool(
                    state.get("citation_binding") and state["citation_binding"].success
                ),
                "faithfulness_passed": state.get("faithfulness_passed"),
                "guardrail_errors": state.get("guardrail_errors", []),
            },
            provider_name=state.get("llm_provider"),
            diagnostics={
                "retrieval": state.get("retrieval_diagnostics", {}),
                "ignored_filter_keys": state.get("ignored_filter_keys", []),
            },
        )
    )
    add_audit_event(
        db,
        event_type="turn_refused" if answer.refused else "turn_completed",
        user_id=user_id,
        session_id=session_id,
        route="/api/chat",
        request_id=request_id,
        payload={
            "turn_id": str(turn_id),
            "confidence": answer.confidence,
            "refusal_reason": answer.refusal_reason,
            "evidence_ids": [card.citation_id for card in answer.evidence],
            "version_hashes": sorted({card.version_hash for card in answer.evidence}),
        },
    )
    await db.commit()
    return turn_id


def _initial_state(request: AnswerRequest, session_id: str, settings: Settings) -> AgentState:
    return initial_agent_state(
        request.query,
        session_id=session_id,
        filters=request.filters,
        max_retries=settings.max_faithfulness_retries,
    )


@router.post("", response_model=ChatResponse, dependencies=[Depends(enforce_chat_rate_limit)])
async def chat(
    payload: AnswerRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(require_roles("researcher", "admin")),
    graph: Any = Depends(get_agent_graph),
    settings: Settings = Depends(get_settings_dep),
) -> ChatResponse:
    """Run the guarded graph and persist one authoritative final turn."""
    chat_session = await _resolve_session(db, user, payload.session_id)
    final_state: AgentState = await graph.ainvoke(
        _initial_state(payload, chat_session.id, settings)
    )
    turn_id = await _persist_final_turn(
        db,
        session_id=chat_session.id,
        request_id=request.state.request_id,
        query=payload.query,
        state=final_state,
        user_id=user.user_id,
    )
    return ChatResponse(
        session_id=chat_session.id,
        turn_id=str(turn_id),
        answer=final_state["answer"],
        transparency=_transparency(final_state),
    )


@router.post(
    "/stream",
    response_model=ChatStreamEvent,
    response_class=EventSourceResponse,
    responses={
        200: {
            "description": "Named SSE events carrying the documented chat stream protocol.",
            "content": {
                "text/event-stream": {"schema": {"$ref": "#/components/schemas/ChatStreamEvent"}}
            },
        }
    },
    dependencies=[Depends(enforce_chat_rate_limit), Depends(acquire_stream_lease)],
)
async def chat_stream(
    payload: AnswerRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(require_roles("researcher", "admin")),
    graph: Any = Depends(get_agent_graph),
    settings: Settings = Depends(get_settings_dep),
) -> EventSourceResponse:
    """Stream node progress and one durable committed/refused final event."""
    chat_session = await _resolve_session(db, user, payload.session_id)

    async def events() -> AsyncIterator[dict[str, str]]:
        yield {
            "event": "started",
            "data": ChatStreamEvent(
                event="started", data={"session_id": chat_session.id}
            ).model_dump_json(),
        }
        latest_state: AgentState | None = None
        trace_count = 0
        try:
            async for state in graph.astream(
                _initial_state(payload, chat_session.id, settings), stream_mode="values"
            ):
                if await request.is_disconnected():
                    await record_audit_event(
                        db,
                        event_type="chat_cancelled",
                        user_id=user.user_id,
                        session_id=chat_session.id,
                        route="/api/chat/stream",
                        request_id=request.state.request_id,
                    )
                    return
                latest_state = state
                traces = state.get("execution_trace", [])
                for entry in traces[trace_count:]:
                    yield {
                        "event": "node",
                        "data": ChatStreamEvent(
                            event="node", data=_safe_trace(entry)
                        ).model_dump_json(),
                    }
                trace_count = len(traces)

            if latest_state is None or "answer" not in latest_state:
                raise RuntimeError("Agent stream ended without a final answer")
            turn_id = await _persist_final_turn(
                db,
                session_id=chat_session.id,
                request_id=request.state.request_id,
                query=payload.query,
                state=latest_state,
                user_id=user.user_id,
            )
            answer: Answer = latest_state["answer"]
            event_name = "refused" if answer.refused else "committed"
            final_data = {
                "session_id": chat_session.id,
                "turn_id": str(turn_id),
                "answer": answer.model_dump(mode="json"),
                "transparency": _transparency(latest_state).model_dump(mode="json"),
            }
            yield {"event": event_name, "data": json.dumps(final_data)}
        except Exception:
            yield {
                "event": "error",
                "data": ChatStreamEvent(
                    event="error", data={"message": "The chat stream could not be completed."}
                ).model_dump_json(),
            }
        finally:
            yield {"event": "done", "data": ChatStreamEvent(event="done").model_dump_json()}

    return EventSourceResponse(events())

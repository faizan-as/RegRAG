"""Server-owned summary and transcript export routes."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.audit import add_audit_event
from apps.api.deps import get_artifact_store_dep, get_db_session
from apps.api.errors import NotFoundAPIError, ValidationAPIError
from apps.api.ratelimit import enforce_export_rate_limit
from apps.api.routes.sessions import get_owned_session
from apps.api.schemas.answer import Answer
from apps.api.schemas.evidence import EvidenceCard
from apps.api.schemas.exports import ExportKind, ExportRequest, ExportResult, ExportStatus
from apps.api.schemas.summaries import SummaryResult, SummaryType
from apps.api.security import AuthenticatedUser, require_roles
from src.common.storage import LocalArtifactStore
from src.db.models import ChatTurnRecord, ExportRecordORM, GroundedSummaryRecord
from src.reports.exporter import write_export_artifact
from src.reports.templates import render_summary_text, render_transcript_text

router = APIRouter(prefix="/api/exports", tags=["exports"])


def _result(record: ExportRecordORM) -> ExportResult:
    return ExportResult(
        export_id=str(record.id),
        status=ExportStatus(record.status),
        export_format=record.export_format,
        error_message=record.error_message,
        created_at=record.created_at,
    )


async def _owned_export(
    db: AsyncSession, export_id: UUID, user: AuthenticatedUser
) -> ExportRecordORM:
    record = await db.get(ExportRecordORM, export_id)
    if record is None or (record.requested_by != user.user_id and "admin" not in user.roles):
        raise NotFoundAPIError("Export was not found.")
    return record


async def _export_text(
    request: ExportRequest, db: AsyncSession, user: AuthenticatedUser
) -> tuple[str, str | None, UUID | None, str | None]:
    if request.export_type == ExportKind.SUMMARY:
        if request.summary_id is None or request.session_id is not None:
            raise ValidationAPIError("Summary export requires only summary_id.")
        summary = await db.get(GroundedSummaryRecord, request.summary_id)
        if summary is None or (summary.owner_user_id != user.user_id and "admin" not in user.roles):
            raise NotFoundAPIError("Grounded summary was not found.")
        result = SummaryResult(
            summary_id=str(summary.id),
            document_id=summary.document_slug or "withdrawn-document",
            summary_type=SummaryType(summary.summary_type),
            text=summary.text,
            evidence=[EvidenceCard.model_validate(card) for card in summary.evidence],
            refused=summary.refused,
            refusal_reason=summary.refusal_reason,
            current_version_hash=summary.current_version_hash,
            previous_version_hash=summary.previous_version_hash,
            faithfulness_passed=summary.guardrail_metadata.get("faithfulness_passed"),
            generated_at=summary.created_at,
        )
        return render_summary_text(result), None, summary.id, summary.document_slug

    if request.session_id is None or request.summary_id is not None:
        raise ValidationAPIError("Transcript export requires only session_id.")
    await get_owned_session(db, request.session_id, user.user_id)
    turns = list(
        await db.scalars(
            select(ChatTurnRecord)
            .where(ChatTurnRecord.session_id == request.session_id)
            .order_by(ChatTurnRecord.created_at, ChatTurnRecord.id)
        )
    )
    answers = [
        Answer(
            text=turn.answer_text,
            evidence=[EvidenceCard.model_validate(card) for card in turn.evidence],
            confidence=turn.confidence,
            refused=turn.refused,
            refusal_reason=turn.refusal_reason,
            session_id=turn.session_id,
            generated_at=turn.created_at,
        )
        for turn in turns
    ]
    return render_transcript_text(answers), request.session_id, None, None


@router.post("", response_model=ExportResult, dependencies=[Depends(enforce_export_rate_limit)])
async def create_export(
    payload: ExportRequest,
    db: AsyncSession = Depends(get_db_session),
    store: LocalArtifactStore = Depends(get_artifact_store_dep),
    user: AuthenticatedUser = Depends(require_roles("researcher", "admin")),
) -> ExportResult:
    """Generate an export only from an authorized durable source record."""
    text, session_id, summary_id, document_slug = await _export_text(payload, db, user)
    export_id = uuid4()
    record = ExportRecordORM(
        id=export_id,
        export_type=payload.export_type.value,
        export_format=payload.export_format.value,
        status=ExportStatus.PENDING.value,
        requested_by=user.user_id,
        session_id=session_id,
        summary_id=summary_id,
        document_slug=document_slug,
    )
    db.add(record)
    try:
        _, object_key, _ = await asyncio.to_thread(
            write_export_artifact,
            text,
            payload.export_format,
            artifact_store=store,
            export_id=str(export_id),
        )
        record.object_key = object_key
        record.status = ExportStatus.COMPLETED.value
    except Exception:
        record.status = ExportStatus.FAILED.value
        record.error_message = "generation_failed"
    add_audit_event(
        db,
        event_type="export_created",
        user_id=user.user_id,
        session_id=session_id,
        route="/api/exports",
        payload={"export_id": str(export_id), "status": record.status},
    )
    await db.commit()
    await db.refresh(record)
    return _result(record)


@router.get("/{export_id}", response_model=ExportResult)
async def get_export(
    export_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(require_roles("researcher", "admin")),
) -> ExportResult:
    return _result(await _owned_export(db, export_id, user))


@router.get("/{export_id}/download")
async def download_export(
    export_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    store: LocalArtifactStore = Depends(get_artifact_store_dep),
    user: AuthenticatedUser = Depends(require_roles("researcher", "admin")),
) -> Response:
    record = await _owned_export(db, export_id, user)
    if record.status != ExportStatus.COMPLETED.value or not record.object_key:
        raise NotFoundAPIError("Completed export artifact was not found.")
    try:
        data = store.read_bytes(record.object_key)
    except (FileNotFoundError, ValueError) as exc:
        raise NotFoundAPIError("Completed export artifact was not found.") from exc
    media_types = {
        "text": "text/plain",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
    }
    return Response(
        data,
        media_type=media_types[record.export_format],
        headers={
            "Content-Disposition": f'attachment; filename="export-{export_id}.{record.export_format}"'
        },
    )

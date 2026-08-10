"""FDA guidance metadata, section, passage, and artifact routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.audit import record_audit_event
from apps.api.deps import get_artifact_store_dep, get_db_session
from apps.api.errors import NotFoundAPIError
from apps.api.ratelimit import enforce_document_rate_limit
from apps.api.schemas.documents import (
    DocumentArtifact,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersionResponse,
    GuidanceDocument,
    PassageResponse,
    SectionNavigationEntry,
)
from apps.api.security import AuthenticatedUser, require_roles
from src.common.storage import LocalArtifactStore
from src.db.models import GuidanceChunk, GuidanceRegistry, LifecycleState, SourceArtifact

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _document_status(record: GuidanceRegistry) -> DocumentStatus:
    if record.lifecycle_state == LifecycleState.WITHDRAWN:
        return DocumentStatus.WITHDRAWN
    try:
        return DocumentStatus(record.status or DocumentStatus.FINAL.value)
    except ValueError:
        return DocumentStatus.FINAL


async def _registry_or_404(session: AsyncSession, document_id: str) -> GuidanceRegistry:
    record = await session.get(GuidanceRegistry, document_id)
    if record is None:
        raise NotFoundAPIError("FDA guidance document was not found.")
    return record


@router.get(
    "/{document_id}",
    response_model=GuidanceDocument,
    dependencies=[Depends(enforce_document_rate_limit)],
)
async def get_document(
    document_id: str,
    session: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(require_roles("researcher", "admin")),
) -> GuidanceDocument:
    """Return canonical metadata, versions, and known sections."""
    record = await _registry_or_404(session, document_id)
    source_url = record.landing_url or record.pdf_url
    if not source_url:
        raise NotFoundAPIError("FDA guidance source URL was not found.")
    artifacts = list(
        await session.scalars(
            select(SourceArtifact)
            .where(SourceArtifact.document_slug == document_id)
            .order_by(SourceArtifact.created_at.desc())
        )
    )
    chunks = list(
        await session.scalars(
            select(GuidanceChunk)
            .where(GuidanceChunk.document_slug == document_id)
            .order_by(GuidanceChunk.chunk_id)
        )
    )
    version_hash = next((item.version_hash for item in artifacts if item.version_hash), None)
    if version_hash is None and chunks:
        version_hash = chunks[0].version_hash
    if version_hash is None:
        raise NotFoundAPIError("No indexed version exists for this FDA guidance document.")
    status = _document_status(record)
    versions = [
        DocumentVersionResponse(
            document_id=document_id,
            version_hash=artifact.version_hash,
            source_url=artifact.source_url or source_url,
            status=status,
            lifecycle_state=record.lifecycle_state,
            fda_last_changed=record.fda_last_changed,
            created_at=artifact.created_at,
        )
        for artifact in artifacts
        if artifact.version_hash and artifact.source_url
    ]
    return GuidanceDocument(
        metadata=DocumentMetadata(
            document_id=document_id,
            title=record.title,
            source_url=source_url,
            status=status,
            version_hash=version_hash,
            docket_number=record.docket_id,
            docket_url=record.docket_url,
            issuing_office=record.center,
            center=record.center,
            topics=record.topics,
            communication_type=record.communication_type,
            regulated_product=record.regulated_product,
            issue_date=record.issue_date,
            fda_last_changed=record.fda_last_changed,
            comment_close=record.comment_close_date,
            open_comment=record.open_comment,
            lifecycle_state=record.lifecycle_state,
            retrieved_at=record.last_synced_at or record.last_seen_at,
        ),
        versions=versions,
        section_ids=list(dict.fromkeys(chunk.section_id for chunk in chunks if chunk.section_id)),
        artifacts=[
            DocumentArtifact(
                artifact_id=artifact.id,
                content_type=artifact.content_type,
                artifact_kind=artifact.artifact_kind,
                version_hash=artifact.version_hash,
                size_bytes=artifact.size_bytes,
                created_at=artifact.created_at,
            )
            for artifact in artifacts
        ],
    )


@router.get("/{document_id}/sections", response_model=list[SectionNavigationEntry])
async def get_sections(
    document_id: str,
    session: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(require_roles("researcher", "admin")),
) -> list[SectionNavigationEntry]:
    """Return ordered parent-section navigation for a document."""
    await _registry_or_404(session, document_id)
    chunks = await session.scalars(
        select(GuidanceChunk)
        .where(GuidanceChunk.document_slug == document_id)
        .order_by(GuidanceChunk.chunk_id)
    )
    entries: dict[str, SectionNavigationEntry] = {}
    for chunk in chunks:
        if chunk.section_id and chunk.section_id not in entries:
            entries[chunk.section_id] = SectionNavigationEntry(
                section_id=chunk.section_id,
                section_title=chunk.section_title,
                page_number=chunk.page_number,
            )
    return list(entries.values())


@router.get("/{document_id}/passages/{chunk_id:path}", response_model=PassageResponse)
async def get_passage(
    document_id: str,
    chunk_id: str,
    session: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(require_roles("researcher", "admin")),
) -> PassageResponse:
    """Resolve an exact cited passage within the requested document."""
    chunk = await session.get(GuidanceChunk, chunk_id)
    if chunk is None or chunk.document_slug != document_id or not chunk.source_url:
        raise NotFoundAPIError("Cited passage was not found.")
    return PassageResponse(
        document_id=document_id,
        chunk_id=chunk.chunk_id,
        section_id=chunk.section_id,
        section_title=chunk.section_title,
        page_number=chunk.page_number,
        text=chunk.text,
        source_url=chunk.source_url,
        version_hash=chunk.version_hash,
    )


@router.get("/{document_id}/artifacts/{artifact_id}/download")
async def download_artifact(
    document_id: str,
    artifact_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    store: LocalArtifactStore = Depends(get_artifact_store_dep),
    user: AuthenticatedUser = Depends(require_roles("researcher", "admin")),
) -> Response:
    """Stream an authorized preserved source artifact without exposing its object key."""
    artifact = await session.get(SourceArtifact, artifact_id)
    if artifact is None or artifact.document_slug != document_id:
        raise NotFoundAPIError("Source artifact was not found.")
    try:
        data = store.read_bytes(artifact.object_key)
    except (FileNotFoundError, ValueError) as exc:
        raise NotFoundAPIError("Source artifact was not found.") from exc
    await record_audit_event(
        session,
        event_type="artifact_downloaded",
        user_id=user.user_id,
        session_id=None,
        route="/api/documents/{document_id}/artifacts/{artifact_id}/download",
        payload={"artifact_id": str(artifact.id), "document_id": document_id},
    )
    extension = "pdf" if artifact.content_type == "application/pdf" else "html"
    return Response(
        content=data,
        media_type=artifact.content_type,
        headers={"Content-Disposition": f'attachment; filename="{document_id}.{extension}"'},
    )

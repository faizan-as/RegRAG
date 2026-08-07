"""Export artifact generation (DOCX/PDF/plain text) for summaries and transcripts."""

from __future__ import annotations

import io
from uuid import uuid4

from apps.api.schemas.exports import ExportFormat
from src.common.storage import LocalArtifactStore

_CONTENT_TYPES = {
    ExportFormat.TEXT: "text/plain",
    ExportFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ExportFormat.PDF: "application/pdf",
}
_EXTENSIONS = {ExportFormat.TEXT: "txt", ExportFormat.DOCX: "docx", ExportFormat.PDF: "pdf"}


class ExportGenerationError(RuntimeError):
    """Raised when an export artifact cannot be rendered."""


def _render_docx_bytes(text: str) -> bytes:
    from docx import Document

    document = Document()
    for line in text.splitlines() or [""]:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _render_pdf_bytes(text: str) -> bytes:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=LETTER)
    width, height = LETTER
    y = height - 72
    for line in text.splitlines() or [""]:
        if y < 72:
            pdf.showPage()
            y = height - 72
        pdf.drawString(72, y, line[:110])
        y -= 14
    pdf.save()
    return buffer.getvalue()


def render_export_bytes(text: str, export_format: ExportFormat) -> tuple[bytes, str]:
    """Render export content to bytes, returning ``(data, content_type)``."""
    if export_format == ExportFormat.TEXT:
        return text.encode("utf-8"), _CONTENT_TYPES[ExportFormat.TEXT]
    if export_format == ExportFormat.DOCX:
        return _render_docx_bytes(text), _CONTENT_TYPES[ExportFormat.DOCX]
    if export_format == ExportFormat.PDF:
        return _render_pdf_bytes(text), _CONTENT_TYPES[ExportFormat.PDF]
    raise ExportGenerationError(f"Unsupported export format: {export_format}")


def build_export_object_key(export_id: str, export_format: ExportFormat) -> str:
    """Build a safe, namespaced object-store key for an export artifact."""
    return f"exports/{export_id}.{_EXTENSIONS[export_format]}"


def write_export_artifact(
    text: str,
    export_format: ExportFormat,
    *,
    artifact_store: LocalArtifactStore,
    export_id: str | None = None,
) -> tuple[str, str, int]:
    """Render and persist an export artifact.

    Returns ``(export_id, object_key, size_bytes)``.
    """
    export_id = export_id or str(uuid4())
    data, content_type = render_export_bytes(text, export_format)
    object_key = build_export_object_key(export_id, export_format)
    result = artifact_store.put_bytes(object_key, data, content_type=content_type)
    return export_id, result.object_key, result.size_bytes

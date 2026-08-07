"""Plain-text rendering templates for summary and transcript exports."""

from __future__ import annotations

from apps.api.schemas.answer import Answer
from apps.api.schemas.evidence import EvidenceCard
from apps.api.schemas.summaries import SummaryResult


def _citation_line(card: EvidenceCard) -> str:
    section = card.section_title or card.section_id or "N/A"
    page = card.page_number if card.page_number is not None else "N/A"
    return f"{card.citation_id} {card.title} - {section} (page {page}) - {card.source_url}"


def render_summary_text(summary: SummaryResult) -> str:
    """Render a grounded summary result as plain text with a citation appendix."""
    lines = [
        f"FDA Guidance Summary: {summary.document_id}",
        f"Type: {summary.summary_type.value}",
        "",
        summary.text,
    ]
    if summary.evidence:
        lines.append("")
        lines.append("Citations:")
        lines.extend(_citation_line(card) for card in summary.evidence)
    return "\n".join(lines)


def render_transcript_text(answers: list[Answer]) -> str:
    """Render a chat transcript export as plain text with a citation appendix."""
    lines = ["FDA Regulatory Intelligence Chat Transcript", ""]
    for index, answer in enumerate(answers, start=1):
        status = "refused" if answer.refused else "answered"
        lines.append(f"Q{index} ({status}):")
        lines.append(answer.text)
        if answer.evidence:
            lines.append("Citations:")
            lines.extend(_citation_line(card) for card in answer.evidence)
        lines.append("")
    return "\n".join(lines)

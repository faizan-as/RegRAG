"""Fail-closed citation binding for generated answers."""

from __future__ import annotations

import re
from collections.abc import Iterable

from apps.api.schemas.evidence import EvidenceCard
from src.agents.state import CitationBindingResult

_CITATION_PATTERN = re.compile(r"\[(\d+)]")
_BRACKETED_NUMBER_PATTERN = re.compile(r"\[[^\]]*\d+[^\]]*]")


def bind_citations(answer_text: str, evidence_cards: list[EvidenceCard]) -> CitationBindingResult:
    """Bind emitted citation markers to pre-assigned Evidence Cards."""
    cited_ids = _ordered_unique(f"[{match}]" for match in _CITATION_PATTERN.findall(answer_text))
    malformed = [
        item.group(0)
        for item in _BRACKETED_NUMBER_PATTERN.finditer(answer_text)
        if item.group(0) not in cited_ids
    ]
    if malformed:
        return CitationBindingResult(
            success=False,
            cited_ids=cited_ids,
            missing_ids=malformed,
            error="Malformed citation marker emitted by the model.",
        )
    if not cited_ids:
        return CitationBindingResult(success=False, error="Generated answer contains no citations.")

    cards_by_id = {card.citation_id: card for card in evidence_cards}
    missing_ids = [citation_id for citation_id in cited_ids if citation_id not in cards_by_id]
    if missing_ids:
        return CitationBindingResult(
            success=False,
            cited_ids=cited_ids,
            missing_ids=missing_ids,
            error="Generated answer cites unavailable evidence.",
        )

    return CitationBindingResult(
        success=True,
        bound_cards=[cards_by_id[citation_id] for citation_id in cited_ids],
        cited_ids=cited_ids,
    )


def _ordered_unique(values: Iterable[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            ordered.append(value)
            seen.add(value)
    return ordered
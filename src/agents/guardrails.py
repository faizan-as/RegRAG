"""Confidence, refusal, retry, and faithfulness guardrails."""

from __future__ import annotations

import re
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from apps.api.schemas.evidence import EvidenceCard
from src.agents.state import RefusalMetadata


class FaithfulnessResult(BaseModel):
    """Outcome from a faithfulness validator."""

    model_config = ConfigDict(extra="forbid")
    passed: bool
    reason: str | None = None
    score: float | None = Field(default=None, ge=0.0, le=1.0)


class FaithfulnessValidator(Protocol):
    """Validator protocol for answer-grounding checks."""

    async def validate(
        self,
        *,
        answer_text: str,
        evidence_cards: list[EvidenceCard],
    ) -> FaithfulnessResult:
        """Validate that an answer is supported by the supplied evidence."""


class PermissiveFaithfulnessValidator:
    """Deterministic validator used when no external validator is configured."""

    async def validate(
        self,
        *,
        answer_text: str,
        evidence_cards: list[EvidenceCard],
    ) -> FaithfulnessResult:
        del answer_text
        return FaithfulnessResult(
            passed=bool(evidence_cards),
            reason=None if evidence_cards else "No evidence supplied for validation.",
            score=1.0 if evidence_cards else 0.0,
        )


_PROHIBITED_PATTERNS = [
    re.compile(r"\byou are compliant\b", re.IGNORECASE),
    re.compile(r"\byou are not compliant\b", re.IGNORECASE),
    re.compile(r"\bfda will approve\b", re.IGNORECASE),
    re.compile(r"\bsubmission will be accepted\b", re.IGNORECASE),
    re.compile(r"\bwill be accepted by fda\b", re.IGNORECASE),
]


def aggregate_confidence(evidence_cards: list[EvidenceCard]) -> float:
    """Return the answer-level confidence from reranked evidence."""
    if not evidence_cards:
        return 0.0
    return max(card.confidence for card in evidence_cards)


def confidence_is_sufficient(confidence: float, *, threshold: float) -> bool:
    """Check confidence against the configured refusal threshold."""
    return confidence >= threshold


def can_retry(retry_count: int, max_retries: int) -> bool:
    """Return whether another generation attempt is allowed."""
    return retry_count < max_retries


def contains_compliance_determination(text: str) -> bool:
    """Detect prohibited final compliance or regulatory determinations."""
    return any(pattern.search(text) for pattern in _PROHIBITED_PATTERNS)


def refusal(reason: str, *, detail: str | None = None) -> RefusalMetadata:
    """Build standardized refusal metadata."""
    messages = {
        "no_evidence": "I could not find FDA guidance evidence strong enough to answer this with citations.",
        "low_confidence": "The retrieved FDA guidance evidence is too weak to support a citation-backed answer.",
        "retrieval_failure": "Retrieval failed before usable FDA guidance evidence could be collected.",
        "citation_binding_failure": "I could not bind the generated claims to valid FDA Evidence Cards.",
        "faithfulness_failure": "The generated answer could not be validated against the cited FDA evidence.",
        "unsupported_query": "This request is outside the supported FDA guidance research scope.",
        "compliance_determination_risk": "I cannot make final legal, compliance, approval, or submission-acceptance determinations.",
    }
    message = messages.get(reason, "I could not produce a supported citation-backed answer.")
    if detail:
        message = f"{message} {detail}"
    return RefusalMetadata(reason=reason, message=message)
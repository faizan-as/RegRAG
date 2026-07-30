"""Citation-first prompt templates and evidence formatting."""

from __future__ import annotations

from apps.api.schemas.evidence import EvidenceCard

QUERY_UNDERSTAND_PROMPT_VERSION = "query-understand-v1"
GROUNDED_ANSWER_PROMPT_VERSION = "grounded-answer-v1"
FAITHFULNESS_PROMPT_VERSION = "faithfulness-v1"


def build_query_understand_prompt(query: str) -> str:
    """Build a structured query-understanding prompt."""
    return f"""You classify FDA guidance research questions.
Return compact JSON with keys: rewritten_query, intent, entities.
Allowed intent values: question, summary, requirements, changes, unsupported.
Entities must be an object whose values are arrays of strings.
Do not answer the question.

User query:
{query}
"""


def format_evidence_context(evidence_cards: list[EvidenceCard]) -> str:
    """Format Evidence Cards for citation-first generation."""
    blocks: list[str] = []
    for card in evidence_cards:
        section = card.section_title or card.section_id or "Unknown section"
        page = f"page {card.page_number}" if card.page_number is not None else "page unavailable"
        blocks.append(
            "\n".join(
                [
                    f"{card.citation_id} {card.title}",
                    f"Section: {section}; {page}",
                    f"Status: {card.document_status.value}; version: {card.version_hash}",
                    f"Scores: retrieval={card.retrieval_score:.4f}; rerank={card.rerank_score:.4f}; confidence={card.confidence:.4f}",
                    f"Source: {card.source_url}",
                    f"Passage: {card.passage}",
                ]
            )
        )
    return "\n\n".join(blocks)


def build_grounded_answer_prompt(query: str, evidence_cards: list[EvidenceCard]) -> str:
    """Build the grounded answer-generation prompt."""
    return f"""You are an FDA regulatory intelligence assistant, not legal counsel.
Answer only from the Evidence Cards below. Every factual claim must use inline citation markers such as [1] that exactly match the provided Evidence Card ids. Do not renumber citations.
If the evidence does not support an answer, say that the available FDA guidance evidence is insufficient.
Do not make final legal, compliance, FDA approval, or submission-acceptance determinations.

Question:
{query}

Evidence Cards:
{format_evidence_context(evidence_cards)}

Return a concise answer with citations.
"""


def build_faithfulness_prompt(answer_text: str, evidence_cards: list[EvidenceCard]) -> str:
    """Build a prompt for LLM-based faithfulness validation."""
    return f"""Decide whether the answer is fully supported by the Evidence Cards.
Return JSON with keys passed (boolean), reason (string), and score (0 to 1).
Reject unsupported claims and final compliance/legal determinations.

Answer:
{answer_text}

Evidence Cards:
{format_evidence_context(evidence_cards)}
"""


def refusal_prompt(reason: str) -> str:
    """Return a short refusal instruction for a given reason."""
    return (
        "Explain that a citation-backed FDA guidance answer cannot be provided for this request. "
        f"Reason: {reason}. Keep it concise and do not speculate."
    )
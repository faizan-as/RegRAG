"""Tests for deterministic local development model adapters."""

from __future__ import annotations

import math

from apps.api.local_runtime import (
    LocalEmbeddingModel,
    LocalGroundedLLMClient,
    LocalRerankerModel,
)


def test_local_embedding_is_stable_normalized_and_dimensioned() -> None:
    model = LocalEmbeddingModel(32)

    first, second = model.encode(["FDA safety guidance", "FDA safety guidance"])

    assert first == second
    assert len(first) == 32
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0)


def test_local_reranker_prefers_lexical_overlap() -> None:
    scores = LocalRerankerModel().predict(
        [
            ("clinical trial safety", "manufacturing quality systems"),
            ("clinical trial safety", "clinical trial safety monitoring"),
        ]
    )

    assert scores[1] > scores[0]


async def test_local_llm_returns_json_and_bound_citations() -> None:
    client = LocalGroundedLLMClient()
    understanding = await client.generate(
        "Return compact JSON with keys: rewritten_query, intent, entities.\nUser query:\nFDA safety"
    )
    answer = await client.generate(
        "Evidence Cards:\n[1] FDA Guidance\nSection: Safety\nPassage: Sponsors should monitor\n"
        "safety throughout the clinical trial.\n\nReturn a concise answer."
    )

    assert '"rewritten_query": "FDA safety"' in understanding
    assert answer == "Sponsors should monitor safety throughout the clinical trial. [1]"

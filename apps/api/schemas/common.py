"""Shared transparency metadata attached to API responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TransparencyMetadata(BaseModel):
    """Node/tool execution transparency surfaced to API clients."""

    model_config = ConfigDict(extra="forbid")

    execution_trace: list[dict[str, Any]] = Field(
        default_factory=list, description="Ordered workflow node execution trace."
    )
    retrieval_diagnostics: dict[str, Any] = Field(
        default_factory=dict, description="Dense/BM25/reranker diagnostics from retrieval."
    )
    provider_fallback_trace: list[str] = Field(
        default_factory=list, description="LLM provider fallback events, if any."
    )
    ignored_filter_keys: list[str] = Field(
        default_factory=list, description="Unrecognized filter keys ignored during routing."
    )
    guardrail_errors: list[str] = Field(
        default_factory=list, description="Guardrail failures encountered during the workflow."
    )

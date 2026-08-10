"""Process-wide API resource initialization and shutdown."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI

from apps.api.local_runtime import (
    LocalEmbeddingModel,
    LocalGroundedLLMClient,
    LocalRerankerModel,
)
from apps.api.settings import Settings, get_settings
from src.common.clients import get_opensearch_client, get_postgres_sessionmaker
from src.common.db import dispose_engine
from src.common.storage import LocalArtifactStore, get_artifact_store
from src.ingestion.embedder import load_embedding_model
from src.llm.router import LLMClient, build_llm_client
from src.retrieval.reranker import load_reranker_model


@dataclass
class AppResources:
    """Shared process resources and sanitized initialization errors."""

    settings: Settings
    artifact_store: LocalArtifactStore
    opensearch_client: Any = None
    llm_client: LLMClient | None = None
    embedding_model: Any = None
    reranker_model: Any = None
    agent_graph: Any = None
    startup_errors: dict[str, str] = field(default_factory=dict)


async def initialize_resources(app: FastAPI) -> AppResources:
    """Initialize shared clients, models, and the compiled graph once."""
    settings = get_settings()
    artifact_store = get_artifact_store()
    artifact_store.ensure_store()
    resources = AppResources(settings=settings, artifact_store=artifact_store)

    try:
        resources.opensearch_client = get_opensearch_client()
    except Exception:
        resources.startup_errors["opensearch"] = "initialization_failed"

    if settings.local_demo_mode:
        resources.llm_client = LocalGroundedLLMClient()
        resources.embedding_model = LocalEmbeddingModel(settings.embedding_dim)
        resources.reranker_model = LocalRerankerModel()
    else:
        try:
            resources.llm_client = build_llm_client(settings)
        except Exception:
            resources.startup_errors["llm"] = "configuration_invalid"

        try:
            resources.embedding_model = await asyncio.to_thread(
                load_embedding_model, settings.embedding_model
            )
        except Exception:
            resources.startup_errors["embedding_model"] = "initialization_failed"

        try:
            resources.reranker_model = await asyncio.to_thread(
                load_reranker_model, settings.reranker_model
            )
        except Exception:
            resources.startup_errors["reranker_model"] = "initialization_failed"

    if (
        resources.llm_client is not None
        and resources.opensearch_client is not None
        and resources.embedding_model is not None
        and resources.reranker_model is not None
    ):
        from src.agents.graph import build_agent_graph
        from src.agents.nodes import AgentNodeDependencies

        sessionmaker = get_postgres_sessionmaker()
        dependencies = AgentNodeDependencies(
            llm_client=resources.llm_client,
            session_factory=lambda: sessionmaker(),
            opensearch_client_factory=lambda: resources.opensearch_client,
            embedding_model=resources.embedding_model,
            reranker_model=resources.reranker_model,
            settings=settings,
        )
        resources.agent_graph = build_agent_graph(dependencies)
    else:
        resources.startup_errors["agent_graph"] = "dependencies_unavailable"

    app.state.resources = resources
    return resources


async def close_resources(resources: AppResources) -> None:
    """Close shared clients and dispose the database engine."""
    if resources.opensearch_client is not None and hasattr(resources.opensearch_client, "close"):
        await asyncio.to_thread(resources.opensearch_client.close)
    await dispose_engine()

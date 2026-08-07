"""Dependency injection for FastAPI routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.errors import RetrievalUnavailableError
from apps.api.resources import AppResources
from apps.api.settings import Settings, get_settings
from src.common.db import get_session
from src.common.storage import LocalArtifactStore
from src.llm.router import LLMClient


def get_settings_dep() -> Settings:
    """Return the cached application settings."""
    return get_settings()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped async database session."""
    async with get_session() as session:
        yield session


def get_resources(request: Request) -> AppResources:
    """Return process-wide resources initialized during lifespan."""
    resources = getattr(request.app.state, "resources", None)
    if resources is None:
        raise RetrievalUnavailableError("API resources are not initialized.")
    return resources


def get_opensearch(resources: AppResources = Depends(get_resources)) -> Any:
    """Return the shared OpenSearch client."""
    if resources is None or resources.opensearch_client is None:
        raise RetrievalUnavailableError("Keyword retrieval is unavailable.")
    return resources.opensearch_client


def get_artifact_store_dep(
    resources: AppResources = Depends(get_resources),
) -> LocalArtifactStore:
    """Return the shared local artifact store."""
    if resources is None:
        raise RetrievalUnavailableError("Artifact storage is unavailable.")
    return resources.artifact_store


def get_llm_client_dep(resources: AppResources = Depends(get_resources)) -> LLMClient:
    """Return a configured LLM client for the current request."""
    if resources is None or resources.llm_client is None:
        raise RetrievalUnavailableError("Answer generation is unavailable.")
    return resources.llm_client


def get_agent_graph(resources: AppResources = Depends(get_resources)) -> Any:
    """Return the process-wide compiled LangGraph."""
    if resources is None or resources.agent_graph is None:
        raise RetrievalUnavailableError("Agent workflow is unavailable.")
    return resources.agent_graph

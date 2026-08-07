"""Liveness and dependency-aware readiness routes."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_db_session, get_resources
from apps.api.resources import AppResources
from apps.api.schemas.health import DependencyStatus, HealthResponse, ReadinessResponse
from apps.api.settings import Settings, get_settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Report cheap process liveness without downstream calls."""
    return HealthResponse(status="ok", env=settings.app_env.value)


async def _database_status(session: AsyncSession) -> DependencyStatus:
    try:
        await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=2.0)
        return DependencyStatus(name="postgresql", healthy=True)
    except Exception:
        return DependencyStatus(name="postgresql", healthy=False, detail="unavailable")


async def _opensearch_status(resources: AppResources) -> DependencyStatus:
    if resources.opensearch_client is None:
        return DependencyStatus(name="opensearch", healthy=False, detail="unavailable")
    try:
        healthy = await asyncio.wait_for(
            asyncio.to_thread(resources.opensearch_client.ping), timeout=2.0
        )
        return DependencyStatus(
            name="opensearch", healthy=bool(healthy), detail=None if healthy else "unavailable"
        )
    except Exception:
        return DependencyStatus(name="opensearch", healthy=False, detail="unavailable")


async def _artifact_status(resources: AppResources) -> DependencyStatus:
    key = f"health/{uuid4()}.tmp"
    try:
        await asyncio.to_thread(resources.artifact_store.put_bytes, key, b"ok")
        data = await asyncio.to_thread(resources.artifact_store.read_bytes, key)
        await asyncio.to_thread(resources.artifact_store.delete, key)
        healthy = data == b"ok"
        return DependencyStatus(
            name="artifact_store", healthy=healthy, detail=None if healthy else "unavailable"
        )
    except Exception:
        return DependencyStatus(name="artifact_store", healthy=False, detail="unavailable")


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    resources: AppResources = Depends(get_resources),
) -> ReadinessResponse:
    """Report timeout-bounded readiness for required API dependencies."""
    dependencies = list(
        await asyncio.gather(
            _database_status(session),
            _opensearch_status(resources),
            _artifact_status(resources),
        )
    )
    dependencies.extend(
        [
            DependencyStatus(
                name="llm",
                healthy=resources.llm_client is not None,
                detail=None if resources.llm_client is not None else "unavailable",
            ),
            DependencyStatus(
                name="embedding_model",
                healthy=resources.embedding_model is not None,
                detail=None if resources.embedding_model is not None else "unavailable",
            ),
            DependencyStatus(
                name="reranker_model",
                healthy=resources.reranker_model is not None,
                detail=None if resources.reranker_model is not None else "unavailable",
            ),
            DependencyStatus(
                name="agent_graph",
                healthy=resources.agent_graph is not None,
                detail=None if resources.agent_graph is not None else "unavailable",
            ),
        ]
    )
    ready = all(item.healthy for item in dependencies)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="ready" if ready else "not_ready", dependencies=dependencies)

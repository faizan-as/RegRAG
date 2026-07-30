"""Shared client factories for PostgreSQL, pgvector, OpenSearch, and artifact storage."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from opensearchpy import OpenSearch
from pgvector.sqlalchemy import Vector
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from apps.api.settings import get_settings
from src.common.db import get_engine, get_sessionmaker
from src.common.storage import get_artifact_store, get_object_store_client


@dataclass(frozen=True)
class PgvectorConfig:
    """Configuration used by retrieval/indexing code for pgvector tables."""

    table_name: str
    embedding_dim: int
    vector_type: type[Vector]


def get_postgres_engine() -> AsyncEngine:
    """Return the shared async PostgreSQL engine."""
    return get_engine()


def get_postgres_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the shared async PostgreSQL session factory."""
    return get_sessionmaker()


@lru_cache
def get_pgvector_config() -> PgvectorConfig:
    """Return pgvector table and embedding-dimension settings."""
    settings = get_settings()
    return PgvectorConfig(
        table_name=settings.pgvector_table,
        embedding_dim=settings.embedding_dim,
        vector_type=Vector,
    )


@lru_cache
def get_opensearch_client() -> OpenSearch:
    """Return a cached OpenSearch client configured from settings."""
    settings = get_settings()
    return OpenSearch(
        hosts=[settings.opensearch_url],
        http_auth=(settings.opensearch_user, settings.opensearch_password),
        use_ssl=settings.opensearch_url.startswith("https://"),
        verify_certs=settings.opensearch_url.startswith("https://"),
    )


__all__ = [
    "PgvectorConfig",
    "get_artifact_store",
    "get_object_store_client",
    "get_opensearch_client",
    "get_pgvector_config",
    "get_postgres_engine",
    "get_postgres_sessionmaker",
]
"""Application configuration via Pydantic v2 settings.

All runtime configuration is loaded from environment variables (or a local
``.env`` file). See ``.env.example`` for the full list of supported variables.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(str, Enum):
    """Deployment environment identifiers."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PILOT = "pilot"


class LLMProvider(str, Enum):
    """Supported LLM providers. Azure OpenAI is the MVP default."""

    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    VLLM = "vllm"


class Settings(BaseSettings):
    """Typed application settings sourced from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Application ----
    app_env: AppEnv = Field(default=AppEnv.DEVELOPMENT, alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")

    # ---- Vector (pgvector) & keyword search ----
    # Dense vectors live in PostgreSQL via pgvector (see database_url below).
    pgvector_table: str = Field(default="guidance_chunks", alias="PGVECTOR_TABLE")
    embedding_dim: int = Field(default=1024, alias="EMBEDDING_DIM")
    opensearch_url: str = Field(default="http://localhost:9200", alias="OPENSEARCH_URL")
    opensearch_user: str = Field(default="admin", alias="OPENSEARCH_USER")
    opensearch_password: str = Field(default="admin", alias="OPENSEARCH_PASSWORD")
    opensearch_index: str = Field(default="fda_guidance", alias="OPENSEARCH_INDEX")

    # ---- LLM configuration ----
    llm_provider: LLMProvider = Field(default=LLMProvider.AZURE_OPENAI, alias="LLM_PROVIDER")
    azure_openai_endpoint: str | None = Field(default=None, alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: str | None = Field(default=None, alias="AZURE_OPENAI_API_KEY")
    azure_openai_api_version: str = Field(default="2024-10-21", alias="AZURE_OPENAI_API_VERSION")
    azure_openai_deployment: str = Field(default="gpt-4.1", alias="AZURE_OPENAI_DEPLOYMENT")
    llm_choice: str = Field(default="gpt-4.1", alias="LLM_CHOICE")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    onprem_llm_base_url: str | None = Field(default=None, alias="ONPREM_LLM_BASE_URL")

    # ---- Embeddings & reranking ----
    embedding_model: str = Field(default="BAAI/bge-m3", alias="EMBEDDING_MODEL")
    reranker_model: str = Field(default="BAAI/bge-reranker-large", alias="RERANKER_MODEL")

    # ---- Ingestion ----
    fda_guidance_json_url: str = Field(
        default="https://www.fda.gov/files/api/datatables/static/search-for-guidance.json",
        alias="FDA_GUIDANCE_JSON_URL",
    )
    fda_base_url: str = Field(default="https://www.fda.gov", alias="FDA_BASE_URL")
    parent_chunk_size: int = Field(default=8000, alias="PARENT_CHUNK_SIZE")
    child_chunk_size: int = Field(default=1200, alias="CHILD_CHUNK_SIZE")
    child_chunk_overlap: int = Field(default=150, alias="CHILD_CHUNK_OVERLAP")
    embed_batch_size: int = Field(default=32, alias="EMBED_BATCH_SIZE")
    ingest_schedule_cron: str = Field(default="0 2 * * *", alias="INGEST_SCHEDULE_CRON")

    # ---- Metadata DB ----
    database_url: str = Field(
        default="postgresql+asyncpg://fda:fda@localhost:5432/fda_copilot",
        alias="DATABASE_URL",
    )

    # ---- Artifact storage ----
    object_store_backend: str = Field(default="local", alias="OBJECT_STORE_BACKEND")
    object_store_base_path: Path = Field(
        default=Path("data/object_store"), alias="OBJECT_STORE_BASE_PATH"
    )

    # ---- Auth (Supabase) ----
    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_key: str | None = Field(default=None, alias="SUPABASE_KEY")
    supabase_jwt_secret: str | None = Field(default=None, alias="SUPABASE_JWT_SECRET")
    supabase_jwks_url: str | None = Field(default=None, alias="SUPABASE_JWKS_URL")
    supabase_jwt_issuer: str | None = Field(default=None, alias="SUPABASE_JWT_ISSUER")
    supabase_jwt_audience: str | None = Field(
        default="authenticated", alias="SUPABASE_JWT_AUDIENCE"
    )
    supabase_jwt_algorithms: str = Field(default="RS256,ES256", alias="SUPABASE_JWT_ALGORITHMS")
    supabase_app_roles_claim: str = Field(
        default="app_metadata.roles", alias="SUPABASE_APP_ROLES_CLAIM"
    )
    supabase_jwt_leeway_seconds: int = Field(
        default=30, ge=0, le=300, alias="SUPABASE_JWT_LEEWAY_SECONDS"
    )
    auth_dev_bypass: bool = Field(
        default=False,
        alias="AUTH_DEV_BYPASS",
        description="Bypass JWT validation with a fake admin user. Development only.",
    )

    # ---- API hardening ----
    cors_allowed_origins: str = Field(
        default="http://localhost:3000",
        alias="CORS_ALLOWED_ORIGINS",
        description="Comma-separated list of allowed CORS origins.",
    )
    rate_limit_per_minute: int = Field(default=30, alias="RATE_LIMIT_PER_MINUTE")
    chat_rate_limit_per_minute: int = Field(default=10, alias="CHAT_RATE_LIMIT_PER_MINUTE")
    search_rate_limit_per_minute: int = Field(default=30, alias="SEARCH_RATE_LIMIT_PER_MINUTE")
    summary_rate_limit_per_minute: int = Field(default=5, alias="SUMMARY_RATE_LIMIT_PER_MINUTE")
    export_rate_limit_per_minute: int = Field(default=10, alias="EXPORT_RATE_LIMIT_PER_MINUTE")
    document_rate_limit_per_minute: int = Field(default=60, alias="DOCUMENT_RATE_LIMIT_PER_MINUTE")
    max_active_streams_per_user: int = Field(default=2, alias="MAX_ACTIVE_STREAMS_PER_USER")

    # ---- Observability (Langfuse) ----
    langfuse_host: str = Field(default="http://localhost:3000", alias="LANGFUSE_HOST")
    langfuse_public_key: str | None = Field(default=None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str | None = Field(default=None, alias="LANGFUSE_SECRET_KEY")

    # ---- Retrieval tuning ----
    retrieval_top_k: int = Field(default=20, alias="RETRIEVAL_TOP_K")
    rerank_top_k: int = Field(default=5, alias="RERANK_TOP_K")
    confidence_threshold: float = Field(default=0.5, alias="CONFIDENCE_THRESHOLD")
    max_faithfulness_retries: int = Field(default=1, alias="MAX_FAITHFULNESS_RETRIES")

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        """Return CORS allowed origins as a parsed list."""
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def supabase_jwt_algorithms_list(self) -> list[str]:
        """Return the explicitly configured JWT algorithm allowlist."""
        return [item.strip() for item in self.supabase_jwt_algorithms.split(",") if item.strip()]

    @model_validator(mode="after")
    def validate_deployment_safety(self) -> Settings:
        """Reject development-only authentication bypass outside development."""
        if self.auth_dev_bypass and self.app_env != AppEnv.DEVELOPMENT:
            raise ValueError("AUTH_DEV_BYPASS is allowed only when APP_ENV=development")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance.

    Returns:
        The application settings, loaded once and cached for the process
        lifetime.
    """
    return Settings()

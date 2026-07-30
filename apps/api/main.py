"""FastAPI application entrypoint.

Wires configuration and structured logging, and exposes a health endpoint
for readiness checks. Feature routers are added in later phases.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from apps.api.settings import AppEnv, get_settings
from src.common.logging import configure_logging, get_logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure logging on startup.

    Args:
        app: The FastAPI application instance.

    Yields:
        Control back to the ASGI server for the application lifetime.
    """
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        json_logs=settings.app_env != AppEnv.DEVELOPMENT,
    )
    logger = get_logger(__name__)
    logger.info("api_startup", env=settings.app_env.value, port=settings.app_port)
    yield
    logger.info("api_shutdown")


app = FastAPI(
    title="FDA Regulatory Intelligence Platform",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Report basic API liveness.

    Returns:
        A payload with service status and the active environment.
    """
    settings = get_settings()
    return {"status": "ok", "env": settings.app_env.value}

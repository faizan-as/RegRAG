"""FastAPI application entrypoint.

Wires configuration and structured logging, and exposes a health endpoint
for readiness checks. Feature routers are added in later phases.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from apps.api.errors import register_exception_handlers
from apps.api.resources import AppResources, close_resources, initialize_resources
from apps.api.routes.alerts import router as alerts_router
from apps.api.routes.audit import router as audit_router
from apps.api.routes.chat import router as chat_router
from apps.api.routes.documents import router as documents_router
from apps.api.routes.exports import router as exports_router
from apps.api.routes.health import router as health_router
from apps.api.routes.search import router as search_router
from apps.api.routes.sessions import router as sessions_router
from apps.api.routes.summaries import router as summaries_router
from apps.api.schemas.errors import API_ERROR_RESPONSES
from apps.api.settings import AppEnv, get_settings
from src.common.logging import configure_logging, get_logger

ResourceInitializer = Callable[[FastAPI], Awaitable[AppResources]]


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a stable request id to state and response headers."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request.state.request_id = request.headers.get("x-request-id") or str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response


def create_app(resource_initializer: ResourceInitializer = initialize_resources) -> FastAPI:
    """Create the configured FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = get_settings()
        configure_logging(
            level=settings.log_level,
            json_logs=settings.app_env != AppEnv.DEVELOPMENT,
        )
        logger = get_logger(__name__)
        logger.info("api_startup", env=settings.app_env.value, port=settings.app_port)
        resources = await resource_initializer(app)
        try:
            yield
        finally:
            await close_resources(resources)
            logger.info("api_shutdown")

    settings = get_settings()
    application = FastAPI(
        title="FDA Regulatory Intelligence Platform",
        version="0.1.0",
        lifespan=lifespan,
        responses=API_ERROR_RESPONSES,
    )
    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["Content-Disposition", "X-Request-ID", "Retry-After"],
    )
    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(sessions_router)
    application.include_router(chat_router)
    application.include_router(search_router)
    application.include_router(documents_router)
    application.include_router(summaries_router)
    application.include_router(exports_router)
    application.include_router(alerts_router)
    application.include_router(audit_router)
    return application


app = create_app()

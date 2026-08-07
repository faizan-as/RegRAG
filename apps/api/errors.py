"""Structured API exception types and FastAPI exception handlers."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.common.logging import get_logger

logger = get_logger(__name__)


class APIError(Exception):
    """Base class for structured, client-safe API errors."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ValidationAPIError(APIError):
    """A request failed structured validation (e.g. unknown filter value)."""

    status_code = 422
    code = "validation_error"


class AuthenticationError(APIError):
    """The request lacks valid authentication credentials."""

    status_code = 401
    code = "authentication_error"


class AuthorizationError(APIError):
    """The authenticated user lacks the role required for this action."""

    status_code = 403
    code = "authorization_error"


class RateLimitError(APIError):
    """The caller exceeded the allotted request rate."""

    status_code = 429
    code = "rate_limit_exceeded"


class RetrievalUnavailableError(APIError):
    """Retrieval could not produce results due to a dependency failure."""

    status_code = 503
    code = "retrieval_unavailable"


class NotFoundAPIError(APIError):
    """The requested resource does not exist or is not visible to the caller."""

    status_code = 404
    code = "not_found"


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def register_exception_handlers(app: FastAPI) -> None:
    """Register structured exception handlers on the FastAPI app."""

    @app.exception_handler(APIError)
    async def handle_api_error(request: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "request_id": _request_id(request),
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Invalid request payload.",
                    "request_id": _request_id(request),
                    "details": exc.errors(),
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": "http_error",
                    "message": str(exc.detail),
                    "request_id": _request_id(request),
                    "details": None,
                }
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = _request_id(request) or str(uuid4())
        logger.error(
            "unhandled_api_error",
            path=str(request.url.path),
            error_type=type(exc).__name__,
            request_id=request_id,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred.",
                    "request_id": request_id,
                    "details": None,
                }
            },
        )

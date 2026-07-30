"""Structured logging configuration using ``structlog``.

Emits JSON logs in non-development environments and human-friendly console
logs during development. Call :func:`configure_logging` once at application
startup, then obtain loggers via :func:`get_logger`.
"""

from __future__ import annotations

import logging
import sys

import structlog

_CONFIGURED = False


def configure_logging(level: str = "INFO", *, json_logs: bool = True) -> None:
    """Configure the standard library and ``structlog`` logging pipelines.

    Args:
        level: Minimum log level name (e.g. ``"INFO"``, ``"DEBUG"``).
        json_logs: When ``True`` render JSON; otherwise use a console renderer.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _CONFIGURED = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structured logger.

    Args:
        name: Optional logger name, typically ``__name__``.

    Returns:
        A configured ``structlog`` bound logger.
    """
    return structlog.get_logger(name)

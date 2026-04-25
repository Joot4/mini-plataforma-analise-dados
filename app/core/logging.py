from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: str = "INFO", *, debug: bool = False) -> None:
    """Configure structlog + stdlib logging to emit JSON (or pretty in DEBUG) to stdout.

    Idempotent: safe to call multiple times (tests, uvicorn reload).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Route stdlib logging -> stdout at the chosen level.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        force=True,
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if debug:
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger, optionally namespaced."""
    return structlog.get_logger(name)

"""structlog configuration.

JSON to stdout in prod (Loki/Promtail-friendly); colorized console renderer
in dev so a developer can read the output directly. Call
``configure_logging(env)`` exactly once at app factory time — structlog's
configuration is process-global and ``cache_logger_on_first_use`` means a
second call has no effect.
"""
from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(env: str) -> None:
    """Initialize structlog processors for the given environment.

    ``env`` is the ``AP_ENV`` value: ``"prod"`` selects ``JSONRenderer``;
    anything else (including ``"dev"``) selects ``ConsoleRenderer``.
    """
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if env == "prod":
        processors = shared_processors + [structlog.processors.JSONRenderer()]
    else:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True)
        ]
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

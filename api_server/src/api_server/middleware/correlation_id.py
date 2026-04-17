"""Thin wrapper around asgi-correlation-id's CorrelationIdMiddleware.

Keeps ``from api_server.middleware.correlation_id import CorrelationIdMiddleware``
as a stable import path so we can swap the implementation later (or wrap it)
without touching call sites in main.py / route handlers.
"""
from __future__ import annotations

# Re-export the library class. The library already handles:
#   - Minting a UUID when the X-Request-Id header is absent.
#   - Binding it into a contextvar (``correlation_id.get()`` inside handlers).
#   - Echoing it back in the response header.
from asgi_correlation_id import CorrelationIdMiddleware
from asgi_correlation_id import correlation_id  # re-exported for convenience

__all__ = ["CorrelationIdMiddleware", "correlation_id"]

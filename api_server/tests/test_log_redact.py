"""Prove AccessLogMiddleware never logs Authorization / Cookie / X-Api-Key / body.

Plan 19-06 acceptance tests. Each HTTP test fires a request with a secret in
one of the sensitive surfaces and then asserts that the captured log records
(serialized to JSON) contain NO substring of the secret. The unit tests cover
the ``mask_known_prefixes`` util directly.
"""
from __future__ import annotations

import json
import logging

import pytest
import structlog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api_server.middleware.correlation_id import CorrelationIdMiddleware
from api_server.middleware.log_redact import AccessLogMiddleware
from api_server.routes.health import router as health_router
from api_server.util.redaction import mask_known_prefixes


@pytest.fixture
def captured_logs():
    """Attach a structlog processor that appends every event dict to a list.

    Restores structlog's default config on teardown so this fixture doesn't
    bleed into other tests.
    """
    records: list[dict] = []

    def _capture(logger, name, event_dict):
        records.append(dict(event_dict))
        return event_dict

    structlog.configure(
        processors=[_capture, structlog.processors.JSONRenderer()],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        cache_logger_on_first_use=False,
    )
    yield records
    structlog.reset_defaults()


def _build_app() -> FastAPI:
    """Minimal FastAPI app: correlation-id + access-log + the health router."""
    app = FastAPI()
    # Middleware application order: AccessLog goes on first so it wraps the
    # correlation_id middleware — every logged record gets the request id.
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.include_router(health_router)
    return app


@pytest.mark.asyncio
async def test_authorization_header_not_logged(captured_logs):
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(
            "/healthz",
            headers={"Authorization": "Bearer sk-secret-xxxxxxxxxxxxxxxx"},
        )
    assert r.status_code == 200
    serialized = json.dumps(captured_logs)
    # Primary invariant: the secret body must never appear in the log stream.
    assert "sk-secret-xxxxxxxxxxxxxxxx" not in serialized
    # Secondary invariant: the Authorization header key must not be in the
    # allowlisted headers dict either. (case-insensitive substring check)
    assert "authorization" not in serialized.lower()


@pytest.mark.asyncio
async def test_cookie_header_not_logged(captured_logs):
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        await c.get("/healthz", headers={"Cookie": "session=secret-cookie-value"})
    serialized = json.dumps(captured_logs)
    assert "secret-cookie-value" not in serialized


@pytest.mark.asyncio
async def test_x_api_key_header_not_logged(captured_logs):
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        await c.get("/healthz", headers={"X-Api-Key": "api-key-xyz12345"})
    serialized = json.dumps(captured_logs)
    assert "api-key-xyz12345" not in serialized


@pytest.mark.asyncio
async def test_request_body_not_logged(captured_logs):
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # Non-existent endpoint still traverses middleware; the middleware
        # never reads the body, so the secret inside it cannot leak.
        await c.post("/nonexistent", content=b"secret=abc")
    serialized = json.dumps(captured_logs)
    assert "secret=abc" not in serialized


def test_mask_known_prefixes():
    """Unit test: the redaction util masks Bearer + sk-* patterns."""
    masked = mask_known_prefixes(
        "auth: Bearer sk-real-0123456789abcdefghij failed",
    )
    assert "sk-real-0123456789abcdefghij" not in masked
    assert "<REDACTED>" in masked


def test_mask_known_prefixes_with_explicit_val():
    """Unit test: passing api_key_val masks the literal value."""
    masked = mask_known_prefixes(
        "the key abc12345xyz leaked",
        api_key_val="abc12345xyz",
    )
    assert "abc12345xyz" not in masked

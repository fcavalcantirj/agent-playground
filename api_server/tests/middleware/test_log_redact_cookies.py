"""Phase 22c cookie-redaction invariant tests.

Proves by construction that ``ap_session`` and ``ap_oauth_state`` cookie
VALUES never appear in log output emitted by ``AccessLogMiddleware``. The
middleware's ``_LOG_HEADERS`` allowlist does not include ``cookie`` /
``set-cookie``, so no Cookie header is ever formatted into a log record.

These tests stand up a minimal FastAPI app with BOTH
``AccessLogMiddleware`` and ``SessionMiddleware`` mounted, send a real
request carrying a cookie with a unique sentinel value, and assert the
serialized log stream contains zero occurrences of the sentinel.
"""
from __future__ import annotations

import json
import logging
import uuid

import pytest
import structlog
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from api_server.middleware.log_redact import AccessLogMiddleware
from api_server.middleware.session import SessionMiddleware


@pytest.fixture
def captured_logs():
    """Append every structlog event dict to a list; restore on teardown."""
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
    """Minimal app: AccessLog wraps SessionMiddleware + /_test/ping route.

    No real DB pool — requests carry obviously-invalid cookie values
    (non-UUIDs or UUIDs with no corresponding session row), so
    SessionMiddleware short-circuits to user_id=None without issuing a
    PG query. That keeps these tests DB-free by construction.
    """
    app = FastAPI()

    # No-op pool stand-in for the middleware's scope['app'].state.db path.
    # Even if a SELECT were attempted, the outer SessionMiddleware wraps
    # it in try/except and fails-closed — but the non-UUID cookie path
    # avoids the query entirely.
    class _NoopPool:
        def acquire(self):
            raise AssertionError(
                "DB pool should not be touched in cookie-redact tests; "
                "SessionMiddleware should short-circuit on the non-UUID "
                "cookie before reaching acquire()."
            )

    app.state.db = _NoopPool()
    app.add_middleware(SessionMiddleware)
    app.add_middleware(AccessLogMiddleware)

    @app.get("/_test/ping")
    async def ping(request: Request):
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_ap_session_cookie_value_not_in_logs(captured_logs):
    """``Cookie: ap_session=<sentinel>`` → sentinel MUST NOT appear in logs."""
    sentinel = f"session-sentinel-{uuid.uuid4()}"
    app = _build_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://t"
    ) as c:
        r = await c.get(
            "/_test/ping",
            headers={"Cookie": f"ap_session={sentinel}"},
        )
    assert r.status_code == 200, r.text
    serialized = json.dumps(captured_logs)
    assert sentinel not in serialized, (
        f"ap_session cookie value leaked into logs: "
        f"sentinel={sentinel!r} in serialized log stream"
    )
    # Allowlist invariant: the literal header key must also be absent.
    assert "ap_session=" not in serialized, (
        "ap_session= substring found in logs — Cookie header was formatted"
    )


@pytest.mark.asyncio
async def test_ap_oauth_state_cookie_value_not_in_logs(captured_logs):
    """``Cookie: ap_oauth_state=<sentinel>`` → sentinel MUST NOT appear in logs."""
    sentinel = f"state-sentinel-{uuid.uuid4()}"
    app = _build_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://t"
    ) as c:
        r = await c.get(
            "/_test/ping",
            headers={"Cookie": f"ap_oauth_state={sentinel}"},
        )
    assert r.status_code == 200, r.text
    serialized = json.dumps(captured_logs)
    assert sentinel not in serialized, (
        f"ap_oauth_state cookie value leaked into logs: "
        f"sentinel={sentinel!r} in serialized log stream"
    )
    assert "ap_oauth_state=" not in serialized, (
        "ap_oauth_state= substring found in logs — Cookie header was formatted"
    )

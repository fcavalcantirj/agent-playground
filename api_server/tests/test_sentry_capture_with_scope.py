"""2026-05-12 — unit tests for instrumentation.sentry.capture_with_scope.

Verifies the new ``capture_with_scope(exc, **tags)`` helper:

1. Captures the exception with the expected scope tags (route-filterable).
2. ``_before_send`` drops events whose ``ap_error_code`` tag is in the
   USER_ERROR bucket (auth chaff filter — protects Free-tier quota).
3. Server errors (INFRA_UNAVAILABLE, INTERNAL, etc.) pass through.
4. Helper is a no-op when Sentry DSN is unset (safe to call from any
   except block, dev or prod).

No real Sentry server — we use ``sentry_sdk.init(transport=...)`` with
an in-memory transport stub that lets us inspect what would have been
sent.
"""
from __future__ import annotations

import pytest
import sentry_sdk

from api_server.instrumentation.sentry import (
    _USER_ERROR_CODES,
    _before_send,
    capture_with_scope,
)


class _CapturingTransport(sentry_sdk.transport.Transport):
    """In-memory Sentry transport that retains envelopes for inspection."""

    def __init__(self):
        super().__init__()
        self.envelopes: list = []

    def capture_envelope(self, envelope) -> None:
        self.envelopes.append(envelope)

    def flush(self, *args, **kwargs) -> None:
        return None

    def kill(self) -> None:
        return None


@pytest.fixture
def sentry_transport(monkeypatch):
    """Init Sentry against an in-memory transport for the test scope."""
    transport = _CapturingTransport()
    sentry_sdk.init(
        dsn="https://test@example.invalid/1",
        transport=transport,
        before_send=_before_send,
        traces_sample_rate=0.0,
    )
    yield transport
    sentry_sdk.flush(timeout=1)
    # Reset hub between tests to avoid cross-test scope leak.
    sentry_sdk.init()  # disables further capture


# --- helpers ---------------------------------------------------------------


def _captured_events(transport: _CapturingTransport) -> list[dict]:
    sentry_sdk.flush(timeout=1)
    events: list[dict] = []
    for env in transport.envelopes:
        for item in env.items:
            if item.headers.get("type") == "event":
                payload = item.payload.json
                if payload:
                    events.append(payload)
    return events


# --- tests -----------------------------------------------------------------


def test_capture_with_scope_emits_tags(sentry_transport):
    """Tags surface on the captured event for filtering."""
    try:
        raise RuntimeError("boom")
    except RuntimeError as e:
        capture_with_scope(
            e,
            endpoint="agent_lifecycle.start",
            code="INFRA_UNAVAILABLE",
            recipe="hermes",
            channel="telegram",
            agent_id="abc-123",
            run_id="01J0XYZ",
        )

    events = _captured_events(sentry_transport)
    assert len(events) == 1, f"expected 1 event, got {len(events)}"
    tags = events[0].get("tags") or {}
    assert tags.get("endpoint") == "agent_lifecycle.start"
    assert tags.get("ap_error_code") == "INFRA_UNAVAILABLE"
    assert tags.get("recipe") == "hermes"
    assert tags.get("channel") == "telegram"
    assert tags.get("agent_id") == "abc-123"
    extras = events[0].get("extra") or {}
    assert extras.get("run_id") == "01J0XYZ"


def test_before_send_drops_user_error_bucket(sentry_transport):
    """USER_ERROR-bucket codes are dropped before they hit transport.

    Auth chaff (UNAUTHORIZED, INVALID_REQUEST, etc.) would otherwise burn
    Free-tier Sentry quota under DDoS. _before_send checks the
    ap_error_code scope tag.
    """
    for code in ["UNAUTHORIZED", "INVALID_REQUEST", "RATE_LIMITED"]:
        try:
            raise ValueError(f"user error: {code}")
        except ValueError as e:
            capture_with_scope(e, endpoint="auth.test", code=code)

    events = _captured_events(sentry_transport)
    assert events == [], f"USER_ERROR codes leaked: {events!r}"


def test_before_send_keeps_server_errors(sentry_transport):
    """Server-side codes (INFRA_UNAVAILABLE, INTERNAL) pass the filter."""
    for code in ["INFRA_UNAVAILABLE", "INTERNAL", "RUNNER_TIMEOUT"]:
        try:
            raise RuntimeError(f"server error: {code}")
        except RuntimeError as e:
            capture_with_scope(e, endpoint="agent_lifecycle.test", code=code)

    events = _captured_events(sentry_transport)
    assert len(events) == 3, (
        f"expected 3 server-error events, got {len(events)} "
        f"(codes were INFRA_UNAVAILABLE/INTERNAL/RUNNER_TIMEOUT)"
    )


def test_user_error_bucket_covers_known_4xx_codes():
    """Regression: every code we route to _err(4xx, …) is in the bucket.

    If a new 4xx code is added without listing it here, the filter would
    let auth-bucket events through and risk quota. This is a coupling
    point — keep the test current with ErrorCode additions.
    """
    expected = {
        "UNAUTHORIZED",
        "INVALID_REQUEST",
        "RECIPE_NOT_FOUND",
        "SCHEMA_NOT_FOUND",
        "RATE_LIMITED",
        "AGENT_NOT_FOUND",
        "AGENT_NOT_RUNNING",
        "AGENT_ALREADY_RUNNING",
        "INSUFFICIENT_BALANCE",
        "TIER_LIMIT_EXCEEDED",
    }
    missing = expected - _USER_ERROR_CODES
    assert not missing, f"USER_ERROR bucket missing codes: {missing}"

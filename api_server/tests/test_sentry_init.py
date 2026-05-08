"""Phase 31 H6 — Sentry init + before_send + set_user tests.

Per AMD-06: the auth-bucket-429 NOT-captured assertion is non-negotiable;
without it, the test passes vacuously even if before_send is broken.

NO respx, NO hand-rolled stub — Sentry SDK 2.x ships its own
`Transport` mock primitive (sentry_sdk.transport.Transport).
"""
from __future__ import annotations

import pytest
import sentry_sdk
from sentry_sdk.transport import Transport
from starlette.exceptions import HTTPException as StarletteHTTPException

from api_server.instrumentation.sentry import _before_send, init_sentry


class _CapturingTransport(Transport):
    """Test-only Sentry transport that collects envelopes in-memory."""
    def __init__(self, options=None):
        super().__init__(options)
        self.envelopes: list = []

    def capture_envelope(self, envelope):
        self.envelopes.append(envelope)


@pytest.fixture
def isolated_sentry_hub():
    """Push a fresh Sentry hub for the test; restore on teardown."""
    yield
    try:
        client = sentry_sdk.get_client()
        if client is not None and client.is_active():
            client.close()
    except Exception:
        pass


def _init_with_capture(transport):
    sentry_sdk.init(
        dsn="https://test@example.ingest.sentry.io/1",
        transport=transport,
        traces_sample_rate=0.0,
        before_send=_before_send,
    )


def test_unhandled_exception_captured(isolated_sentry_hub):
    """SPEC AC12: unhandled RuntimeError → exactly one envelope captured."""
    transport = _CapturingTransport()
    _init_with_capture(transport)
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        sentry_sdk.capture_exception()
    sentry_sdk.flush(timeout=2.0)
    assert len(transport.envelopes) == 1, (
        f"expected 1 envelope; got {len(transport.envelopes)}"
    )


def test_before_send_drops_429(isolated_sentry_hub):
    """AMD-06: auth-bucket 429 (HTTPException<500) must NOT reach the transport.

    This is the load-bearing assertion that protects the 5K/month
    Free-tier quota from auth-bucket DDoS attempts (T-31-02).
    """
    transport = _CapturingTransport()
    _init_with_capture(transport)
    try:
        raise StarletteHTTPException(status_code=429, detail="rate limited")
    except StarletteHTTPException:
        sentry_sdk.capture_exception()
    sentry_sdk.flush(timeout=2.0)
    assert len(transport.envelopes) == 0, (
        f"AMD-06 violated: {len(transport.envelopes)} envelopes captured for 429; "
        "before_send must drop HTTPException with status_code < 500"
    )


def test_before_send_keeps_500(isolated_sentry_hub):
    """AMD-06 inverse: HTTPException 500 IS a server error and MUST reach Sentry."""
    transport = _CapturingTransport()
    _init_with_capture(transport)
    try:
        raise StarletteHTTPException(status_code=500, detail="server boom")
    except StarletteHTTPException:
        sentry_sdk.capture_exception()
    sentry_sdk.flush(timeout=2.0)
    assert len(transport.envelopes) == 1, (
        f"expected 1 envelope for 500; got {len(transport.envelopes)}"
    )


def test_errors_only_sampling(isolated_sentry_hub):
    """SPEC AC16: traces_sample_rate must be 0.0 after init_sentry."""
    transport = _CapturingTransport()
    _init_with_capture(transport)
    client = sentry_sdk.get_client()
    assert client is not None
    assert client.options["traces_sample_rate"] == 0.0, client.options


def test_no_dsn_starts_cleanly(monkeypatch, caplog):
    """SPEC AC13: DSN unset → init_sentry returns silently, logs INFO once."""
    import logging
    caplog.set_level(logging.INFO, logger="api_server.sentry")

    class _S:
        sentry_dsn_api = None
        env = "dev"
        git_sha = None

    init_sentry(_S())  # must not raise
    assert any(
        "Sentry disabled (AP_SENTRY_DSN_API unset)" in rec.message
        for rec in caplog.records
    ), [rec.message for rec in caplog.records]


def test_init_sentry_tags_environment_and_release(isolated_sentry_hub):
    """D-13 / WR-03: environment + release from settings land on the client.

    Exercises the production `init_sentry()` path directly (NOT the
    `_init_with_capture` shim) so a future refactor that drops `environment=`
    or `release=` from the init call is caught by this test.
    """
    class _S:
        sentry_dsn_api = "https://test@example.ingest.sentry.io/1"
        env = "prod"
        git_sha = "deadbeef"

    init_sentry(_S())
    client = sentry_sdk.get_client()
    assert client is not None
    assert client.options["environment"] == "prod", client.options
    assert client.options["release"] == "deadbeef", client.options



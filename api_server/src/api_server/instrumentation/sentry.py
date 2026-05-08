"""Sentry init helper — Phase 31 H6 (D-10, D-12, D-13, D-14, AMD-06).

Errors-only Sentry instrumentation. Called once from main.create_app()
BEFORE the middleware stack so unhandled exceptions in middleware are
also captured. Graceful no-op when AP_SENTRY_DSN_API is unset (mirrors
auth/oauth.py's `OAuth config oauth_X missing in dev; using placeholder`
pattern).

The `_before_send` filter is LOAD-BEARING: it drops Starlette
HTTPException envelopes with status_code < 500 (404, 422, 429, etc.) so
the auth-bucket DDoS scenario (T-31-02) cannot blow the 5K/month
Free-tier quota in minutes. AMD-06 mandates the import path
`from starlette.exceptions import HTTPException as StarletteHTTPException`
because FastAPI re-exports the same class.
"""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

import sentry_sdk
from starlette.exceptions import HTTPException as StarletteHTTPException

if TYPE_CHECKING:
    from ..config import Settings

_log = logging.getLogger("api_server.sentry")


def _before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Drop client-error envelopes before they hit Sentry quota.

    Phase 31 D-12 + AMD-06: HTTPException with status_code < 500 is a
    client mistake (404, 422, 429), not a server bug.
    """
    exc_info = hint.get("exc_info")
    if exc_info is not None:
        _exc_type, exc_value, _tb = exc_info
        if isinstance(exc_value, StarletteHTTPException) and exc_value.status_code < 500:
            return None
    return event


def init_sentry(settings: "Settings") -> None:
    """Initialize Sentry if AP_SENTRY_DSN_API is set; else log INFO + return.

    D-10: called from main.create_app() BEFORE middleware stack setup so
    unhandled exceptions in middleware are also captured.
    D-13: environment from settings.env, release from settings.git_sha.
    D-14: DSN-unset → log INFO once, then silent.
    """
    dsn = getattr(settings, "sentry_dsn_api", None)
    if not dsn:
        _log.info("Sentry disabled (AP_SENTRY_DSN_API unset)")
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=getattr(settings, "env", "dev"),
        release=getattr(settings, "git_sha", None) or None,
        traces_sample_rate=0.0,
        before_send=_before_send,
    )
    _log.info(
        "Sentry initialized",
        extra={
            "environment": getattr(settings, "env", "dev"),
            "release": getattr(settings, "git_sha", None),
        },
    )

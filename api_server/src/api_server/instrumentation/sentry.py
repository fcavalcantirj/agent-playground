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

    2026-05-12 extension: also drop events whose scope tag
    ``ap_error_code`` is in the user-error bucket
    (``UNAUTHORIZED``, ``INVALID_API_KEY``, ``USER_ERROR``,
    ``INVALID_REQUEST``, ``TIER_LIMIT_EXCEEDED``,
    ``INSUFFICIENT_BALANCE``, ``CHANNEL_NOT_CONFIGURED``,
    ``CHANNEL_INPUTS_INVALID``, ``IDEMPOTENCY_BODY_MISMATCH``,
    ``INVALID_PACK_ID``, ``STRIPE_WEBHOOK_INVALID``,
    ``RATE_LIMITED``, ``PAYLOAD_TOO_LARGE``,
    ``CONCURRENT_POLL_LIMIT``, ``AGENT_NOT_FOUND``,
    ``AGENT_NOT_RUNNING``, ``AGENT_ALREADY_RUNNING``,
    ``RECIPE_NOT_FOUND``, ``SCHEMA_NOT_FOUND``).
    These are 4xx-class business errors that may also be captured by
    explicit ``capture_with_scope`` calls inside except blocks for
    redaction tracing — but their Sentry value is near-zero and the
    auth-bucket DDoS scenario (T-31-02) would otherwise blow the
    5K/month Free-tier quota.
    """
    exc_info = hint.get("exc_info")
    if exc_info is not None:
        _exc_type, exc_value, _tb = exc_info
        if isinstance(exc_value, StarletteHTTPException) and exc_value.status_code < 500:
            return None
    tags = (event.get("tags") or {})
    if tags.get("ap_error_code") in _USER_ERROR_CODES:
        return None
    return event


# Codes that are user mistakes / 4xx-class business errors. When a route
# emits one of these (typically via _err(...)) the scope tag is set so
# _before_send can drop the event. We never want auth chaff or invalid-
# input replay to consume Sentry quota.
_USER_ERROR_CODES = frozenset({
    "UNAUTHORIZED",
    "INVALID_API_KEY",          # llm_proxy BYOK rejection
    "USER_ERROR",               # generic category from a few routes
    "INVALID_REQUEST",
    "RECIPE_NOT_FOUND",
    "SCHEMA_NOT_FOUND",
    "PAYLOAD_TOO_LARGE",
    "RATE_LIMITED",
    "IDEMPOTENCY_BODY_MISMATCH",
    "AGENT_NOT_FOUND",
    "AGENT_NOT_RUNNING",
    "AGENT_ALREADY_RUNNING",
    "CHANNEL_NOT_CONFIGURED",
    "CHANNEL_INPUTS_INVALID",
    "CONCURRENT_POLL_LIMIT",
    "INSUFFICIENT_BALANCE",
    "TIER_LIMIT_EXCEEDED",
    "INVALID_PACK_ID",
    "STRIPE_WEBHOOK_INVALID",
})


def capture_with_scope(
    exc: BaseException,
    *,
    endpoint: str,
    code: str | None = None,
    recipe: str | None = None,
    channel: str | None = None,
    agent_id: Any = None,
    run_id: str | None = None,
    user_id: Any = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Capture ``exc`` to Sentry with route-filterable tags.

    No-op when Sentry DSN is unset (``sentry_sdk.capture_exception``
    silently drops events for an uninitialized client). Safe to call
    from any except handler that returns a structured 5xx response.

    The ``code`` tag (``ap_error_code``) drives _before_send filtering.
    Pass the same ErrorCode the response carries — the filter drops
    user-error codes so we don't burn quota on auth chaff or 422s.
    """
    # 2026-05-12 — sentry-sdk 2.x deprecated push_scope in favor of new_scope;
    # both yield a Scope context, but new_scope is the forward-compatible path.
    with sentry_sdk.new_scope() as scope:
        _apply_scope(
            scope,
            endpoint=endpoint,
            code=code,
            recipe=recipe,
            channel=channel,
            agent_id=agent_id,
            run_id=run_id,
            user_id=user_id,
            extra=extra,
        )
        sentry_sdk.capture_exception(exc)


def capture_message_with_scope(
    message: str,
    *,
    level: str = "warning",
    endpoint: str,
    code: str | None = None,
    recipe: str | None = None,
    channel: str | None = None,
    agent_id: Any = None,
    run_id: str | None = None,
    user_id: Any = None,
    model: str | None = None,
    classified: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Capture a free-text Sentry event when there is no exception to attach.

    Used for "business" failures that complete normally on the wire but
    represent a real product problem we want to see (e.g. a smoke run
    returns ``verdict=FAIL`` because the upstream provider 401-ed). These
    don't raise, so ``capture_with_scope`` can't reach them.

    ``classified`` is a stable family tag (``upstream_auth_missing``,
    ``upstream_credit_low``, ``unclassified``, …) so the dashboard can
    group these events at a glance.
    """
    with sentry_sdk.new_scope() as scope:
        _apply_scope(
            scope,
            endpoint=endpoint,
            code=code,
            recipe=recipe,
            channel=channel,
            agent_id=agent_id,
            run_id=run_id,
            user_id=user_id,
            extra=extra,
        )
        if model:
            scope.set_tag("model", model)
        if classified:
            scope.set_tag("classified", classified)
        sentry_sdk.capture_message(message, level=level)


def _apply_scope(
    scope: Any,
    *,
    endpoint: str,
    code: str | None,
    recipe: str | None,
    channel: str | None,
    agent_id: Any,
    run_id: str | None,
    user_id: Any,
    extra: dict[str, Any] | None,
) -> None:
    scope.set_tag("endpoint", endpoint)
    if code:
        scope.set_tag("ap_error_code", code)
    if recipe:
        scope.set_tag("recipe", recipe)
    if channel:
        scope.set_tag("channel", channel)
    if agent_id is not None:
        scope.set_tag("agent_id", str(agent_id))
    if user_id is not None:
        scope.set_tag("user_id", str(user_id))
    if run_id:
        scope.set_extra("run_id", run_id)
    if extra:
        for k, v in extra.items():
            scope.set_extra(k, v)


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

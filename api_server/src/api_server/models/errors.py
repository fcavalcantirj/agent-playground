"""Stripe-shape error envelope + shared error codes.

Every 4xx/5xx response emitted by any route under ``api_server.routes``
MUST return a body matching ``ErrorEnvelope``. This gives clients a single
predictable shape — never a raw FastAPI ``{"detail": "..."}`` leak.

Shape mirrors Stripe's error object:

.. code-block:: json

    {"error": {
        "type": "not_found",
        "code": "RECIPE_NOT_FOUND",
        "category": null,
        "message": "recipe 'bogus' not found",
        "param": "name",
        "request_id": "01HX..."
    }}

``request_id`` is pulled from the ``asgi-correlation-id`` contextvar that
``CorrelationIdMiddleware`` sets at request entry (Plan 19-06).
"""
from __future__ import annotations

from typing import Any

from asgi_correlation_id import correlation_id
from pydantic import BaseModel


class ErrorCode:
    """Shared error code string constants.

    Referenced by routes across Plans 19-03/04/05 to avoid stringly-typed
    copy-paste drift. The ``_CODE_TO_TYPE`` map below translates codes into
    the coarse ``type`` field Stripe uses.
    """

    INVALID_REQUEST = "INVALID_REQUEST"
    RECIPE_NOT_FOUND = "RECIPE_NOT_FOUND"
    SCHEMA_NOT_FOUND = "SCHEMA_NOT_FOUND"
    LINT_FAIL = "LINT_FAIL"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    RATE_LIMITED = "RATE_LIMITED"
    IDEMPOTENCY_BODY_MISMATCH = "IDEMPOTENCY_BODY_MISMATCH"
    UNAUTHORIZED = "UNAUTHORIZED"
    INTERNAL = "INTERNAL"
    RUNNER_TIMEOUT = "RUNNER_TIMEOUT"
    INFRA_UNAVAILABLE = "INFRA_UNAVAILABLE"
    # Phase 22-05: persistent-mode agent lifecycle error codes.
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    AGENT_NOT_RUNNING = "AGENT_NOT_RUNNING"
    AGENT_ALREADY_RUNNING = "AGENT_ALREADY_RUNNING"
    CHANNEL_NOT_CONFIGURED = "CHANNEL_NOT_CONFIGURED"
    CHANNEL_INPUTS_INVALID = "CHANNEL_INPUTS_INVALID"


_CODE_TO_TYPE = {
    ErrorCode.INVALID_REQUEST: "invalid_request",
    ErrorCode.RECIPE_NOT_FOUND: "not_found",
    ErrorCode.SCHEMA_NOT_FOUND: "not_found",
    ErrorCode.LINT_FAIL: "lint_error",
    ErrorCode.PAYLOAD_TOO_LARGE: "invalid_request",
    ErrorCode.RATE_LIMITED: "rate_limit_error",
    ErrorCode.IDEMPOTENCY_BODY_MISMATCH: "invalid_request",
    ErrorCode.UNAUTHORIZED: "unauthorized",
    ErrorCode.INTERNAL: "internal_error",
    ErrorCode.RUNNER_TIMEOUT: "runner_error",
    ErrorCode.INFRA_UNAVAILABLE: "infra_error",
    # Phase 22-05 additions. "conflict" is a new type used for 409s on the
    # persistent-mode endpoints (double-start, stop-when-not-running). No
    # collision with the existing surface — only used by these codes today.
    ErrorCode.AGENT_NOT_FOUND: "not_found",
    ErrorCode.AGENT_NOT_RUNNING: "conflict",
    ErrorCode.AGENT_ALREADY_RUNNING: "conflict",
    ErrorCode.CHANNEL_NOT_CONFIGURED: "invalid_request",
    ErrorCode.CHANNEL_INPUTS_INVALID: "invalid_request",
}


class ErrorBody(BaseModel):
    type: str
    code: str
    category: str | None = None
    message: str
    param: str | None = None
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class LintError(BaseModel):
    """Single lint error — a path + human-readable message.

    ``path`` is the dotted JSON-pointer-ish path emitted by
    ``run_recipe.lint_recipe`` (e.g. ``"runtime.provider"``), or
    ``"(root)"`` / ``"(yaml)"`` when the error is not field-scoped.
    """

    path: str
    message: str


class LintResponse(BaseModel):
    """Response body for ``POST /v1/lint``.

    Always 200 — ``valid=False`` is a lint verdict, not an HTTP failure.
    The HTTP failure cases are limited to 413 (oversize body) and 500
    (unexpected internal error), which use the ``ErrorEnvelope`` shape.
    """

    valid: bool
    errors: list[LintError]


def make_error_envelope(
    code: str,
    message: str,
    *,
    param: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Build a fully-populated error envelope dict ready for JSONResponse.

    Pulls ``request_id`` from the ``asgi-correlation-id`` contextvar.
    When no id is set (e.g. synthetic call outside a request), falls back
    to the literal ``"unknown"`` so the field stays non-empty.
    """
    req_id = correlation_id.get() or "unknown"
    return ErrorEnvelope(
        error=ErrorBody(
            type=_CODE_TO_TYPE.get(code, "internal_error"),
            code=code,
            category=category,
            message=message,
            param=param,
            request_id=req_id,
        )
    ).model_dump()

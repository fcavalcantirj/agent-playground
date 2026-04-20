"""Request-level auth helpers — Phase 22c.

Exports ``require_user`` which returns either a ``JSONResponse`` (401 when
no session) or a ``UUID`` (the authenticated user). Matches the codebase
convention of inline ``_err()``-style early-return (see
``routes/agent_events.py::_err``) rather than FastAPI ``Depends`` +
``HTTPException`` which would double-wrap the Stripe-shape envelope and
diverge from every existing 4xx/5xx emitter in ``routes/*.py``
(D-22c-AUTH-03, RESEARCH §Anti-Patterns).

Usage in a route::

    from ..auth.deps import require_user

    @router.get("/users/me")
    async def get_me(request: Request):
        result = require_user(request)
        if isinstance(result, JSONResponse):
            return result
        user_id: UUID = result
        ...

Protected routes (list per CONTEXT.md §D-22c-AUTH-03): /v1/runs,
/v1/agents, /v1/agents/:id/*, /v1/users/me, /v1/auth/logout. Public
routes skip this helper entirely.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse

from ..models.errors import ErrorCode, make_error_envelope


def require_user(request: Request) -> JSONResponse | UUID:
    """Resolve ``request.state.user_id`` or return a 401 ``JSONResponse``.

    ``SessionMiddleware`` (plan 22c-04) populates ``scope['state']['user_id']``
    with a ``UUID`` (valid session) or ``None`` (no/invalid/expired/revoked
    session). FastAPI promotes scope['state'] values onto ``request.state``
    as attributes, so ``request.state.user_id`` is the idiomatic read.

    Return shape — inline, never raising — mirrors every ``_err()`` site in
    ``routes/runs.py``, ``routes/agent_events.py``, ``routes/agent_lifecycle.py``
    so the Stripe-shape envelope stays byte-identical across the surface.
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        return JSONResponse(
            status_code=401,
            content=make_error_envelope(
                ErrorCode.UNAUTHORIZED,
                "Authentication required",
                param="ap_session",
            ),
        )
    if isinstance(user_id, UUID):
        return user_id
    # SessionMiddleware should always set UUID or None; defensive coerce.
    try:
        return UUID(str(user_id))
    except (ValueError, AttributeError):
        return JSONResponse(
            status_code=401,
            content=make_error_envelope(
                ErrorCode.UNAUTHORIZED,
                "Authentication required",
                param="ap_session",
            ),
        )


__all__ = ["require_user"]

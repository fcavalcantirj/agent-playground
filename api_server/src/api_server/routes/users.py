"""User-scoped routes (Phase 22c).

Surface::

    GET /v1/users/me — return the session-authenticated user's row

Auth posture: protected by ``require_user`` (D-22c-AUTH-03 inline
early-return). No cookie or an expired/revoked session returns a
401 Stripe-shape envelope before the DB is touched.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth.deps import require_user
from ..models.errors import ErrorCode, make_error_envelope
from ..models.users import SessionUserResponse

router = APIRouter()


@router.get("/users/me", response_model=SessionUserResponse)
async def get_me(request: Request):
    """Return the currently-authenticated user's row.

    Flow:

    1. ``require_user`` resolves ``request.state.user_id`` → 401 inline
       JSONResponse if absent (no cookie, expired, revoked, or malformed).
    2. SELECT users WHERE id = $1 — fully-parameterized; no SQL injection
       surface.
    3. If the session row points at a user that was later deleted (rare —
       would require the ``users`` row to be cascaded-deleted by some
       future admin flow), treat as 401 rather than leaking the deletion
       state.
    4. Project the asyncpg Record into the Pydantic response model. The
       model's ``from_attributes=True`` config lets us pass ``**dict(row)``
       and get field-by-name coercion (including ``email=None``,
       ``avatar_url=None`` for OAuth providers that don't return them).
    """
    result = require_user(request)
    if isinstance(result, JSONResponse):
        return result
    user_id = result

    pool = request.app.state.db
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, display_name, avatar_url, provider, created_at "
            "FROM users WHERE id = $1",
            user_id,
        )
    if row is None:
        # Session pointed at a deleted user — rare, treat as 401.
        return JSONResponse(
            status_code=401,
            content=make_error_envelope(
                ErrorCode.UNAUTHORIZED,
                "User not found",
                param="ap_session",
            ),
        )
    return SessionUserResponse(**dict(row))

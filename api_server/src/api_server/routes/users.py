"""User-scoped routes (Phase 22c).

Surface::

    GET    /v1/users/me — return the session-authenticated user's row
    DELETE /v1/users/me — delete the user's account + all data (5.1.1(v))

Auth posture: protected by ``require_user`` (D-22c-AUTH-03 inline
early-return). No cookie or an expired/revoked session returns a
401 Stripe-shape envelope before the DB is touched.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from ..auth.deps import require_user
from ..models.errors import ErrorCode, make_error_envelope
from ..models.users import SessionUserResponse

router = APIRouter()

_SESSION_COOKIE = "ap_session"


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


@router.delete("/users/me", status_code=204)
async def delete_me(request: Request):
    """Delete the authenticated user's account and all owned data.

    App Store Guideline 5.1.1(v) — apps that enable account creation
    must offer in-app account deletion. Play Store has the same
    requirement (2024 policy update).

    Cleanup posture (all in one transaction):

      * **Explicit DELETE** for tables whose FK to ``users`` lacks
        ``ON DELETE CASCADE`` — ``agent_containers``, ``agent_instances``,
        ``idempotency_keys``. Without these, the final ``DELETE FROM
        users`` would error on FK violation.
      * **FK CASCADE** handles: ``sessions``, ``inapp_messages``,
        ``usage_logs``, ``credit_ledger``, plus any other ``ondelete=
        "CASCADE"`` references.
      * **FK SET NULL** handles ``auth_events_revoked`` — we keep the
        audit row but anonymize the user pointer.

    Caveat: any running Docker containers for this user's agents become
    orphans. They are killed by the idle-reaper at its next sweep; a
    synchronous container-stop sweep is deferred to a future phase.

    Returns 204 No Content + clears the ``ap_session`` cookie so the
    client falls back to the login flow on its next request.
    """
    settings = request.app.state.settings
    result = require_user(request)
    if isinstance(result, JSONResponse):
        return result
    user_id = result

    pool = request.app.state.db
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Tables without ON DELETE CASCADE on user_id — clear them
            # before the final DELETE FROM users.
            await conn.execute(
                "DELETE FROM agent_containers WHERE user_id = $1", user_id,
            )
            await conn.execute(
                "DELETE FROM agent_instances WHERE user_id = $1", user_id,
            )
            await conn.execute(
                "DELETE FROM idempotency_keys WHERE user_id = $1", user_id,
            )
            await conn.execute(
                "DELETE FROM users WHERE id = $1", user_id,
            )

    resp = Response(status_code=204)
    resp.set_cookie(
        key=_SESSION_COOKIE,
        value="",
        max_age=0,
        httponly=True,
        samesite="lax",
        secure=(settings.env == "prod"),
        path="/",
    )
    return resp

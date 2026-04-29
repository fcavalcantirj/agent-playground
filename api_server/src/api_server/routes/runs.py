"""POST /v1/runs + GET /v1/runs/{id} — the load-bearing endpoints.

Implements CONTEXT.md D-07 flow verbatim:

    1. Parse ``Authorization: Bearer <key>`` → ``provider_key`` (memory only)
    2. Validate ``body.recipe_name`` against ``app.state.recipes``
    3. Resolve ``user_id`` via ``require_user`` (plan 22c-05 / 22c-06) —
       authenticated session cookie ``ap_session`` is mandatory
    4. Upsert ``agent_instances(user_id, recipe_name, model)``
    5. Mint ULID ``run_id``, insert ``runs`` row (verdict=NULL)
    6. RELEASE DB connection (Pitfall 4)
    7. Acquire per-tag Lock + Semaphore → ``to_thread(run_cell)``
    8. Re-acquire DB connection; ``write_verdict(run_id, details)``
    9. Return RunResponse

BYOK invariants enforced here (data side; log side is Plan 19-06):

- ``provider_key`` is a LOCAL variable in the route handler — never stored
  in ``app.state``, never passed to logger functions, never included in a
  DB query parameter, never echoed in a response body.
- On runner exceptions, the exception string is redacted via
  ``str.replace(provider_key, "<REDACTED>")`` before landing in any
  log line or ``runs.detail`` column — closes the gap where a runner
  crash message might contain the raw key.

Pitfall 4 (DB connection release across ``to_thread``): each DB
interaction uses its own ``async with pool.acquire() as conn:`` scope.
The long ``await execute_run(...)`` sits OUTSIDE any acquire scope so the
pool isn't starved while the runner is spinning for 10-200s.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from ..auth.deps import require_user
from ..models.errors import ErrorCode, make_error_envelope
from ..models.runs import RunGetResponse, RunRequest, RunResponse
from ..services.personality import is_known as personality_is_known
from ..services.personality import smoke_prompt_for
from ..services.run_store import (
    fetch_run,
    insert_pending_run,
    upsert_agent_instance,
    write_verdict,
)
from ..services.runner_bridge import execute_run
from ..util.ulid import is_valid_ulid, new_run_id

router = APIRouter()

# Module-scoped logger — never receives the provider key. The access-log
# middleware (Plan 19-06) separately drops the Authorization header; this
# logger is for explicit operational signals only.
_log = logging.getLogger("api_server.runs")


def _err(
    status: int,
    code: str,
    message: str,
    *,
    param: str | None = None,
    category: str | None = None,
) -> JSONResponse:
    """Build a JSONResponse with a Stripe-shape error envelope.

    Separated from the inline call-site so all 4xx/5xx paths share the
    exact status + envelope construction and can't drift.
    """
    return JSONResponse(
        status_code=status,
        content=make_error_envelope(
            code, message, param=param, category=category
        ),
    )


@router.post("/runs")
async def create_run(
    request: Request,
    body: RunRequest,
    authorization: str = Header(default=""),
):
    """``POST /v1/runs`` — execute a recipe + persist the run.

    The Pydantic ``RunRequest`` model runs BEFORE this handler fires —
    so by the time we're inside the function body, ``body.recipe_name``
    already matches ``^[a-z0-9][a-z0-9_-]*$`` (SQL-injection defense)
    and no extra fields are present (inline-YAML injection defense).
    """
    # --- Step 1a: Session cookie → user_id (Phase 22c require_user gate) ---
    # Runs BEFORE the Bearer parse so an unauthenticated caller gets the
    # single canonical 401 (UNAUTHORIZED / ap_session) rather than a
    # Bearer-shape 401 that would mislead on-boarding.
    session_result = require_user(request)
    if isinstance(session_result, JSONResponse):
        return session_result
    user_id: UUID = session_result

    # --- Step 1b: Authorization header → provider_key (memory only) ---
    if not authorization.startswith("Bearer "):
        return _err(
            401,
            ErrorCode.UNAUTHORIZED,
            "Bearer token required",
            param="Authorization",
        )
    provider_key = authorization[len("Bearer "):].strip()
    if not provider_key:
        return _err(
            401,
            ErrorCode.UNAUTHORIZED,
            "Bearer token is empty",
            param="Authorization",
        )

    # --- Step 2: recipe_name must be a known recipe ---
    recipes = request.app.state.recipes
    recipe = recipes.get(body.recipe_name)
    if recipe is None:
        return _err(
            404,
            ErrorCode.RECIPE_NOT_FOUND,
            f"recipe {body.recipe_name!r} not found",
            param="recipe_name",
        )

    # --- Step 5 prep: recipe must advertise an api_key env var ---
    # This lives with the recipe schema (runtime.process_env.api_key); if
    # a committed recipe is missing it, that's an INTERNAL error — not a
    # 400, because the client can't fix it.
    api_key_var = (
        recipe.get("runtime", {})
        .get("process_env", {})
        .get("api_key")
    )
    if not api_key_var:
        return _err(
            500,
            ErrorCode.INTERNAL,
            "recipe missing runtime.process_env.api_key",
        )

    # --- Step 5b: validate personality preset if supplied ---
    if body.personality is not None and not personality_is_known(body.personality):
        return _err(
            422,
            ErrorCode.INVALID_REQUEST,
            f"unknown personality preset {body.personality!r}",
            param="personality",
        )

    # --- Step 6 prep: resolve smoke prompt ---
    # Precedence: explicit body.prompt (legacy / power-user) >
    #             personality preset's smoke prompt >
    #             recipe.smoke.prompt > empty.
    # The personality-derived prompt deliberately overrides recipe defaults
    # so the agent's persona is actually exercised during the deploy smoke.
    prompt = (
        body.prompt
        or smoke_prompt_for(body.personality)
        or recipe.get("smoke", {}).get("prompt")
        or ""
    )
    run_id = new_run_id()

    # Default agent name when caller didn't supply one (back-compat with
    # legacy callers + smoke-tests that just want to run a recipe).
    agent_name = body.agent_name or f"{body.recipe_name}-{body.model.replace('/', '-')}"

    # Phase 22c.1: when a personality preset overrode the recipe's smoke
    # prompt (priority chain above), the recipe's name-eliciting
    # ``response_contains_name`` contract no longer holds — the personality
    # prompt isn't designed to force the recipe name into the reply, and
    # most recipes don't bake user-supplied agent_name into their identity
    # yet (that's Phase 22c.2). Loosen the smoke check to "did the bot
    # actually reply?" by overriding pass_if to ``replied_ok`` for these
    # runs. The recipe's verified_cells + its own smoke.prompt path is
    # untouched.
    if body.personality and recipe.get("smoke", {}).get("pass_if") == "response_contains_name":
        recipe = {**recipe, "smoke": {**recipe["smoke"], "pass_if": "replied_ok"}}

    # --- Step 3 + 4 + 5: upsert agent_instance + insert pending run ---
    # Scope 1 of 2 on the DB pool: opens + closes inside this with block
    # so the connection is released BEFORE the long ``to_thread`` await
    # below (Pitfall 4 — DB pool exhaustion if conn held across the run).
    pool = request.app.state.db
    async with pool.acquire() as conn:
        agent_instance_id = await upsert_agent_instance(
            conn,
            user_id,
            body.recipe_name,
            body.model,
            agent_name,
            body.personality,
        )
        await insert_pending_run(conn, run_id, agent_instance_id, prompt)

    # --- Step 7: execute_run (per-tag Lock + global Semaphore + to_thread) ---
    # No DB connection held here. The per-tag lock + semaphore gate
    # concurrency (Pattern 2 from RESEARCH.md).
    try:
        details = await execute_run(
            request.app.state,
            recipe,
            prompt=prompt,
            model=body.model,
            api_key_var=api_key_var,
            api_key_val=provider_key,
            agent_name=body.agent_name,
        )
    except Exception as e:  # pragma: no cover - runner failure path
        # Redact the key from the exception string BEFORE it lands in
        # either the runs.detail column or the log line. Defense in depth
        # over Plan 19-06's log-middleware redaction.
        redacted = str(e).replace(provider_key, "<REDACTED>")
        _log.error("runner failure", extra={"run_id": run_id})
        async with pool.acquire() as conn:
            await write_verdict(conn, run_id, {
                "verdict": "FAIL",
                "category": "INFRA_FAIL",
                "detail": redacted[:500],
                "exit_code": -1,
                "wall_time_s": None,
                "filtered_payload": None,
                "stderr_tail": None,
            })
        return _err(
            502,
            ErrorCode.INFRA_UNAVAILABLE,
            "runner failed to execute",
            category="INFRA_FAIL",
        )

    # --- Step 8: persist verdict (DB scope 2) ---
    async with pool.acquire() as conn:
        await write_verdict(conn, run_id, details)

    # --- Step 9: return RunResponse ---
    now = datetime.now(timezone.utc)
    return RunResponse(
        run_id=run_id,
        agent_instance_id=str(agent_instance_id),
        recipe=details.get("recipe") or body.recipe_name,
        model=details.get("model") or body.model,
        prompt=details.get("prompt") or prompt,
        pass_if=details.get("pass_if"),
        verdict=details["verdict"],
        category=details["category"],
        detail=details.get("detail"),
        exit_code=details.get("exit_code"),
        wall_time_s=details.get("wall_time_s"),
        filtered_payload=details.get("filtered_payload"),
        stderr_tail=details.get("stderr_tail"),
        created_at=now,
        completed_at=now,
    ).model_dump(mode="json")


@router.get("/runs/{run_id}")
async def get_run(request: Request, run_id: str):
    """``GET /v1/runs/{id}`` — fetch a persisted run by ULID.

    ULID validation happens BEFORE the DB round-trip so a malformed id
    can't cost a Postgres query. The 404 path also runs a parameterized
    query (not string concat) so even if the ULID validator is ever
    relaxed, the query layer stays safe.
    """
    if not is_valid_ulid(run_id):
        return _err(
            400,
            ErrorCode.INVALID_REQUEST,
            "run_id must be a 26-character Crockford base32 ULID",
            param="run_id",
        )
    pool = request.app.state.db
    async with pool.acquire() as conn:
        row = await fetch_run(conn, run_id)
    if row is None:
        return _err(
            404,
            ErrorCode.RECIPE_NOT_FOUND,
            f"run {run_id!r} not found",
            param="run_id",
        )
    return RunGetResponse(**row).model_dump(mode="json")

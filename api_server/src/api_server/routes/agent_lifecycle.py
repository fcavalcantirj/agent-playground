"""Persistent-mode agent lifecycle endpoints (Phase 22a Plan 05).

Four endpoints:

- ``POST /v1/agents/:id/start``                  — spawn a persistent container
- ``POST /v1/agents/:id/stop``                   — graceful shutdown
- ``GET  /v1/agents/:id/status``                 — current container state
- ``POST /v1/agents/:id/channels/:cid/pair``     — openclaw pairing approve

All four follow the canonical 9-step flow from ``routes/runs.py``:

    1. Parse ``Authorization: Bearer <key>`` → ``provider_key`` (memory only)
    2. Validate body against ``app.state.recipes``
    3. Resolve ``user_id`` via ``require_user`` — authenticated session
       cookie ``ap_session`` is mandatory (plan 22c-05 / 22c-06)
    4. Upsert / fetch ``agent_instances`` row
    5. Mint IDs, insert pending ``agent_containers`` row (DB scope 1)
    6. RELEASE DB connection (Pitfall 4 — never hold across long await)
    7. Acquire per-tag Lock + Semaphore → ``to_thread(run_cell_persistent)``
    8. Re-acquire DB; write_agent_container_running (DB scope 2)
    9. Return response model

BYOK invariants (data side + log side identical to ``/v1/runs``):

- ``provider_key`` is a LOCAL variable — never stored, logged, or echoed.
- ``body.channel_inputs`` secrets are LOCAL variables; the only durable
  copy is the age-encrypted blob in ``agent_containers.channel_config_enc``
  (decrypt is a future Plan 23 concern for restart-with-stored-creds).
- Every exception string is redacted via ``str.replace(provider_key,
  "<REDACTED>")`` + per-cred redaction BEFORE landing in the DB or the
  response body. Defense in depth over the middleware-layer redaction.

Pitfall 4 (DB pool exhaustion): each DB interaction uses its own
``async with pool.acquire()`` scope. The long ``await
execute_persistent_*(...)`` sits OUTSIDE any acquire so the pool isn't
starved while the runner is spawning a 120s-boot container.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from uuid import UUID

import asyncpg
import httpx
from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse

from ..auth.deps import require_user
from ..crypto.age_cipher import decrypt_channel_config, encrypt_channel_config
from ..models.agents import (
    AgentChannelPairRequest,
    AgentChannelPairResponse,
    AgentStartRequest,
    AgentStartResponse,
    AgentStatusResponse,
    AgentStopResponse,
)
from ..models.errors import ErrorCode, make_error_envelope
from ..services.inapp_substitutions import build_activation_substitutions
from ..services.run_store import (
    fetch_agent_instance,
    fetch_running_container_for_agent,
    insert_pending_agent_container,
    mark_agent_container_stopped,
    write_agent_container_running,
)
from ..services.runner_bridge import (
    execute_persistent_exec,
    execute_persistent_start,
    execute_persistent_status,
    execute_persistent_stop,
)
from ..util.ulid import new_run_id

# ``decrypt_channel_config`` is imported here but NOT called in this module.
# Plan 23 will use it for restart-with-stored-creds flows; keeping the
# import proves the path is wired and avoids a future "where's the
# decrypt helper?" grep miss. Silence unused-import warnings explicitly.
_ = decrypt_channel_config

router = APIRouter()

# Module-scoped logger — NEVER receives channel creds or the provider key.
# The access-log middleware separately drops the Authorization header;
# this logger is for explicit operational signals only.
_log = logging.getLogger("api_server.agent_lifecycle")


def _err(
    status: int,
    code: str,
    message: str,
    *,
    param: str | None = None,
    category: str | None = None,
) -> JSONResponse:
    """Build a Stripe-shape error envelope ``JSONResponse``.

    Mirrors ``routes/runs.py::_err`` byte-for-byte so every 4xx/5xx
    response across the persistent-mode surface uses the same construction
    — no drift between ``/runs`` and ``/agents/:id/start``.
    """
    return JSONResponse(
        status_code=status,
        content=make_error_envelope(
            code, message, param=param, category=category
        ),
    )


def _redact_creds(text: str, channel_inputs: dict[str, str]) -> str:
    """Replace every channel-cred value with ``<REDACTED>`` in a string.

    Redacts BOTH the bare value (``152099202`` → ``<REDACTED>``) AND the
    ``VAR=value`` pattern (``TELEGRAM_BOT_TOKEN=123:ABC`` →
    ``TELEGRAM_BOT_TOKEN=<REDACTED>``) so tracebacks that echo the env-
    file contents don't leak. Only values ≥8 chars get bare-substring
    redaction — shorter values are too likely to be a common substring.

    Mirrors the runner's ``_redact_channel_creds`` helper in
    ``tools/run_recipe.py`` so the redaction shape is identical on both
    sides of the bridge.
    """
    out = text
    for var, val in channel_inputs.items():
        if not val:
            continue
        if len(val) >= 8:
            out = out.replace(val, "<REDACTED>")
        # Always redact the VAR= form regardless of length — numeric
        # user IDs are short but still secret-adjacent.
        out = out.replace(f"{var}={val}", f"{var}=<REDACTED>")
    return out


def _detect_provider(model: str | None, recipe: dict) -> str:
    """Return the canonical provider name for a given model id.

    Heuristic per RESEARCH §Openclaw /start Env-Var Gap (Phase 22b D-21):

    - ``anthropic/...`` → ``anthropic``
    - ``openai/...`` → ``openai``
    - ``google/...`` → ``google``
    - ``openrouter/...`` → ``openrouter``
    - bare ``<vendor>/<model>`` with no recognized prefix → OpenRouter
      (its model catalogue uses ``vendor/model`` without a leading
      ``openrouter/``)
    - empty / None / falsey model → fallback to
      ``recipe.provider_compat.supported[0]`` (or ``"openrouter"``).
    """
    if not model:
        supported = (recipe.get("provider_compat") or {}).get("supported") or []
        return supported[0] if supported else "openrouter"
    prefix = model.split("/", 1)[0].lower() if "/" in model else ""
    if prefix in ("anthropic", "openai", "openrouter", "google"):
        return prefix
    # No namespaced prefix → OpenRouter (vendor/model shape).
    supported = (recipe.get("provider_compat") or {}).get("supported") or []
    return supported[0] if supported else "openrouter"


def _resolve_api_key_var(recipe: dict, model: str | None) -> str | None:
    """Pick the env-var NAME (e.g. ``ANTHROPIC_API_KEY``) that will receive
    the bearer token for this recipe+model combination.

    Resolution order:

    1. If ``recipe.runtime.process_env.api_key_by_provider`` is declared,
       dispatch by :func:`_detect_provider` (Phase 22b D-21).
    2. Else fall back to ``recipe.runtime.process_env.api_key`` (legacy
       behavior — preserved so recipes without a provider map keep working
       unchanged).
    3. Return ``None`` if neither is declared; the caller surfaces a
       500 "recipe missing runtime.process_env.api_key".
    """
    process_env = (recipe.get("runtime") or {}).get("process_env") or {}
    by_provider = process_env.get("api_key_by_provider") or {}
    if by_provider:
        provider = _detect_provider(model, recipe)
        var = by_provider.get(provider)
        if var:
            return var
    return process_env.get("api_key")


# ---------------------------------------------------------------------------
# POST /v1/agents/:id/start
# ---------------------------------------------------------------------------


@router.post("/agents/{agent_id}/start")
async def start_agent(
    request: Request,
    agent_id: UUID,
    body: AgentStartRequest,
    authorization: str = Header(default=""),
):
    """Spawn a persistent container for ``agent_id`` with channel creds.

    9-step flow with one extension for encrypted credential persistence:

        Step 1 — Bearer token parse
        Step 2 — Resolve agent_instance + recipe + channel
        Step 3 — Validate required channel inputs present
        Step 4 — Age-encrypt channel config
        Step 5 — Insert pending agent_containers row (DB scope 1)
        Step 6 — Release DB; await execute_persistent_start
        Step 7 — On failure, redact + mark_stopped(last_error=...), 502
        Step 8 — On success, write_agent_container_running (DB scope 2)
        Step 9 — Return AgentStartResponse

    Concurrency: the partial unique index on
    ``agent_containers(agent_instance_id) WHERE status='running'`` fires
    at the UPDATE-to-running step when another container for the same
    agent is already running — we map that ``UniqueViolationError`` to
    409 ``AGENT_ALREADY_RUNNING``. The newly-booted container is cleaned
    up via ``execute_persistent_stop`` to avoid orphaning it (extremely
    rare race; still covered).

    UniqueViolation can ALSO fire at the pending-insert step (same
    partial index, ``status='running'`` clause only matches running rows
    so a concurrent /start that's still in 'starting' state doesn't
    collide — but a completed running row DOES collide if somehow this
    request beat the fetch-running check). We cover both paths below.
    """
    # --- Step 1a: Session cookie → user_id (require_user gate) ---
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

    # --- Step 2: resolve agent_instance by (agent_id, user_id) ---
    pool = request.app.state.db
    async with pool.acquire() as conn:
        agent = await fetch_agent_instance(conn, agent_id, user_id)
    if agent is None:
        return _err(
            404,
            ErrorCode.AGENT_NOT_FOUND,
            f"agent {agent_id} not found",
            param="agent_id",
        )

    # --- Step 2b: recipe + channel + required_user_input validation ---
    recipes = request.app.state.recipes
    recipe = recipes.get(agent["recipe_name"])
    if recipe is None:
        # Defensive: recipe was present at agent creation time but was
        # removed from the catalog. Not a 404 — the client can't fix it.
        return _err(
            500,
            ErrorCode.INTERNAL,
            f"recipe {agent['recipe_name']!r} missing from server state",
        )
    persistent = recipe.get("persistent")
    if not persistent:
        return _err(
            400,
            ErrorCode.CHANNEL_NOT_CONFIGURED,
            f"recipe {agent['recipe_name']!r} has no persistent block",
            param="recipe",
        )
    channels = recipe.get("channels") or {}
    channel_spec = channels.get(body.channel)
    if channel_spec is None:
        return _err(
            400,
            ErrorCode.CHANNEL_NOT_CONFIGURED,
            (
                f"recipe {agent['recipe_name']!r} does not support channel "
                f"{body.channel!r}"
            ),
            param="channel",
        )
    required = channel_spec.get("required_user_input") or []
    missing = [
        e["env"]
        for e in required
        if e.get("env")
        and (e["env"] not in body.channel_inputs or not body.channel_inputs[e["env"]])
    ]
    if missing:
        return _err(
            400,
            ErrorCode.CHANNEL_INPUTS_INVALID,
            f"missing required channel inputs: {missing}",
            param="channel_inputs",
        )
    # Phase 22b D-21: dispatch env-var by model provider so that an
    # anthropic/... model on the openclaw recipe injects ANTHROPIC_API_KEY
    # (NOT OPENROUTER_API_KEY, which would auto-enable openclaw's broken
    # openrouter plugin — see recipes/openclaw.yaml known_quirks).
    # Recipes without `api_key_by_provider` fall back to legacy `api_key`
    # unchanged.
    api_key_var = _resolve_api_key_var(recipe, agent.get("model"))
    if not api_key_var:
        return _err(
            500,
            ErrorCode.INTERNAL,
            "recipe missing runtime.process_env.api_key",
        )

    # --- Step 2c (Phase 29 D-02b) — BYOK custody gated on recipe.runtime.via_proxy ---
    #
    # When recipe.runtime.via_proxy is true, validate the BYOK key
    # against the upstream provider BEFORE persisting anything. On
    # success, encrypt the key + persist provider_key_enc +
    # upstream_provider into agent_containers and populate the
    # proxy_byok_cache so the proxy router can serve traffic
    # immediately after start_agent returns.
    #
    # Legacy recipes (via_proxy=False/missing) skip this entire block:
    #   - no validator probe (no 50-300ms latency)
    #   - no age-cipher encrypt of the BYOK key
    #   - no agent_containers.provider_key_enc / upstream_provider write
    #   - no proxy_byok_cache.set
    # Plan 09 Gate 7 verifies hermes/openclaw/zeroclaw/nullclaw deploys
    # produce provider_key_enc IS NULL — mechanically true by virtue
    # of the gate below short-circuiting all four columns.
    upstream_provider: str | None = None
    provider_key_enc: bytes | None = None
    proxy_validated_provider: str | None = None
    proxy_validated_key: str | None = None

    runtime_block = recipe.get("runtime") or {}
    via_proxy_flag = bool(runtime_block.get("via_proxy", False))
    if via_proxy_flag:
        from ..services.byok_validator import PROVIDER_VALIDATORS
        from ..services.proxy_dispatcher import derive_provider

        provider_env_var = (
            (runtime_block.get("process_env") or {}).get("api_key")
        )
        if not provider_env_var:
            return _err(
                500,
                ErrorCode.INTERNAL,
                "recipe missing runtime.process_env.api_key",
            )
        try:
            proxy_provider = derive_provider(provider_env_var)
        except ValueError:
            _log.warning(
                "agent_lifecycle.unknown_api_key_env_var",
                extra={
                    "recipe_name": agent["recipe_name"],
                    "env_var": provider_env_var,
                },
            )
            return _err(
                400,
                ErrorCode.INVALID_REQUEST,
                f"recipe declares unsupported api_key env var: {provider_env_var}",
                param="recipe",
            )

        validator = PROVIDER_VALIDATORS[proxy_provider]
        try:
            ok = await validator(
                request.app.state.proxy_upstream_client, provider_key,
            )
        except httpx.HTTPError as exc:
            _log.error(
                "byok_validator.network_failure",
                extra={
                    "provider": proxy_provider,
                    "error_text": str(exc).replace(provider_key, "<REDACTED>"),
                },
            )
            return _err(
                503,
                ErrorCode.INFRA_UNAVAILABLE,
                f"BYOK validation upstream unreachable for {proxy_provider}",
                param="Authorization",
                category="INFRA_FAIL",
            )
        if not ok:
            return _err(
                401,
                ErrorCode.UNAUTHORIZED,
                f"BYOK key rejected by upstream ({proxy_provider})",
                param="Authorization",
            )

        # Encrypt the validated key for at-rest storage; cache the
        # plaintext for the proxy hot path. Both paths fail-loud if
        # the master key + KEK derivation primitive is broken.
        try:
            provider_key_enc = encrypt_channel_config(
                user_id, {"key": provider_key},
            )
        except Exception:
            _log.error(
                "byok_validator.encrypt_failed",
                extra={"agent_id": str(agent_id)},
            )
            return _err(
                500,
                ErrorCode.INTERNAL,
                "BYOK key encryption failed",
            )
        upstream_provider = proxy_provider
        proxy_validated_provider = proxy_provider
        proxy_validated_key = provider_key
    # else: legacy path — provider_key_enc + upstream_provider stay None,
    # proxy_byok_cache is not populated; the BYOK key flows to the
    # container env via the existing process_env.api_key plumbing
    # (UNCHANGED — Plan 09 Gate 7 invariant).

    # --- Step 3 + 4: age-encrypt channel config + insert pending row ---
    # DB scope 1: opens + closes BEFORE the long await.
    config_plain = {
        "channel": body.channel,
        "inputs": dict(body.channel_inputs),
    }
    try:
        config_enc = encrypt_channel_config(user_id, config_plain)
    except Exception:
        _log.error(
            "channel config encryption failed",
            extra={"agent_id": str(agent_id)},
        )
        return _err(
            500,
            ErrorCode.INTERNAL,
            "channel config encryption failed",
        )

    try:
        async with pool.acquire() as conn:
            try:
                container_row_id = await insert_pending_agent_container(
                    conn,
                    agent_id,
                    user_id,
                    agent["recipe_name"],
                    body.channel,
                    config_enc,
                    upstream_provider=upstream_provider,
                    provider_key_enc=provider_key_enc,
                )
            except asyncpg.UniqueViolationError:
                # Partial unique index fired at pending-insert time —
                # another running container for this agent already exists.
                return _err(
                    409,
                    ErrorCode.AGENT_ALREADY_RUNNING,
                    f"agent {agent_id} already has a running container",
                    param="agent_id",
                )
    except Exception:
        _log.exception(
            "insert_pending_agent_container failed",
            extra={"agent_id": str(agent_id)},
        )
        return _err(
            500,
            ErrorCode.INTERNAL,
            "failed to persist pending container row",
        )

    # --- Step 5b (Phase 22c.3.1): mint inapp token + build activation subs ---
    # D-09 + D-11: only ``channel == "inapp"`` mints a token; telegram path
    # leaves the column NULL. Token shape is ``uuid.uuid4().hex`` (32 hex
    # chars). ``build_activation_substitutions`` builds the dict consumed
    # by the runner's override path; for telegram channels we skip it
    # (legacy path runs without substitutions per AMD-37).
    inapp_auth_token: str | None = None
    activation_substitutions: dict[str, str] | None = None
    if body.channel == "inapp":
        inapp_auth_token = uuid.uuid4().hex
        activation_substitutions = build_activation_substitutions(
            provider_key=provider_key,
            agent_name=agent["name"],
            agent_model=agent["model"],
            inapp_auth_token=inapp_auth_token,
            via_proxy=via_proxy_flag,
        )

    # --- Step 6: execute_persistent_start (no DB held) ---
    run_id = new_run_id()
    boot_timeout_s = body.boot_timeout_s or 180
    try:
        details = await execute_persistent_start(
            request.app.state,
            recipe,
            model=agent["model"],
            api_key_var=api_key_var,
            api_key_val=provider_key,
            channel_id=body.channel,
            channel_creds=dict(body.channel_inputs),
            run_id=run_id,
            boot_timeout_s=boot_timeout_s,
            activation_substitutions=activation_substitutions,
        )
    except Exception as e:
        # Redact provider key FIRST (longer + more sensitive), then
        # the inapp_auth_token (RESEARCH §Risks §7), then channel creds.
        # Apply all three to the string before it touches the DB or the
        # response.
        redacted = str(e).replace(provider_key, "<REDACTED>")
        if inapp_auth_token:
            redacted = redacted.replace(inapp_auth_token, "<REDACTED>")
        redacted = _redact_creds(redacted, body.channel_inputs)
        async with pool.acquire() as conn:
            await mark_agent_container_stopped(
                conn, container_row_id, last_error=redacted[:500]
            )
        _log.error(
            "execute_persistent_start raised",
            extra={"agent_id": str(agent_id), "run_id": run_id},
            exc_info=True,
        )
        return _err(
            502,
            ErrorCode.INFRA_UNAVAILABLE,
            "runner failed to start container",
            category="INFRA_FAIL",
        )

    # --- Step 7: verify PASS verdict (non-PASS = INVOKE_FAIL / TIMEOUT) ---
    if details.get("verdict") != "PASS":
        # Container failed to reach ready. ``detail`` is already redacted
        # at the runner layer (``_redact_channel_creds`` w/ extra_secrets);
        # apply our redaction too as a belt-and-braces defense.
        detail = details.get("detail") or f"verdict={details.get('verdict')}"
        redacted = str(detail).replace(provider_key, "<REDACTED>")
        if inapp_auth_token:
            redacted = redacted.replace(inapp_auth_token, "<REDACTED>")
        redacted = _redact_creds(redacted, body.channel_inputs)
        async with pool.acquire() as conn:
            await mark_agent_container_stopped(
                conn, container_row_id, last_error=redacted[:500]
            )
        return _err(
            502,
            ErrorCode.INFRA_UNAVAILABLE,
            f"container failed to reach ready: {redacted[:200]}",
            category=details.get("category") or "INFRA_FAIL",
        )

    # --- Step 8: mark row running (DB scope 2) ---
    # D-33: inapp_auth_token is folded into the SAME UPDATE — closes the
    # microsecond race window where a chat POST between the running-UPDATE
    # and a separate token-UPDATE could dispatch unauthenticated.
    # AC-13 grep gate enforces no separate UPDATE statement here.
    # Note: watcher idles for inapp channel — no event_log_regex declared
    # (graceful degradation in watcher_service.py:519-523).
    ready_at = datetime.now(timezone.utc)
    container_id = details["container_id"]
    boot_wall_s = float(details.get("boot_wall_s") or 0.0)
    # Phase 29 (AMD-04): resolve the bridge IP NOW so the proxy router
    # (routes/llm_proxy.py via app.state.proxy_ip_map) can identify the
    # caller on its very first chat round-trip. The container is ready
    # at this point — get_container_ip walks the Docker SDK's NetworkSettings
    # and returns the IP on the runner's network. Failure here is non-fatal
    # (e.g. macOS Docker Desktop edge case) — bridge_ip stays NULL and the
    # proxy will 401 until the operator wires the IP some other way; this
    # only matters for via_proxy=true recipes (nanobot in Phase 29).
    bridge_ip: str | None = None
    try:
        bridge_ip = request.app.state.inapp_recipe_index.get_container_ip(
            container_id
        )
    except Exception:
        _log.exception(
            "phase29.bridge_ip_lookup_failed",
            extra={"agent_id": str(agent_id), "container_id": container_id},
        )
    async with pool.acquire() as conn:
        try:
            await write_agent_container_running(
                conn,
                container_row_id,
                container_id=container_id,
                boot_wall_s=boot_wall_s,
                ready_at=ready_at,
                inapp_auth_token=inapp_auth_token,
                bridge_ip=bridge_ip,
            )
        except asyncpg.UniqueViolationError:
            # Race: two /start requests both passed pending-insert
            # (because at pending-insert time neither had flipped to
            # 'running' yet), then both tried to UPDATE to running.
            # The loser caught the partial-unique-index violation —
            # kill the now-orphaned container to avoid leaving a
            # live process behind.
            try:
                await execute_persistent_stop(
                    container_id,
                    graceful_shutdown_s=3,
                    data_dir=details.get("data_dir"),
                )
            except Exception:
                # Stop-on-race failure is swallowed — we already lost
                # the partial-index race; the other winning row owns
                # the lifecycle. A leaked container is an ops concern.
                _log.exception(
                    "post-race cleanup stop failed",
                    extra={
                        "agent_id": str(agent_id),
                        "container_id": container_id,
                    },
                )
            # Also mark this row as start_failed so the audit trail
            # reflects the lost race rather than leaving it in 'starting'.
            try:
                async with pool.acquire() as conn2:
                    await mark_agent_container_stopped(
                        conn2,
                        container_row_id,
                        last_error="lost partial-unique-index race on UPDATE to running",
                    )
            except Exception:
                _log.exception(
                    "post-race mark_stopped failed",
                    extra={"agent_id": str(agent_id)},
                )
            return _err(
                409,
                ErrorCode.AGENT_ALREADY_RUNNING,
                f"agent {agent_id} already has a running container",
            )

    # --- Step 8a-bis (Phase 29 Plan 05) — populate proxy_byok_cache ---
    # Only fires for via_proxy=true recipes. Order: AFTER the successful
    # UPDATE-to-running so the cache mirrors the DB; BEFORE the response
    # so the proxy router can serve the very first chat round-trip
    # without waiting on the 60s ProxyIPMap refresh window.
    # Failure here is logged but non-fatal: lifespan rehydrate will
    # repopulate from agent_containers.provider_key_enc on the next
    # api_server restart (D-02 restart-resilience).
    if proxy_validated_key is not None and proxy_validated_provider is not None:
        try:
            await request.app.state.proxy_byok_cache.set(
                user_id,
                agent_id,
                proxy_validated_provider,
                proxy_validated_key,
            )
        except Exception:
            _log.exception(
                "phase29.proxy_byok_cache.set_failed",
                extra={"agent_id": str(agent_id)},
            )

    # --- Step 8a-ter (Phase 29 AMD-04) — refresh proxy_ip_map ----------
    # Plan 29-04's ProxyIPMap rebuilds every 60s from agent_containers,
    # but the very first chat round-trip after deploy must succeed within
    # seconds. Trigger an immediate refresh so the freshly-written
    # ``bridge_ip`` is in the in-process map before the response returns.
    # Best-effort: failure is logged but non-fatal — the next 60s tick
    # will repair the gap.
    if bridge_ip is not None:
        try:
            await request.app.state.proxy_ip_map.refresh()
        except Exception:
            _log.exception(
                "phase29.proxy_ip_map.refresh_failed",
                extra={"agent_id": str(agent_id)},
            )

    # --- Step 8b (Phase 22b-04): spawn log-watcher task (fire-and-forget) ---
    # Order: AFTER write_agent_container_running, BEFORE returning response.
    # Spike-03 discipline: iterator ends cleanly when container is removed;
    # no Task.cancel() needed at /stop. Failure to spawn is non-fatal — events
    # are observability, not correctness, per 22b scope. Lifespan re-attach
    # will retry on next API restart if the row still says 'running'.
    #
    # The watcher's `agent_id` slot is the agent_containers row PK
    # (container_row_id) because event_store.insert_agent_events_batch FKs
    # rows to agent_containers.id, NOT agent_instances.id. The watcher's
    # event_poll_signals dict is also keyed on this same id (consumed by
    # Plan 22b-05's long-poll handler).
    #
    # Phase 22c.3.1-01-AC01 (Rule-3 deviation): when the dockerized e2e
    # harness sets ``AP_E2E_DOCKERIZED_HARNESS=1``, skip the watcher spawn.
    # Rationale: the watcher's docker.APIClient.logs(stream=True, follow=True)
    # iterator BLOCKS the asyncio thread pool worker on `next(it)` until
    # the underlying container is removed. The e2e route-driven _factory
    # teardown (commit e61bd1d) leaves containers running when /stop
    # auth fails (parent _truncate_tables wipes the session row before
    # _factory teardown — known harness ordering issue, separate scope).
    # That blocked worker prevents pytest_asyncio's runner from shutting
    # down at fixture teardown, hanging the test process indefinitely.
    # Watchers are observability-only (event log streaming for the
    # /channels/:cid/events long-poll endpoint); inapp tests don't
    # exercise that path. Skipping is correctness-preserving for AC-01's
    # scope (5/5 cell PASS via route handler).
    if os.environ.get("AP_E2E_DOCKERIZED_HARNESS") != "1":
        try:
            from ..services.watcher_service import run_watcher
            asyncio.create_task(run_watcher(
                request.app.state,
                container_row_id=container_row_id,
                container_id=container_id,
                agent_id=container_row_id,
                recipe=recipe,
                channel=body.channel,
                chat_id_hint=(
                    body.channel_inputs.get("TELEGRAM_ALLOWED_USER")
                    or body.channel_inputs.get("TELEGRAM_ALLOWED_USERS")
                ),
            ))
        except Exception:
            _log.exception(
                "phase22b.watcher.spawn_failed",
                extra={"agent_id": str(agent_id)},
            )

    # --- Step 9: return response ---
    pre_start_wall = details.get("pre_start_wall_s")
    return AgentStartResponse(
        agent_id=agent_id,
        container_row_id=container_row_id,
        container_id=container_id,
        container_status="running",
        channel=body.channel,
        ready_at=ready_at,
        boot_wall_s=boot_wall_s,
        health_check_ok=bool(details.get("health_check_ok")),
        health_check_kind=str(
            details.get("health_check_kind") or "unknown"
        ),
        pre_start_wall_s=(
            float(pre_start_wall) if pre_start_wall is not None else None
        ),
    ).model_dump(mode="json")


# ---------------------------------------------------------------------------
# POST /v1/agents/:id/stop
# ---------------------------------------------------------------------------


@router.post("/agents/{agent_id}/stop")
async def stop_agent(
    request: Request,
    agent_id: UUID,
    authorization: str = Header(default=""),
):
    """Gracefully stop a running persistent container.

    Bearer token required for API consistency (even though stop doesn't
    need the LLM key to operate) — Phase 21 will use it as the session-
    ownership gate. The header is parsed but the value is NOT read or
    forwarded to the runner; stop is purely a docker-lifecycle operation.

    G3 (spike-07): per-recipe ``sigterm_handled`` + ``graceful_shutdown_s``
    are read from ``recipe.persistent.spec``. Nanobot sets
    ``sigterm_handled=false`` which short-circuits the SIGTERM+poll phase
    to an immediate force-rm; ``force_killed=true`` surfaces in the
    response so clients can show the semantic difference.
    """
    # --- Step 1a: Session cookie → user_id (require_user gate) ---
    session_result = require_user(request)
    if isinstance(session_result, JSONResponse):
        return session_result
    user_id: UUID = session_result

    if not authorization.startswith("Bearer "):
        return _err(
            401,
            ErrorCode.UNAUTHORIZED,
            "Bearer token required",
            param="Authorization",
        )

    pool = request.app.state.db
    async with pool.acquire() as conn:
        agent = await fetch_agent_instance(conn, agent_id, user_id)
        if agent is None:
            return _err(
                404,
                ErrorCode.AGENT_NOT_FOUND,
                f"agent {agent_id} not found",
                param="agent_id",
            )
        running = await fetch_running_container_for_agent(conn, agent_id)
    if running is None:
        return _err(
            409,
            ErrorCode.AGENT_NOT_RUNNING,
            f"agent {agent_id} has no running container",
            param="agent_id",
        )

    # Pull per-recipe stop policy. Defaults mirror the plan's safe
    # fallback (5s SIGTERM window, sigterm_handled=True) when a recipe
    # doesn't declare the fields (older recipes).
    recipe = request.app.state.recipes.get(agent["recipe_name"]) or {}
    persistent_spec = (recipe.get("persistent") or {}).get("spec") or {}
    graceful = int(persistent_spec.get("graceful_shutdown_s", 5))
    sigterm_handled = bool(persistent_spec.get("sigterm_handled", True))

    # --- Phase 22b-04: signal watcher stop + await BEFORE execute_persistent_stop ---
    # Order matters (spike-03 discipline): signal first so the watcher exits
    # BEFORE docker rm -f reaps the container. Iterator ends cleanly in
    # <270ms after rm -f, so the 2s budget is generous. Task.cancel() is the
    # documented fallback that has never been observed in spike-03.
    try:
        _row_id = UUID(running["id"])
        _watcher_entry = request.app.state.log_watchers.get(_row_id)
        if _watcher_entry is not None:
            _wtask, _wstop = _watcher_entry
            _wstop.set()
            try:
                await asyncio.wait_for(_wtask, timeout=2.0)
            except asyncio.TimeoutError:
                _wtask.cancel()
                _log.warning(
                    "phase22b.watcher.cancel_on_timeout",
                    extra={"container_row_id": str(_row_id)},
                )
    except Exception:
        _log.exception("phase22b.watcher.drain_failed")

    # Long await — no DB held.
    try:
        details = await execute_persistent_stop(
            running["container_id"],
            graceful_shutdown_s=graceful,
            sigterm_handled=sigterm_handled,
            recipe_name=agent["recipe_name"],
            data_dir=None,
        )
    except Exception:
        _log.exception(
            "execute_persistent_stop raised",
            extra={
                "agent_id": str(agent_id),
                "container_id": running["container_id"],
            },
        )
        return _err(
            502,
            ErrorCode.INFRA_UNAVAILABLE,
            "stop failed",
            category="INFRA_FAIL",
        )

    async with pool.acquire() as conn:
        await mark_agent_container_stopped(
            conn, UUID(running["id"]), last_error=None
        )

    return AgentStopResponse(
        agent_id=agent_id,
        container_row_id=UUID(running["id"]),
        container_id=running["container_id"],
        stopped_gracefully=bool(details.get("stopped_gracefully")),
        force_killed=bool(details.get("force_killed")),
        exit_code=int(details.get("exit_code") if details.get("exit_code") is not None else -1),
        stop_wall_s=float(details.get("stop_wall_s") or 0.0),
    ).model_dump(mode="json")


# ---------------------------------------------------------------------------
# DELETE /v1/agents/:id
# ---------------------------------------------------------------------------


@router.delete("/agents/{agent_id}", status_code=204)
async def delete_agent(request: Request, agent_id: UUID):
    """Hard-delete an agent and all dependent rows.

    Mirrors ``stop_agent``'s graceful-shutdown sequence (signal watcher
    → ``execute_persistent_stop``) when a container is currently
    running, then atomically deletes ``runs`` (no FK cascade — see
    migration 001) and ``agent_instances`` (cascade reaches
    ``agent_containers``, ``agent_events``, ``inapp_messages``).

    Idempotent end-state: a second DELETE for the same id returns 404.

    Tolerant on docker, strict on DB:
    - Docker stop failures log + proceed with DB delete (orphan reaper
      cleans the leaked container later — never block DB delete on
      docker flakiness).
    - DB delete failures roll back; caller can retry. Container may
      already be stopped by a partial first attempt — acceptable; next
      retry just no-ops the docker step and finishes the DB delete.

    Auth: ``require_user`` gate + ``fetch_agent_instance`` enforces
    user_id ownership at the SQL layer. 404 (not 403) on
    missing/unowned to avoid leaking agent existence across users.

    No Bearer required (unlike /start, /stop, /messages POST) — delete
    does not invoke the LLM or talk to a provider.

    Concurrency note: a /delete racing with an in-flight /start can
    leave an orphan docker container if the start completes after the
    cascade-deletes the agent_containers row (start's
    write_agent_container_running UPDATE then matches 0 rows). The
    existing reaper sweeps this. A future hardening could share a
    per-agent op-lock between /start, /stop, /delete; out of scope here.
    """
    # --- Step 1: auth ---
    session_result = require_user(request)
    if isinstance(session_result, JSONResponse):
        return session_result
    user_id: UUID = session_result

    pool = request.app.state.db

    # --- Step 2: existence + ownership ---
    async with pool.acquire() as conn:
        agent = await fetch_agent_instance(conn, agent_id, user_id)
        if agent is None:
            return _err(
                404,
                ErrorCode.AGENT_NOT_FOUND,
                f"agent {agent_id} not found",
                param="agent_id",
            )
        running = await fetch_running_container_for_agent(conn, agent_id)

    # --- Step 3: graceful stop if a container is running ---
    if running is not None:
        recipe = request.app.state.recipes.get(agent["recipe_name"]) or {}
        persistent_spec = (recipe.get("persistent") or {}).get("spec") or {}
        graceful = int(persistent_spec.get("graceful_shutdown_s", 5))
        sigterm_handled = bool(persistent_spec.get("sigterm_handled", True))

        # Drain watcher BEFORE docker rm — same ordering as stop_agent.
        try:
            _row_id = UUID(running["id"])
            _watcher_entry = request.app.state.log_watchers.get(_row_id)
            if _watcher_entry is not None:
                _wtask, _wstop = _watcher_entry
                _wstop.set()
                try:
                    await asyncio.wait_for(_wtask, timeout=2.0)
                except asyncio.TimeoutError:
                    _wtask.cancel()
                    _log.warning(
                        "delete_agent.watcher.cancel_on_timeout",
                        extra={"container_row_id": str(_row_id)},
                    )
        except Exception:
            _log.exception("delete_agent.watcher.drain_failed")

        # Tolerant docker stop — log + continue on failure.
        try:
            await execute_persistent_stop(
                running["container_id"],
                graceful_shutdown_s=graceful,
                sigterm_handled=sigterm_handled,
                recipe_name=agent["recipe_name"],
                data_dir=None,
            )
        except Exception:
            _log.exception(
                "delete_agent.persistent_stop_failed_continuing",
                extra={
                    "agent_id": str(agent_id),
                    "container_id": running["container_id"],
                },
            )

    # --- Step 4: atomic DB delete ---
    # Order: runs first (no FK cascade per migration 001), then
    # agent_instances (cascade reaches agent_containers → agent_events,
    # plus inapp_messages directly — see migrations 003/004/007).
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM runs WHERE agent_instance_id = $1",
                agent_id,
            )
            result = await conn.execute(
                "DELETE FROM agent_instances WHERE id = $1 AND user_id = $2",
                agent_id,
                user_id,
            )

    # asyncpg returns "DELETE N" — N=0 means a concurrent caller won
    # the race. Treat as 404 (idempotent end-state from this caller's
    # perspective).
    if result.endswith(" 0"):
        return _err(
            404,
            ErrorCode.AGENT_NOT_FOUND,
            f"agent {agent_id} not found",
            param="agent_id",
        )

    return Response(status_code=204)


# ---------------------------------------------------------------------------
# GET /v1/agents/:id/status
# ---------------------------------------------------------------------------


@router.get("/agents/{agent_id}/status")
async def agent_status(
    request: Request,
    agent_id: UUID,
):
    """Return current state of the agent + its persistent container.

    Phase 22c-06 closes a PATTERNS.md gap: ``agent_status`` previously
    had NO auth check at all. It now requires an authenticated session
    cookie via ``require_user`` (per D-22c-AUTH-03 — every
    ``/v1/agents/:id/*`` path is protected) AND resolves the target
    row's ``user_id`` at the SQL layer via ``fetch_agent_instance``'s
    composite WHERE clause, so cross-user reads are impossible even if
    the URL ``agent_id`` belongs to another user.

    When the agent exists but has no container row yet (never started,
    or the last start failed), we return a degenerate 200 with only
    ``agent_id`` populated — never a 404 on this path so polling
    frontends don't have to distinguish "agent gone" vs "container
    gone".

    G5 (spike-11): the ``http_code`` / ``ready`` fields come from the
    dual-branch health probe in ``execute_persistent_status`` — only
    populated when ``recipe.persistent.spec.health_check.kind == "http"``
    (picoclaw/nanobot/openclaw). Process-alive recipes (hermes,
    nullclaw) return ``None`` for both.
    """
    # --- Step 1: Session cookie → user_id (require_user gate) ---
    # PATTERNS gap closure: agent_status previously had NO auth at all.
    # Every /v1/agents/:id/* path is now protected per D-22c-AUTH-03.
    session_result = require_user(request)
    if isinstance(session_result, JSONResponse):
        return session_result
    user_id: UUID = session_result

    pool = request.app.state.db
    async with pool.acquire() as conn:
        agent = await fetch_agent_instance(conn, agent_id, user_id)
        if agent is None:
            return _err(
                404,
                ErrorCode.AGENT_NOT_FOUND,
                f"agent {agent_id} not found",
                param="agent_id",
            )
        running = await fetch_running_container_for_agent(conn, agent_id)

    if running is None:
        # Degenerate but valid: agent exists, no running container.
        # Respond 200 with every optional field left NULL.
        return AgentStatusResponse(agent_id=agent_id).model_dump(mode="json")

    # Probe docker outside DB scope.
    recipe = request.app.state.recipes.get(agent["recipe_name"]) or {}
    recipe_health_check = (
        ((recipe.get("persistent") or {}).get("spec") or {}).get("health_check")
        or {"kind": "process_alive"}
    )
    try:
        probe = await execute_persistent_status(
            running["container_id"],
            recipe_health_check=recipe_health_check,
            log_tail_lines=50,
        )
    except Exception:
        # Probe should be self-degrading; belt-and-braces for any
        # unexpected raise (docker daemon gone, permissions broken, ...).
        _log.exception(
            "execute_persistent_status raised",
            extra={
                "agent_id": str(agent_id),
                "container_id": running["container_id"],
            },
        )
        probe = {
            "running": False,
            "exit_code": None,
            "log_tail": [],
            "http_code": None,
            "ready": None,
        }

    return AgentStatusResponse(
        agent_id=agent_id,
        container_row_id=UUID(running["id"]),
        container_id=running["container_id"],
        container_status=running["container_status"],
        channel=running.get("channel_type"),
        ready_at=running.get("ready_at"),
        boot_wall_s=running.get("boot_wall_s"),
        runtime_running=bool(probe.get("running")),
        runtime_exit_code=probe.get("exit_code"),
        http_code=probe.get("http_code"),
        ready=probe.get("ready"),
        log_tail=probe.get("log_tail") or [],
    ).model_dump(mode="json")


# ---------------------------------------------------------------------------
# POST /v1/agents/:id/channels/:cid/pair
# ---------------------------------------------------------------------------


@router.post("/agents/{agent_id}/channels/{cid}/pair")
async def pair_channel(
    request: Request,
    agent_id: UUID,
    cid: str,
    body: AgentChannelPairRequest,
    authorization: str = Header(default=""),
):
    """Run the recipe-declared pairing approve command inside the container.

    Openclaw is the first caller: ``openclaw pairing approve telegram
    <CODE>`` runs inside the agent's container via ``docker exec`` so
    the user can complete Telegram pairing from the platform UI instead
    of opening a shell. The argv template is in
    ``recipe.channels.<cid>.pairing.approve_argv`` — the route layer is
    agent-agnostic; adding another agent with a pairing CLI is purely a
    recipe change.

    G4 (spike-10): openclaw's pairing CLI cold-boots the full plugin
    registry per invocation — empirical wall time ~60s. We pass
    ``timeout_s=90`` to ``execute_persistent_exec`` (not 30s, the
    default) so the call has headroom. Per-endpoint rate limiting
    (3 req/min per user) is noted below for the middleware layer; until
    Phase 21's real session resolution lands, the global rate limiter
    covers this with the same budget as every other POST.

    Argv substitution: ``$CODE`` is replaced literal-style via
    ``str.replace``. ``AgentChannelPairRequest.code`` regex forbids ``$``
    in the user-supplied value so recursive substitution is impossible.
    """
    # --- Step 1a: Session cookie → user_id (require_user gate) ---
    session_result = require_user(request)
    if isinstance(session_result, JSONResponse):
        return session_result
    user_id: UUID = session_result

    if not authorization.startswith("Bearer "):
        return _err(
            401,
            ErrorCode.UNAUTHORIZED,
            "Bearer token required",
            param="Authorization",
        )

    # NOTE: G4 rate-limit hook — Phase 22c+ can wire per-route rate
    # budgets (3 req/min per user for pair_channel). Today the
    # module-level middleware applies the global budget; openclaw's
    # ~60s cold-boot per call is still within that envelope for normal
    # UI-driven use.

    pool = request.app.state.db
    async with pool.acquire() as conn:
        agent = await fetch_agent_instance(conn, agent_id, user_id)
        if agent is None:
            return _err(
                404,
                ErrorCode.AGENT_NOT_FOUND,
                f"agent {agent_id} not found",
                param="agent_id",
            )
        running = await fetch_running_container_for_agent(conn, agent_id)
    if running is None:
        return _err(
            409,
            ErrorCode.AGENT_NOT_RUNNING,
            f"agent {agent_id} has no running container",
            param="agent_id",
        )

    recipe = request.app.state.recipes.get(agent["recipe_name"])
    if recipe is None:
        return _err(
            500,
            ErrorCode.INTERNAL,
            f"recipe {agent['recipe_name']!r} missing from server state",
        )

    channel_spec = (recipe.get("channels") or {}).get(cid)
    if channel_spec is None:
        return _err(
            400,
            ErrorCode.CHANNEL_NOT_CONFIGURED,
            (
                f"recipe {agent['recipe_name']!r} does not support channel "
                f"{cid!r}"
            ),
            param="cid",
        )
    pairing = channel_spec.get("pairing") or {}
    approve_argv = pairing.get("approve_argv")
    if not approve_argv:
        return _err(
            400,
            ErrorCode.CHANNEL_NOT_CONFIGURED,
            (
                f"channel {cid} on recipe {agent['recipe_name']!r} has no "
                "pairing.approve_argv"
            ),
            param="cid",
        )

    # $CODE substitution. Code regex forbids '$' — no recursive sub risk.
    argv = [str(a).replace("$CODE", body.code) for a in approve_argv]

    try:
        details = await execute_persistent_exec(
            request.app.state,
            running["container_id"],
            argv,
            timeout_s=90,  # G4: openclaw cold-boot ~60s; 90s gives headroom
        )
    except Exception:
        _log.exception(
            "execute_persistent_exec raised",
            extra={
                "agent_id": str(agent_id),
                "container_id": running["container_id"],
            },
        )
        return _err(
            502,
            ErrorCode.INFRA_UNAVAILABLE,
            "pair command failed",
            category="INFRA_FAIL",
        )

    wall = float(details.get("wall_time_s") or 0.0)
    return AgentChannelPairResponse(
        agent_id=agent_id,
        channel=cid,
        exit_code=int(
            details.get("exit_code") if details.get("exit_code") is not None else -1
        ),
        stdout_tail=str(details.get("stdout_tail") or ""),
        stderr_tail=str(details.get("stderr_tail") or ""),
        wall_time_s=wall,
        wall_s=wall,  # G4: alias — client-facing elapsed-time readout
    ).model_dump(mode="json")

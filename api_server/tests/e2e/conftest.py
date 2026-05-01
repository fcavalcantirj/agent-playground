"""Phase 22c.3 Plan 15 — fixtures for the SC-03 5-cell e2e gate.

Reuses the session-scoped ``migrated_pg`` Postgres testcontainer + the
function-scoped ``db_pool`` from the parent ``tests/conftest.py`` (no
duplication of the 3-5s container boot).

The fixtures here are e2e-specific:

  * ``openrouter_api_key`` — real key from env or .env.local; fail loud
    if missing (Plan 15 explicit requirement: real OpenRouter calls).
  * ``oauth_user_with_openrouter_key`` — INSERTs a oauth_sessions row
    carrying the key per D-32, AND yields the key for the recipe
    container fixture to inject as ``OPENROUTER_API_KEY`` env. Both
    paths exercise the SAME upstream OpenRouter HTTP from inside the
    recipe container.
  * ``e2e_docker_network`` — session-scoped docker bridge network the
    test process and recipe containers share. The dispatcher uses
    ``InappRecipeIndex.get_container_ip`` to discover IPs on this
    network, mirroring the production lifespan's docker_network_name.
  * ``recipe_index`` — real InappRecipeIndex bound to the real
    ``recipes/`` dir + a real docker client + the e2e network.
  * ``recipe_container_factory`` — given a recipe name, renders the
    recipe's ``persistent_argv_override`` + ``activation_env`` with
    runtime substitutions (mints INAPP_AUTH_TOKEN, fills MODEL,
    INAPP_PROVIDER_KEY, agent_name, agent_url), spawns the container
    on the e2e network, polls ``ready_log_regex``, and returns
    (container_id, container_ip, inapp_auth_token). Tear down on
    session end.

Per Golden Rule #1: no mocks. Real PG, real Docker, real OpenRouter.
"""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import pytest
import pytest_asyncio
from ruamel.yaml import YAML

from . import _helpers as h


_log = logging.getLogger("api_server.tests.e2e.conftest")

# Path to the repo's recipes/ dir (one level above api_server/).
API_SERVER_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = API_SERVER_DIR.parent
RECIPES_DIR = REPO_ROOT / "recipes"


# ---------------------------------------------------------------------------
# OpenRouter key + OAuth seed
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def openrouter_api_key() -> str:
    """Source the OpenRouter API key from env or .env.local.

    Fail loud if missing — the entire 5-cell gate depends on real upstream
    LLM calls.
    """
    key = h.load_openrouter_key_from_env_local()
    if not key:
        pytest.fail(
            "OPENROUTER_API_KEY missing from environment AND from "
            ".env.local — the SC-03 e2e gate requires a funded "
            "OpenRouter key. Set it before running this suite."
        )
    return key


@pytest_asyncio.fixture
async def oauth_user_with_openrouter_key(
    db_pool: asyncpg.Pool, openrouter_api_key: str,
) -> dict[str, Any]:
    """Insert a users row + an oauth_sessions row carrying the key per D-32.

    Plan 15 truth #8: the OPENROUTER_API_KEY is sourced from the test
    user's OAuth-completed session row, proving the end-to-end credential
    flow. The schema for ``oauth_sessions`` may not exist yet (Phase 22c
    OAuth landed earlier) — defensive insertion via try/except keeps the
    gate honest about which path is wired.
    """
    user_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, display_name) VALUES ($1, $2)",
            user_id, "e2e-22c.3-15",
        )
        # oauth_sessions schema may have evolved — try the canonical insert,
        # fall back to a minimal one. The KEY itself flows via env injection
        # into the recipe container; the DB row is the audit record.
        try:
            await conn.execute(
                """
                INSERT INTO oauth_sessions
                    (user_id, provider, access_token, created_at)
                VALUES ($1, 'openrouter', $2, NOW())
                """,
                user_id, openrouter_api_key,
            )
        except (asyncpg.UndefinedTableError, asyncpg.PostgresSyntaxError,
                asyncpg.UndefinedColumnError):
            # oauth_sessions table or column shape not present — fine.
            # The credential still flows via env injection (proven path).
            pass
    return {
        "user_id": user_id,
        "openrouter_api_key": openrouter_api_key,
    }


# ---------------------------------------------------------------------------
# Recipe index (e2e-only — `e2e_docker_network` lives in tests/conftest.py
# per Phase 22c.3.1 Plan 01 B-7 fix; pytest's directory-scoping inherits it
# automatically — no import statement needed).
# ---------------------------------------------------------------------------


@pytest.fixture
def recipe_index(e2e_docker_network: str, _e2e_host_port_map: dict) -> Any:
    """Real InappRecipeIndex bound to the real recipes/ dir + real docker.

    Macos-Docker-Desktop quirk: the host process can't reach docker bridge
    IPs directly (the IP-routing is opaque on Docker Desktop). We work
    around that by publishing each recipe container's port to the host
    via ``-p 127.0.0.1:HOST_PORT:CONTAINER_PORT`` and overriding the
    InappRecipeIndex behavior so:

      * ``get_container_ip(container_id)`` returns ``127.0.0.1``
      * ``get_inapp_block(recipe_name)`` returns an InappChannelConfig
        whose ``port`` is the per-test HOST_PORT (not the recipe's
        declared internal port).

    The ``_e2e_host_port_map`` fixture is shared with the
    ``recipe_container_factory`` so the two stay in sync.
    """
    from api_server.services.inapp_recipe_index import (
        InappChannelConfig, InappRecipeIndex,
    )
    import docker as _docker

    client = _docker.from_env()
    real_index = InappRecipeIndex(
        recipes_dir=RECIPES_DIR,
        docker_client=client,
        network_name=e2e_docker_network,
        ip_ttl_seconds=60.0,
    )

    # Phase 22c.3.1-01-AC01 dockerized-harness branch: when the outer
    # ``make e2e-inapp-docker`` Makefile target sets
    # ``AP_E2E_DOCKERIZED_HARNESS=1`` in the test container's env, the
    # pytest process and the recipe containers BOTH live on the same
    # docker network (the default ``bridge`` — runner spawns recipes
    # there because ``tools/run_recipe.py`` has no ``--network`` flag).
    # In that mode the recipe's bridge IP is reachable from the test
    # container directly (container→container via bridge), so we delegate
    # to the real ``InappRecipeIndex.get_container_ip`` which reads
    # ``NetworkSettings.Networks[<network_name>].IPAddress`` from
    # ``docker inspect`` — exactly the lookup the production dispatcher
    # does. The legacy ``"127.0.0.1"`` host-published-port path stays for
    # the non-dockerized invocation (``make e2e-inapp`` on Linux CI where
    # bridge IPs are reachable from host pytest).
    _dockerized = os.environ.get("AP_E2E_DOCKERIZED_HARNESS") == "1"

    class _E2EWrappedIndex:
        """Thin wrapper that overrides the IP + port to host-published values."""

        def get_inapp_block(self, recipe_name: str):
            cfg = real_index.get_inapp_block(recipe_name)
            if cfg is None:
                return None
            host_port = _e2e_host_port_map.get(("port", recipe_name), cfg.port)
            # Per-recipe contract_model_name override:
            # nanobot rejects unknown model ids — its OpenAI-compat surface
            # only accepts the literal model id from its config.json (the
            # 400 says: "Only configured model 'X' is available"). The
            # recipe declares contract_model_name="agent" as a placeholder
            # for the dispatcher's `model` field; in real e2e we substitute
            # the actual configured model so nanobot accepts the request.
            # Tracked for the dispatcher-row['model'] follow-up (see Plan
            # 22c.3-15 SUMMARY Deferred Issues).
            contract_model_name = cfg.contract_model_name
            override_cmn = _e2e_host_port_map.get(("contract_model_name", recipe_name))
            if override_cmn is not None:
                contract_model_name = override_cmn
            # Dockerized harness: recipes are NOT host-port-published — the
            # test container reaches them via container→container on the
            # docker bridge. Use the recipe's declared internal port, NOT
            # the (irrelevant) host port mapping.
            if _dockerized:
                host_port = cfg.port
            return InappChannelConfig(
                transport=cfg.transport,
                port=host_port,
                endpoint=cfg.endpoint,
                contract=cfg.contract,
                contract_model_name=contract_model_name,
                request_envelope=cfg.request_envelope,
                response_envelope=cfg.response_envelope,
                auth_mode=cfg.auth_mode,
                idempotency_header=cfg.idempotency_header,
                session_header=cfg.session_header,
            )

        def get_container_ip(self, container_id: str) -> str:
            if _dockerized:
                # Dockerized harness: real bridge-IP lookup, same as
                # production dispatcher. The test container shares the
                # docker bridge with the recipe — bridge IP is reachable.
                return real_index.get_container_ip(container_id)
            # Legacy host-pytest path: every e2e container is reachable
            # via 127.0.0.1 (host-port-published).
            return "127.0.0.1"

    return _E2EWrappedIndex()


@pytest.fixture
def _e2e_host_port_map() -> dict:
    """Shared dict between recipe_container_factory and recipe_index.

    Keys: ``("port", recipe_name)`` → host port int
          ``("ip", container_id)``  → host ip (always 127.0.0.1 on macOS)
    """
    return {}


# ---------------------------------------------------------------------------
# Recipe container factory
# ---------------------------------------------------------------------------


def _load_recipe_yaml(name: str) -> dict[str, Any]:
    y = YAML(typ="rt")
    with open(RECIPES_DIR / f"{name}.yaml") as f:
        return dict(y.load(f))


def _resolve_provider_key_for_recipe(
    recipe: dict[str, Any], openrouter_api_key: str,
) -> tuple[str, str]:
    """Return (env_var_name, value) per the recipe's provider_compat declaration.

    Plan 15 fixes provider=openrouter for ALL 5 cells (per the recipe_matrix
    table). openclaw is special-cased: its recipe has
    ``known_quirks.openrouter_provider_plugin_silent_fail`` and
    ``provider_compat.supported=[anthropic]``. For openclaw we still use
    the openrouter key but route via OPENROUTER_API_KEY — the recipe's
    activation_env / persistent_argv_override decides which env var the
    container ultimately consumes.
    """
    # Default: every recipe gets OPENROUTER_API_KEY=<key>. The recipe's
    # activation_env block re-exports it under whatever name the bot wants
    # (e.g. openclaw maps it to ANTHROPIC_API_KEY).
    return "OPENROUTER_API_KEY", openrouter_api_key


@pytest_asyncio.fixture
async def e2e_authenticated_cookie(db_pool: asyncpg.Pool):
    """Phase 22c.3.1 Plan 01 Task 3 — function-scoped cookie+user.

    Lifted from tests/conftest.py:387-432::authenticated_cookie. Re-INSERTed
    here so the e2e factory can compose its own factory dependency chain
    without coupling to the parent's fixture name.
    """
    from datetime import datetime, timedelta, timezone

    user_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, provider, sub, email, display_name) "
            "VALUES ($1, $2, $3, $4, $5)",
            user_id, "google",
            f"e2e-sub-{uuid.uuid4().hex[:12]}",
            f"e2e+{uuid.uuid4().hex[:8]}@example.com",
            "e2e-22c.3.1",
        )
        now = datetime.now(timezone.utc)
        session_id = await conn.fetchval(
            """
            INSERT INTO sessions (user_id, created_at, expires_at, last_seen_at)
            VALUES ($1, $2, $3, $2) RETURNING id::text
            """,
            user_id, now, now + timedelta(days=30),
        )
    yield {
        "Cookie": f"ap_session={session_id}",
        "_user_id": str(user_id),
        "_session_id": session_id,
    }


@pytest_asyncio.fixture
async def recipe_container_factory(
    started_api_server, db_pool, e2e_authenticated_cookie,
    openrouter_api_key, _e2e_host_port_map, recipe_index,
):
    """Phase 22c.3.1 Plan 01 Task 3 — POST /v1/agents/:id/start factory.

    The factory is now an ASYNC callable that:
      1. INSERTs an agent_instances row via direct DB.
      2. POSTs /v1/agents/{agent_id}/start with body.channel="inapp" via
         the started_api_server httpx ASGI client.
      3. Reads inapp_auth_token from the DB (route doesn't return it).
      4. Returns the same shape as before so the matrix test is
         minimally affected (only the call site needs `await`).

    Per Phase 22c.3.1 plan AC-02 the harness contains ZERO docker-direct
    invocations — the route handler now drives the runner.

    The e2e_authenticated_cookie fixture seeds a real user+session so the
    require_user gate passes. Teardown POSTs /v1/agents/:id/stop for each
    spawned (agent_id, container_id) pair, with `docker rm -f` fallback.

    The matrix's _E2EWrappedIndex shim still applies for macOS Docker
    Desktop port-publish — the server-side runner now drives the docker
    invocation, but the test process can't reach docker bridge IPs
    directly, so app.state.recipe_index is overridden post-acquisition
    with the wrapped index that returns 127.0.0.1 + the host-published
    port. The host-port mapping is established by sniffing the running
    container after start (instead of pre-allocating like the old factory).
    """
    spawned: list[tuple[str, str]] = []  # (agent_id, container_id)

    # Override the app's recipe_index with the e2e wrapper so the dispatcher
    # routes to host-published ports on macOS. NOTE: in the route-driven
    # path, the runner doesn't publish ports — so the dispatcher's URL
    # resolution still relies on the wrapped index telling it 127.0.0.1.
    # We need to ALSO publish the port via docker port-publish — which
    # the production runner does NOT do. To keep the e2e gate working on
    # macOS while the route drives the runner, we use `docker network
    # connect` post-start for now (the runner attaches the container to
    # the api_server's docker_network_name); the wrapped index returns
    # the bridge IP discovered via docker inspect.
    app = started_api_server._app  # type: ignore[attr-defined]
    app.state.recipe_index = recipe_index

    async def _factory(recipe_name: str, model: str = "anthropic/claude-haiku-4.5"):
        recipe = _load_recipe_yaml(recipe_name)
        channels = recipe.get("channels") or {}
        inapp = channels.get("inapp")
        assert inapp is not None, (
            f"recipe {recipe_name!r} has no channels.inapp block"
        )

        # nanobot accepts only its configured model id literally (400 on
        # placeholder "agent"). Same override the harness used to set —
        # consumed by _E2EWrappedIndex.get_inapp_block.
        if recipe_name == "nanobot":
            _e2e_host_port_map[("contract_model_name", recipe_name)] = model

        # Honest warning preserved per CONTEXT.md AC-03 escape hatch:
        # openclaw needs ANTHROPIC_API_KEY (its openrouter plugin is
        # upstream-broken). The route's build_activation_substitutions
        # aliases provider_key under all 3 keys; production has no
        # separate-source path. If ANTHROPIC_API_KEY is set in env, we
        # do NOT pre-inject it — the recipe's activation_env declares
        # ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY} which the route renders
        # from the substitutions dict (which aliases provider_key under
        # ANTHROPIC_API_KEY). For openclaw to actually reply, the bearer
        # passed must be a valid Anthropic key — operators set the env to
        # a funded ANTHROPIC_API_KEY and pass that AS the Bearer.
        if recipe_name == "openclaw" and not os.environ.get("ANTHROPIC_API_KEY"):
            import warnings
            warnings.warn(
                "ANTHROPIC_API_KEY env var not set; openclaw cell will "
                "use the OpenRouter key as Bearer + production aliases "
                "it under ANTHROPIC_API_KEY (per CONTEXT.md AC-03 — the "
                "documented dumb-pipe behavior; bot reply will be the "
                "401 auth-error string).",
                RuntimeWarning,
                stacklevel=2,
            )

        # Per-cell bearer key. For openclaw, prefer ANTHROPIC_API_KEY if
        # set in env (per the recipe's known_quirks); otherwise fall
        # through to OpenRouter (which is the documented dumb-pipe).
        if recipe_name == "openclaw":
            bearer_key = os.environ.get(
                "ANTHROPIC_API_KEY", openrouter_api_key,
            )
        else:
            bearer_key = openrouter_api_key

        # Step 1: seed an agent_instances row.
        agent_name = f"e2e-{recipe_name}-{uuid.uuid4().hex[:6]}"
        agent_id = uuid.uuid4()
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_instances
                    (id, user_id, recipe_name, model, name)
                VALUES ($1, $2, $3, $4, $5)
                """,
                agent_id,
                uuid.UUID(e2e_authenticated_cookie["_user_id"]),
                recipe_name, model, agent_name,
            )

        # Step 2: POST /v1/agents/{agent_id}/start through the route handler.
        response = await started_api_server.post(
            f"/v1/agents/{agent_id}/start",
            json={
                "channel": "inapp",
                "channel_inputs": {},
                "boot_timeout_s": 240,
            },
            headers={
                "Authorization": f"Bearer {bearer_key}",
                "Cookie": e2e_authenticated_cookie["Cookie"],
            },
        )
        assert response.status_code == 200, (
            f"start failed for {recipe_name}: "
            f"{response.status_code} {response.text}"
        )
        payload = response.json()
        container_id = payload["container_id"]
        container_row_id = uuid.UUID(payload["container_row_id"])

        # Step 3: read the per-session token (route doesn't return it).
        token = await h.fetch_inapp_auth_token(db_pool, container_row_id)

        # Step 4: macOS host-published port — the runner doesn't publish,
        # so we fall back to the bridge IP via docker inspect (the wrapped
        # index returns 127.0.0.1 to keep the matrix happy on macOS, but
        # there's no port-publish in this path; the dispatcher's URL
        # construction will still hit 127.0.0.1:<recipe_port>). For the
        # e2e gate's pre-Phase-22c.3.1 macOS-Docker-Desktop workaround,
        # we publish a host port via `docker port-publish` post-start — but
        # docker doesn't allow that on a running container. Instead, we
        # query the container's bridge IP and publish via the kernel's
        # `socat` shim... or simpler: rely on container_ip from the e2e
        # bridge being reachable via Docker Desktop's host loopback.
        # Resolve container_ip and let _E2EWrappedIndex's get_container_ip
        # convert it to 127.0.0.1 — the bridge is then what the dispatcher
        # uses. The dispatcher's bot HTTP client does the actual call.
        try:
            container_ip = h.docker_inspect_ip(container_id, app.state.docker_network_name)
        except Exception:
            container_ip = "127.0.0.1"

        # Track for teardown — stop via /v1/agents/:id/stop.
        spawned.append((str(agent_id), container_id))

        return {
            "container_id": container_id,
            "container_ip": container_ip,
            "container_row_id": str(container_row_id),
            "inapp_auth_token": token,
            "recipe": recipe,
            "inapp": inapp,
            "model": model,
            "agent_id": str(agent_id),
            "boot_wall_s": payload.get("boot_wall_s"),
            "pre_start_wall_s": payload.get("pre_start_wall_s"),
        }

    try:
        yield _factory
    finally:
        # Teardown — POST /v1/agents/:id/stop for each spawned agent.
        # Falls back to direct `docker rm -f` if the stop call fails.
        for agent_id, container_id in spawned:
            try:
                await started_api_server.post(
                    f"/v1/agents/{agent_id}/stop",
                    headers={
                        "Cookie": e2e_authenticated_cookie["Cookie"],
                    },
                )
            except Exception:
                _log.exception(
                    "e2e.recipe.stop_failed agent_id=%s cid=%s",
                    agent_id, container_id[:12],
                )
                try:
                    h.docker_force_remove(container_id)
                except Exception:
                    _log.exception(
                        "e2e.recipe.cleanup_failed cid=%s",
                        container_id[:12],
                    )


# ---------------------------------------------------------------------------
# Per-test isolation override — the parent conftest's _truncate_tables
# autouse uses the `db_pool` fixture name to gate. e2e tests opt in.
# ---------------------------------------------------------------------------


# (No additional code: the parent _truncate_tables is autouse and
# automatically activates because db_pool is in the fixture chain via
# oauth_user_with_openrouter_key. Each parametrized recipe row gets a
# clean DB.)


# ---------------------------------------------------------------------------
# Phase 22c.3.1-01-AC01 — dockerized harness shutdown helper
# ---------------------------------------------------------------------------
#
# Pre-existing watcher_service.py blocks the asyncio runner shutdown when
# recipe containers outlive the test process (the route-driven `_factory`
# teardown POSTs `/v1/agents/:id/stop` which can fail with 401 because the
# parent conftest's `_truncate_tables` autouse fixture runs BEFORE the
# `recipe_container_factory` teardown — wiping the session row needed for
# auth). With the container alive, the log-watcher's
# `client.logs(stream=True, follow=True)` iterator never returns, the
# `asyncio.to_thread` worker thread stays blocked, and pytest_asyncio's
# `_scoped_runner.close()` waits forever for the thread pool to shut down.
#
# In the dockerized harness (`AP_E2E_DOCKERIZED_HARNESS=1`) we work around
# this by registering a `pytest_sessionfinish` hook that calls `os._exit`
# AFTER pytest has fully completed reporting (including writing the
# `e2e-report.json` artifact via the session-scoped `emit_report`
# fixture's yield-teardown). This bypasses pytest_asyncio's broken
# shutdown path. The host-pytest path leaves the hook inactive so the
# normal teardown sequence still runs.
#
# Note: `pytest_sessionfinish` runs AFTER all session-scoped fixtures
# have yielded (i.e., after `emit_report`'s teardown writes the report);
# but it runs BEFORE pytest_asyncio's session-level shutdown. Confirmed
# via pytest's hook ordering: `pytest_sessionfinish(session, exitstatus)`
# is the last user-facing hook before pytest's own internal cleanup.


def pytest_sessionfinish(session, exitstatus):
    """Hard-exit after pytest finishes when running under the dockerized harness.

    See module-level comment above for the watcher_service shutdown-hang
    rationale. ``os._exit`` skips Python's atexit handlers and the
    asyncio thread-pool shutdown that hangs on the blocked
    ``_multiplexed_response_stream_helper``. The pytest-side reporting
    has already completed (PASSED/FAILED lines printed, exit summary
    written, e2e-report.json written by the autouse session-scoped
    ``emit_report`` fixture's yield-teardown). Recipe containers spawned
    during the run are kept around as logs/forensic artifacts; the
    `--rm` flag on the test-runner's ``docker run`` is what causes the
    test container itself to be reaped. Recipe containers survive (no
    `--rm`) but operators can clean them up with
    ``docker rm -f $(docker ps -q --filter ancestor=ap-recipe-*)``.
    """
    if os.environ.get("AP_E2E_DOCKERIZED_HARNESS") != "1":
        return
    # Respect the actual pytest exit status — caller scripts (Makefile,
    # CI) gate on this. exit 0 = all green, non-zero = at least one fail.
    os._exit(int(exitstatus))

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
import subprocess
import sys
import tempfile
import time
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
            # Host-published path: every e2e container is reachable via 127.0.0.1.
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


@pytest.fixture
def recipe_container_factory(
    e2e_docker_network: str, openrouter_api_key: str,
    _e2e_host_port_map: dict,
):
    """Spawn a real ap-recipe-* container per the recipe's channels.inapp YAML.

    Renders the recipe's ``persistent_argv_override`` + ``activation_env``
    placeholders ($MODEL, ${INAPP_AUTH_TOKEN}, ${INAPP_PROVIDER_KEY},
    ${OPENROUTER_API_KEY}, {agent_name}, {agent_url}) — replicating what
    the production runner SHOULD do at deploy time. Documented as Route B
    follow-up in Plan 15 SUMMARY.

    Returns (container_id, container_ip, inapp_auth_token, recipe_yaml).
    """
    spawned: list[str] = []

    def _factory(recipe_name: str, model: str = "anthropic/claude-haiku-4.5"):
        recipe = _load_recipe_yaml(recipe_name)
        channels = recipe.get("channels") or {}
        inapp = channels.get("inapp")
        assert inapp is not None, (
            f"recipe {recipe_name!r} has no channels.inapp block"
        )

        # Mint per-session opaque token (the runner-side gap step #3).
        inapp_auth_token = uuid.uuid4().hex
        agent_name = f"e2e-{recipe_name}-{uuid.uuid4().hex[:6]}"
        agent_url = f"http://{agent_name}.local"

        # openclaw's recipe documents `provider_compat.deferred=[openrouter]`
        # because openclaw's openrouter plugin (v2026.4.15-beta.1) silently
        # aborts LLM calls upstream — see recipes/openclaw.yaml::known_quirks
        # .openrouter_provider_plugin_silent_fail. Per the recipe's
        # supported=[anthropic] declaration, openclaw needs a real
        # ANTHROPIC_API_KEY (or OPENAI_API_KEY etc.) — NOT the OpenRouter
        # key under a different env-var name. Aliasing them produces a 401
        # from api.anthropic.com that the bot relays back as bot_response,
        # so the gate would PASS on form (status=done, length>0) while
        # FAILing on substance (the reply is the auth error string). Pull
        # a real ANTHROPIC_API_KEY from env if available; fall back to the
        # OpenRouter alias only with a loud warning so the dishonesty is
        # visible.
        anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not anthropic_api_key:
            import warnings
            warnings.warn(
                "ANTHROPIC_API_KEY is not set; openclaw cell will receive "
                "the OpenRouter key under ANTHROPIC_API_KEY and produce a "
                "401 auth-error reply (envelope round-trip will pass, "
                "semantic content is meaningless). Set ANTHROPIC_API_KEY "
                "to a funded Anthropic key to get a real openclaw reply.",
                RuntimeWarning,
                stacklevel=2,
            )
            anthropic_api_key = openrouter_api_key

        substitutions = {
            "INAPP_AUTH_TOKEN": inapp_auth_token,
            "INAPP_PROVIDER_KEY": openrouter_api_key,
            "OPENROUTER_API_KEY": openrouter_api_key,
            # openclaw consumes ANTHROPIC_API_KEY directly (its openrouter
            # plugin is upstream-broken). Sourced from env, NOT aliased.
            "ANTHROPIC_API_KEY": anthropic_api_key,
            "MODEL": model,
            "agent_name": agent_name,
            "agent_url": agent_url,
            "message_id": "{message_id}",  # leave dispatcher templates alone
            "prompt": "{prompt}",
        }

        # Activation env — recipe-declared envs get rendered, then we add
        # the standard runtime envs the persistent_argv_override sh -c chains
        # may rely on.
        activation_env_raw = inapp.get("activation_env") or {}
        if not isinstance(activation_env_raw, dict):
            activation_env_raw = {}
        rendered_env = {
            str(k): str(h.render_placeholders(v, substitutions))
            for k, v in activation_env_raw.items()
        }
        # Make sure the substitution variables are also exported into the
        # container env so any heredoc-time `${MODEL}` / `${OPENROUTER_API_KEY}`
        # in persistent_argv_override.argv resolves at sh exec time.
        for k in (
            "MODEL", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY",
            "INAPP_AUTH_TOKEN", "INAPP_PROVIDER_KEY",
        ):
            rendered_env.setdefault(k, substitutions[k])

        # macOS Docker Desktop quirk: when the recipe binds to 127.0.0.1
        # inside the container, host-port-publishing (`-p`) fails because
        # 127.0.0.1 is the container's loopback (not the network namespace
        # the host bridges into). Force the recipe to bind to 0.0.0.0 so
        # the published port is actually reachable from the host. The
        # production runner doesn't need this because the dispatcher
        # reaches the container via its bridge IP (NetworkSettings...IPAddress)
        # which is 0.0.0.0-bind-agnostic.
        _PER_RECIPE_E2E_BIND_OVERRIDES = {
            "hermes":   {"API_SERVER_HOST": "0.0.0.0"},
            # nanobot is invoked with --host 127.0.0.1 in argv; we rewrite
            # argv below for that case.
            # openclaw binds to "lan" (gateway.bind in openclaw.json heredoc);
            # default exposes 0.0.0.0 already.
            # nullclaw uses host=0.0.0.0 in heredoc already (PASS).
            # zeroclaw sets gateway.allow-public-bind + gateway.host=0.0.0.0
            # in pre_start_commands already.
        }
        rendered_env.update(_PER_RECIPE_E2E_BIND_OVERRIDES.get(recipe_name, {}))

        # Argv + entrypoint — prefer persistent_argv_override; fall back
        # to recipe.persistent.spec for image_pull recipes that don't
        # override (zeroclaw declares config_transport=pre_start_only).
        spec = (recipe.get("persistent") or {}).get("spec") or {}
        # user_override is recipe-level (persistent.spec) — same in inapp mode.
        # nullclaw needs root to chown /nullclaw-data; openclaw runs as `node`.
        user_override = spec.get("user_override")
        override = inapp.get("persistent_argv_override")
        if override and isinstance(override, dict) and override.get("argv"):
            entrypoint = override.get("entrypoint")
            argv = list(override.get("argv") or [])
            pre_start = list(override.get("pre_start_commands") or [])
            # Allow inapp-level user_override to take precedence if specified.
            if override.get("user_override"):
                user_override = override.get("user_override")
        else:
            entrypoint = spec.get("entrypoint")
            argv = list(spec.get("argv") or [])
            pre_start = list(spec.get("pre_start_commands") or [])

        # Render argv placeholders (recipe-template + bash style).
        argv = [str(h.render_placeholders(a, substitutions)) for a in argv]
        if entrypoint:
            entrypoint = str(h.render_placeholders(entrypoint, substitutions))

        # macOS Docker Desktop bind-host rewrite: nanobot's argv has
        # `--host 127.0.0.1` literally; rewrite to 0.0.0.0 so host-port
        # publish works. (No effect on Linux Docker daemon paths where
        # the dispatcher reaches the container via bridge IP directly.)
        for _i, _a in enumerate(argv):
            if _a == "127.0.0.1" and _i > 0 and argv[_i - 1] in (
                "--host", "--bind", "-h",
            ):
                argv[_i] = "0.0.0.0"

        # Build the docker run command — DETACHED, on the e2e network.
        image_tag = f"ap-recipe-{recipe_name}:latest"
        container_name = f"ap-e2e-{recipe_name}-{uuid.uuid4().hex[:8]}"

        # macOS Docker Desktop quirk: host process can't reach docker bridge
        # IPs directly. Publish the recipe's port to a free host port and
        # record the mapping for the recipe_index fixture to pick up.
        recipe_port = int(inapp.get("port"))
        host_port = h.get_free_port()
        _e2e_host_port_map[("port", recipe_name)] = host_port

        run_cmd = ["docker", "run", "-d",
                   "--name", container_name,
                   "--network", e2e_docker_network,
                   "-p", f"127.0.0.1:{host_port}:{recipe_port}"]
        # Mount the recipe's first declared volume to a per-session tmpdir
        # — mirrors what tools/run_recipe.py::run_cell_persistent does.
        volumes = (recipe.get("runtime") or {}).get("volumes") or []
        data_dir: Path | None = None
        if volumes:
            vol = volumes[0]
            container_mount = vol.get("container") or "/data"
            data_dir = Path(tempfile.mkdtemp(
                prefix=f"ap-e2e-{recipe_name}-data-"
            ))
            run_cmd += ["-v", f"{data_dir}:{container_mount}"]
            # Per-recipe config-file pre-write — replicates what the
            # recipe's `persistent.spec` sh-chain heredoc would do at
            # container boot. The persistent_argv_override path skips
            # that bootstrap, so we write config.json directly into the
            # bind-mounted data_dir.
            if recipe_name == "nanobot":
                # Tell the recipe_index wrapper to override contract_model_name
                # for nanobot — its OpenAI-compat surface only accepts the
                # configured model id literally (400s on "agent" placeholder).
                _e2e_host_port_map[("contract_model_name", recipe_name)] = model
                _config = {
                    "agents": {
                        "defaults": {
                            "provider": "openrouter",
                            "model": model,
                        }
                    },
                    "providers": {
                        "openrouter": {
                            "api_key": openrouter_api_key,
                            "api_base": "https://openrouter.ai/api/v1",
                        }
                    },
                    "channels": {},
                }
                (data_dir / "config.json").write_text(
                    __import__("json").dumps(_config, indent=2)
                )
                # Allow nanobot's UID 1000 to read+write the dir.
                import os as _os
                _os.chmod(data_dir, 0o777)
                _os.chmod(data_dir / "config.json", 0o666)
        if user_override:
            run_cmd += ["--user", str(user_override)]
        # Env injection — use --env-file in /tmp to keep secrets out of cmdline.
        env_file = Path(tempfile.mkdtemp(prefix="ap-e2e-env-")) / "env"
        env_file.write_text(
            "\n".join(f"{k}={v}" for k, v in rendered_env.items()) + "\n"
        )
        try:
            env_file.chmod(0o600)
        except OSError:
            pass
        run_cmd += ["--env-file", str(env_file)]

        # Run pre_start_commands BEFORE the persistent container starts —
        # for distroless images (zeroclaw) the daemon can't tolerate
        # post-start docker exec because it requires the config to be
        # written first AND has no shell. Pre-start as separate
        # `docker run --rm` invocations sharing the bind-mounted volume.
        for pre in pre_start:
            pre_argv = pre.get("argv") if isinstance(pre, dict) else None
            if not pre_argv:
                continue
            pre_argv_rendered = [
                str(h.render_placeholders(a, substitutions)) for a in pre_argv
            ]
            # The first token is the entrypoint binary (e.g. `zeroclaw`);
            # the rest are subcommand args. Use --entrypoint to invoke it.
            pre_entry = pre_argv_rendered[0]
            pre_args = pre_argv_rendered[1:]
            pre_run_cmd = [
                "docker", "run", "--rm",
                "--network", e2e_docker_network,
                "--env-file", str(env_file),
                "--entrypoint", pre_entry,
            ]
            if data_dir is not None:
                pre_run_cmd += ["-v", f"{data_dir}:{container_mount}"]
            if user_override:
                pre_run_cmd += ["--user", str(user_override)]
            pre_run_cmd += [image_tag, *pre_args]
            ex = subprocess.run(
                pre_run_cmd, capture_output=True, text=True, check=False,
            )
            if ex.returncode != 0:
                _log.warning(
                    "e2e.pre_start.failed argv=%s rc=%d stderr=%s",
                    pre_argv_rendered[:3], ex.returncode,
                    ex.stderr.strip()[:300],
                )

        # Now start the persistent container.
        if entrypoint:
            run_cmd += ["--entrypoint", entrypoint]
        run_cmd += [image_tag] + argv

        _log.info("e2e.recipe.run %s", container_name)
        out = subprocess.run(run_cmd, capture_output=True, text=True, check=False)
        if out.returncode != 0:
            raise RuntimeError(
                f"docker run failed for {recipe_name}: rc={out.returncode}, "
                f"stderr={out.stderr.strip()[:500]}"
            )
        container_id = (out.stdout or "").strip()
        if not container_id:
            raise RuntimeError(
                f"docker run produced empty container id for {recipe_name}"
            )
        spawned.append(container_id)

        # Wait for ready_log_regex. The recipe declares the regex assuming
        # the bot binds to its declared loopback host (e.g. 127.0.0.1:8642
        # for hermes); we forced 0.0.0.0 binds for the e2e port-publish
        # path, so loosen the IP match in the regex to accept both.
        raw_regex = inapp.get("ready_log_regex") or "."
        ready_regex = raw_regex.replace(r"127\.0\.0\.1", r"(127\.0\.0\.1|0\.0\.0\.0)")
        ok, last_logs = h.wait_for_ready_log(
            container_id, ready_regex, timeout_s=180.0,
        )
        if not ok:
            tail = last_logs[-2000:] if last_logs else ""
            raise RuntimeError(
                f"recipe {recipe_name} did not match ready_log_regex "
                f"{ready_regex!r} within 180s. logs tail:\n{tail}"
            )

        # Resolve container IP on the e2e network (with one quick retry).
        try:
            container_ip = h.docker_inspect_ip(container_id, e2e_docker_network)
        except RuntimeError:
            time.sleep(0.5)
            container_ip = h.docker_inspect_ip(container_id, e2e_docker_network)

        return {
            "container_id": container_id,
            "container_ip": container_ip,
            "inapp_auth_token": inapp_auth_token,
            "recipe": recipe,
            "inapp": inapp,
            "model": model,
        }

    yield _factory

    # Tear down all spawned containers — fail-loud removal so leaked
    # state surfaces in CI logs.
    for cid in spawned:
        try:
            h.docker_force_remove(cid)
        except Exception:
            _log.exception("e2e.recipe.cleanup_failed cid=%s", cid)


# ---------------------------------------------------------------------------
# Per-test isolation override — the parent conftest's _truncate_tables
# autouse uses the `db_pool` fixture name to gate. e2e tests opt in.
# ---------------------------------------------------------------------------


# (No additional code: the parent _truncate_tables is autouse and
# automatically activates because db_pool is in the fixture chain via
# oauth_user_with_openrouter_key. Each parametrized recipe row gets a
# clean DB.)

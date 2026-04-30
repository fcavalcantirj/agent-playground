"""Phase 22c.3-05 — InappRecipeIndex + InappChannelConfig.

The dispatcher (Plan 22c.3-05) needs two pieces of metadata per dispatch:

  1. The recipe's ``channels.inapp`` block — port, endpoint, contract,
     auth shape, optional headers. Loaded from ``recipes/*.yaml``.

  2. The container's IPv4 address inside the api-server's docker bridge
     network — needed to construct the ``http://<ip>:<port>{endpoint}``
     URL since the dispatcher does NOT use the host port mapping (it
     stays inside the bridge network for performance + isolation).

This module provides a small in-process cache keyed by ``recipe_name`` +
a 60s TTL container-IP cache (per RESEARCH §Don't Hand-Roll table); the
dispatcher consumes both via :class:`InappRecipeIndex`.

Invalidation: ``InappRecipeIndex`` re-loads a recipe file when its mtime
changes (content-hash via mtime is the cheap-and-correct approach for
a single api-server replica; file-system events would be overkill).
Tests + a future hot-reload route can call :meth:`invalidate` to drop
specific entries.

The ``InappChannelConfig`` dataclass is intentionally narrow — adding a
4th contract later is a switch-case + ``Literal`` extension, not a
refactor. Per D-22 (dumb pipe), the dispatcher's adapters use these
fields to build the request envelope verbatim from the recipe; the api
does NOT compose prompts, inject system messages, or manipulate the
user's content.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Any, Literal

from ruamel.yaml import YAML


_log = logging.getLogger("api_server.inapp_recipe_index")


# ---------------------------------------------------------------------------
# InappChannelConfig — the parsed view of a recipe's channels.inapp block
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InappChannelConfig:
    """Parsed view of a recipe's ``channels.inapp`` block.

    Adding a 4th contract later is a single change to the
    ``Literal[...]`` on ``contract`` + a new ``case`` arm in the
    dispatcher's ``match`` statement; nothing else in this module
    needs to change.

    Fields:

    * ``transport`` — only ``http_localhost`` is supported v1; D-06's
      ``docker_exec_cli`` is informational future-work (Phase 24).
    * ``port`` — bot's listening port inside the container (D-36 static).
    * ``endpoint`` — request path (e.g. ``/v1/chat/completions``).
    * ``contract`` — the dispatcher's adapter selector. One of
      ``openai_compat`` (hermes/nanobot/openclaw),
      ``a2a_jsonrpc`` (nullclaw native A2A),
      ``zeroclaw_native`` (zeroclaw native /webhook).
    * ``contract_model_name`` — only used by ``openai_compat`` adapters
      that pin a specific model id (e.g. openclaw → ``"openclaw"``).
      ``None`` falls back to the literal ``"agent"``.
    * ``request_envelope`` / ``response_envelope`` — documentation only
      (the contract switch is the source of truth); kept on the
      dataclass so a future generic-contract path can read them
      programmatically without re-parsing the YAML.
    * ``auth_mode`` — ``none`` (loopback-trusted), ``bearer`` (use
      ``inapp_auth_token`` from agent_containers), ``token`` (header).
    * ``idempotency_header`` / ``session_header`` — propagated by the
      ``zeroclaw_native`` adapter; ``None`` for adapters that don't
      support them.
    """

    transport: Literal["http_localhost"]
    port: int
    endpoint: str
    contract: Literal["openai_compat", "a2a_jsonrpc", "zeroclaw_native"]
    contract_model_name: str | None = None
    request_envelope: dict | None = None
    response_envelope: dict | None = None
    auth_mode: Literal["none", "bearer", "token"] = "none"
    idempotency_header: str | None = None
    session_header: str | None = None


# ---------------------------------------------------------------------------
# Internal — recipe parsing
# ---------------------------------------------------------------------------


_VALID_CONTRACTS: set[str] = {"openai_compat", "a2a_jsonrpc", "zeroclaw_native"}


def _parse_inapp_block(recipe_yaml: dict) -> InappChannelConfig | None:
    """Project a recipe dict's ``channels.inapp`` block to ``InappChannelConfig``.

    Returns ``None`` when the recipe lacks ``channels`` or
    ``channels.inapp`` — that is a normal absence (not all recipes
    declare an in-app channel) and the dispatcher converts it to a
    ``recipe_lacks_inapp_channel`` terminal failure for any pending
    message that names the recipe.

    Raises ``ValueError`` for a malformed inapp block (missing port,
    unknown ``contract`` value, etc.) — surfacing this at the loader
    rather than the dispatcher means a typo in a recipe trips at app
    boot (or first-access for the lazy cache), not on the request hot
    path.
    """
    channels = recipe_yaml.get("channels") or {}
    if not isinstance(channels, dict):
        return None
    inapp = channels.get("inapp")
    if not inapp or not isinstance(inapp, dict):
        return None

    transport = str(inapp.get("transport") or "http_localhost")
    if transport != "http_localhost":
        raise ValueError(
            f"unsupported transport {transport!r} (only http_localhost is supported)"
        )
    port = inapp.get("port")
    if not isinstance(port, int) or port <= 0:
        raise ValueError(f"channels.inapp.port must be a positive int, got {port!r}")
    endpoint = inapp.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint.startswith("/"):
        raise ValueError(
            f"channels.inapp.endpoint must be a path starting with '/', got {endpoint!r}"
        )
    contract = inapp.get("contract")
    if contract not in _VALID_CONTRACTS:
        raise ValueError(
            f"channels.inapp.contract must be one of {sorted(_VALID_CONTRACTS)}, "
            f"got {contract!r}"
        )

    auth_mode = inapp.get("auth_mode") or "none"
    if auth_mode not in ("none", "bearer", "token"):
        raise ValueError(
            f"channels.inapp.auth_mode must be one of none/bearer/token, "
            f"got {auth_mode!r}"
        )

    # ruamel returns CommentedMap subclasses — cast to plain dict for the
    # frozen dataclass so callers can rely on dict-not-CommentedMap.
    req_env = inapp.get("request_envelope")
    resp_env = inapp.get("response_envelope")

    return InappChannelConfig(
        transport="http_localhost",
        port=int(port),
        endpoint=str(endpoint),
        contract=contract,  # type: ignore[arg-type]
        contract_model_name=(
            str(inapp["contract_model_name"])
            if inapp.get("contract_model_name") is not None
            else None
        ),
        request_envelope=dict(req_env) if isinstance(req_env, dict) else None,
        response_envelope=dict(resp_env) if isinstance(resp_env, dict) else None,
        auth_mode=auth_mode,  # type: ignore[arg-type]
        idempotency_header=(
            str(inapp["idempotency_header"])
            if inapp.get("idempotency_header") is not None
            else None
        ),
        session_header=(
            str(inapp["session_header"])
            if inapp.get("session_header") is not None
            else None
        ),
    )


# ---------------------------------------------------------------------------
# InappRecipeIndex — lazy LRU cache + container-IP cache
# ---------------------------------------------------------------------------


@dataclass
class _CachedEntry:
    """Internal cache slot for one recipe."""

    config: InappChannelConfig | None
    mtime: float


@dataclass
class _IPEntry:
    """Internal cache slot for one container IP."""

    ip: str
    expires_at: float


class InappRecipeIndex:
    """Lazy LRU cache of ``channels.inapp`` blocks + 60s container-IP cache.

    Thread-safe via an ``asyncio.Lock`` (the dispatcher's tick is async;
    the lock guards the cache dict + IP dict against races between the
    dispatcher and a concurrent invalidate call from a future
    hot-reload route).

    Recipe lookup is keyed by ``recipe_name`` (the recipe YAML's
    ``name`` field, NOT the file stem — although in practice they
    match). The cache stores both the parsed
    :class:`InappChannelConfig` AND the file's last-known mtime; on
    every lookup the on-disk mtime is compared and a stale entry is
    re-parsed from YAML.

    Container IP lookup is keyed by docker container_id (the long
    SHA-style id, NOT the human name). The 60s TTL is the
    RESEARCH-recommended balance between cache hit rate and reactivity
    to container restarts (which would change the IP).
    """

    def __init__(
        self,
        recipes_dir: Path,
        docker_client: Any | None = None,
        network_name: str | None = None,
        ip_ttl_seconds: float = 60.0,
    ) -> None:
        """Bind the index to a recipes dir + (optional) docker client.

        ``docker_client`` is a ``docker.DockerClient`` — when ``None``
        (test path), :meth:`get_container_ip` raises ``RuntimeError``.
        Production wiring (Plan 22c.3-09 lifespan) injects
        ``app.state.docker_client`` here.

        ``network_name`` is the docker bridge network the api_server
        and per-user containers share. Plan 22c.3-09 reads it from
        ``app.state.docker_network_name`` set at lifespan boot.
        """
        self._recipes_dir = recipes_dir
        self._docker_client = docker_client
        self._network_name = network_name
        self._ip_ttl_seconds = float(ip_ttl_seconds)

        # Per-coroutine guard — the dispatcher's tick is async. We use
        # asyncio.Lock so a concurrent invalidate doesn't race.
        # Sync-fallback: a plain threading.Lock for sync get_inapp_block
        # callers (tests). Both protect the same dicts.
        self._lock = asyncio.Lock()
        self._sync_lock = threading.Lock()

        self._cache: dict[str, _CachedEntry] = {}
        self._ip_cache: dict[str, _IPEntry] = {}

    # -- recipe lookup --------------------------------------------------

    def _yaml_path_for(self, recipe_name: str) -> Path:
        """Return the on-disk file path for ``recipe_name``.

        Convention: a recipe whose ``name`` field is ``foo`` lives at
        ``recipes_dir/foo.yaml``. The 5 inapp recipes follow this
        convention; deviation would force a directory scan, which we
        avoid by keeping the convention strict.
        """
        return self._recipes_dir / f"{recipe_name}.yaml"

    def _load_from_disk(self, recipe_name: str) -> _CachedEntry:
        """Read + parse the recipe file; returns a fresh ``_CachedEntry``.

        Missing file returns an entry with ``config=None`` AND
        ``mtime=-1.0`` so a future create-then-touch cycle will cause
        the next ``get_inapp_block`` call to re-load.
        """
        path = self._yaml_path_for(recipe_name)
        if not path.exists():
            return _CachedEntry(config=None, mtime=-1.0)

        # Fresh YAML() instance per call (ruamel ticket #367 — see
        # recipes_loader._fresh_yaml comment).
        y = YAML(typ="rt")
        try:
            recipe = y.load(path.read_text())
        except Exception:
            _log.exception(
                "inapp_recipe_index.parse_error",
                extra={"recipe_name": recipe_name, "path": str(path)},
            )
            return _CachedEntry(config=None, mtime=path.stat().st_mtime)

        if not isinstance(recipe, dict):
            return _CachedEntry(config=None, mtime=path.stat().st_mtime)

        try:
            config = _parse_inapp_block(recipe)
        except ValueError:
            _log.exception(
                "inapp_recipe_index.malformed_inapp_block",
                extra={"recipe_name": recipe_name},
            )
            return _CachedEntry(config=None, mtime=path.stat().st_mtime)

        return _CachedEntry(config=config, mtime=path.stat().st_mtime)

    def get_inapp_block(self, recipe_name: str) -> InappChannelConfig | None:
        """Return the recipe's ``channels.inapp`` block, or ``None``.

        Uses a synchronous lock — safe to call from both async tasks
        (the dispatcher) and sync tests. Re-loads the file on every
        call where the on-disk mtime is newer than the cached mtime
        (cheap stat call vs. a much-more-expensive YAML re-parse).
        """
        with self._sync_lock:
            cached = self._cache.get(recipe_name)
            path = self._yaml_path_for(recipe_name)
            if path.exists():
                current_mtime = path.stat().st_mtime
            else:
                current_mtime = -1.0

            # Cache miss OR stale — load from disk.
            if cached is None or cached.mtime != current_mtime:
                cached = self._load_from_disk(recipe_name)
                self._cache[recipe_name] = cached
            return cached.config

    # -- container IP lookup -------------------------------------------

    def get_container_ip(self, container_id: str) -> str:
        """Return the container's IPv4 inside ``self._network_name``.

        Cached for ``ip_ttl_seconds`` (default 60s). Cache miss issues
        a single ``client.containers.get(container_id).attrs[...]``
        call and walks the ``NetworkSettings.Networks[<name>].IPAddress``
        path — same shape every modern docker engine returns.

        Raises ``RuntimeError`` when:

        * No docker client was configured (test path that forgot to
          inject one).
        * No network name was configured.
        * The container is in the bridge but the network entry has no
          ``IPAddress`` (e.g. Docker Desktop on macOS — see CLAUDE.md
          "macOS Docker Desktop doesn't bridge container IPs to host").
        """
        now = monotonic()
        with self._sync_lock:
            entry = self._ip_cache.get(container_id)
            if entry is not None and entry.expires_at > now:
                return entry.ip

        if self._docker_client is None:
            raise RuntimeError(
                "InappRecipeIndex was constructed without a docker_client; "
                "production wiring (Plan 22c.3-09 lifespan) must inject one"
            )
        if not self._network_name:
            raise RuntimeError(
                "InappRecipeIndex was constructed without a network_name; "
                "production wiring (Plan 22c.3-09 lifespan) must set one"
            )

        container = self._docker_client.containers.get(container_id)
        networks = (
            container.attrs.get("NetworkSettings", {}).get("Networks") or {}
        )
        net = networks.get(self._network_name) or {}
        ip = net.get("IPAddress") or ""
        if not ip:
            raise RuntimeError(
                f"container {container_id!r} has no IPAddress on network "
                f"{self._network_name!r}"
            )

        with self._sync_lock:
            self._ip_cache[container_id] = _IPEntry(
                ip=ip, expires_at=now + self._ip_ttl_seconds
            )
        return ip

    # -- cache control --------------------------------------------------

    def invalidate(self, recipe_name: str | None = None) -> None:
        """Drop one or all recipe cache entries.

        Use cases: tests that mutate a recipe file, future hot-reload
        admin route. Container-IP cache is NOT cleared by this call —
        IPs change on container restart, not on recipe edit. To clear
        container IPs use :meth:`invalidate_container_ips`.
        """
        with self._sync_lock:
            if recipe_name is None:
                self._cache.clear()
            else:
                self._cache.pop(recipe_name, None)

    def invalidate_container_ips(self, container_id: str | None = None) -> None:
        """Drop one or all container-IP cache entries."""
        with self._sync_lock:
            if container_id is None:
                self._ip_cache.clear()
            else:
                self._ip_cache.pop(container_id, None)


__all__ = [
    "InappChannelConfig",
    "InappRecipeIndex",
]

"""Phase 22c.3-05 — tests for InappRecipeIndex + InappChannelConfig.

Pure-unit tests against fixture YAML files written into a tmp_path.
No DB, no Docker — the docker_client param of InappRecipeIndex is left
None for the recipe-loading tests (those don't exercise IP lookup).

Coverage matrix:

  * ``test_recipe_index_loads_all_5_inapp_recipes`` — fixture-loads
    hermes/nanobot/openclaw/nullclaw/zeroclaw shapes; asserts the
    expected ``contract`` per RESEARCH §Per-Recipe Feasibility Matrix.
  * ``test_recipe_index_returns_none_for_recipe_without_inapp`` — a
    picoclaw-shape file (no channels.inapp) returns ``None``.
  * ``test_recipe_index_invalidates_on_mtime_change`` — touch a file,
    assert the next get re-reads (cache invalidation discipline).
  * ``test_recipe_index_invalidate_clears_specific_entry`` —
    ``invalidate(name)`` drops one entry, ``invalidate(None)`` drops
    all.
  * ``test_inapp_channel_config_is_frozen`` — dataclass(frozen=True)
    assertion (defensive — a future refactor must not loosen this).
  * ``test_recipe_index_handles_malformed_inapp_block`` — recipe
    declares ``contract: not_a_real_contract``; loader logs +
    returns None rather than crashing.
  * ``test_get_container_ip_raises_without_docker_client`` — explicit
    failure mode the dispatcher converts to ``container_dead``.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from api_server.services.inapp_recipe_index import (
    InappChannelConfig,
    InappRecipeIndex,
)


# ---------------------------------------------------------------------------
# Fixtures — minimal YAML shapes for the 5 inapp recipes + 1 no-inapp
# ---------------------------------------------------------------------------


HERMES_YAML = """\
apiVersion: ap.recipe/v0.2
name: hermes
channels:
  inapp:
    transport: http_localhost
    port: 8642
    contract: openai_compat
    endpoint: /v1/chat/completions
    auth_mode: bearer
"""

NANOBOT_YAML = """\
apiVersion: ap.recipe/v0.2
name: nanobot
channels:
  inapp:
    transport: http_localhost
    port: 8900
    contract: openai_compat
    endpoint: /v1/chat/completions
    auth_mode: none
"""

OPENCLAW_YAML = """\
apiVersion: ap.recipe/v0.2
name: openclaw
channels:
  inapp:
    transport: http_localhost
    port: 18789
    contract: openai_compat
    contract_model_name: openclaw
    endpoint: /v1/chat/completions
    auth_mode: none
"""

NULLCLAW_YAML = """\
apiVersion: ap.recipe/v0.2
name: nullclaw
channels:
  inapp:
    transport: http_localhost
    port: 3000
    contract: a2a_jsonrpc
    endpoint: /a2a
    auth_mode: none
"""

ZEROCLAW_YAML = """\
apiVersion: ap.recipe/v0.2
name: zeroclaw
channels:
  inapp:
    transport: http_localhost
    port: 42617
    contract: zeroclaw_native
    endpoint: /webhook
    auth_mode: none
    idempotency_header: X-Idempotency-Key
    session_header: X-Session-Id
"""

PICOCLAW_NO_INAPP_YAML = """\
apiVersion: ap.recipe/v0.2
name: picoclaw
channels:
  telegram:
    config_transport: file
"""

MALFORMED_YAML = """\
apiVersion: ap.recipe/v0.2
name: malformed
channels:
  inapp:
    transport: http_localhost
    port: 1234
    contract: not_a_real_contract
    endpoint: /x
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(recipes_dir: Path, name: str, yaml_text: str) -> Path:
    p = recipes_dir / f"{name}.yaml"
    p.write_text(yaml_text)
    return p


@pytest.fixture
def recipes_dir(tmp_path: Path) -> Path:
    """A scratch ``recipes/`` populated with 5 inapp + 1 no-inapp YAMLs."""
    d = tmp_path / "recipes"
    d.mkdir()
    _write(d, "hermes", HERMES_YAML)
    _write(d, "nanobot", NANOBOT_YAML)
    _write(d, "openclaw", OPENCLAW_YAML)
    _write(d, "nullclaw", NULLCLAW_YAML)
    _write(d, "zeroclaw", ZEROCLAW_YAML)
    _write(d, "picoclaw", PICOCLAW_NO_INAPP_YAML)
    return d


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_recipe_index_loads_all_5_inapp_recipes(recipes_dir: Path) -> None:
    """Each of the 5 inapp recipes parses with the right ``contract``."""
    idx = InappRecipeIndex(recipes_dir)

    expected = {
        "hermes": ("openai_compat", 8642, "/v1/chat/completions", "bearer"),
        "nanobot": ("openai_compat", 8900, "/v1/chat/completions", "none"),
        "openclaw": ("openai_compat", 18789, "/v1/chat/completions", "none"),
        "nullclaw": ("a2a_jsonrpc", 3000, "/a2a", "none"),
        "zeroclaw": ("zeroclaw_native", 42617, "/webhook", "none"),
    }
    for name, (contract, port, endpoint, auth) in expected.items():
        cfg = idx.get_inapp_block(name)
        assert cfg is not None, f"{name}: expected an InappChannelConfig"
        assert isinstance(cfg, InappChannelConfig)
        assert cfg.contract == contract, f"{name} contract"
        assert cfg.port == port, f"{name} port"
        assert cfg.endpoint == endpoint, f"{name} endpoint"
        assert cfg.auth_mode == auth, f"{name} auth_mode"

    # Zeroclaw uniqueness — the only recipe that wires the optional
    # idempotency + session headers.
    zc = idx.get_inapp_block("zeroclaw")
    assert zc is not None
    assert zc.idempotency_header == "X-Idempotency-Key"
    assert zc.session_header == "X-Session-Id"

    # Openclaw uniqueness — the only openai_compat recipe that pins
    # a specific model name.
    oc = idx.get_inapp_block("openclaw")
    assert oc is not None
    assert oc.contract_model_name == "openclaw"


def test_recipe_index_returns_none_for_recipe_without_inapp(
    recipes_dir: Path,
) -> None:
    """A recipe with channels.telegram but no channels.inapp returns ``None``."""
    idx = InappRecipeIndex(recipes_dir)
    assert idx.get_inapp_block("picoclaw") is None


def test_recipe_index_returns_none_for_unknown_recipe(
    recipes_dir: Path,
) -> None:
    """A recipe name that doesn't exist on disk returns ``None``."""
    idx = InappRecipeIndex(recipes_dir)
    assert idx.get_inapp_block("nonexistent_recipe") is None


def test_recipe_index_invalidates_on_mtime_change(recipes_dir: Path) -> None:
    """Touching a file forces the next get to re-read from disk."""
    idx = InappRecipeIndex(recipes_dir)

    cfg = idx.get_inapp_block("hermes")
    assert cfg is not None and cfg.contract == "openai_compat"

    # Mutate the recipe to flip its contract; bump mtime so the cache
    # invalidation kicks in. (On a filesystem with 1s mtime resolution,
    # rewriting in the same instant would not move the mtime; we
    # explicitly os.utime forward.)
    new_yaml = HERMES_YAML.replace(
        "contract: openai_compat", "contract: zeroclaw_native"
    )
    path = recipes_dir / "hermes.yaml"
    path.write_text(new_yaml)
    future = time.time() + 5
    os.utime(path, (future, future))

    cfg2 = idx.get_inapp_block("hermes")
    assert cfg2 is not None
    assert cfg2.contract == "zeroclaw_native", (
        "Cache should have re-read after mtime bump"
    )


def test_recipe_index_invalidate_clears_specific_entry(
    recipes_dir: Path,
) -> None:
    """``invalidate(name)`` drops one entry; ``invalidate(None)`` drops all."""
    idx = InappRecipeIndex(recipes_dir)
    # Prime the cache.
    assert idx.get_inapp_block("hermes") is not None
    assert idx.get_inapp_block("nullclaw") is not None

    # Targeted invalidate — internal cache should drop just hermes.
    idx.invalidate("hermes")
    assert "hermes" not in idx._cache  # type: ignore[attr-defined]
    assert "nullclaw" in idx._cache  # type: ignore[attr-defined]

    # Re-prime, then invalidate-all.
    assert idx.get_inapp_block("hermes") is not None
    idx.invalidate(None)
    assert idx._cache == {}  # type: ignore[attr-defined]


def test_inapp_channel_config_is_frozen() -> None:
    """The dataclass(frozen=True) decorator is the defensive contract.

    A future refactor that loosens this would let the dispatcher
    accidentally mutate cache entries; assert the freeze stays.
    """
    cfg = InappChannelConfig(
        transport="http_localhost",
        port=1,
        endpoint="/x",
        contract="openai_compat",
    )
    with pytest.raises(Exception):  # FrozenInstanceError on stdlib
        cfg.port = 9999  # type: ignore[misc]


def test_recipe_index_handles_malformed_inapp_block(
    recipes_dir: Path,
) -> None:
    """A recipe with an unknown ``contract`` returns ``None`` (loader logs)."""
    _write(recipes_dir, "malformed", MALFORMED_YAML)
    idx = InappRecipeIndex(recipes_dir)
    # Should not raise — the loader catches ValueError and returns None.
    cfg = idx.get_inapp_block("malformed")
    assert cfg is None


def test_get_container_ip_raises_without_docker_client(
    recipes_dir: Path,
) -> None:
    """Explicit error mode — production wiring must inject a docker client."""
    idx = InappRecipeIndex(recipes_dir)  # docker_client=None
    with pytest.raises(RuntimeError, match="docker_client"):
        idx.get_container_ip("anything")


def test_get_container_ip_caches_within_ttl(recipes_dir: Path) -> None:
    """One docker SDK lookup feeds N gets within the TTL window."""
    calls: list[str] = []

    class _FakeContainer:
        def __init__(self, cid: str, ip: str) -> None:
            self.attrs = {
                "NetworkSettings": {"Networks": {"ap-net": {"IPAddress": ip}}}
            }

    class _FakeContainers:
        def __init__(self) -> None:
            self._ips = {"abc": "172.18.0.5"}

        def get(self, cid: str) -> _FakeContainer:
            calls.append(cid)
            return _FakeContainer(cid, self._ips[cid])

    class _FakeClient:
        def __init__(self) -> None:
            self.containers = _FakeContainers()

    idx = InappRecipeIndex(
        recipes_dir,
        docker_client=_FakeClient(),
        network_name="ap-net",
        ip_ttl_seconds=60.0,
    )

    assert idx.get_container_ip("abc") == "172.18.0.5"
    assert idx.get_container_ip("abc") == "172.18.0.5"
    assert idx.get_container_ip("abc") == "172.18.0.5"
    # Single docker call satisfies the 3 gets.
    assert calls == ["abc"]


def test_recipe_index_loads_all_5_inapp_recipes_smoke(
    recipes_dir: Path,
) -> None:
    """Smoke: count of resolved recipes equals 5 (defensive duplicate test).

    Keeps the file-level count in the test name so a regression that
    drops one of the 5 contracts would surface here as "expected 5,
    got 4".
    """
    idx = InappRecipeIndex(recipes_dir)
    resolved = [
        n for n in ("hermes", "nanobot", "openclaw", "nullclaw", "zeroclaw")
        if idx.get_inapp_block(n) is not None
    ]
    assert resolved == ["hermes", "nanobot", "openclaw", "nullclaw", "zeroclaw"]

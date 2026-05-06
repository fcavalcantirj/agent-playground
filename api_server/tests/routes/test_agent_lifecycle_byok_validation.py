"""Phase 29 Plan 05 Task 3 — integration tests for start_agent BYOK gate.

Drives /v1/agents/:id/start through the started_api_server fixture
(real PG17 + mocked Docker via patched execute_persistent_start).
respx mocks the upstream provider validators so each test stays
hermetic — no real OpenRouter / Anthropic / OpenAI traffic.

Coverage map (8 behaviors enumerated in 29-05-PLAN.md):
  1. happy path (via_proxy=true): validator 200 → row has
     upstream_provider + provider_key_enc + cache populated.
  2. validator 401 (via_proxy=true): no agent_containers row inserted.
  3. validator 503 (via_proxy=true): network failure → 503 envelope.
  4. unknown env var (via_proxy=true): recipe declares BOGUS_KEY → 400.
  5. encrypted blob round-trips: decrypt provider_key_enc back to dict
     containing the original BYOK key.
  6. BYOK key never appears in caplog on 401 path.
  7. **GATE-7 INVARIANT**: legacy recipe (via_proxy=false) skips validator
     entirely — respx call_count==0; provider_key_enc IS NULL;
     upstream_provider IS NULL; ProxyBYOKCache.get returns (None, None).
  8. **GATE-7 INVARIANT**: legacy recipe with INVALID key still 200s
     (no validation gate on legacy path) — proves the via_proxy gate
     short-circuits all four columns.
"""
from __future__ import annotations

import logging
import os
from copy import deepcopy
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
import respx

from api_server.crypto.age_cipher import decrypt_channel_config


pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_TEST_BYOK_KEY = "sk-or-v1-test-byok-aaaabbbbccccdddd"


def _openrouter_key() -> str:
    """Reuse the test fixture pattern from test_agent_lifecycle_inapp.py."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    repo_root = Path(__file__).resolve().parents[3]
    env_local = repo_root / ".env.local"
    if env_local.exists():
        for line in env_local.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    pytest.skip("OPENROUTER_API_KEY missing — cannot exercise route")


async def _seed_agent_with_recipe(
    pool, user_id: str, recipe_name: str = "hermes",
    model: str = "anthropic/claude-haiku-4.5",
) -> UUID:
    """Seed agent_instances row, return agent_id."""
    agent_id = uuid4()
    name = f"e2e-{recipe_name}-{uuid4().hex[:6]}"
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, $3, $4, $5)
            """,
            agent_id, UUID(user_id), recipe_name, model, name,
        )
    return agent_id


def _make_fake_runner(captured: dict | None = None):
    """Return a fake execute_persistent_start that emits a PASS verdict.

    The route still has to talk to its real internals — recipes lookup,
    DB writes, proxy_byok_cache.set, etc. We only short-circuit the
    Docker-spawning step.
    """
    async def _fake(*args, **kwargs):
        if captured is not None:
            captured["args"] = args
            captured["kwargs"] = dict(kwargs)
        return {
            "verdict": "PASS",
            "container_id": f"fakecid{uuid4().hex[:24]}",
            "boot_wall_s": 0.1,
            "pre_start_wall_s": 0.0,
            "health_check_ok": True,
            "health_check_kind": "process_alive",
            "data_dir": "/tmp/fake",
        }
    return _fake


def _patch_recipe_via_proxy(app, recipe_name: str, *, via_proxy: bool) -> None:
    """Mutate ``app.state.recipes[recipe_name]`` to flip ``runtime.via_proxy``.

    Test-only path that exercises the via_proxy gate without writing a
    new YAML file. Mutation is in-place on a deep-copied recipe so we
    don't leak across tests (the caller is expected to restore via
    monkeypatch teardown if needed; the started_api_server fixture is
    function-scoped so each test gets a fresh app anyway).
    """
    recipe = deepcopy(app.state.recipes[recipe_name])
    runtime = recipe.setdefault("runtime", {})
    runtime["via_proxy"] = via_proxy
    app.state.recipes[recipe_name] = recipe


# ---------------------------------------------------------------------------
# Test 1 — Happy path: via_proxy=true + validator 200 → row + cache populated
# ---------------------------------------------------------------------------


@respx.mock
async def test_via_proxy_happy_path_persists_and_caches(
    started_api_server, db_pool, authenticated_cookie, monkeypatch,
) -> None:
    """When recipe.runtime.via_proxy=true and the validator probe
    returns 200, the route MUST:

      - call OpenRouter /v1/key once
      - insert agent_containers with upstream_provider='openrouter'
        AND non-empty provider_key_enc
      - populate proxy_byok_cache via set()
    """
    # Mock the validator upstream — return 200 OK.
    or_route = respx.get("https://openrouter.ai/api/v1/key").mock(
        return_value=httpx.Response(200, json={"data": {"limit": 100}}),
    )

    # Patch the runner to skip real Docker boot.
    import api_server.routes.agent_lifecycle as al
    monkeypatch.setattr(al, "execute_persistent_start", _make_fake_runner())

    # Flip the hermes recipe to via_proxy=true.
    app = started_api_server._app  # type: ignore[attr-defined]
    _patch_recipe_via_proxy(app, "hermes", via_proxy=True)

    agent_id = await _seed_agent_with_recipe(
        db_pool, authenticated_cookie["_user_id"], recipe_name="hermes",
    )

    r = await started_api_server.post(
        f"/v1/agents/{agent_id}/start",
        json={"channel": "inapp", "channel_inputs": {}},
        headers={
            "Authorization": f"Bearer {_TEST_BYOK_KEY}",
            "Cookie": authenticated_cookie["Cookie"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # Validator was called exactly once with the BYOK key.
    assert or_route.called
    assert or_route.call_count == 1
    sent = or_route.calls.last.request
    assert sent.headers["Authorization"] == f"Bearer {_TEST_BYOK_KEY}"

    # Row has provider + encrypted blob.
    container_row_id = UUID(body["container_row_id"])
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT upstream_provider, provider_key_enc
            FROM agent_containers
            WHERE id = $1
            """,
            container_row_id,
        )
    assert row is not None
    assert row["upstream_provider"] == "openrouter"
    assert row["provider_key_enc"] is not None
    assert len(bytes(row["provider_key_enc"])) > 0

    # Cache is populated.
    cache = app.state.proxy_byok_cache
    user_uuid = UUID(authenticated_cookie["_user_id"])
    got = await cache.get(user_uuid, agent_id)
    assert got == ("openrouter", _TEST_BYOK_KEY), (
        f"cache miss/wrong: {got!r}"
    )


# ---------------------------------------------------------------------------
# Test 2 — Validator 401: deploy returns 401, no row inserted
# ---------------------------------------------------------------------------


@respx.mock
async def test_via_proxy_validator_401_blocks_deploy(
    started_api_server, db_pool, authenticated_cookie, monkeypatch,
) -> None:
    """A 401 from the validator MUST short-circuit the deploy with a
    401 envelope. NO agent_containers row is inserted (provider_key_enc
    encryption + insert_pending_agent_container both skipped).
    """
    respx.get("https://openrouter.ai/api/v1/key").mock(
        return_value=httpx.Response(401, json={"error": {"message": "bad key"}}),
    )

    import api_server.routes.agent_lifecycle as al
    monkeypatch.setattr(al, "execute_persistent_start", _make_fake_runner())

    app = started_api_server._app  # type: ignore[attr-defined]
    _patch_recipe_via_proxy(app, "hermes", via_proxy=True)

    agent_id = await _seed_agent_with_recipe(
        db_pool, authenticated_cookie["_user_id"], recipe_name="hermes",
    )

    r = await started_api_server.post(
        f"/v1/agents/{agent_id}/start",
        json={"channel": "inapp", "channel_inputs": {}},
        headers={
            "Authorization": f"Bearer {_TEST_BYOK_KEY}",
            "Cookie": authenticated_cookie["Cookie"],
        },
    )
    assert r.status_code == 401, r.text
    body = r.json()
    assert body["error"]["code"] == "UNAUTHORIZED"
    assert "BYOK key rejected by upstream" in body["error"]["message"]

    # No agent_containers row.
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id FROM agent_containers WHERE agent_instance_id = $1",
            agent_id,
        )
    assert rows == [], (
        f"unexpected agent_containers row(s) inserted on 401 path: {rows!r}"
    )


# ---------------------------------------------------------------------------
# Test 3 — Validator network failure → 503
# ---------------------------------------------------------------------------


@respx.mock
async def test_via_proxy_validator_network_failure_returns_503(
    started_api_server, db_pool, authenticated_cookie, monkeypatch,
) -> None:
    """An httpx.ConnectError from the validator MUST surface as a 503
    INFRA_UNAVAILABLE envelope (NOT a 401), so the client distinguishes
    "key invalid" from "upstream unreachable".
    """
    respx.get("https://openrouter.ai/api/v1/key").mock(
        side_effect=httpx.ConnectError("simulated upstream down"),
    )

    import api_server.routes.agent_lifecycle as al
    monkeypatch.setattr(al, "execute_persistent_start", _make_fake_runner())

    app = started_api_server._app  # type: ignore[attr-defined]
    _patch_recipe_via_proxy(app, "hermes", via_proxy=True)

    agent_id = await _seed_agent_with_recipe(
        db_pool, authenticated_cookie["_user_id"], recipe_name="hermes",
    )

    r = await started_api_server.post(
        f"/v1/agents/{agent_id}/start",
        json={"channel": "inapp", "channel_inputs": {}},
        headers={
            "Authorization": f"Bearer {_TEST_BYOK_KEY}",
            "Cookie": authenticated_cookie["Cookie"],
        },
    )
    assert r.status_code == 503, r.text
    body = r.json()
    assert body["error"]["code"] == "INFRA_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Test 4 — Unknown api_key env var → 400
# ---------------------------------------------------------------------------


async def test_via_proxy_unknown_api_key_env_var_returns_400(
    started_api_server, db_pool, authenticated_cookie, monkeypatch,
) -> None:
    """A recipe that flips via_proxy=true AND declares an
    api_key env var that's NOT in ENV_TO_PROVIDER (e.g. 'BOGUS_KEY')
    must return 400 INVALID_REQUEST. derive_provider raises ValueError
    on unknown env var; the route catches it.
    """
    import api_server.routes.agent_lifecycle as al
    monkeypatch.setattr(al, "execute_persistent_start", _make_fake_runner())

    app = started_api_server._app  # type: ignore[attr-defined]
    # Mutate the hermes recipe with bogus env var + via_proxy=true.
    recipe = deepcopy(app.state.recipes["hermes"])
    runtime = recipe["runtime"]
    runtime["via_proxy"] = True
    runtime["process_env"]["api_key"] = "BOGUS_KEY"
    app.state.recipes["hermes"] = recipe

    agent_id = await _seed_agent_with_recipe(
        db_pool, authenticated_cookie["_user_id"], recipe_name="hermes",
    )

    r = await started_api_server.post(
        f"/v1/agents/{agent_id}/start",
        json={"channel": "inapp", "channel_inputs": {}},
        headers={
            "Authorization": f"Bearer {_TEST_BYOK_KEY}",
            "Cookie": authenticated_cookie["Cookie"],
        },
    )
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert "BOGUS_KEY" in body["error"]["message"]


# ---------------------------------------------------------------------------
# Test 5 — Encrypted blob round-trips (decrypt yields the original key)
# ---------------------------------------------------------------------------


@respx.mock
async def test_via_proxy_encrypted_blob_round_trips(
    started_api_server, db_pool, authenticated_cookie, monkeypatch,
) -> None:
    """After a successful via_proxy=true deploy, fetch the row and
    decrypt provider_key_enc — the decrypted dict's 'key' field must
    equal the original BYOK key. Proves the at-rest encryption is
    correct (PROBE-VAL-07 round-trip applied to the deploy path).
    """
    respx.get("https://openrouter.ai/api/v1/key").mock(
        return_value=httpx.Response(200, json={"data": {}}),
    )

    import api_server.routes.agent_lifecycle as al
    monkeypatch.setattr(al, "execute_persistent_start", _make_fake_runner())

    app = started_api_server._app  # type: ignore[attr-defined]
    _patch_recipe_via_proxy(app, "hermes", via_proxy=True)

    agent_id = await _seed_agent_with_recipe(
        db_pool, authenticated_cookie["_user_id"], recipe_name="hermes",
    )

    r = await started_api_server.post(
        f"/v1/agents/{agent_id}/start",
        json={"channel": "inapp", "channel_inputs": {}},
        headers={
            "Authorization": f"Bearer {_TEST_BYOK_KEY}",
            "Cookie": authenticated_cookie["Cookie"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()

    container_row_id = UUID(body["container_row_id"])
    user_uuid = UUID(authenticated_cookie["_user_id"])
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT provider_key_enc FROM agent_containers WHERE id = $1",
            container_row_id,
        )
    assert row is not None
    blob = bytes(row["provider_key_enc"])
    decrypted = decrypt_channel_config(user_uuid, blob)
    assert decrypted == {"key": _TEST_BYOK_KEY}, (
        f"round-trip failed: {decrypted!r}"
    )


# ---------------------------------------------------------------------------
# Test 6 — BYOK key never in caplog on 401 path (T-29-01 / Gate 6)
# ---------------------------------------------------------------------------


@respx.mock
async def test_byok_key_never_in_caplog_on_401(
    started_api_server, db_pool, authenticated_cookie, monkeypatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Acceptance Gate 6 invariant: even when the validator returns 401
    and the route logs the failure, the BYOK key MUST NOT appear in
    caplog.text. Defense-in-depth verification of the redaction path.
    """
    respx.get("https://openrouter.ai/api/v1/key").mock(
        return_value=httpx.Response(401, json={"error": {}}),
    )

    import api_server.routes.agent_lifecycle as al
    monkeypatch.setattr(al, "execute_persistent_start", _make_fake_runner())

    app = started_api_server._app  # type: ignore[attr-defined]
    _patch_recipe_via_proxy(app, "hermes", via_proxy=True)

    agent_id = await _seed_agent_with_recipe(
        db_pool, authenticated_cookie["_user_id"], recipe_name="hermes",
    )

    secret_byok = "sk-or-v1-LEAKMARKER-401-zzzzzzzzzzz"
    with caplog.at_level(
        logging.DEBUG, logger="api_server.agent_lifecycle",
    ):
        r = await started_api_server.post(
            f"/v1/agents/{agent_id}/start",
            json={"channel": "inapp", "channel_inputs": {}},
            headers={
                "Authorization": f"Bearer {secret_byok}",
                "Cookie": authenticated_cookie["Cookie"],
            },
        )
    assert r.status_code == 401, r.text
    # The BYOK key must not appear in the captured log text.
    assert secret_byok not in caplog.text, (
        f"BYOK key leaked to logs: {caplog.text!r}"
    )
    assert "LEAKMARKER" not in caplog.text, (
        f"BYOK marker leaked to logs: {caplog.text!r}"
    )


# ---------------------------------------------------------------------------
# Test 7 — GATE-7 INVARIANT: legacy recipe (via_proxy=false) skips validator
# ---------------------------------------------------------------------------


@respx.mock
async def test_legacy_recipe_skips_validator_entirely(
    started_api_server, db_pool, authenticated_cookie, monkeypatch,
) -> None:
    """When recipe.runtime.via_proxy is False/missing:

      - validator upstream is NOT called (respx call_count == 0)
      - agent_containers.upstream_provider IS NULL
      - agent_containers.provider_key_enc IS NULL
      - proxy_byok_cache.get(...) returns (None, None)

    Plan 09 Gate 7 acceptance test passes by construction because of
    the via_proxy gate's short-circuit semantics.
    """
    # Set up the respx route — but we expect it NOT to be hit.
    or_route = respx.get("https://openrouter.ai/api/v1/key").mock(
        return_value=httpx.Response(200, json={"data": {}}),
    )

    import api_server.routes.agent_lifecycle as al
    monkeypatch.setattr(al, "execute_persistent_start", _make_fake_runner())

    app = started_api_server._app  # type: ignore[attr-defined]
    # Make sure via_proxy is explicitly False (or absent — the gate
    # treats both as legacy). hermes' on-disk recipe has no via_proxy.
    _patch_recipe_via_proxy(app, "hermes", via_proxy=False)

    agent_id = await _seed_agent_with_recipe(
        db_pool, authenticated_cookie["_user_id"], recipe_name="hermes",
    )

    r = await started_api_server.post(
        f"/v1/agents/{agent_id}/start",
        json={"channel": "inapp", "channel_inputs": {}},
        headers={
            "Authorization": f"Bearer {_TEST_BYOK_KEY}",
            "Cookie": authenticated_cookie["Cookie"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # No validator call.
    assert or_route.call_count == 0, (
        f"validator hit on legacy path: {or_route.call_count} calls"
    )

    container_row_id = UUID(body["container_row_id"])
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT upstream_provider, provider_key_enc
            FROM agent_containers
            WHERE id = $1
            """,
            container_row_id,
        )
    assert row["upstream_provider"] is None
    assert row["provider_key_enc"] is None

    # Cache has no entry for this agent.
    cache = app.state.proxy_byok_cache
    user_uuid = UUID(authenticated_cookie["_user_id"])
    got = await cache.get(user_uuid, agent_id)
    assert got == (None, None), f"cache should be empty for legacy path: {got!r}"


# ---------------------------------------------------------------------------
# Test 8 — GATE-7 INVARIANT: legacy + bogus key still 200s (no validation)
# ---------------------------------------------------------------------------


@respx.mock
async def test_legacy_recipe_with_bogus_key_still_succeeds(
    started_api_server, db_pool, authenticated_cookie, monkeypatch,
) -> None:
    """The "legacy path doesn't validate" invariant. A deliberately
    bogus BYOK key with via_proxy=False MUST still produce a 200
    deploy — the existing key-in-env code path is unchanged.

    Counter-example check for the via_proxy gate: if the gate's
    conditional ever short-circuits in the wrong direction, this test
    catches it because:
      - the bogus key would FAIL a real upstream probe → 401
      - but the legacy path doesn't probe at all → 200

    Combined with Test 7 (no respx call), this proves the via_proxy
    gate genuinely skips the entire validation block for legacy recipes.
    """
    # Stub a 401 — would block the deploy if it were called.
    or_route = respx.get("https://openrouter.ai/api/v1/key").mock(
        return_value=httpx.Response(401, json={"error": {"message": "no"}}),
    )

    import api_server.routes.agent_lifecycle as al
    monkeypatch.setattr(al, "execute_persistent_start", _make_fake_runner())

    app = started_api_server._app  # type: ignore[attr-defined]
    _patch_recipe_via_proxy(app, "hermes", via_proxy=False)

    agent_id = await _seed_agent_with_recipe(
        db_pool, authenticated_cookie["_user_id"], recipe_name="hermes",
    )

    bogus_key = "sk-or-bogus-deliberately-invalid-zzz"
    r = await started_api_server.post(
        f"/v1/agents/{agent_id}/start",
        json={"channel": "inapp", "channel_inputs": {}},
        headers={
            "Authorization": f"Bearer {bogus_key}",
            "Cookie": authenticated_cookie["Cookie"],
        },
    )
    assert r.status_code == 200, (
        f"legacy path should not validate; got {r.status_code} {r.text}"
    )
    assert or_route.call_count == 0, (
        f"legacy + bogus key probed validator: {or_route.call_count}"
    )

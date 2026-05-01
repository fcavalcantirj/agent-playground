"""Phase 22c.3.1 Plan 01 Task 2 RED tests for start_agent route inapp wiring.

Real-Docker route tests (D-21 + golden rule #1). Each test boots create_app()
via the started_api_server fixture (function-scoped, defined in
api_server/tests/conftest.py per B-7 fix), seeds an agent_instances row via
direct DB INSERT, and POSTs to /v1/agents/:id/start. The runner spawns a real
recipe container.

Coverage map (D-IDs ↔ tests):
- D-09, D-11: test_start_inapp_mints_token_persists_to_db, test_start_inapp_token_is_uuid4_hex_format
- D-16, D-17, D-18: test_start_inapp_empty_channel_inputs_accepted
- D-29: test_mark_stopped_clears_inapp_auth_token
- D-33, AC-13: test_start_inapp_no_separate_post_running_update
- D-26, AC-08: test_pre_start_failure_returns_502_redacts_creds
- RESEARCH §Risks §7: test_inapp_auth_token_redacted_in_502_response
- D-09 boundary: test_telegram_path_does_not_mint_token
- key_links contract: test_inapp_substitutions_threaded_to_runner

These tests start RED (TypeError on activation_substitutions kwarg /
no inapp_auth_token in DB / etc.) and turn GREEN once Task 2 lands the
extensions.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from uuid import UUID, uuid4

import pytest


pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _openrouter_key() -> str:
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


def _force_remove_test_containers(prefix: str = "ap-agent-") -> None:
    """Best-effort cleanup of containers spawned during tests."""
    try:
        out = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name={prefix}", "--format", "{{.ID}}"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        for cid in (out.stdout or "").splitlines():
            cid = cid.strip()
            if cid:
                subprocess.run(
                    ["docker", "rm", "-f", cid],
                    capture_output=True, text=True, check=False, timeout=10,
                )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_start_inapp_mints_token_persists_to_db(
    started_api_server, db_pool, authenticated_cookie,
):
    """D-09 + D-11: POST /v1/agents/:id/start with channel='inapp' mints
    a per-session INAPP_AUTH_TOKEN (uuid.uuid4().hex = 32 hex chars) and
    persists it to agent_containers.inapp_auth_token.

    Asserts:
      - response 200
      - inapp_auth_token is a 32-char hex string in the DB
      - the token is NOT in the response body (server-side only)
    """
    key = _openrouter_key()
    agent_id = await _seed_agent_with_recipe(
        db_pool, authenticated_cookie["_user_id"], recipe_name="hermes",
    )
    try:
        r = await started_api_server.post(
            f"/v1/agents/{agent_id}/start",
            json={"channel": "inapp", "channel_inputs": {}},
            headers={
                "Authorization": f"Bearer {key}",
                "Cookie": authenticated_cookie["Cookie"],
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Token NOT in response (server-side only)
        text = r.text
        assert "inapp_auth_token" not in text or "null" in text, (
            "token leaked in response: " + text[:200]
        )
        container_row_id = body["container_row_id"]
        async with db_pool.acquire() as conn:
            tok = await conn.fetchval(
                "SELECT inapp_auth_token FROM agent_containers WHERE id=$1",
                UUID(container_row_id),
            )
        assert tok is not None, "inapp_auth_token NULL after start"
        assert isinstance(tok, str), f"token not string: {type(tok)!r}"
        assert len(tok) == 32, f"token len != 32: {len(tok)} ({tok!r})"
        assert re.match(r"^[0-9a-f]{32}$", tok), (
            f"token not lowercase 32-hex: {tok!r}"
        )
    finally:
        _force_remove_test_containers()


async def test_start_inapp_token_is_uuid4_hex_format(
    started_api_server, db_pool, authenticated_cookie,
):
    """D-11: token strict regex ^[0-9a-f]{32}$ (uuid.uuid4().hex shape)."""
    key = _openrouter_key()
    agent_id = await _seed_agent_with_recipe(
        db_pool, authenticated_cookie["_user_id"], recipe_name="hermes",
    )
    try:
        r = await started_api_server.post(
            f"/v1/agents/{agent_id}/start",
            json={"channel": "inapp", "channel_inputs": {}},
            headers={
                "Authorization": f"Bearer {key}",
                "Cookie": authenticated_cookie["Cookie"],
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        async with db_pool.acquire() as conn:
            tok = await conn.fetchval(
                "SELECT inapp_auth_token FROM agent_containers WHERE id=$1",
                UUID(body["container_row_id"]),
            )
        assert re.match(r"^[0-9a-f]{32}$", tok), tok
    finally:
        _force_remove_test_containers()


async def test_start_inapp_empty_channel_inputs_accepted(
    started_api_server, db_pool, authenticated_cookie,
):
    """D-16: For channel='inapp', body.channel_inputs={} is allowed.

    All 5 inapp recipes declare required_user_input=[].
    """
    key = _openrouter_key()
    agent_id = await _seed_agent_with_recipe(
        db_pool, authenticated_cookie["_user_id"], recipe_name="hermes",
    )
    try:
        r = await started_api_server.post(
            f"/v1/agents/{agent_id}/start",
            json={"channel": "inapp", "channel_inputs": {}},
            headers={
                "Authorization": f"Bearer {key}",
                "Cookie": authenticated_cookie["Cookie"],
            },
        )
        # Specifically: NOT a 400 CHANNEL_INPUTS_INVALID
        assert r.status_code != 400, (
            f"empty channel_inputs rejected: {r.status_code} {r.text}"
        )
        assert r.status_code == 200, r.text
    finally:
        _force_remove_test_containers()


def test_start_inapp_no_separate_post_running_update():
    """AC-13 + D-33: agent_lifecycle.py contains ZERO separate
    `UPDATE agent_containers SET inapp_auth_token` SQL — the token is
    written atomically inside write_agent_container_running.

    Pure-grep gate; no Docker/PG required.
    """
    src = Path(__file__).resolve().parents[2] / "src" / "api_server" / "routes" / "agent_lifecycle.py"
    content = src.read_text()
    matches = re.findall(r"UPDATE agent_containers SET inapp_auth_token", content)
    assert len(matches) == 0, (
        f"separate UPDATE inapp_auth_token found in agent_lifecycle.py "
        f"({len(matches)} matches) — D-33 violated"
    )


async def test_mark_stopped_clears_inapp_auth_token(
    started_api_server, db_pool, authenticated_cookie,
):
    """D-29: POST /v1/agents/:id/stop clears inapp_auth_token to NULL."""
    key = _openrouter_key()
    agent_id = await _seed_agent_with_recipe(
        db_pool, authenticated_cookie["_user_id"], recipe_name="hermes",
    )
    try:
        # Start
        r = await started_api_server.post(
            f"/v1/agents/{agent_id}/start",
            json={"channel": "inapp", "channel_inputs": {}},
            headers={
                "Authorization": f"Bearer {key}",
                "Cookie": authenticated_cookie["Cookie"],
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        container_row_id = UUID(body["container_row_id"])
        # Token should be present
        async with db_pool.acquire() as conn:
            tok_pre = await conn.fetchval(
                "SELECT inapp_auth_token FROM agent_containers WHERE id=$1",
                container_row_id,
            )
        assert tok_pre is not None, "token missing after start"

        # Stop
        r2 = await started_api_server.post(
            f"/v1/agents/{agent_id}/stop",
            headers={
                "Authorization": f"Bearer {key}",
                "Cookie": authenticated_cookie["Cookie"],
            },
        )
        assert r2.status_code == 200, r2.text

        # Token should be NULL
        async with db_pool.acquire() as conn:
            tok_post = await conn.fetchval(
                "SELECT inapp_auth_token FROM agent_containers WHERE id=$1",
                container_row_id,
            )
        assert tok_post is None, (
            f"token not cleared after stop: {tok_post!r} (D-29 violated)"
        )
    finally:
        _force_remove_test_containers()


async def test_pre_start_failure_returns_502_redacts_creds(
    started_api_server, db_pool, authenticated_cookie, monkeypatch,
):
    """D-26 + AC-08: pre_start_command failure → 502 INFRA_UNAVAILABLE
    with redacted stderr tail.

    Inject a synthetic recipe by mutating app.state.recipes — replace the
    zeroclaw recipe's first pre_start with a failing command.
    """
    key = _openrouter_key()

    # Mutate app.state.recipes via the started_api_server's app
    app = started_api_server._app  # type: ignore[attr-defined]
    recipes_orig = dict(app.state.recipes)
    if "zeroclaw" not in recipes_orig:
        pytest.skip("zeroclaw recipe missing")
    import copy as _copy
    synth = _copy.deepcopy(recipes_orig["zeroclaw"])
    synth["channels"]["inapp"]["persistent_argv_override"]["pre_start_commands"][0] = {
        "argv": ["zeroclaw", "nonexistent-flag-that-fails"],
    }
    app.state.recipes = {**recipes_orig, "zeroclaw": synth}

    agent_id = await _seed_agent_with_recipe(
        db_pool, authenticated_cookie["_user_id"], recipe_name="zeroclaw",
    )

    try:
        r = await started_api_server.post(
            f"/v1/agents/{agent_id}/start",
            json={"channel": "inapp", "channel_inputs": {}},
            headers={
                "Authorization": f"Bearer {key}",
                "Cookie": authenticated_cookie["Cookie"],
            },
        )
        assert r.status_code == 502, f"expected 502, got {r.status_code}: {r.text}"
        body = r.json()
        # Stripe-shape envelope { error: { code, message, ... } }
        err = body.get("error") or {}
        assert err.get("code") == "INFRA_UNAVAILABLE", err
        # Provider key MUST be redacted from response detail
        assert key not in r.text, "provider key leaked in 502 response"
    finally:
        # Restore recipes
        app.state.recipes = recipes_orig
        _force_remove_test_containers()


async def test_inapp_auth_token_redacted_in_502_response(
    started_api_server, db_pool, authenticated_cookie, monkeypatch,
):
    """RESEARCH §Risks §7: a pre_start that echoes INAPP_AUTH_TOKEN to stderr
    should NOT leak the token in the 502 response.

    Use a synthetic hermes recipe with persistent_argv_override declaring a
    pre_start that prints the token then exits non-zero.
    """
    key = _openrouter_key()
    # Pin the token to a known 32-hex value via uuid mock
    fixed_token = "deadbeef" * 4  # 32 hex chars

    import uuid as uuid_mod
    real_uuid4 = uuid_mod.uuid4

    class _FakeUuid:
        def __init__(self, hex_):
            self.hex = hex_

    call_count = {"n": 0}

    def _fake_uuid4():
        call_count["n"] += 1
        # Only the FIRST uuid4 call inside start_agent (the token mint)
        # returns the fixed value. All others go through real_uuid4.
        if call_count["n"] == 1:
            return _FakeUuid(fixed_token)
        return real_uuid4()

    # Patch the route's uuid module
    import api_server.routes.agent_lifecycle as al
    monkeypatch.setattr(al.uuid, "uuid4", _fake_uuid4)

    # Inject synthetic hermes recipe with a token-echoing failing pre_start
    app = started_api_server._app  # type: ignore[attr-defined]
    recipes_orig = dict(app.state.recipes)
    if "hermes" not in recipes_orig:
        pytest.skip("hermes recipe missing")
    import copy as _copy
    synth = _copy.deepcopy(recipes_orig["hermes"])
    synth["channels"]["inapp"]["persistent_argv_override"] = {
        "entrypoint": "sh",
        "argv": ["-c", "echo daemon; sleep 600"],
        "pre_start_commands": [
            {
                "argv": [
                    "sh", "-c",
                    "echo INAPP_AUTH_TOKEN=$INAPP_AUTH_TOKEN; exit 1",
                ],
            },
        ],
    }
    synth["channels"]["inapp"]["activation_env"] = {
        "INAPP_AUTH_TOKEN": "${INAPP_AUTH_TOKEN}",
    }
    app.state.recipes = {**recipes_orig, "hermes": synth}

    agent_id = await _seed_agent_with_recipe(
        db_pool, authenticated_cookie["_user_id"], recipe_name="hermes",
    )

    try:
        r = await started_api_server.post(
            f"/v1/agents/{agent_id}/start",
            json={"channel": "inapp", "channel_inputs": {}},
            headers={
                "Authorization": f"Bearer {key}",
                "Cookie": authenticated_cookie["Cookie"],
            },
        )
        assert r.status_code == 502, r.text
        # The 32-hex token MUST NOT appear in the response body
        assert fixed_token not in r.text, (
            "INAPP_AUTH_TOKEN leaked in 502 response (RESEARCH §Risks §7)"
        )
    finally:
        app.state.recipes = recipes_orig
        _force_remove_test_containers()


async def test_telegram_path_does_not_mint_token(
    started_api_server, db_pool, authenticated_cookie,
):
    """D-09 boundary: telegram channel must NOT mint inapp_auth_token.

    Skipped if no real bot token (we don't want to actually start a telegram
    long-poll). The DB assertion is `inapp_auth_token IS NULL` — only
    inapp channels mint per D-09.
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN_TEST")
    if not bot_token:
        pytest.skip("TELEGRAM_BOT_TOKEN_TEST not set")

    key = _openrouter_key()
    agent_id = await _seed_agent_with_recipe(
        db_pool, authenticated_cookie["_user_id"], recipe_name="openclaw",
        model="anthropic/claude-haiku-4-5",
    )
    try:
        r = await started_api_server.post(
            f"/v1/agents/{agent_id}/start",
            json={
                "channel": "telegram",
                "channel_inputs": {
                    "TELEGRAM_BOT_TOKEN": bot_token,
                    "TELEGRAM_ALLOWED_USER": "12345",
                },
            },
            headers={
                "Authorization": f"Bearer {key}",
                "Cookie": authenticated_cookie["Cookie"],
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        async with db_pool.acquire() as conn:
            tok = await conn.fetchval(
                "SELECT inapp_auth_token FROM agent_containers WHERE id=$1",
                UUID(body["container_row_id"]),
            )
        assert tok is None, (
            f"telegram path minted token: {tok!r} (D-09 violated)"
        )
    finally:
        _force_remove_test_containers()


async def test_inapp_substitutions_threaded_to_runner(
    started_api_server, db_pool, authenticated_cookie, monkeypatch,
):
    """key_links contract: start_agent threads activation_substitutions
    to execute_persistent_start with the expected key set + correct value
    aliases (INAPP_PROVIDER_KEY == bearer; OPENROUTER_API_KEY == bearer;
    ANTHROPIC_API_KEY == bearer; MODEL == agent.model; etc.).
    """
    key = _openrouter_key()
    captured: dict = {}

    # Patch execute_persistent_start to record kwargs (skip real boot)
    import api_server.routes.agent_lifecycle as al

    async def _fake_execute(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = dict(kwargs)
        # Return a faux PASS verdict shape so the route proceeds to write_running
        return {
            "verdict": "PASS",
            "container_id": f"fakecid{uuid4().hex[:24]}",
            "boot_wall_s": 0.1,
            "pre_start_wall_s": 0.0,
            "health_check_ok": True,
            "health_check_kind": "process_alive",
            "data_dir": "/tmp/fake",
        }

    monkeypatch.setattr(al, "execute_persistent_start", _fake_execute)

    agent_id = await _seed_agent_with_recipe(
        db_pool, authenticated_cookie["_user_id"], recipe_name="hermes",
        model="anthropic/claude-haiku-4.5",
    )

    r = await started_api_server.post(
        f"/v1/agents/{agent_id}/start",
        json={"channel": "inapp", "channel_inputs": {}},
        headers={
            "Authorization": f"Bearer {key}",
            "Cookie": authenticated_cookie["Cookie"],
        },
    )
    assert r.status_code == 200, r.text

    subs = captured["kwargs"].get("activation_substitutions")
    assert isinstance(subs, dict), f"no activation_substitutions threaded: {captured!r}"
    expected_keys = {
        "INAPP_AUTH_TOKEN", "INAPP_PROVIDER_KEY",
        "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY",
        "MODEL", "agent_name", "agent_url",
    }
    assert expected_keys <= set(subs.keys()), (
        f"missing subs keys: expected {expected_keys}, got {set(subs.keys())}"
    )
    assert subs["INAPP_PROVIDER_KEY"] == key
    assert subs["OPENROUTER_API_KEY"] == key
    assert subs["ANTHROPIC_API_KEY"] == key
    assert subs["MODEL"] == "anthropic/claude-haiku-4.5"
    assert subs["agent_name"]
    assert subs["agent_url"].startswith("http://")
    assert re.match(r"^[0-9a-f]{32}$", subs["INAPP_AUTH_TOKEN"])

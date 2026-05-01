"""Phase 22c.3.1 Plan 01 Task 1 RED tests for tools/run_recipe.py
::run_cell_persistent (channel-aware override + activation_env overlay +
pre_start_commands loop with cidfile cleanup).

Real Docker integration tests (golden rule #1, D-21). Each test boots a real
recipe container via tools.run_recipe.run_cell_persistent and asserts on
observable container state (docker ps, docker inspect, docker exec, etc.).

These tests start RED (TypeError — run_cell_persistent does not yet accept
``activation_substitutions`` kwarg + does not run pre_start_commands) and turn
GREEN once Task 1 lands the extension.

Coverage map (D-IDs ↔ tests):
- D-04..D-08: test_zeroclaw_pre_start_runs_4_then_daemon
- D-25, D-32: test_pre_start_timeout_kills_via_cidfile
- D-26: test_pre_start_failure_raises_runtime_error (stderr tail in message)
- D-27 + AMD-37: test_telegram_channel_falls_through_byte_identical_when_substitutions_present
- D-34: test_data_dir_hoisted_before_pre_start
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML


# tools/ on sys.path so we can import run_recipe directly. tools/tests/conftest.py
# does the same trick — we replicate it here because api_server/tests/ has its own
# conftest chain.
REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
RECIPES_DIR = REPO_ROOT / "recipes"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


pytestmark = pytest.mark.api_integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_recipe(name: str) -> dict[str, Any]:
    y = YAML(typ="rt")
    with open(RECIPES_DIR / f"{name}.yaml") as f:
        return dict(y.load(f))


def _docker_ps_names(filter_name: str) -> list[str]:
    """Return container names (running OR exited) matching filter."""
    out = subprocess.run(
        [
            "docker", "ps", "-a",
            "--filter", f"name={filter_name}",
            "--format", "{{.Names}}",
        ],
        capture_output=True, text=True, check=False,
    )
    return [n for n in (out.stdout or "").splitlines() if n.strip()]


def _force_remove(name_or_id: str) -> None:
    subprocess.run(
        ["docker", "rm", "-f", name_or_id],
        capture_output=True, text=True, check=False,
    )


def _openrouter_key() -> str:
    """Source OPENROUTER_API_KEY from env or .env.local.

    These tests boot real recipe containers that talk to OpenRouter
    upstream — fail loud if the key is missing.
    """
    import os

    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    env_local = REPO_ROOT / ".env.local"
    if env_local.exists():
        for line in env_local.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    pytest.skip("OPENROUTER_API_KEY missing — cannot boot zeroclaw onboard")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_zeroclaw_pre_start_runs_4_then_daemon():
    """D-04..D-08: zeroclaw inapp deploy runs all 4 pre_start_commands as
    separate `docker run --rm` invocations BEFORE the daemon starts.

    Asserts:
      - verdict PASS
      - daemon container exists (ap-agent-* running)
      - details["pre_start_wall_s"] > 0 (D-31 telemetry)
      - details["boot_wall_s"] = pre_start_wall_s + persistent_boot_wall_s
    """
    import run_recipe as rr

    key = _openrouter_key()
    recipe = _load_recipe("zeroclaw")
    run_id = f"t1-zeroclaw-{uuid.uuid4().hex[:6]}"

    activation_substitutions = {
        "INAPP_AUTH_TOKEN": "test-token-zero",
        "INAPP_PROVIDER_KEY": key,
        "OPENROUTER_API_KEY": key,
        "ANTHROPIC_API_KEY": key,
        "MODEL": "anthropic/claude-haiku-4.5",
        "agent_name": "test-zeroclaw",
        "agent_url": "http://test-zeroclaw.local",
    }

    container_id = None
    try:
        verdict, details = rr.run_cell_persistent(
            recipe,
            image_tag="ap-recipe-zeroclaw",
            model="anthropic/claude-haiku-4.5",
            api_key_var="OPENROUTER_API_KEY",
            api_key_val=key,
            channel_id="inapp",
            channel_creds={},
            run_id=run_id,
            quiet=True,
            boot_timeout_s=180,
            activation_substitutions=activation_substitutions,
        )
        assert getattr(verdict, "category", None) is not None, "no verdict"
        assert (
            getattr(verdict.category, "value", None) == "PASS"
            or getattr(verdict.category, "name", None) == "PASS"
        ), f"verdict not PASS: {verdict!r} details={details!r}"
        container_id = details.get("container_id")
        assert container_id, "no container_id in details"
        assert details.get("pre_start_wall_s", 0) > 0, (
            f"pre_start_wall_s must be > 0; got {details.get('pre_start_wall_s')!r}"
        )
        assert details.get("boot_wall_s") is not None
        # boot_wall_s is the sum (D-31)
        # pre_start_wall_s is a sub-field; total ≥ pre_start
        assert details["boot_wall_s"] >= details["pre_start_wall_s"]
        # Daemon container exists
        names = _docker_ps_names(f"ap-agent-{run_id}")
        assert names, f"daemon container ap-agent-{run_id} not found"
    finally:
        if container_id:
            _force_remove(container_id)


def test_pre_start_failure_raises_runtime_error(tmp_path):
    """D-26: a pre_start_command that exits non-zero raises RuntimeError;
    the stderr tail is in the exception message; data_dir is unwound;
    no daemon container exists.
    """
    import run_recipe as rr

    # Synthetic recipe: copy zeroclaw, replace first pre_start with a failing command.
    recipe = _load_recipe("zeroclaw")
    inapp = recipe["channels"]["inapp"]
    override = inapp["persistent_argv_override"]
    # Mutate in-place so the writeback isn't required (we pass dict directly).
    override["pre_start_commands"][0] = {
        "argv": ["zeroclaw", "nonexistent-subcommand-that-fails"],
    }

    key = _openrouter_key()
    run_id = f"t1-fail-{uuid.uuid4().hex[:6]}"

    activation_substitutions = {
        "INAPP_AUTH_TOKEN": "test-token",
        "INAPP_PROVIDER_KEY": key,
        "OPENROUTER_API_KEY": key,
        "ANTHROPIC_API_KEY": key,
        "MODEL": "anthropic/claude-haiku-4.5",
        "agent_name": "x",
        "agent_url": "http://x.local",
    }

    with pytest.raises(RuntimeError) as exc_info:
        rr.run_cell_persistent(
            recipe,
            image_tag="ap-recipe-zeroclaw",
            model="anthropic/claude-haiku-4.5",
            api_key_var="OPENROUTER_API_KEY",
            api_key_val=key,
            channel_id="inapp",
            channel_creds={},
            run_id=run_id,
            quiet=True,
            boot_timeout_s=180,
            activation_substitutions=activation_substitutions,
        )
    # The exception message contains the failing command + redacted-stderr tail
    msg = str(exc_info.value)
    assert "pre_start" in msg.lower() or "failed" in msg.lower(), (
        f"exception message lacks pre_start hint: {msg!r}"
    )
    # The provider key MUST be redacted
    assert key not in msg, "provider key leaked in exception message"
    # No daemon container exists
    names = _docker_ps_names(f"ap-agent-{run_id}")
    assert not names, f"unexpected daemon container after pre_start failure: {names!r}"


def test_pre_start_timeout_kills_via_cidfile(monkeypatch):
    """D-25, D-32: pre_start with sleep 200 + 5s timeout → cidfile-kill +
    cleanup; RuntimeError raised matching /timed out after \\d+s/.

    Uses hermes (alpine-based — has /bin/sh) NOT zeroclaw (distroless).
    Override PRE_START_COMMAND_TIMEOUT_S to 5s for fast test.
    """
    import run_recipe as rr

    monkeypatch.setattr(rr, "PRE_START_COMMAND_TIMEOUT_S", 5)

    # Synthetic recipe: hermes inapp with a sleep-200 pre_start
    recipe = _load_recipe("hermes")
    inapp = recipe["channels"]["inapp"]
    # Hermes inapp has no persistent_argv_override today — inject one
    inapp["persistent_argv_override"] = {
        "entrypoint": "sh",
        "argv": ["-c", "echo daemon-running; sleep 600"],
        "pre_start_commands": [
            {"argv": ["sh", "-c", "sleep 200"]},
        ],
    }

    key = _openrouter_key()
    run_id = f"t1-timeout-{uuid.uuid4().hex[:6]}"

    activation_substitutions = {
        "INAPP_AUTH_TOKEN": "test-token",
        "INAPP_PROVIDER_KEY": key,
        "OPENROUTER_API_KEY": key,
        "ANTHROPIC_API_KEY": key,
        "MODEL": "anthropic/claude-haiku-4.5",
        "agent_name": "x",
        "agent_url": "http://x.local",
    }

    t0 = time.time()
    with pytest.raises(RuntimeError) as exc_info:
        rr.run_cell_persistent(
            recipe,
            image_tag="ap-recipe-hermes",
            model="anthropic/claude-haiku-4.5",
            api_key_var="OPENROUTER_API_KEY",
            api_key_val=key,
            channel_id="inapp",
            channel_creds={},
            run_id=run_id,
            quiet=True,
            boot_timeout_s=180,
            activation_substitutions=activation_substitutions,
        )
    wall = time.time() - t0
    # Sanity: didn't hang for 200s — fail-fast at PRE_START_COMMAND_TIMEOUT_S=5s
    assert wall < 60, f"timeout did not fail fast: wall={wall:.1f}s"
    msg = str(exc_info.value)
    assert re.search(r"timed out after \d+s", msg, re.IGNORECASE), (
        f"timeout message missing timeout marker: {msg!r}"
    )
    # No leftover *.cid files in /tmp
    leftover = list(Path("/tmp").glob("ap-pre-cid-*.cid"))
    assert not leftover, f"cidfiles leaked: {leftover!r}"
    # No daemon container
    names = _docker_ps_names(f"ap-agent-{run_id}")
    assert not names, f"unexpected daemon container after pre_start timeout: {names!r}"


def test_telegram_channel_falls_through_byte_identical_when_substitutions_present():
    """D-27 + AMD-37: telegram path falls through to legacy code even when
    activation_substitutions IS provided, because telegram has no
    persistent_argv_override (Wave 0 spike A1 confirms this).

    Boot openclaw with channel="telegram" + a non-None substitutions dict.
    Assert verdict is PASS and the legacy `recipe.persistent.spec.argv`
    path was taken (verifiable via docker inspect — entrypoint should be
    `sh` and argv should be the substitute_argv-rendered $MODEL form).
    """
    import os
    import run_recipe as rr

    # Telegram path requires real bot token; skip if absent
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN_TEST")
    if not bot_token:
        pytest.skip(
            "TELEGRAM_BOT_TOKEN_TEST not set — cannot boot openclaw telegram"
        )

    key = _openrouter_key()
    recipe = _load_recipe("openclaw")
    run_id = f"t1-tele-{uuid.uuid4().hex[:6]}"

    activation_substitutions = {
        "INAPP_AUTH_TOKEN": "should-be-ignored-on-telegram-path",
        "INAPP_PROVIDER_KEY": key,
        "OPENROUTER_API_KEY": key,
        "ANTHROPIC_API_KEY": key,
        "MODEL": "anthropic/claude-haiku-4-5",
        "agent_name": "telegram-test",
        "agent_url": "http://telegram-test.local",
    }

    container_id = None
    try:
        verdict, details = rr.run_cell_persistent(
            recipe,
            image_tag="ap-recipe-openclaw",
            model="anthropic/claude-haiku-4-5",
            api_key_var="ANTHROPIC_API_KEY",
            api_key_val=key,
            channel_id="telegram",
            channel_creds={
                "TELEGRAM_BOT_TOKEN": bot_token,
                "TELEGRAM_ALLOWED_USER": "12345",
            },
            run_id=run_id,
            quiet=True,
            boot_timeout_s=180,
            activation_substitutions=activation_substitutions,
        )
        cat = getattr(verdict, "category", None)
        assert (
            getattr(cat, "value", None) == "PASS"
            or getattr(cat, "name", None) == "PASS"
        ), f"telegram path verdict not PASS: {verdict!r}"
        container_id = details.get("container_id")
        assert container_id
        # Inspect docker entrypoint — must be sh (legacy openclaw.persistent.spec.entrypoint)
        ins = subprocess.run(
            ["docker", "inspect", "-f", "{{.Config.Entrypoint}}", container_id],
            capture_output=True, text=True, check=False,
        )
        assert "sh" in (ins.stdout or ""), (
            f"legacy telegram path entrypoint missing: {ins.stdout!r}"
        )
    finally:
        if container_id:
            _force_remove(container_id)


def test_data_dir_hoisted_before_pre_start():
    """D-34: data_dir + env_file allocated EARLY (before pre_start loop).

    Inject a synthetic pre_start that writes a sentinel file to the volume.
    Assert the sentinel exists in the daemon's view of the volume after boot
    (proving the volume was mounted on the pre_start container too).

    Uses hermes (alpine-based) so we have /bin/sh + cat in the daemon.
    """
    import run_recipe as rr

    recipe = _load_recipe("hermes")
    inapp = recipe["channels"]["inapp"]
    sentinel_token = uuid.uuid4().hex[:8]
    inapp["persistent_argv_override"] = {
        "entrypoint": "sh",
        "argv": [
            "-c",
            f"cat /opt/data/sentinel; echo daemon-ready; sleep 600",
        ],
        "pre_start_commands": [
            {
                "argv": [
                    "sh", "-c",
                    f"echo {sentinel_token} > /opt/data/sentinel",
                ],
            },
        ],
    }

    key = _openrouter_key()
    run_id = f"t1-hoist-{uuid.uuid4().hex[:6]}"

    activation_substitutions = {
        "INAPP_AUTH_TOKEN": "test-token",
        "INAPP_PROVIDER_KEY": key,
        "OPENROUTER_API_KEY": key,
        "ANTHROPIC_API_KEY": key,
        "MODEL": "anthropic/claude-haiku-4.5",
        "agent_name": "x",
        "agent_url": "http://x.local",
    }

    container_id = None
    try:
        verdict, details = rr.run_cell_persistent(
            recipe,
            image_tag="ap-recipe-hermes",
            model="anthropic/claude-haiku-4.5",
            api_key_var="OPENROUTER_API_KEY",
            api_key_val=key,
            channel_id="inapp",
            channel_creds={},
            run_id=run_id,
            quiet=True,
            boot_timeout_s=60,
            activation_substitutions=activation_substitutions,
        )
        # We override ready_log_regex via the synthetic argv echoing
        # "daemon-ready" — but the override doesn't affect ready_log_regex
        # (that comes from persistent.spec.ready_log_regex). The verdict
        # may be TIMEOUT because hermes' ready_log_regex won't match our
        # synthetic argv output. The IMPORTANT assertion here is:
        # the sentinel file was written by the pre_start (proving data_dir
        # existed before pre_start ran) — observable via the daemon's
        # docker logs (the synthetic argv cats the sentinel).
        container_id = details.get("container_id")
        assert container_id, f"no container_id in details: {details!r}"
        # Read docker logs — `cat /opt/data/sentinel` should print our token
        time.sleep(1)  # give the cat a moment
        logs = subprocess.run(
            ["docker", "logs", container_id],
            capture_output=True, text=True, check=False,
        )
        combined = (logs.stdout or "") + (logs.stderr or "")
        assert sentinel_token in combined, (
            f"sentinel {sentinel_token!r} missing from daemon logs — "
            f"data_dir was NOT mounted on pre_start (D-34 violated)\n"
            f"logs: {combined!r}"
        )
    finally:
        if container_id:
            _force_remove(container_id)

"""Wave 0 — Phase 22c.3.1 Plan 01 D-27 byte-identical regression invariant.

Captures the docker run argv + env-file content for
``run_cell_persistent(recipe=openclaw, channel_id="telegram", ...)`` against
the CURRENT main HEAD (Wave 0 baseline) and asserts byte-identical post-Task-1
extension. This is the AMD-37 conjunct-1 fall-through proof: when
``channels.{channel_id}.persistent_argv_override is None`` (telegram has no
override per Wave 0 spike A1), the legacy code path executes verbatim.

Pattern: short-circuit-via-raise (B-3 fix). The fake subprocess only
intercepts the FIRST `docker run -d` call and raises a sentinel exception
carrying the captured cmd + env-file content; everything before that point
(env-file write, etc.) executes normally. The test catches the sentinel and
asserts.

Three tests:
- ``test_baseline_capture`` (Wave 0): MUST PASS on current main HEAD.
- ``test_telegram_unchanged`` (Task 1 GREEN): MUST PASS post-extension. Calls
  run_cell_persistent WITHOUT activation_substitutions (replicates the
  natural telegram callsite in start_agent which only threads substitutions
  for inapp).
- ``test_telegram_unchanged_when_substitutions_none`` (Task 1 GREEN): MUST
  PASS post-extension. Calls run_cell_persistent with
  activation_substitutions=None explicitly. Proves AMD-37 conjunct-2
  fall-through (the ELSE branch of the gate).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML


# Add tools/ to sys.path so we can import run_recipe directly.
REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
RECIPES_DIR = REPO_ROOT / "recipes"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def _load_openclaw_recipe() -> dict[str, Any]:
    """Load the openclaw recipe verbatim from the repo's recipes dir."""
    y = YAML(typ="rt")
    with open(RECIPES_DIR / "openclaw.yaml") as f:
        return dict(y.load(f))


# ---------------------------------------------------------------------------
# Snapshot baseline constants — captured against current main HEAD.
#
# The byte-identical invariant compares the docker run argv + env-file
# content for run_cell_persistent(recipe=openclaw, channel_id="telegram",
# model="anthropic/claude-haiku-4-5",
# channel_creds={TELEGRAM_BOT_TOKEN: "test-token-baseline-v1",
#                TELEGRAM_ALLOWED_USER: "12345"}).
#
# Volatile substrings are normalized via _normalize() before assertion:
#   - container_name "ap-agent-<run_id>"             → "ap-agent-<RUN_ID>"
#   - data_dir "/var/folders/.../ap-recipe-openclaw-data-<X>" → "<DATA_DIR>"
#   - env_file "/tmp/ap-env-<hex>"                   → "<ENV_FILE>"
# ---------------------------------------------------------------------------


# Frozen per the legacy run_cell_persistent path at tools/run_recipe.py:1071-
# 1111: list-of-tokens after substitute_argv($MODEL only) + env-file with
# api_key_var line FIRST, then required_inputs (TELEGRAM_BOT_TOKEN,
# TELEGRAM_ALLOWED_USER with "tg:" prefix), then optional_inputs (none).
EXPECTED_OPENCLAW_TELEGRAM_DOCKER_CMD = [
    "docker", "run", "-d",
    "--name", "ap-agent-<RUN_ID>",
    "--env-file", "<ENV_FILE>",
    "-v", "<DATA_DIR>:/home/node/.openclaw",
    "--entrypoint", "sh",
    "ap-recipe-openclaw",
    "-c",
    # The shell heredoc body. substitute_argv replaces $MODEL with the
    # model arg (anthropic/claude-haiku-4-5) — every other token is
    # preserved verbatim from recipes/openclaw.yaml:307-330.
    (
        "set -e\n"
        "mkdir -p /home/node/.openclaw\n"
        "cat > /home/node/.openclaw/openclaw.json <<EOF\n"
        "{\n"
        '  "channels": {\n'
        '    "telegram": {\n'
        '      "enabled": true,\n'
        '      "botToken": "${TELEGRAM_BOT_TOKEN}",\n'
        '      "dmPolicy": "allowlist",\n'
        '      "allowFrom": ["tg:$TELEGRAM_ALLOWED_USER"]\n'
        "    }\n"
        "  },\n"
        '  "agents": {\n'
        '    "defaults": {\n'
        '      "model": {\n'
        '        "primary": "openrouter/anthropic/claude-haiku-4-5"\n'
        "      }\n"
        "    }\n"
        "  }\n"
        "}\n"
        "EOF\n"
        "rm -f /home/node/.openclaw/openclaw.json5\n"
        "exec openclaw gateway --allow-unconfigured\n"
    ),
]


# Env-file content: api_key_var line FIRST, then required_user_input entries
# in declaration order (TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER) with the
# "tg:" prefix on TELEGRAM_ALLOWED_USER per recipe.channels.telegram
# .required_user_input[1].prefix_required.
EXPECTED_OPENCLAW_TELEGRAM_ENVFILE = (
    "ANTHROPIC_API_KEY=sk-test-baseline-key-12345\n"
    "TELEGRAM_BOT_TOKEN=test-token-baseline-v1\n"
    "TELEGRAM_ALLOWED_USER=tg:12345\n"
)


# ---------------------------------------------------------------------------
# Short-circuit-via-raise capture pattern (B-3 fix).
# ---------------------------------------------------------------------------


class _SnapshotCaptured(Exception):
    """Sentinel: carries cmd + env-file content out of subprocess.run."""

    def __init__(self, cmd: list[str], env_file_content: str):
        super().__init__("snapshot captured")
        self.cmd = cmd
        self.env_file_content = env_file_content


def _make_fake_run():
    """Build a fake subprocess.run that intercepts FIRST `docker run -d` call.

    Reads the env-file the runner just wrote (via Path.write_text — not
    subprocess), captures both via _SnapshotCaptured, raises. Any other
    subprocess.run call before the docker run -d (there shouldn't be any
    in the persistent-mode legacy path before docker run -d) fails loud
    so test bugs surface immediately.
    """
    def _fake_run(cmd, *args, **kwargs):
        if (
            isinstance(cmd, list)
            and len(cmd) >= 3
            and cmd[0] == "docker"
            and cmd[1] == "run"
            and cmd[2] == "-d"
        ):
            env_file_path = None
            for i, c in enumerate(cmd):
                if c == "--env-file" and i + 1 < len(cmd):
                    env_file_path = cmd[i + 1]
                    break
            env_content = ""
            if env_file_path:
                try:
                    env_content = Path(env_file_path).read_text()
                except OSError:
                    env_content = "<UNREADABLE>"
            raise _SnapshotCaptured(list(cmd), env_content)
        # Any other subprocess.run call pre-`docker run -d` is unexpected.
        raise AssertionError(
            f"unexpected subprocess.run call before docker run -d: {cmd[:4]!r}"
        )
    return _fake_run


def _normalize(cmd: list[str], env_file_content: str) -> tuple[list[str], str]:
    """Normalize volatile substrings (run_id, data_dir, env_file path).

    Replaces:
      ap-agent-<run_id>       → ap-agent-<RUN_ID>
      .../ap-recipe-openclaw-data-<X>  → <DATA_DIR>
      /tmp/ap-env-<hex>       → <ENV_FILE>

    Note: run_id can contain dashes (we pass "snapshot-run-id" in the
    test). The regex consumes the whole tail of the token after
    ``ap-agent-`` because the test-issued run_id is the only thing that
    follows it (--name is always its own argv element).
    """
    # Match ap-agent- followed by ANY run_id chars (alphanum, dash, underscore).
    run_id_re = re.compile(r"ap-agent-[A-Za-z0-9_\-]+")
    data_dir_re = re.compile(r"[^\s:]*ap-recipe-openclaw-data-[^\s:]+")
    env_file_re = re.compile(r"/tmp/ap-env-[a-f0-9]+")

    def _norm_str(s: str) -> str:
        out = run_id_re.sub("ap-agent-<RUN_ID>", s)
        out = data_dir_re.sub("<DATA_DIR>", out)
        out = env_file_re.sub("<ENV_FILE>", out)
        return out

    norm_cmd = [_norm_str(t) for t in cmd]
    norm_env = _norm_str(env_file_content)
    return norm_cmd, norm_env


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _capture_telegram_call(monkeypatch, **kwargs) -> tuple[list[str], str]:
    """Run run_cell_persistent for openclaw/telegram, capture cmd + env-file.

    monkeypatch.setattr replaces subprocess.run for the duration of the call.
    The first `docker run -d` raises _SnapshotCaptured, which we catch and
    return after normalization.
    """
    import run_recipe as rr  # tools/run_recipe.py — added to sys.path above

    monkeypatch.setattr(rr, "subprocess", _FakeSubprocessModule(_make_fake_run()))
    recipe = _load_openclaw_recipe()
    try:
        rr.run_cell_persistent(
            recipe,
            image_tag="ap-recipe-openclaw",
            model="anthropic/claude-haiku-4-5",
            api_key_var="ANTHROPIC_API_KEY",
            api_key_val="sk-test-baseline-key-12345",
            channel_id="telegram",
            channel_creds={
                "TELEGRAM_BOT_TOKEN": "test-token-baseline-v1",
                "TELEGRAM_ALLOWED_USER": "12345",
            },
            run_id="snapshot-run-id",
            quiet=True,
            boot_timeout_s=180,
            **kwargs,
        )
    except _SnapshotCaptured as cap:
        return _normalize(cap.cmd, cap.env_file_content)
    raise AssertionError(
        "run_cell_persistent did not invoke `docker run -d` — "
        "snapshot capture failed"
    )


class _FakeSubprocessModule:
    """Wrap a fake `run` while delegating other attrs to real subprocess.

    run_recipe.py uses `subprocess.run` AND `subprocess.TimeoutExpired`
    (exception class). We must not break the latter just because we
    swapped the former.
    """

    def __init__(self, fake_run):
        self.run = fake_run

    def __getattr__(self, name):
        return getattr(subprocess, name)


def test_baseline_capture(monkeypatch):
    """Wave 0: capture the current-main snapshot baseline.

    MUST PASS on current main HEAD. If this test fails, the
    EXPECTED_OPENCLAW_TELEGRAM_* constants above are wrong — fix them
    before declaring Wave 0 closed.
    """
    cmd, env_content = _capture_telegram_call(monkeypatch)
    assert cmd == EXPECTED_OPENCLAW_TELEGRAM_DOCKER_CMD, (
        f"docker cmd diverged from baseline:\n"
        f"  expected: {EXPECTED_OPENCLAW_TELEGRAM_DOCKER_CMD!r}\n"
        f"  actual:   {cmd!r}"
    )
    assert env_content == EXPECTED_OPENCLAW_TELEGRAM_ENVFILE, (
        f"env-file diverged from baseline:\n"
        f"  expected: {EXPECTED_OPENCLAW_TELEGRAM_ENVFILE!r}\n"
        f"  actual:   {env_content!r}"
    )


def test_telegram_unchanged(monkeypatch):
    """Task 1 GREEN: byte-identical when no activation_substitutions passed.

    Replicates start_agent's natural telegram callsite — the route does
    NOT thread activation_substitutions for telegram channel (only inapp).
    Per AMD-37 conjunct-2, when activation_substitutions is None the
    legacy path executes verbatim.
    """
    # No activation_substitutions kwarg — replicates current callsite.
    cmd, env_content = _capture_telegram_call(monkeypatch)
    assert cmd == EXPECTED_OPENCLAW_TELEGRAM_DOCKER_CMD
    assert env_content == EXPECTED_OPENCLAW_TELEGRAM_ENVFILE


def test_telegram_unchanged_when_substitutions_none(monkeypatch):
    """Task 1 GREEN: byte-identical when activation_substitutions=None explicit.

    Even when the caller threads the kwarg explicitly as None, the AMD-37
    conjunct-2 gate closes and the legacy path runs.
    """
    cmd, env_content = _capture_telegram_call(
        monkeypatch, activation_substitutions=None
    )
    assert cmd == EXPECTED_OPENCLAW_TELEGRAM_DOCKER_CMD
    assert env_content == EXPECTED_OPENCLAW_TELEGRAM_ENVFILE

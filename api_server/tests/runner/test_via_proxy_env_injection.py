"""Phase 29 Plan 08 Task 1 — runner via_proxy env injection.

Covers D-17 + D-18 + AMD-06 + AMD-09:

  - When ``recipe.runtime.via_proxy=true`` the runner STRIPS the real BYOK
    key from the container env and injects:
      * ``AP_PROXY_BASE_URL`` (canonical proxy URL — used by config-file-
        reading bots like nanobot per AMD-09; recipes sh-expand it via
        ``${AP_PROXY_BASE_URL:-https://openrouter.ai/api/v1}`` in JSON
        heredocs)
      * ``OPENAI_BASE_URL`` / ``ANTHROPIC_BASE_URL`` (SDK-conventional
        env var pair)
      * ``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY`` =
        ``ap-proxy-<inapp_auth_token>`` (placeholder validated by the
        proxy route against ``agent_containers``)

  - When ``via_proxy=false`` (or absent) the runner uses the legacy path:
    real BYOK key remains in the env-file, no BASE_URL override, no
    AP_PROXY_BASE_URL — D-27 byte-identical invariant for the existing 5
    non-cutover recipes.

  - Unknown ``runtime.process_env.api_key`` env var raises ``ValueError``
    with the offending var name (closed enum dispatch — D-09 + D-17).

Tests 1-7 are PURE — they exercise the runner's pure-function helpers
(_build_via_proxy_overrides + _build_env_file_content) directly with
synthetic recipe dicts. No Docker, no Postgres. Test 8 is the integration
gate (real ``docker run`` for a stub recipe with via_proxy=true) and is
gated on ``api_integration`` per the existing runner-integration pattern.

Locator note: ``tools/`` is not on sys.path in the api_server layout, so
we add it the same way ``test_run_recipe_persistent_inapp.py`` does.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

# tools/ on sys.path so we can import run_recipe directly.
REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLS_DIR = REPO_ROOT / "tools"
RECIPES_DIR = REPO_ROOT / "recipes"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import run_recipe  # noqa: E402


_PROXY_URL = "http://api_server:8000/v1/llm/forward"
_TOKEN = "0123456789abcdef0123456789abcdef"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stub_recipe(*, api_key_var: str, via_proxy: bool | None) -> dict[str, Any]:
    """Build a minimal recipe dict for the env-build pure-function tests.

    Includes only the fields ``run_cell_persistent`` reads when computing
    via_proxy_overrides. Real persistent-mode validation (volumes,
    ready_log_regex, health_check) is exercised in Test 8 below.
    """
    runtime: dict[str, Any] = {
        "process_env": {"api_key": api_key_var},
    }
    if via_proxy is not None:
        runtime["via_proxy"] = via_proxy
    return {
        "name": "stub",
        "runtime": runtime,
    }


# ---------------------------------------------------------------------------
# Test 1 — via_proxy=true + OPENROUTER_API_KEY
# ---------------------------------------------------------------------------


def test_via_proxy_true_openrouter_dispatches_openai_sdk_envs() -> None:
    """OPENROUTER_API_KEY → OPENAI_BASE_URL + OPENAI_API_KEY (the
    OpenAI-SDK shape — OpenRouter is OpenAI-compat). AP_PROXY_BASE_URL
    is injected too (AMD-09)."""
    overrides = run_recipe._build_via_proxy_overrides(
        api_key_var="OPENROUTER_API_KEY",
        inapp_auth_token=_TOKEN,
    )
    assert overrides["AP_PROXY_BASE_URL"] == _PROXY_URL
    assert overrides["OPENAI_BASE_URL"] == _PROXY_URL
    assert overrides["OPENAI_API_KEY"] == f"ap-proxy-{_TOKEN}"
    # Real BYOK env-var-name MUST NOT be present in the overrides.
    assert "OPENROUTER_API_KEY" not in overrides
    assert "ANTHROPIC_BASE_URL" not in overrides
    assert "ANTHROPIC_API_KEY" not in overrides

    # Now pipe through _build_env_file_content and assert env-file shape.
    content = run_recipe._build_env_file_content(
        api_key_var="OPENROUTER_API_KEY",
        api_key_val="sk-or-v1-real-byok-aaaa-bbbb-cccc",
        required_inputs=[],
        optional_inputs=[],
        channel_creds={},
        rendered_activation_env=None,
        via_proxy_overrides=overrides,
    )
    # The real BYOK key MUST NOT appear in the env-file.
    assert "sk-or-v1-real-byok" not in content
    assert "OPENROUTER_API_KEY=" not in content
    # The proxy injections MUST be present.
    assert f"AP_PROXY_BASE_URL={_PROXY_URL}" in content
    assert f"OPENAI_BASE_URL={_PROXY_URL}" in content
    assert f"OPENAI_API_KEY=ap-proxy-{_TOKEN}" in content


# ---------------------------------------------------------------------------
# Test 2 — via_proxy=true + ANTHROPIC_API_KEY
# ---------------------------------------------------------------------------


def test_via_proxy_true_anthropic_dispatches_anthropic_sdk_envs() -> None:
    """ANTHROPIC_API_KEY → ANTHROPIC_BASE_URL + ANTHROPIC_API_KEY (the
    Anthropic-SDK shape). AP_PROXY_BASE_URL is injected too."""
    overrides = run_recipe._build_via_proxy_overrides(
        api_key_var="ANTHROPIC_API_KEY",
        inapp_auth_token=_TOKEN,
    )
    assert overrides["AP_PROXY_BASE_URL"] == _PROXY_URL
    assert overrides["ANTHROPIC_BASE_URL"] == _PROXY_URL
    assert overrides["ANTHROPIC_API_KEY"] == f"ap-proxy-{_TOKEN}"
    assert "OPENAI_BASE_URL" not in overrides
    assert "OPENAI_API_KEY" not in overrides

    content = run_recipe._build_env_file_content(
        api_key_var="ANTHROPIC_API_KEY",
        api_key_val="sk-ant-api03-REAL-VALUE-DO-NOT-LEAK",
        required_inputs=[],
        optional_inputs=[],
        channel_creds={},
        rendered_activation_env=None,
        via_proxy_overrides=overrides,
    )
    assert "sk-ant-api03-REAL-VALUE-DO-NOT-LEAK" not in content
    # legacy api_key_var line is omitted entirely
    assert "ANTHROPIC_API_KEY=sk-ant" not in content
    assert f"AP_PROXY_BASE_URL={_PROXY_URL}" in content
    assert f"ANTHROPIC_BASE_URL={_PROXY_URL}" in content
    assert f"ANTHROPIC_API_KEY=ap-proxy-{_TOKEN}" in content


# ---------------------------------------------------------------------------
# Test 3 — via_proxy=true + OPENAI_API_KEY
# ---------------------------------------------------------------------------


def test_via_proxy_true_openai_dispatches_openai_sdk_envs() -> None:
    """OPENAI_API_KEY (direct OpenAI provider) → OPENAI_BASE_URL +
    OPENAI_API_KEY (same SDK shape as openrouter)."""
    overrides = run_recipe._build_via_proxy_overrides(
        api_key_var="OPENAI_API_KEY",
        inapp_auth_token=_TOKEN,
    )
    assert overrides["AP_PROXY_BASE_URL"] == _PROXY_URL
    assert overrides["OPENAI_BASE_URL"] == _PROXY_URL
    assert overrides["OPENAI_API_KEY"] == f"ap-proxy-{_TOKEN}"
    assert "ANTHROPIC_BASE_URL" not in overrides


# ---------------------------------------------------------------------------
# Test 4 — via_proxy=true + unknown env var raises ValueError
# ---------------------------------------------------------------------------


def test_via_proxy_true_unknown_env_var_raises_value_error() -> None:
    """Unknown ``api_key`` env var must fail-loud with ValueError carrying
    the offending var name (closed enum — D-09 + D-17)."""
    with pytest.raises(ValueError) as exc:
        run_recipe._build_via_proxy_overrides(
            api_key_var="BOGUS_API_KEY",
            inapp_auth_token=_TOKEN,
        )
    assert "BOGUS_API_KEY" in str(exc.value)


# ---------------------------------------------------------------------------
# Test 5 — via_proxy=false explicit: legacy path preserved
# ---------------------------------------------------------------------------


def test_via_proxy_false_preserves_legacy_env_file_shape() -> None:
    """When the env-file is built with via_proxy_overrides=None the
    legacy first line ``API_KEY_VAR=API_KEY_VAL`` is preserved AND no
    proxy keys are injected. D-27 byte-identical invariant."""
    content = run_recipe._build_env_file_content(
        api_key_var="OPENROUTER_API_KEY",
        api_key_val="sk-or-v1-legacy-key-keep-me",
        required_inputs=[],
        optional_inputs=[],
        channel_creds={},
        rendered_activation_env=None,
        via_proxy_overrides=None,
    )
    # Legacy first line MUST be preserved.
    assert content.startswith("OPENROUTER_API_KEY=sk-or-v1-legacy-key-keep-me\n")
    # No proxy injections allowed.
    assert "AP_PROXY_BASE_URL" not in content
    assert "OPENAI_BASE_URL" not in content
    assert "ap-proxy-" not in content


# ---------------------------------------------------------------------------
# Test 6 — via_proxy_overrides default arg (None) preserves legacy path
# ---------------------------------------------------------------------------


def test_via_proxy_default_arg_preserves_legacy_env_file_shape() -> None:
    """When _build_env_file_content is called WITHOUT via_proxy_overrides
    (default arg) it MUST behave identically to via_proxy_overrides=None
    — proves the legacy 5 recipes are unaffected."""
    legacy = run_recipe._build_env_file_content(
        api_key_var="OPENROUTER_API_KEY",
        api_key_val="sk-or-default-arg-test-key",
        required_inputs=[],
        optional_inputs=[],
        channel_creds={},
        rendered_activation_env=None,
        # via_proxy_overrides omitted — defaults to None
    )
    explicit = run_recipe._build_env_file_content(
        api_key_var="OPENROUTER_API_KEY",
        api_key_val="sk-or-default-arg-test-key",
        required_inputs=[],
        optional_inputs=[],
        channel_creds={},
        rendered_activation_env=None,
        via_proxy_overrides=None,
    )
    assert legacy == explicit
    assert legacy.startswith("OPENROUTER_API_KEY=sk-or-default-arg-test-key\n")


# ---------------------------------------------------------------------------
# Test 7 — RecipeSummary surfaces via_proxy
# ---------------------------------------------------------------------------


def test_recipe_summary_surfaces_via_proxy_field() -> None:
    """``RecipeSummary.via_proxy`` reflects ``runtime.via_proxy``;
    defaults to False when the field is absent."""
    from api_server.services.recipes_loader import to_summary

    # Recipe with via_proxy: true
    flipped = {
        "name": "stub-flipped",
        "apiVersion": "ap.recipe/v0.2",
        "runtime": {
            "provider": "openrouter",
            "process_env": {"api_key": "OPENROUTER_API_KEY"},
            "via_proxy": True,
            "volumes": [{"container": "/x"}],
        },
    }
    summary = to_summary(flipped)
    assert summary.via_proxy is True

    # Recipe without via_proxy field — should default to False.
    legacy = {
        "name": "stub-legacy",
        "apiVersion": "ap.recipe/v0.2",
        "runtime": {
            "provider": "openrouter",
            "process_env": {"api_key": "OPENROUTER_API_KEY"},
            "volumes": [{"container": "/x"}],
        },
    }
    summary_legacy = to_summary(legacy)
    assert summary_legacy.via_proxy is False

    # Recipe with explicit via_proxy: false
    explicit_false = {
        "name": "stub-explicit-false",
        "apiVersion": "ap.recipe/v0.2",
        "runtime": {
            "provider": "openrouter",
            "process_env": {"api_key": "OPENROUTER_API_KEY"},
            "via_proxy": False,
            "volumes": [{"container": "/x"}],
        },
    }
    summary_explicit = to_summary(explicit_false)
    assert summary_explicit.via_proxy is False


# ---------------------------------------------------------------------------
# Test 8 — Integration: docker exec env shows proxy injection (api_integration)
# ---------------------------------------------------------------------------


@pytest.mark.api_integration
def test_via_proxy_env_visible_in_running_container_env() -> None:
    """End-to-end: spawn a real busybox container with --env-file built
    via the via_proxy path; ``docker exec <id> env`` shows the injected
    proxy vars AND lacks the real BYOK key.

    Uses a minimal sh-keepalive container (no recipe machinery) — we are
    asserting the runner's env-file path produces the right docker -e
    environment, not nanobot-specific behavior. The full nanobot proxy
    e2e is Plan 09's gate.
    """
    # Skip cleanly if Docker daemon unavailable (CI without Docker).
    docker_ok = subprocess.run(
        ["docker", "info"],
        capture_output=True, text=True, check=False,
    )
    if docker_ok.returncode != 0:
        pytest.skip("Docker daemon unavailable")

    overrides = run_recipe._build_via_proxy_overrides(
        api_key_var="OPENROUTER_API_KEY",
        inapp_auth_token=_TOKEN,
    )
    content = run_recipe._build_env_file_content(
        api_key_var="OPENROUTER_API_KEY",
        api_key_val="sk-or-v1-DO-NOT-LEAK-ME",
        required_inputs=[],
        optional_inputs=[],
        channel_creds={},
        rendered_activation_env=None,
        via_proxy_overrides=overrides,
    )

    env_file = Path(f"/tmp/ap-via-proxy-test-{uuid.uuid4().hex}.env")
    env_file.write_text(content)
    try:
        env_file.chmod(0o600)
    except OSError:
        pass

    cname = f"ap-via-proxy-test-{uuid.uuid4().hex[:8]}"
    try:
        # Run busybox keepalive with the env-file.
        run = subprocess.run(
            [
                "docker", "run", "-d",
                "--name", cname,
                "--env-file", str(env_file),
                "busybox:1.36",
                "sh", "-c", "sleep 30",
            ],
            capture_output=True, text=True, check=False, timeout=30,
        )
        if run.returncode != 0:
            pytest.skip(f"docker run failed (likely no busybox image / no daemon access): {run.stderr.strip()}")

        # Read env from inside the container.
        ex = subprocess.run(
            ["docker", "exec", cname, "env"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        assert ex.returncode == 0, f"docker exec env failed: {ex.stderr}"

        env_lines = (ex.stdout or "").splitlines()
        env_dict = {}
        for line in env_lines:
            if "=" in line:
                k, v = line.split("=", 1)
                env_dict[k] = v

        # Proxy injections present.
        assert env_dict.get("AP_PROXY_BASE_URL") == _PROXY_URL
        assert env_dict.get("OPENAI_BASE_URL") == _PROXY_URL
        assert env_dict.get("OPENAI_API_KEY") == f"ap-proxy-{_TOKEN}"
        # Real BYOK key absent.
        assert "OPENROUTER_API_KEY" not in env_dict
        # Defense-in-depth: the literal real key string is nowhere.
        all_env = "\n".join(env_lines)
        assert "sk-or-v1-DO-NOT-LEAK-ME" not in all_env
    finally:
        subprocess.run(
            ["docker", "rm", "-f", cname],
            capture_output=True, text=True, check=False, timeout=10,
        )
        env_file.unlink(missing_ok=True)

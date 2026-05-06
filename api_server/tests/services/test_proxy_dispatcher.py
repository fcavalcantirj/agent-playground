"""Phase 29 Plan 03 — pure-function tests for proxy_dispatcher.

These are pure-function tests (no Postgres, no Docker, no upstream HTTP).
They verify the closed-set provider dispatch table that Plans 04, 05, 06,
and 07 will import from. Exact shapes mirror PROBE-VAL-04 spike evidence
(Bearer for OpenRouter/OpenAI; x-api-key + anthropic-version for Anthropic).

Coverage:
  * Test 1 — PROVIDERS keys are exactly the 3 strings (closed enum)
  * Test 2 — openrouter spec shape (base_url, auth, extra_headers, sse_format)
  * Test 3 — openai spec shape
  * Test 4 — anthropic spec shape
  * Test 5 — UpstreamSpec is frozen (assignment raises FrozenInstanceError)
  * Test 6 — auth_value_template substitutes the BYOK key correctly
  * Test 7 — ENV_TO_PROVIDER maps recipe env-var names to provider strings
  * Test 8 — derive_provider() happy path for the 3 known env vars
  * Test 9 — derive_provider() raises ValueError on unknown env var
  * Test 10 — ENV_TO_PROVIDER parity with services.recipes_loader._ENV_TO_PROVIDER
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from api_server.services.proxy_dispatcher import (
    ENV_TO_PROVIDER,
    PROVIDERS,
    UpstreamSpec,
    derive_provider,
)


# ---------------------------------------------------------------------------
# Test 1 — closed-set provider enum
# ---------------------------------------------------------------------------


def test_providers_keys_are_exactly_three() -> None:
    """SSRF defense — closed enum (D-09 + D-17). Adding a 4th provider is a
    deliberate dict-entry addition; this test breaks if anyone widens the set
    accidentally (e.g. by aliasing 'or' -> 'openrouter')."""
    assert set(PROVIDERS.keys()) == {"openrouter", "openai", "anthropic"}


# ---------------------------------------------------------------------------
# Tests 2-4 — per-provider spec shapes (mirror PROBE-VAL-04 evidence)
# ---------------------------------------------------------------------------


def test_openrouter_spec_shape() -> None:
    spec = PROVIDERS["openrouter"]
    assert spec.base_url == "https://openrouter.ai/api/v1"
    assert spec.auth_header_name == "Authorization"
    assert spec.auth_value_template == "Bearer {key}"
    assert spec.sse_format == "openai"
    # Both attribution headers required by OpenRouter.
    assert "HTTP-Referer" in spec.extra_headers
    assert "X-Title" in spec.extra_headers


def test_openai_spec_shape() -> None:
    spec = PROVIDERS["openai"]
    assert spec.base_url == "https://api.openai.com/v1"
    assert spec.auth_header_name == "Authorization"
    assert spec.auth_value_template == "Bearer {key}"
    assert spec.sse_format == "openai"
    assert spec.extra_headers == {}


def test_anthropic_spec_shape() -> None:
    spec = PROVIDERS["anthropic"]
    assert spec.base_url == "https://api.anthropic.com"
    assert spec.auth_header_name == "x-api-key"
    # No "Bearer" prefix for Anthropic — verified via PROBE-VAL-04 sub-probe (b).
    assert spec.auth_value_template == "{key}"
    assert spec.sse_format == "anthropic"
    assert spec.extra_headers["anthropic-version"] == "2023-06-01"


# ---------------------------------------------------------------------------
# Test 5 — frozen-dataclass discipline
# ---------------------------------------------------------------------------


def test_upstream_spec_is_frozen() -> None:
    """Defensive — a future refactor must not loosen frozen=True."""
    spec = PROVIDERS["openrouter"]
    with pytest.raises(FrozenInstanceError):
        spec.base_url = "https://evil.example.com"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test 6 — auth_value_template substitution
# ---------------------------------------------------------------------------


def test_auth_value_template_substitutes_key() -> None:
    """Bearer prefix for OAI/OR; bare key for Anthropic — verified by
    PROBE-VAL-04 (Bearer→Anthropic returns 401 invalid_bearer_token)."""
    assert PROVIDERS["openrouter"].auth_value_template.format(key="abc") == "Bearer abc"
    assert PROVIDERS["openai"].auth_value_template.format(key="abc") == "Bearer abc"
    assert PROVIDERS["anthropic"].auth_value_template.format(key="abc") == "abc"


# ---------------------------------------------------------------------------
# Test 7 — ENV_TO_PROVIDER mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "env_var,expected_provider",
    [
        ("OPENROUTER_API_KEY", "openrouter"),
        ("ANTHROPIC_API_KEY", "anthropic"),
        ("OPENAI_API_KEY", "openai"),
    ],
)
def test_env_to_provider_mapping(env_var: str, expected_provider: str) -> None:
    assert ENV_TO_PROVIDER[env_var] == expected_provider


# ---------------------------------------------------------------------------
# Tests 8-9 — derive_provider helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "env_var,expected_provider",
    [
        ("OPENROUTER_API_KEY", "openrouter"),
        ("ANTHROPIC_API_KEY", "anthropic"),
        ("OPENAI_API_KEY", "openai"),
    ],
)
def test_derive_provider_happy_path(env_var: str, expected_provider: str) -> None:
    assert derive_provider(env_var) == expected_provider


def test_derive_provider_raises_on_unknown_env_var() -> None:
    """Closed enum — unknown env-var names must surface loudly so a recipe
    typo cannot quietly pick a wrong upstream."""
    with pytest.raises(ValueError) as exc_info:
        derive_provider("BOGUS_KEY")
    msg = str(exc_info.value)
    assert "BOGUS_KEY" in msg
    assert "unknown" in msg.lower()


# ---------------------------------------------------------------------------
# Test 10 — parity with the existing recipes_loader source-of-truth
# ---------------------------------------------------------------------------


def test_env_to_provider_parity_with_recipes_loader() -> None:
    """The proxy subsystem owns its own ENV_TO_PROVIDER (no circular import
    via recipes_loader), but the two must stay in lockstep — a recipe whose
    runtime.process_env.api_key is OPENROUTER_API_KEY must be classified
    identically by both modules."""
    from api_server.services.recipes_loader import _ENV_TO_PROVIDER

    assert ENV_TO_PROVIDER == _ENV_TO_PROVIDER


# Re-export for grep-checkable acceptance criteria — the module-under-test
# symbol is loaded above; this line is here only so a static reader confirms
# UpstreamSpec is one of the four imports the test file exercises.
_ = UpstreamSpec

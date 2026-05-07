"""Phase 29 Plan 08 Task 2 — recipes/nanobot.yaml flipped to via_proxy: true.

Coverage:

  Test 1 — nanobot has runtime.via_proxy: true.
  Test 2 — ONLY nanobot has via_proxy: true. Regression guard against
           Phase 30's recipe-flip leaking into Phase 29.
  Test 3 — nanobot.channels.inapp.contract == "openai_compat" (sanity:
           the proxy's openai SSE format applies).
  Test 4 — nanobot.runtime.process_env.api_key == "OPENROUTER_API_KEY"
           (sanity: Plan 08 Task 1's runner dispatch routes through the
           OpenAI-SDK shape).
  Test 5 — RecipeSummary.via_proxy is True for nanobot end-to-end via
           recipes_loader.to_summary.

Pure YAML reads — no Postgres, no Docker. No pytestmark needed.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from ruamel.yaml import YAML


REPO_ROOT = Path(__file__).resolve().parents[3]
RECIPES_DIR = REPO_ROOT / "recipes"


def _load(name: str) -> dict:
    y = YAML(typ="rt")
    with open(RECIPES_DIR / f"{name}.yaml") as f:
        return dict(y.load(f))


# ---------------------------------------------------------------------------
# Test 1 — nanobot has via_proxy: true
# ---------------------------------------------------------------------------


def test_nanobot_runtime_via_proxy_is_true() -> None:
    recipe = _load("nanobot")
    assert recipe["runtime"]["via_proxy"] is True, (
        "Phase 29 Plan 08 cutover invariant — runtime.via_proxy must be true"
    )


# ---------------------------------------------------------------------------
# Test 2 — ONLY nanobot has via_proxy: true (regression guard)
# ---------------------------------------------------------------------------


# Phase 30 EXIT GATE (Plan 30-07): the shrinking-_OTHER_RECIPES regression
# guard pattern is retired. The positive-assertion replacement lives at
# api_server/tests/recipes/test_phase30_via_proxy_invariant.py — it
# parametrizes test_all_recipes_have_via_proxy_true over all 6 flipped
# recipes (nanobot + openclaw + nullclaw + picoclaw + zeroclaw + hermes)
# and asserts the count via test_all_recipes_flipped_count. The
# nanobot-specific sanity tests below (inapp contract, api_key env name,
# RecipeSummary surfacing, two-heredoc shape) stay in this file because
# they document nanobot-specific invariants, not Phase-30-wide ones.


# ---------------------------------------------------------------------------
# Phase 30 Plan 30-06 — hermes flipped to via_proxy: true
# ---------------------------------------------------------------------------


def test_hermes_runtime_via_proxy_is_true() -> None:
    """Phase 30 Plan 30-06 cutover invariant — hermes flipped to the proxy."""
    recipe = _load("hermes")
    assert recipe["runtime"]["via_proxy"] is True, (
        "Phase 30 Plan 30-06 cutover invariant — hermes runtime.via_proxy must be true"
    )


def test_hermes_activation_env_sets_openrouter_base_url() -> None:
    """hermes reads OPENROUTER_BASE_URL via os.getenv() in
    hermes_cli/runtime_provider.py (precedence: env > config.yaml >
    hermes_constants.OPENROUTER_BASE_URL). The persistent-mode
    activation_env block must inject OPENROUTER_BASE_URL=${AP_PROXY_BASE_URL}
    so the runner-injected proxy URL reaches hermes's HTTP client."""
    text = (RECIPES_DIR / "hermes.yaml").read_text()
    assert 'OPENROUTER_BASE_URL: "${AP_PROXY_BASE_URL}"' in text, (
        "hermes.yaml's persistent activation_env must inject "
        "OPENROUTER_BASE_URL=${AP_PROXY_BASE_URL} — that's hermes's "
        "documented env-var override path for the upstream URL."
    )


# ---------------------------------------------------------------------------
# Phase 30 Plan 30-05 — zeroclaw flipped to via_proxy: true
# ---------------------------------------------------------------------------


def test_zeroclaw_runtime_via_proxy_is_true() -> None:
    """Phase 30 Plan 30-05 cutover invariant — zeroclaw flipped to the proxy."""
    recipe = _load("zeroclaw")
    assert recipe["runtime"]["via_proxy"] is True, (
        "Phase 30 Plan 30-05 cutover invariant — zeroclaw runtime.via_proxy must be true"
    )


def test_zeroclaw_uses_custom_provider_form() -> None:
    """zeroclaw's named providers (openrouter, openai, etc.) ignore
    `providers.models.<name>.base-url` at request time — outbound calls
    go to hardcoded URLs. The documented escape hatch is the literal
    `custom:<URL>` provider id (per `zeroclaw providers` output:
    "custom:<URL>   Any OpenAI-compatible endpoint"). The recipe must
    onboard with `--provider custom:${AP_PROXY_BASE_URL}` so zeroclaw
    treats the proxy as a first-class custom provider with the configured
    base URL."""
    text = (RECIPES_DIR / "zeroclaw.yaml").read_text()
    assert "custom:${AP_PROXY_BASE_URL}" in text, (
        "zeroclaw.yaml must onboard with --provider "
        "'custom:${AP_PROXY_BASE_URL}' — that's the documented escape "
        "hatch for redirecting zeroclaw's outbound HTTP at an arbitrary "
        "OpenAI-compatible endpoint (the AP proxy)."
    )
    # Defense-in-depth — the `--provider openrouter` argv leaked back if
    # someone mass-replaced. The legacy onboard string MUST be gone.
    assert "- openrouter\n            - --api-key" not in text, (
        "zeroclaw.yaml's onboard step still references the legacy "
        "openrouter provider — should be custom:${AP_PROXY_BASE_URL}"
    )


# ---------------------------------------------------------------------------
# Test 3 — nanobot.channels.inapp.contract is openai_compat
# ---------------------------------------------------------------------------


def test_nanobot_inapp_contract_is_openai_compat() -> None:
    recipe = _load("nanobot")
    assert recipe["channels"]["inapp"]["contract"] == "openai_compat", (
        "the proxy's openai SSE format is the contract for nanobot inapp"
    )


# ---------------------------------------------------------------------------
# Test 4 — nanobot.runtime.process_env.api_key is OPENROUTER_API_KEY
# ---------------------------------------------------------------------------


def test_nanobot_process_env_api_key_is_openrouter() -> None:
    recipe = _load("nanobot")
    assert recipe["runtime"]["process_env"]["api_key"] == "OPENROUTER_API_KEY", (
        "Plan 08 Task 1's runner dispatch routes OPENROUTER_API_KEY → "
        "OPENAI_BASE_URL injection. Other env-var values would change the "
        "injection shape — keep nanobot on OPENROUTER_API_KEY in Phase 29."
    )


# ---------------------------------------------------------------------------
# Test 5 — RecipeSummary.via_proxy=True end-to-end
# ---------------------------------------------------------------------------


def test_nanobot_recipe_summary_surfaces_via_proxy_true() -> None:
    """Load nanobot via recipes_loader.to_summary and assert the surfaced
    via_proxy field is True. Closes the recipe → loader → API contract."""
    from api_server.services.recipes_loader import load_recipe, to_summary

    recipe = load_recipe(RECIPES_DIR / "nanobot.yaml")
    summary = to_summary(recipe)
    assert summary.name == "nanobot"
    assert summary.via_proxy is True


# ---------------------------------------------------------------------------
# Bonus — AMD-09: api_base placeholder substitution lives in BOTH heredocs
# ---------------------------------------------------------------------------


def test_nanobot_api_base_uses_proxy_url_default_form_in_both_heredocs() -> None:
    """AMD-09 — both nanobot config-file heredocs (gateway path for
    channels.telegram + serve path for channels.inapp) substitute the
    proxy URL via sh-default form so via_proxy=true uses the runner-
    injected AP_PROXY_BASE_URL and via_proxy=false falls back to the
    upstream URL (legacy path preserved)."""
    text = (RECIPES_DIR / "nanobot.yaml").read_text()
    pattern = '"api_base": "${AP_PROXY_BASE_URL:-https://openrouter.ai/api/v1}"'
    occurrences = text.count(pattern)
    assert occurrences == 2, (
        f"expected exactly 2 sh-default api_base substitutions in "
        f"nanobot.yaml (gateway heredoc + serve heredoc), got {occurrences}"
    )
    # Defense-in-depth — the original literal MUST be gone.
    assert '"api_base": "https://openrouter.ai/api/v1"' not in text, (
        "the literal upstream URL leaked back into nanobot.yaml — "
        "should be sh-defaulted via AP_PROXY_BASE_URL"
    )


# ---------------------------------------------------------------------------
# Phase 30 Plan 30-02 — openclaw flipped to via_proxy: true (D-03)
# ---------------------------------------------------------------------------


def test_openclaw_runtime_via_proxy_is_true() -> None:
    """Phase 30 Plan 30-02 cutover invariant — openclaw flipped to the proxy."""
    recipe = _load("openclaw")
    assert recipe["runtime"]["via_proxy"] is True, (
        "Phase 30 Plan 30-02 cutover invariant — openclaw runtime.via_proxy must be true"
    )


def test_openclaw_process_env_api_key_is_anthropic() -> None:
    """Sanity — openclaw's api_key env var is ANTHROPIC_API_KEY so AMD-06 dispatch
    injects ANTHROPIC_BASE_URL (not OPENAI_BASE_URL).

    The runner's `_build_via_proxy_overrides` (tools/run_recipe.py:1007-1042)
    is a closed enum: ANTHROPIC_API_KEY -> ANTHROPIC_BASE_URL injection. If
    this ever drifted to OPENROUTER_API_KEY, openclaw would route through the
    OpenAI-SDK shape and the proxy's anthropic SSE branch would never fire.
    """
    recipe = _load("openclaw")
    assert recipe["runtime"]["process_env"]["api_key"] == "ANTHROPIC_API_KEY"


def test_openclaw_heredoc_uses_proxy_base_url_for_anthropic_provider() -> None:
    """Phase 30 followup `e44f1c2` — the original Plan 30-02 design assumed
    openclaw's anthropic plugin would honor the SDK-convention
    ANTHROPIC_BASE_URL env var (injected by the runner). Empirically it
    does NOT — the openclaw anthropic plugin reads only
    `models.providers.anthropic.baseUrl` from openclaw.json. The fix
    writes a `models` block in the bootstrap heredoc with
    `baseUrl: $BASE_URL` derived from `${AP_PROXY_BASE_URL:-...}` so the
    proxy URL reaches openclaw's HTTP client. This test pins the new
    invariant — opposite of the pre-`e44f1c2` shape."""
    text = (RECIPES_DIR / "openclaw.yaml").read_text()
    assert 'BASE_URL="${AP_PROXY_BASE_URL:-https://api.anthropic.com}"' in text, (
        "openclaw.yaml must compute BASE_URL from AP_PROXY_BASE_URL (with "
        "https://api.anthropic.com as the legacy non-proxy fallback) per "
        "the post-30 followup fix"
    )
    assert '"baseUrl": "$BASE_URL"' in text, (
        "openclaw heredoc must write models.providers.anthropic.baseUrl=$BASE_URL "
        "— the load-bearing knob for redirecting outbound Anthropic calls"
    )
    # Defense-in-depth — the model entry's baseUrl must also point at the proxy
    assert '"api": "anthropic-messages"' in text, (
        "openclaw heredoc must declare api=anthropic-messages for the model "
        "entry under providers.anthropic.models[]"
    )


# ---------------------------------------------------------------------------
# Phase 30 Plan 30-03 — nullclaw flipped to via_proxy: true via custom:URL
# ---------------------------------------------------------------------------


def test_nullclaw_runtime_via_proxy_is_true() -> None:
    """Phase 30 Plan 30-03 cutover invariant — nullclaw flipped to the proxy."""
    recipe = _load("nullclaw")
    assert recipe["runtime"]["via_proxy"] is True, (
        "Phase 30 Plan 30-03 cutover invariant — nullclaw runtime.via_proxy must be true"
    )


def test_nullclaw_uses_custom_provider_form() -> None:
    """nullclaw rejects base_url on named providers (openrouter, openai, …)
    with AccessDenied. The escape hatch is the literal `custom:<URL>`
    provider key documented in the binary's onboard --help. The bootstrap
    heredoc must register the proxy via this form, NOT via the openrouter
    provider entry."""
    text = (RECIPES_DIR / "nullclaw.yaml").read_text()
    assert "PROVIDER_KEY=\"custom:${RESOLVED_PROXY_URL}\"" in text, (
        "nullclaw.yaml must set PROVIDER_KEY to the custom:<URL> form when "
        "AP_PROXY_BASE_URL is present — that's the only documented "
        "base_url escape hatch in nullclaw."
    )
    # Sanity — heredoc references the constructed PROVIDER_KEY var, not a
    # hardcoded "openrouter" string in the via_proxy=true path.
    assert "\"models\":{\"providers\":{\"${PROVIDER_KEY}\":" in text, (
        "the providers JSON must be keyed by ${PROVIDER_KEY} so the "
        "custom:<URL> entry materializes when via_proxy=true"
    )
    assert "\"primary\":\"${PROVIDER_KEY}/$MODEL\"" in text, (
        "agents.defaults.model.primary must use the ${PROVIDER_KEY}/<model> "
        "form so the resolved primary points at the custom provider"
    )


def test_nullclaw_legacy_path_still_works() -> None:
    """When AP_PROXY_BASE_URL is unset (legacy direct-to-OpenRouter path),
    PROVIDER_KEY falls back to the bare 'openrouter' string and primary
    becomes openrouter/<model>. D-27 byte-identical legacy invariant."""
    text = (RECIPES_DIR / "nullclaw.yaml").read_text()
    assert "PROVIDER_KEY=\"openrouter\"" in text, (
        "nullclaw legacy fallback — PROVIDER_KEY must default to 'openrouter' "
        "when AP_PROXY_BASE_URL is empty so the recipe still works without "
        "the runner injecting a proxy URL"
    )


# ---------------------------------------------------------------------------
# Phase 30 Plan 30-04 — picoclaw flipped to via_proxy: true
# ---------------------------------------------------------------------------


def test_picoclaw_runtime_via_proxy_is_true() -> None:
    """Phase 30 Plan 30-04 cutover invariant — picoclaw flipped to the proxy."""
    recipe = _load("picoclaw")
    assert recipe["runtime"]["via_proxy"] is True, (
        "Phase 30 Plan 30-04 cutover invariant — picoclaw runtime.via_proxy must be true"
    )


def test_picoclaw_api_base_uses_proxy_url_default_form_in_both_heredocs() -> None:
    """picoclaw has TWO config.json heredocs (one-shot invoke + persistent
    gateway daemon). Both must substitute api_base via the AMD-09
    sh-default form so via_proxy=true uses the runner-injected
    AP_PROXY_BASE_URL and via_proxy=false falls back to the upstream URL.
    Mirrors the nanobot two-heredoc pattern."""
    text = (RECIPES_DIR / "picoclaw.yaml").read_text()
    pattern = '"api_base": "${AP_PROXY_BASE_URL:-https://openrouter.ai/api/v1}"'
    occurrences = text.count(pattern)
    assert occurrences == 2, (
        f"expected exactly 2 sh-default api_base substitutions in "
        f"picoclaw.yaml (one-shot heredoc @line 105 + persistent heredoc "
        f"@line 213), got {occurrences}"
    )
    # Defense-in-depth — the bare upstream literal MUST NOT appear inside
    # an api_base assignment anywhere (comments are fine).
    assert '"api_base": "https://openrouter.ai/api/v1"' not in text, (
        "the literal upstream URL leaked back into picoclaw.yaml — "
        "should be sh-defaulted via AP_PROXY_BASE_URL"
    )


# ---------------------------------------------------------------------------
# Phase 30 followup — QwenPaw added 2026-05-07 with agentscope_runtime contract
# ---------------------------------------------------------------------------


def test_qwenpaw_runtime_via_proxy_is_true() -> None:
    """Phase 30 followup cutover invariant — qwenpaw routes through the proxy."""
    recipe = _load("qwenpaw")
    assert recipe["runtime"]["via_proxy"] is True, (
        "Phase 30 followup invariant — qwenpaw runtime.via_proxy must be true"
    )


def test_qwenpaw_uses_agentscope_runtime_contract() -> None:
    """QwenPaw exposes POST /api/console/chat with the AgentScope Runtime
    SSE shape — body is `input[*].role/content[*].text` (NOT OpenAI's
    `messages[*].content`), response is `data: {sequence_number,status,
    output,...}` events. This is the new 4th contract type added
    alongside openai_compat / a2a_jsonrpc / zeroclaw_native."""
    recipe = _load("qwenpaw")
    assert recipe["channels"]["inapp"]["contract"] == "agentscope_runtime", (
        "qwenpaw.channels.inapp.contract must be agentscope_runtime — "
        "the new dispatcher contract added for AgentScope Runtime SSE shape"
    )
    assert recipe["channels"]["inapp"]["endpoint"] == "/api/console/chat", (
        "qwenpaw chat endpoint per https://qwenpaw.agentscope.io/docs/api-tutorial"
    )
    assert recipe["channels"]["inapp"]["port"] == 8088, (
        "qwenpaw default server port"
    )


def test_qwenpaw_bootstrap_writes_custom_provider_config() -> None:
    """The persistent heredoc must pre-write the QwenPaw custom provider
    config (providers/custom/ap-proxy.json) and active_model.json BEFORE
    the upstream entrypoint runs. Without this, qwenpaw boots with no
    default provider and chat completions fail."""
    text = (RECIPES_DIR / "qwenpaw.yaml").read_text()
    assert "/app/working.secret/providers/custom/ap-proxy.json" in text, (
        "qwenpaw bootstrap heredoc must write the ap-proxy custom provider "
        "config — that's the load-bearing baseUrl override per "
        "https://qwenpaw.agentscope.io/docs/models#custom-provider-configuration"
    )
    assert "/app/working.secret/providers/active_model.json" in text, (
        "qwenpaw bootstrap must also write active_model.json so the "
        "ap-proxy provider becomes the global default"
    )
    assert "${AP_PROXY_BASE_URL:-https://openrouter.ai/api/v1}" in text, (
        "qwenpaw heredoc must use the AMD-09 sh-default form so legacy "
        "non-proxy path falls back to openrouter.ai when AP_PROXY_BASE_URL "
        "is unset (D-27 byte-identical fallback)"
    )

"""Phase 22c.3.1 Plan 01 Task 2 — activation-time substitution dict builder.

Mirrors api_server/tests/e2e/conftest.py:319-331 — the substitution shape
proven across 5/5 inapp recipes by the Phase 22c.3-15 e2e gate.

Per D-12..D-15 the dict carries the activation-time placeholders:
  ${INAPP_AUTH_TOKEN}, ${INAPP_PROVIDER_KEY}, ${OPENROUTER_API_KEY},
  ${ANTHROPIC_API_KEY}, $MODEL, {agent_name}, {agent_url}

Per RESEARCH §Production Failure Modes §3 the provider_key flows under all
of {OPENROUTER, ANTHROPIC, INAPP_PROVIDER} aliases — recipe activation_env
decides which key the bot consumes. BYOK per-recipe key resolution is a
future phase (deferred — see CONTEXT.md `<deferred>` block).
"""
from __future__ import annotations


def build_activation_substitutions(
    *,
    provider_key: str,
    agent_name: str,
    agent_model: str,
    inapp_auth_token: str | None,
    via_proxy: bool = False,
) -> dict[str, str]:
    """Build the activation-time substitution dict consumed by run_cell_persistent.

    Sources mirror api_server/tests/e2e/conftest.py:319-331 — tested in
    Phase 22c.3 e2e harness across all 5 inapp recipes.

    Returns empty-string for inapp_auth_token when None (telegram channel) —
    the runner gates the override path on activation_substitutions presence
    AND override presence (AMD-37); when channel != inapp the route does
    not call this builder at all.

    BYOK: provider_key flows under all of {OPENROUTER, ANTHROPIC,
    INAPP_PROVIDER} — recipe activation_env decides; per-recipe vault is a
    future phase (deferred per CONTEXT.md).

    Phase 29 (AMD-12): when ``via_proxy`` is True, the provider-key
    placeholders (OPENROUTER/ANTHROPIC/INAPP_PROVIDER) substitute to
    ``ap-proxy-<inapp_auth_token>`` instead of the real BYOK key — so
    recipe heredocs like ``"api_key": "${OPENROUTER_API_KEY}"`` render to
    the proxy placeholder Bearer that ``routes/llm_proxy.py``'s D-07
    auth-token check expects. The real BYOK key still flows separately
    via Plan 29-05's ``proxy_byok_cache`` (encrypted at rest in
    ``agent_containers.provider_key_enc``); the proxy decrypts it
    server-side when forwarding to upstream. Without this swap, nanobot's
    ``~/.nanobot/config.json::providers.openrouter.api_key`` ends up
    holding the real key and the bot's outbound auth header mismatches
    the proxy's expected ``Bearer ap-proxy-<token>`` shape (PROBE-VAL-12
    confirmed both openai-SDK and langchain accept the placeholder Bearer).
    """
    proxy_placeholder = f"ap-proxy-{inapp_auth_token}" if inapp_auth_token else ""
    api_key_value = proxy_placeholder if via_proxy else provider_key
    # Phase 30 Plan 30-05: zeroclaw's pre_start_commands need the proxy
    # URL substituted into argv (e.g. `zeroclaw config set
    # providers.models.openrouter.base-url ${AP_PROXY_BASE_URL}`). Mirror
    # tools/run_recipe.py:990 (canonical proxy URL on the deploy_default
    # bridge — recipes spawned by the runner share that bridge).
    proxy_base_url = (
        "http://api_server:8000/v1/llm/forward" if via_proxy else ""
    )
    return {
        "INAPP_AUTH_TOKEN": inapp_auth_token or "",
        "INAPP_PROVIDER_KEY": api_key_value,
        "OPENROUTER_API_KEY": api_key_value,
        "ANTHROPIC_API_KEY": api_key_value,
        "AP_PROXY_BASE_URL": proxy_base_url,
        "MODEL": agent_model,
        "agent_name": agent_name,
        "agent_url": f"http://{agent_name}.local",
    }


__all__ = ["build_activation_substitutions"]

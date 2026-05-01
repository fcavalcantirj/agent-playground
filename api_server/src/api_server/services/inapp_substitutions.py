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
    """
    return {
        "INAPP_AUTH_TOKEN": inapp_auth_token or "",
        "INAPP_PROVIDER_KEY": provider_key,
        "OPENROUTER_API_KEY": provider_key,
        "ANTHROPIC_API_KEY": provider_key,
        "MODEL": agent_model,
        "agent_name": agent_name,
        "agent_url": f"http://{agent_name}.local",
    }


__all__ = ["build_activation_substitutions"]

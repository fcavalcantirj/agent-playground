"""Provider dispatch table for the LLM egress proxy.

Single source of truth for "what upstream URL + auth shape goes with which
provider string." All proxy components (route handler, BYOK validator,
record_usage, backfill activity) consume PROVIDERS via the provider key
derived from agent_containers.upstream_provider (D-09 + D-17).

Adding a 4th provider is a single dict-entry addition — no refactor.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UpstreamSpec:
    """Immutable per-provider upstream descriptor."""

    base_url: str
    auth_header_name: str
    auth_value_template: str  # "Bearer {key}" or "{key}"
    extra_headers: dict[str, str]
    sse_format: str  # "openai" | "anthropic"


PROVIDERS: dict[str, UpstreamSpec] = {
    "openrouter": UpstreamSpec(
        base_url="https://openrouter.ai/api/v1",
        auth_header_name="Authorization",
        auth_value_template="Bearer {key}",
        extra_headers={
            "HTTP-Referer": "https://agentplayground.dev",
            "X-Title": "Agent Playground",
        },
        sse_format="openai",
    ),
    "openai": UpstreamSpec(
        base_url="https://api.openai.com/v1",
        auth_header_name="Authorization",
        auth_value_template="Bearer {key}",
        extra_headers={},
        sse_format="openai",
    ),
    "anthropic": UpstreamSpec(
        base_url="https://api.anthropic.com",
        auth_header_name="x-api-key",
        auth_value_template="{key}",
        extra_headers={"anthropic-version": "2023-06-01"},
        sse_format="anthropic",
    ),
}


# Mirrors services.recipes_loader._ENV_TO_PROVIDER — kept here so the proxy
# subsystem can import without circling through recipes_loader.
ENV_TO_PROVIDER: dict[str, str] = {
    "OPENROUTER_API_KEY": "openrouter",
    "ANTHROPIC_API_KEY": "anthropic",
    "OPENAI_API_KEY": "openai",
}


def derive_provider(env_var_name: str) -> str:
    """Return the provider string for a recipe's runtime.process_env.api_key.

    Raises ValueError on unknown env var (closed enum — D-09 + D-17).
    """
    try:
        return ENV_TO_PROVIDER[env_var_name]
    except KeyError:
        raise ValueError(
            f"unknown api_key env var: {env_var_name!r}; "
            f"expected one of {sorted(ENV_TO_PROVIDER.keys())}"
        ) from None


__all__ = ["UpstreamSpec", "PROVIDERS", "ENV_TO_PROVIDER", "derive_provider"]

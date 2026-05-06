"""BYOK key validators — per-provider deploy-time probe (D-02b).

Each validator runs a short, cheap upstream call BEFORE the deploy
handler persists the key + creates the agent_container. Failure → 401
returned to client, no agent created, no encrypted blob written. This
catches typos / expired keys / scoped-out keys at the deploy moment
instead of mid-chat (where the user has no recovery path).

| Provider     | Validation call                                    | Cost  |
|--------------|----------------------------------------------------|-------|
| OpenRouter   | GET /api/v1/key (Authorization: Bearer)            | $0    |
| Anthropic    | POST /v1/messages max_tokens=1 (x-api-key)         | ~$1e-5 |
| OpenAI       | GET /v1/models (Authorization: Bearer)             | $0    |

Empirical references:
- PROBE-VAL-04 — auth-swap shapes verified end-to-end
- PROBE-VAL-11 — OpenRouter /v1/key endpoint reliability + 401 shape
- MSV mirror: ``api/internal/service/byok_service.go:25-80``

The functions take an injected ``httpx.AsyncClient`` so the deploy
handler can pass ``app.state.proxy_upstream_client`` (Plan 29-04 — the
600s-timeout client dedicated to LLM upstreams). Per-call timeouts
override the client's default (10s for OpenRouter/OpenAI, 15s for
Anthropic — Anthropic's max_tokens=1 round-trip empirically takes
longer than OpenRouter's metadata GET).

Network failures (httpx.ConnectError, httpx.TimeoutException, etc.)
PROPAGATE up — the validator does NOT swallow them. The deploy
handler converts them to a 503 envelope so the client distinguishes
"key invalid" (401) from "upstream unreachable" (503).
"""
from __future__ import annotations

import httpx


async def validate_openrouter(
    client: httpx.AsyncClient, key: str,
) -> bool:
    """``GET /api/v1/key`` — $0 metadata read; 200 = valid, 401 = invalid.

    OpenRouter's key-introspection endpoint returns 200 with key
    metadata when the bearer token is valid; 401 when invalid /
    revoked. PROBE-VAL-11 measured p50=180ms, p99=420ms — well
    inside the 10s timeout.
    """
    resp = await client.get(
        "https://openrouter.ai/api/v1/key",
        headers={"Authorization": f"Bearer {key}"},
        timeout=10.0,
    )
    return resp.status_code == 200


async def validate_anthropic(
    client: httpx.AsyncClient, key: str,
) -> bool:
    """``POST /v1/messages max_tokens=1`` — ~$0.00001; 401 = invalid.

    MSV's exact pattern (``api/internal/service/byok_service.go:28``).
    Anthropic returns 200 when the request reaches the model; 400
    when the max_tokens=1 truncation triggers a request-level error
    BUT auth was OK (treat 400 as valid for our purposes); 401
    explicitly indicates invalid auth. The 15s timeout covers
    Haiku-4.5's empirical p99 of ~3-5s.
    """
    resp = await client.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": "claude-haiku-4-5",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "hi"}],
        },
        timeout=15.0,
    )
    return resp.status_code in (200, 400)


async def validate_openai(
    client: httpx.AsyncClient, key: str,
) -> bool:
    """``GET /v1/models`` — $0; 200 = valid, 401 = invalid.

    OpenAI's model-list endpoint is the canonical "is this key
    accepted at all?" probe. No model is invoked, no tokens spent.
    """
    resp = await client.get(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {key}"},
        timeout=10.0,
    )
    return resp.status_code == 200


PROVIDER_VALIDATORS = {
    "openrouter": validate_openrouter,
    "anthropic": validate_anthropic,
    "openai": validate_openai,
}


__all__ = [
    "PROVIDER_VALIDATORS",
    "validate_openrouter",
    "validate_anthropic",
    "validate_openai",
]

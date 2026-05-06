"""Phase 29 Plan 05 Task 2 — pure-function tests for byok_validator.

These are unit tests (no Postgres, no Docker) that mock the upstream
HTTP calls via respx. Validates the 3 per-provider probes have the
exact auth shapes empirically confirmed by PROBE-VAL-04 and
PROBE-VAL-11.

Coverage map (10 behaviors enumerated in 29-05-PLAN.md):
  1. validate_openrouter returns True on 200
  2. validate_openrouter returns False on 401
  3. validate_openrouter sends ``Authorization: Bearer <key>``
  4. validate_anthropic returns True on 200, True on 400, False on 401
  5. validate_anthropic sends x-api-key + anthropic-version + correct body
  6. validate_openai returns True on 200
  7. validate_openai returns False on 401
  8. validate_openai sends ``Authorization: Bearer <key>``
  9. PROVIDER_VALIDATORS dict shape (3 keys, all async callables)
  10. Timeout / network failure propagates (validator does NOT swallow)
"""
from __future__ import annotations

import inspect

import httpx
import pytest
import respx

from api_server.services.byok_validator import (
    PROVIDER_VALIDATORS,
    validate_anthropic,
    validate_openai,
    validate_openrouter,
)


# ---------------------------------------------------------------------------
# Test 1 — validate_openrouter returns True on 200
# ---------------------------------------------------------------------------


@respx.mock
async def test_validate_openrouter_200_returns_true() -> None:
    respx.get("https://openrouter.ai/api/v1/key").mock(
        return_value=httpx.Response(200, json={"data": {"limit": 100}}),
    )
    async with httpx.AsyncClient() as client:
        ok = await validate_openrouter(client, "sk-or-valid-test")
    assert ok is True


# ---------------------------------------------------------------------------
# Test 2 — validate_openrouter returns False on 401
# ---------------------------------------------------------------------------


@respx.mock
async def test_validate_openrouter_401_returns_false() -> None:
    respx.get("https://openrouter.ai/api/v1/key").mock(
        return_value=httpx.Response(
            401, json={"error": {"message": "Invalid API key"}},
        ),
    )
    async with httpx.AsyncClient() as client:
        ok = await validate_openrouter(client, "sk-or-bogus")
    assert ok is False


# ---------------------------------------------------------------------------
# Test 3 — validate_openrouter sends Authorization: Bearer <key>
# ---------------------------------------------------------------------------


@respx.mock
async def test_validate_openrouter_sends_bearer_auth() -> None:
    route = respx.get("https://openrouter.ai/api/v1/key").mock(
        return_value=httpx.Response(200, json={"data": {}}),
    )
    async with httpx.AsyncClient() as client:
        await validate_openrouter(client, "sk-or-bearer-test")

    assert route.called
    sent = route.calls.last.request
    assert sent.headers.get("Authorization") == "Bearer sk-or-bearer-test", (
        f"expected Bearer header, got {sent.headers.get('Authorization')!r}"
    )


# ---------------------------------------------------------------------------
# Test 4 — validate_anthropic: 200/400 → True; 401 → False
# ---------------------------------------------------------------------------


@respx.mock
async def test_validate_anthropic_200_400_true_401_false() -> None:
    """Anthropic returns 200 on success, 400 on max_tokens=1 truncation
    (treated as success — auth was OK), 401 on invalid key.
    """
    url = "https://api.anthropic.com/v1/messages"

    # 200 → True
    route_200 = respx.post(url).mock(
        return_value=httpx.Response(200, json={"content": []}),
    )
    async with httpx.AsyncClient() as client:
        assert await validate_anthropic(client, "sk-ant-200") is True
    assert route_200.called

    # 400 → True (truncation is OK; key was accepted)
    respx.reset()
    route_400 = respx.post(url).mock(
        return_value=httpx.Response(
            400, json={"error": {"message": "max_tokens too small"}},
        ),
    )
    async with httpx.AsyncClient() as client:
        assert await validate_anthropic(client, "sk-ant-400") is True
    assert route_400.called

    # 401 → False
    respx.reset()
    route_401 = respx.post(url).mock(
        return_value=httpx.Response(
            401, json={"error": {"type": "authentication_error"}},
        ),
    )
    async with httpx.AsyncClient() as client:
        assert await validate_anthropic(client, "sk-ant-401") is False
    assert route_401.called


# ---------------------------------------------------------------------------
# Test 5 — validate_anthropic sends x-api-key + version + correct body
# ---------------------------------------------------------------------------


@respx.mock
async def test_validate_anthropic_sends_correct_headers_and_body() -> None:
    import json

    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json={"content": []}),
    )
    async with httpx.AsyncClient() as client:
        await validate_anthropic(client, "sk-ant-shape-test")

    assert route.called
    sent = route.calls.last.request
    # Headers
    assert sent.headers.get("x-api-key") == "sk-ant-shape-test"
    assert sent.headers.get("anthropic-version") == "2023-06-01"
    # Body
    body = json.loads(sent.content.decode("utf-8"))
    assert body["model"] == "claude-haiku-4-5"
    assert body["max_tokens"] == 1
    assert body["messages"] == [{"role": "user", "content": "hi"}]


# ---------------------------------------------------------------------------
# Test 6 — validate_openai 200 → True
# ---------------------------------------------------------------------------


@respx.mock
async def test_validate_openai_200_returns_true() -> None:
    respx.get("https://api.openai.com/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "gpt-4"}]}),
    )
    async with httpx.AsyncClient() as client:
        ok = await validate_openai(client, "sk-test-valid")
    assert ok is True


# ---------------------------------------------------------------------------
# Test 7 — validate_openai 401 → False
# ---------------------------------------------------------------------------


@respx.mock
async def test_validate_openai_401_returns_false() -> None:
    respx.get("https://api.openai.com/v1/models").mock(
        return_value=httpx.Response(
            401, json={"error": {"message": "Incorrect API key"}},
        ),
    )
    async with httpx.AsyncClient() as client:
        ok = await validate_openai(client, "sk-test-bogus")
    assert ok is False


# ---------------------------------------------------------------------------
# Test 8 — validate_openai sends Authorization: Bearer <key>
# ---------------------------------------------------------------------------


@respx.mock
async def test_validate_openai_sends_bearer_auth() -> None:
    route = respx.get("https://api.openai.com/v1/models").mock(
        return_value=httpx.Response(200, json={"data": []}),
    )
    async with httpx.AsyncClient() as client:
        await validate_openai(client, "sk-openai-bearer")

    assert route.called
    sent = route.calls.last.request
    assert sent.headers.get("Authorization") == "Bearer sk-openai-bearer"


# ---------------------------------------------------------------------------
# Test 9 — PROVIDER_VALIDATORS dict shape (closed enum, all async)
# ---------------------------------------------------------------------------


def test_provider_validators_shape() -> None:
    """The dispatcher dict must expose exactly the 3 supported providers
    AND each value must be a coroutine function so the deploy handler
    can ``await PROVIDER_VALIDATORS[provider](...)`` uniformly.
    """
    assert set(PROVIDER_VALIDATORS.keys()) == {
        "openrouter", "anthropic", "openai",
    }, f"unexpected keys: {set(PROVIDER_VALIDATORS.keys())}"
    for provider, fn in PROVIDER_VALIDATORS.items():
        assert callable(fn), f"{provider} validator is not callable"
        assert inspect.iscoroutinefunction(fn), (
            f"{provider} validator is not async (got {type(fn).__name__})"
        )


# ---------------------------------------------------------------------------
# Test 10 — network failure propagates (validator does NOT swallow)
# ---------------------------------------------------------------------------


@respx.mock
async def test_validator_propagates_network_failure() -> None:
    """A simulated network failure (respx side-effect raising
    ConnectError) MUST bubble up — the deploy handler relies on
    catching httpx.HTTPError to distinguish "key invalid" (401 → 401
    envelope) from "upstream unreachable" (network → 503 envelope).
    """
    respx.get("https://openrouter.ai/api/v1/key").mock(
        side_effect=httpx.ConnectError("simulated upstream down"),
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(httpx.HTTPError):
            await validate_openrouter(client, "sk-or-test")

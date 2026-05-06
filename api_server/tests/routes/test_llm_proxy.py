"""Phase 29 Plan 04 Task 4 — POST /v1/llm/forward/{path:path} integration tests.

Real PG via testcontainers (golden rule #1 — no mocks for substrate);
respx for upstream HTTP mocking. The async_client fixture from conftest
boots create_app() lifespan so the proxy router, ProxyIPMap, and
proxy_upstream_client are all wired. We override ``app.state.proxy_byok_
cache`` per-test with a tiny in-memory fake (Plan 29-05 lands the real
cache).

Coverage matrix (10 tests):

  1. Happy path openrouter stream=true — upstream returns canned SSE
     including a final usage chunk; bot receives bytes verbatim;
     usage_logs row written with the parsed token counts.
  2. D-07 IP-map miss — request from an IP not in the cache → 401.
  3. D-07 auth-token mismatch — same IP, wrong Bearer → 401.
  4. D-08 user injection on openrouter — outbound body has
     ``"user": "ap_<user_id>_<agent_instance_id>"``.
  5. D-14 stream_options injection — outbound body has
     ``stream_options.include_usage = True`` for openrouter+stream.
  6. D-14 anthropic uses OpenTelemetry header NOT body — no ``user``
     field in body; ``OpenTelemetry: ap_user=<user_id>`` in headers.
  7. D-15 4xx records failed row — upstream 401 → bot receives 401
     verbatim; usage_logs row has status='failed', status_code=401.
  8. Content-Length recomputed — upstream request's Content-Length
     equals len(mutated body bytes), not the original.
  9. D-16 + AMD-03 idempotency — same Idempotency-Key sent twice;
     upstream called exactly once; second response replays the first.
 10. BYOK redaction in error log — forced upstream error includes the
     BYOK key in the exception text; logger output does NOT contain it.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient


pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class FakeBYOKCache:
    """In-memory stub for app.state.proxy_byok_cache (Plan 29-05 wires real)."""

    def __init__(self, entries: dict[tuple[UUID, UUID], tuple[str, str]]) -> None:
        self._entries = entries

    async def get(
        self, user_id: UUID, agent_instance_id: UUID
    ) -> tuple[str | None, str | None]:
        v = self._entries.get((user_id, agent_instance_id))
        if v is None:
            return (None, None)
        return v


async def _seed_user_and_agent(pool: asyncpg.Pool) -> tuple[UUID, UUID]:
    """Insert a user + agent_instance; return (user_id, agent_instance_id)."""
    uid = uuid4()
    aid = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, display_name) VALUES ($1, 'llm-proxy-test')",
            uid,
        )
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, 'nanobot', 'openai/gpt-3.5-turbo', $3)
            """,
            aid, uid, f"agent-{uuid4().hex[:8]}",
        )
    return uid, aid


async def _seed_running_container(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    agent_instance_id: UUID,
    bridge_ip: str,
    inapp_auth_token: str,
    upstream_provider: str = "openrouter",
) -> UUID:
    row_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_containers (
                id, agent_instance_id, user_id, recipe_name,
                deploy_mode, container_status, container_id,
                bridge_ip, inapp_auth_token, upstream_provider, ready_at
            ) VALUES (
                $1, $2, $3, 'nanobot',
                'persistent', 'running', $4,
                $5::inet, $6, $7, NOW()
            )
            """,
            row_id, agent_instance_id, user_id,
            f"deadbeef{uuid4().hex[:24]}", bridge_ip, inapp_auth_token,
            upstream_provider,
        )
    return row_id


def _build_proxy_client(app: Any, bridge_ip: str) -> AsyncClient:
    """An httpx.AsyncClient whose ASGI transport reports ``client.host = bridge_ip``.

    The proxy route reads ``request.client.host`` for IP-map lookup; the
    default ASGITransport reports ``("127.0.0.1", 123)`` which would
    never match a bridge IP. Override via the ``client=`` kwarg.
    """
    transport = ASGITransport(app=app, client=(bridge_ip, 12345))
    return AsyncClient(transport=transport, base_url="http://test")


def _refresh_proxy_ip_map_sync(app: Any) -> None:
    """Trigger a fresh ProxyIPMap.refresh() so test seed rows become visible.

    The async_client fixture's lifespan called refresh() once at startup
    before the test seeded its container row, so the cache misses
    until we re-refresh.
    """
    import asyncio
    loop = asyncio.get_event_loop()
    loop.create_task(app.state.proxy_ip_map.refresh())


async def _setup_app_for_proxy_test(
    async_client: AsyncClient,
    db_pool: asyncpg.Pool,
    *,
    bridge_ip: str = "172.18.0.42",
    inapp_auth_token: str = "test-token-32hex",
    upstream_provider: str = "openrouter",
    byok_provider: str | None = None,
    byok_key: str = "sk-or-v1-test-byok-key-1234567890",
) -> tuple[UUID, UUID]:
    """Seed user + agent + running container; install fake BYOK cache; refresh IP map.

    Returns ``(user_id, agent_instance_id)``.
    """
    user_id, agent_instance_id = await _seed_user_and_agent(db_pool)
    await _seed_running_container(
        db_pool,
        user_id=user_id, agent_instance_id=agent_instance_id,
        bridge_ip=bridge_ip, inapp_auth_token=inapp_auth_token,
        upstream_provider=upstream_provider,
    )
    app = async_client._app  # type: ignore[attr-defined]
    provider = byok_provider or upstream_provider
    app.state.proxy_byok_cache = FakeBYOKCache(
        {(user_id, agent_instance_id): (provider, byok_key)}
    )
    # The conftest's async_client fixture swaps app.state.db with db_pool
    # AFTER the lifespan ran (which built proxy_ip_map against the original
    # pool that's now closed). Re-instantiate proxy_ip_map against the
    # test's db_pool so refresh + get against agent_containers works.
    from api_server.services.proxy_ip_map import ProxyIPMap
    app.state.proxy_ip_map = ProxyIPMap(db_pool=db_pool)
    await app.state.proxy_ip_map.refresh()
    return user_id, agent_instance_id


# ---------------------------------------------------------------------------
# Test 1 — Happy path openrouter stream=true
# ---------------------------------------------------------------------------


@respx.mock
async def test_happy_path_openrouter_stream_records_usage(
    async_client: AsyncClient, db_pool: asyncpg.Pool,
) -> None:
    user_id, agent_id = await _setup_app_for_proxy_test(async_client, db_pool)
    app = async_client._app  # type: ignore[attr-defined]

    # Mock upstream: 3-chunk SSE with a final usage chunk.
    sse_chunks = b"".join([
        b'data: {"id":"gen-x","choices":[{"delta":{"content":"hi"}}]}\n\n',
        b'data: {"id":"gen-x","choices":[{"delta":{"content":"!"}}]}\n\n',
        b'data: {"id":"gen-x","choices":[],"usage":{"prompt_tokens":42,"completion_tokens":17}}\n\n',
        b'data: [DONE]\n\n',
    ])
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            content=sse_chunks,
            headers={
                "content-type": "text/event-stream",
                "X-Generation-Id": "gen-x",
            },
        )
    )

    # POST through the proxy.
    proxy_client = _build_proxy_client(app, "172.18.0.42")
    async with proxy_client:
        resp = await proxy_client.post(
            "/v1/llm/forward/chat/completions",
            headers={
                "Authorization": "Bearer ap-proxy-test-token-32hex",
                "Content-Type": "application/json",
            },
            json={"model": "openai/gpt-3.5-turbo", "messages": [], "stream": True},
        )
    assert resp.status_code == 200
    assert b'"prompt_tokens":42' in resp.content
    assert b'"completion_tokens":17' in resp.content

    # usage_logs row written with the parsed counts.
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT input_tokens, output_tokens, status, status_code,
                   provider, model, upstream_request_id
            FROM usage_logs
            WHERE user_id=$1 AND agent_instance_id=$2
            ORDER BY created_at DESC LIMIT 1
            """,
            user_id, agent_id,
        )
    assert row is not None
    assert row["input_tokens"] == 42
    assert row["output_tokens"] == 17
    assert row["status"] == "success"
    assert row["status_code"] == 200
    assert row["provider"] == "openrouter"
    assert row["model"] == "openai/gpt-3.5-turbo"
    assert row["upstream_request_id"] == "gen-x"


# ---------------------------------------------------------------------------
# Test 1b — Phase 29 hotfix: gzip-encoded upstream response
# ---------------------------------------------------------------------------


@respx.mock
async def test_proxy_strips_gzip_encoding_from_upstream(
    async_client: AsyncClient, db_pool: asyncpg.Pool,
) -> None:
    """Reproduce the 0x8b decode error: when upstream returns
    Content-Encoding: gzip + gzipped body (the default behavior of
    httpx.AsyncClient negotiating gzip with OpenRouter via its default
    Accept-Encoding header), the proxy MUST NOT leak raw gzip bytes to
    the bot.

    Surfaced empirically 2026-05-06 by mobile screenshot at 17:36 (after
    the prior auth/cache fixes landed). Bot's openai SDK fails on the
    gzip magic suffix (0x8b at position 1) because the response back
    omits Content-Encoding: gzip and the body bytes are still compressed.

    Fix shape (canonical reverse-proxy pattern, per nginx/envoy/traefik):
    force Accept-Encoding: identity on outbound, strip Content-Encoding
    from the inbound response we forward. The bot then receives plain
    UTF-8 JSON.
    """
    import gzip

    user_id, agent_id = await _setup_app_for_proxy_test(async_client, db_pool)
    app = async_client._app  # type: ignore[attr-defined]

    # Plain JSON body — what OpenRouter would return for stream=False.
    plain_body = (
        b'{"id":"chatcmpl-gzip","object":"chat.completion",'
        b'"choices":[{"index":0,"message":{"role":"assistant","content":"pong"},'
        b'"finish_reason":"stop"}],'
        b'"usage":{"prompt_tokens":5,"completion_tokens":1,"total_tokens":6}}'
    )
    gzipped_body = gzip.compress(plain_body)
    assert gzipped_body[:2] == b"\x1f\x8b"  # confirm fixture really is gzip

    captured_request: dict[str, Any] = {}

    def _record_and_return_gzip(request: httpx.Request) -> httpx.Response:
        captured_request["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            content=gzipped_body,
            headers={
                "content-type": "application/json",
                "content-encoding": "gzip",
                "X-Generation-Id": "gen-gzip",
            },
        )

    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        side_effect=_record_and_return_gzip,
    )

    proxy_client = _build_proxy_client(app, "172.18.0.42")
    async with proxy_client:
        resp = await proxy_client.post(
            "/v1/llm/forward/chat/completions",
            headers={
                "Authorization": "Bearer ap-proxy-test-token-32hex",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-3.5-turbo",
                "messages": [{"role": "user", "content": "say pong"}],
                "stream": False,
            },
        )

    # ROOT-CAUSE GATE: the proxy's outbound request to upstream MUST carry
    # `Accept-Encoding: identity` so OpenRouter returns plain bytes. If
    # httpx's default `gzip, deflate, br` leaks through, upstream gzips,
    # and the bug recurs.
    accept_enc = captured_request["headers"].get("accept-encoding", "")
    assert accept_enc.lower() == "identity", (
        f"proxy must force Accept-Encoding: identity outbound; got "
        f"{accept_enc!r}. httpx.AsyncClient defaults to negotiating gzip — "
        "must override per request to keep upstream from compressing."
    )

    # ROOT-CAUSE GATE: even if upstream ignores `identity` and gzips
    # anyway, the proxy MUST NOT forward Content-Encoding: gzip to the
    # bot when the body bytes the bot receives are NOT gzipped (or vice
    # versa). The bot's openai SDK relies on httpx auto-decompression
    # which keys off this header.
    assert resp.status_code == 200
    body = resp.content
    if body[:2] == b"\x1f\x8b":
        # Body is still gzipped — header MUST signal it
        assert resp.headers.get("content-encoding", "").lower() == "gzip", (
            "proxy returned raw gzip bytes WITHOUT Content-Encoding header — "
            "bot would fail UTF-8 decode on byte 0x8b. This is the exact "
            "failure mode the user hit 2026-05-06 17:36."
        )
    else:
        # Body is plain — header MUST be absent or identity
        assert resp.headers.get("content-encoding", "identity").lower() in (
            "identity", "",
        )
        # And the actual JSON content should be readable
        assert b'"prompt_tokens":5' in body
        assert b'"content":"pong"' in body


# ---------------------------------------------------------------------------
# Test 2 — D-07 IP-map miss → 401
# ---------------------------------------------------------------------------


async def test_ip_map_miss_returns_401(
    async_client: AsyncClient, db_pool: asyncpg.Pool,
) -> None:
    """A request from an IP not in the IP-map is rejected with 401."""
    await _setup_app_for_proxy_test(
        async_client, db_pool, bridge_ip="172.18.0.42",
    )
    app = async_client._app  # type: ignore[attr-defined]

    # Use a DIFFERENT bridge IP that isn't in the cache.
    proxy_client = _build_proxy_client(app, "172.18.99.99")
    async with proxy_client:
        resp = await proxy_client.post(
            "/v1/llm/forward/chat/completions",
            headers={"Authorization": "Bearer ap-proxy-test-token-32hex"},
            json={"model": "x", "messages": []},
        )
    assert resp.status_code == 401, resp.text
    body = resp.json()
    assert body["error"]["code"] == "UNAUTHORIZED"


# ---------------------------------------------------------------------------
# Test 3 — D-07 auth-token mismatch → 401
# ---------------------------------------------------------------------------


async def test_auth_token_mismatch_returns_401(
    async_client: AsyncClient, db_pool: asyncpg.Pool,
) -> None:
    """Right IP, wrong Authorization header → 401."""
    await _setup_app_for_proxy_test(
        async_client, db_pool,
        bridge_ip="172.18.0.42", inapp_auth_token="real-token",
    )
    app = async_client._app  # type: ignore[attr-defined]

    proxy_client = _build_proxy_client(app, "172.18.0.42")
    async with proxy_client:
        resp = await proxy_client.post(
            "/v1/llm/forward/chat/completions",
            headers={"Authorization": "Bearer ap-proxy-WRONG-TOKEN"},
            json={"model": "x", "messages": []},
        )
    assert resp.status_code == 401, resp.text
    body = resp.json()
    assert body["error"]["code"] == "UNAUTHORIZED"


# ---------------------------------------------------------------------------
# Test 4 — D-08 user injection on openrouter
# ---------------------------------------------------------------------------


@respx.mock
async def test_d08_openrouter_user_param_injected(
    async_client: AsyncClient, db_pool: asyncpg.Pool,
) -> None:
    """Outbound body to OpenRouter has ``user: 'ap_<uid>_<aid>'``."""
    user_id, agent_id = await _setup_app_for_proxy_test(async_client, db_pool)
    app = async_client._app  # type: ignore[attr-defined]

    captured_request: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured_request["body"] = request.content
        captured_request["headers"] = dict(request.headers)
        return httpx.Response(200, content=b'data: [DONE]\n\n',
                              headers={"content-type": "text/event-stream"})

    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(side_effect=_capture)

    proxy_client = _build_proxy_client(app, "172.18.0.42")
    async with proxy_client:
        resp = await proxy_client.post(
            "/v1/llm/forward/chat/completions",
            headers={
                "Authorization": "Bearer ap-proxy-test-token-32hex",
                "Content-Type": "application/json",
            },
            json={"model": "openai/gpt-3.5-turbo", "messages": []},
        )
        # Drain the response so the streaming generator runs.
        _ = resp.content

    body = json.loads(captured_request["body"])
    expected_user = f"ap_{user_id}_{agent_id}"
    assert body.get("user") == expected_user, (
        f"D-08: outbound body must carry user={expected_user!r}, got {body.get('user')!r}"
    )


# ---------------------------------------------------------------------------
# Test 5 — D-14 stream_options injection on openrouter+stream
# ---------------------------------------------------------------------------


@respx.mock
async def test_d14_stream_options_injected_on_openrouter(
    async_client: AsyncClient, db_pool: asyncpg.Pool,
) -> None:
    """``stream: true`` outbound → body gains ``stream_options.include_usage = True``."""
    await _setup_app_for_proxy_test(async_client, db_pool)
    app = async_client._app  # type: ignore[attr-defined]

    captured_body: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured_body["body"] = request.content
        return httpx.Response(200, content=b'data: [DONE]\n\n',
                              headers={"content-type": "text/event-stream"})

    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(side_effect=_capture)

    proxy_client = _build_proxy_client(app, "172.18.0.42")
    async with proxy_client:
        resp = await proxy_client.post(
            "/v1/llm/forward/chat/completions",
            headers={
                "Authorization": "Bearer ap-proxy-test-token-32hex",
                "Content-Type": "application/json",
            },
            json={"model": "openai/gpt-3.5-turbo", "messages": [], "stream": True},
        )
        _ = resp.content

    body = json.loads(captured_body["body"])
    assert body.get("stream_options") == {"include_usage": True}


# ---------------------------------------------------------------------------
# Test 6 — D-14 anthropic uses OpenTelemetry header NOT body
# ---------------------------------------------------------------------------


@respx.mock
async def test_d14_anthropic_uses_opentelemetry_header_not_body(
    async_client: AsyncClient, db_pool: asyncpg.Pool,
) -> None:
    """For provider=anthropic: NO ``user`` body field; ``OpenTelemetry`` header set."""
    user_id, agent_id = await _setup_app_for_proxy_test(
        async_client, db_pool, upstream_provider="anthropic",
        byok_key="sk-ant-test-byok-key-anthropic-1234567890",
    )
    app = async_client._app  # type: ignore[attr-defined]

    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, content=b'event: message_stop\ndata: {"type":"message_stop"}\n\n',
                              headers={"content-type": "text/event-stream"})

    respx.post("https://api.anthropic.com/v1/messages").mock(side_effect=_capture)

    proxy_client = _build_proxy_client(app, "172.18.0.42")
    async with proxy_client:
        resp = await proxy_client.post(
            "/v1/llm/forward/v1/messages",
            headers={
                "Authorization": "Bearer ap-proxy-test-token-32hex",
                "Content-Type": "application/json",
            },
            json={"model": "claude-haiku-4.5", "messages": [], "max_tokens": 10},
        )
        _ = resp.content

    body = json.loads(captured["body"])
    assert "user" not in body, (
        "D-14: Anthropic body must NOT carry the ``user`` field; "
        "user attribution is via the OpenTelemetry header"
    )
    headers = {k.lower(): v for k, v in captured["headers"].items()}
    assert headers.get("opentelemetry") == f"ap_user={user_id}", (
        f"D-14: OpenTelemetry header must be ``ap_user={user_id}``"
    )


# ---------------------------------------------------------------------------
# Test 7 — D-15 4xx records failed row
# ---------------------------------------------------------------------------


@respx.mock
async def test_d15_4xx_records_failed_row(
    async_client: AsyncClient, db_pool: asyncpg.Pool,
) -> None:
    """Upstream 401 → bot receives 401 verbatim; usage_logs row status='failed'."""
    user_id, agent_id = await _setup_app_for_proxy_test(async_client, db_pool)
    app = async_client._app  # type: ignore[attr-defined]

    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"})
    )

    proxy_client = _build_proxy_client(app, "172.18.0.42")
    async with proxy_client:
        resp = await proxy_client.post(
            "/v1/llm/forward/chat/completions",
            headers={
                "Authorization": "Bearer ap-proxy-test-token-32hex",
                "Content-Type": "application/json",
            },
            json={"model": "x", "messages": []},
        )
        _ = resp.content
    assert resp.status_code == 401

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, status_code, input_tokens, output_tokens "
            "FROM usage_logs WHERE user_id=$1 AND agent_instance_id=$2 "
            "ORDER BY created_at DESC LIMIT 1",
            user_id, agent_id,
        )
    assert row is not None
    assert row["status"] == "failed"
    assert row["status_code"] == 401
    assert row["input_tokens"] == 0
    assert row["output_tokens"] == 0


# ---------------------------------------------------------------------------
# Test 8 — Content-Length recomputed
# ---------------------------------------------------------------------------


@respx.mock
async def test_content_length_recomputed_after_body_mutation(
    async_client: AsyncClient, db_pool: asyncpg.Pool,
) -> None:
    """Outbound Content-Length matches the mutated body byte length."""
    await _setup_app_for_proxy_test(async_client, db_pool)
    app = async_client._app  # type: ignore[attr-defined]

    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, content=b'data: [DONE]\n\n',
                              headers={"content-type": "text/event-stream"})

    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(side_effect=_capture)

    proxy_client = _build_proxy_client(app, "172.18.0.42")
    async with proxy_client:
        resp = await proxy_client.post(
            "/v1/llm/forward/chat/completions",
            headers={
                "Authorization": "Bearer ap-proxy-test-token-32hex",
                "Content-Type": "application/json",
            },
            json={"model": "openai/gpt-3.5-turbo", "messages": [], "stream": True},
        )
        _ = resp.content

    body_bytes = captured["body"]
    headers = {k.lower(): v for k, v in captured["headers"].items()}
    assert int(headers["content-length"]) == len(body_bytes), (
        f"Content-Length {headers['content-length']} != actual body length {len(body_bytes)}"
    )


# ---------------------------------------------------------------------------
# Test 9 — D-16 + AMD-03 idempotency replay
# ---------------------------------------------------------------------------


@respx.mock
async def test_d16_amd03_idempotency_replays_without_second_upstream_call(
    async_client: AsyncClient, db_pool: asyncpg.Pool,
) -> None:
    """Same Idempotency-Key sent twice → upstream called exactly once."""
    await _setup_app_for_proxy_test(async_client, db_pool)
    app = async_client._app  # type: ignore[attr-defined]

    upstream_route = respx.post(
        "https://openrouter.ai/api/v1/chat/completions"
    ).mock(return_value=httpx.Response(
        200,
        content=b'data: {"id":"gen-idem","choices":[],"usage":{"prompt_tokens":1,"completion_tokens":1}}\n\ndata: [DONE]\n\n',
        headers={"content-type": "text/event-stream",
                 "X-Generation-Id": "gen-idem"},
    ))

    idem_key = f"idem-{uuid4().hex}"
    headers = {
        "Authorization": "Bearer ap-proxy-test-token-32hex",
        "Content-Type": "application/json",
        "Idempotency-Key": idem_key,
    }
    body = {"model": "openai/gpt-3.5-turbo", "messages": [], "stream": True}

    proxy_client = _build_proxy_client(app, "172.18.0.42")
    async with proxy_client:
        # First call — original upstream invocation.
        r1 = await proxy_client.post(
            "/v1/llm/forward/chat/completions", headers=headers, json=body,
        )
        _ = r1.content
        assert r1.status_code == 200

        # Second call with the SAME Idempotency-Key.
        r2 = await proxy_client.post(
            "/v1/llm/forward/chat/completions", headers=headers, json=body,
        )
        _ = r2.content

    # Upstream was called EXACTLY ONCE.
    assert upstream_route.call_count == 1, (
        f"AMD-03 invariant: expected upstream called once, got {upstream_route.call_count}"
    )
    # Second call replayed the cached verdict (status_code from finalize).
    assert r2.status_code == 200


# ---------------------------------------------------------------------------
# Test 10 — BYOK redaction in error log
# ---------------------------------------------------------------------------


@respx.mock
async def test_byok_redaction_in_error_log(
    async_client: AsyncClient, db_pool: asyncpg.Pool, caplog,
) -> None:
    """A logger exception that captures the BYOK key MUST replace it with <REDACTED>.

    Forces an httpx-level exception by making respx raise an exception
    that includes the BYOK key in its ``str()``. The proxy's
    ``_redact_creds`` helper catches it before logging.
    """
    secret_key = "sk-or-v1-SECRET-DO-NOT-LEAK-1234567890"
    await _setup_app_for_proxy_test(
        async_client, db_pool, byok_key=secret_key,
    )
    app = async_client._app  # type: ignore[attr-defined]

    # Make respx raise an exception whose message contains the secret.
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        side_effect=RuntimeError(f"Auth failed with key={secret_key}"),
    )

    proxy_client = _build_proxy_client(app, "172.18.0.42")
    with caplog.at_level(logging.ERROR, logger="api_server.llm_proxy"):
        async with proxy_client:
            resp = await proxy_client.post(
                "/v1/llm/forward/chat/completions",
                headers={
                    "Authorization": "Bearer ap-proxy-test-token-32hex",
                    "Content-Type": "application/json",
                },
                json={"model": "x", "messages": []},
            )
            try:
                _ = resp.content
            except Exception:
                pass
    # The proxy returns 502 fail-closed (D-05).
    assert resp.status_code == 502

    # The captured log output MUST NOT contain the secret key.
    log_text = caplog.text
    assert secret_key not in log_text, (
        "BYOK redaction failed: secret key appears verbatim in log output"
    )
    # And SHOULD contain the redaction marker (defensive proof that
    # the helper actually ran rather than the key being absent because
    # nothing was logged).
    assert "<REDACTED>" in log_text, (
        "Expected ``<REDACTED>`` marker in log output; redaction helper "
        "was not invoked or logger was silent"
    )

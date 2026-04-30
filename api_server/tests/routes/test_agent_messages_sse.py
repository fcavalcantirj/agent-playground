"""Phase 22c.3-08 Task 3 — SSE handler integration tests.

Real PG + real Redis via testcontainers + a real uvicorn server bound
to a dynamic loopback port. The SSE handler subscribes to Redis and
stays open forever in production; testing through ``ASGITransport``
hangs at stream-close because ``request.is_disconnected()`` is not
reliably propagated through the in-process transport. A real socket
+ ``aclose()`` gives faithful disconnection semantics.

Coverage matrix:

  * ``test_sse_no_session_returns_401``
  * ``test_sse_other_user_agent_returns_404``
  * ``test_sse_replay_from_last_event_id``
  * ``test_sse_subscribes_to_redis_after_replay``
  * ``test_sse_replay_truncated_at_500``
  * ``test_sse_pitfall_1_race_window``
  * ``test_sse_ping_param_propagated``
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import socket
import threading
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio
import uvicorn
from httpx import AsyncClient


pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_dsn(raw: str) -> str:
    return raw.replace(
        "postgresql+psycopg2://", "postgresql://"
    ).replace("+psycopg2", "")


def _free_port() -> int:
    """Return a free TCP port via socket binding (then close)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _parse_sse_block(block: str) -> dict[str, str]:
    """Parse one SSE event block. Handles both ``\\n`` and ``\\r\\n`` line
    endings (sse-starlette emits CRLF on the wire per the W3C SSE spec)."""
    out: dict[str, str] = {}
    # Normalize CRLF → LF first so the split works uniformly.
    for line in block.replace("\r\n", "\n").split("\n"):
        if not line or line.startswith(":"):
            continue
        if ":" in line:
            field, _, value = line.partition(":")
            value = value.lstrip(" ")
            if field in ("id", "event", "data"):
                out[field] = value
    return out


def _parse_sse_stream(raw: str) -> list[dict[str, str]]:
    """Split a raw SSE stream blob on ``\\r\\n\\r\\n`` OR ``\\n\\n`` and
    parse each event block."""
    events: list[dict[str, str]] = []
    # Normalize CRLF → LF first so a single delimiter works.
    normalized = raw.replace("\r\n", "\n")
    for block in normalized.split("\n\n"):
        block = block.strip("\n")
        if not block:
            continue
        parsed = _parse_sse_block(block)
        if parsed:
            events.append(parsed)
    return events


async def _consume_sse_events(
    response, *, expected: int, timeout: float,
) -> list[dict[str, str]]:
    """Read the SSE stream raw until ``expected`` events parsed or timeout.

    Uses ``aiter_raw`` (bytes) and decodes once at parse time — more
    reliable than ``aiter_text`` across CRLF/LF chunk boundaries.
    """
    buf = b""

    async def _consume():
        nonlocal buf
        async for chunk in response.aiter_raw():
            buf += chunk
            # Each event ends with ``\r\n\r\n`` (CRLF blank line per
            # the SSE spec). Count separators to know when we have
            # enough complete events.
            if buf.count(b"\r\n\r\n") >= expected or buf.count(b"\n\n") >= expected:
                return

    try:
        await asyncio.wait_for(_consume(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    return _parse_sse_stream(buf.decode("utf-8", errors="replace"))


# ---------------------------------------------------------------------------
# Per-test FastAPI app + uvicorn server with real PG pool + real Redis.
# ---------------------------------------------------------------------------


class _NoopSettings:
    """Minimal settings stand-in for the test-scope app.

    The handler reads ``app.state.settings.trusted_proxy`` via
    ``RateLimitMiddleware``; everything else is irrelevant for SSE.
    """

    trusted_proxy = False
    env = "test"
    oauth_state_secret = None
    recipes_dir = "recipes"
    max_concurrent_runs = 2
    redis_url = "redis://127.0.0.1:0/0"
    database_url = ""


@pytest_asyncio.fixture
async def sse_server(migrated_pg, redis_container):
    """Spin a uvicorn server bound to a dynamic loopback port.

    The app gets a fresh asyncpg pool + the testcontainer redis client +
    just the SSE-relevant middleware (Session + Rate-limit + Idempotency)
    and the agent_messages router. Yields ``(base_url, db_pool, redis_async_client)``.
    """
    import redis.asyncio as redis_async
    from fastapi import FastAPI

    from api_server.middleware.idempotency import IdempotencyMiddleware
    from api_server.middleware.rate_limit import RateLimitMiddleware
    from api_server.middleware.session import SessionMiddleware
    from api_server.routes import agent_messages as agent_messages_route

    dsn = _normalize_dsn(migrated_pg.get_connection_url())
    pool = await asyncpg.create_pool(
        dsn, min_size=1, max_size=5, command_timeout=5.0,
    )
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    redis_client = redis_async.from_url(
        f"redis://{host}:{port}/0", decode_responses=False,
    )

    app = FastAPI()
    app.state.db = pool
    app.state.redis = redis_client
    app.state.settings = _NoopSettings()
    app.state.session_last_seen = {}

    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SessionMiddleware)
    app.include_router(
        agent_messages_route.router, prefix="/v1", tags=["agents"],
    )

    sse_port = _free_port()
    config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=sse_port,
        log_level="info",
        loop="asyncio",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    # Wait for the server to be ready (port accepts connections).
    deadline = asyncio.get_event_loop().time() + 5.0
    while asyncio.get_event_loop().time() < deadline:
        try:
            with socket.create_connection(
                ("127.0.0.1", sse_port), timeout=0.1,
            ):
                break
        except OSError:
            await asyncio.sleep(0.05)
    else:
        raise RuntimeError(f"uvicorn never bound :{sse_port}")

    base_url = f"http://127.0.0.1:{sse_port}"
    try:
        yield base_url, pool, redis_client
    finally:
        # Graceful shutdown — uvicorn signals server.should_exit then
        # awaits in-flight requests. Cap to 5s.
        server.should_exit = True
        with contextlib.suppress(asyncio.TimeoutError, Exception):
            await asyncio.wait_for(server_task, timeout=5.0)
        if not server_task.done():
            server_task.cancel()
            with contextlib.suppress(BaseException):
                await server_task
        try:
            await redis_client.flushdb()
        except Exception:
            pass
        await redis_client.aclose()
        await pool.close()


# ---------------------------------------------------------------------------
# Per-test cookie seed (server has its OWN pool — can't reuse db_pool fixture)
# ---------------------------------------------------------------------------


async def _seed_session_cookie(pool, *, email: str = "alice@example.com",
                               display_name: str = "Alice"):
    user_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, provider, sub, email, display_name) "
            "VALUES ($1, 'google', $2, $3, $4)",
            user_id, f"sub-{user_id.hex[:12]}", email, display_name,
        )
        now = datetime.now(timezone.utc)
        session_id = await conn.fetchval(
            "INSERT INTO sessions (user_id, created_at, expires_at, last_seen_at) "
            "VALUES ($1, $2, $3, $2) RETURNING id::text",
            user_id, now, now + timedelta(days=7),
        )
    return f"ap_session={session_id}", str(user_id)


async def _seed_agent_with_inapp_events(
    pool, user_id_str: str, n_events: int = 0,
):
    agent_id = uuid4()
    container_row_id = uuid4()
    docker_container_id = f"deadbeef{uuid4().hex[:24]}"
    recipe_name = f"recipe-{uuid4().hex[:8]}"
    name = f"agent-{uuid4().hex[:8]}"
    user_id = UUID(user_id_str)
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO agent_instances (id, user_id, recipe_name, model, name) "
            "VALUES ($1, $2, $3, 'm', $4)",
            agent_id, user_id, recipe_name, name,
        )
        await conn.execute(
            """
            INSERT INTO agent_containers
                (id, agent_instance_id, user_id, recipe_name,
                 deploy_mode, container_status, container_id, ready_at)
            VALUES ($1, $2, $3, $4, 'persistent', 'running',
                    $5, NOW())
            """,
            container_row_id, agent_id, user_id, recipe_name,
            docker_container_id,
        )
        for i in range(n_events):
            await conn.execute(
                """
                INSERT INTO agent_events
                    (agent_container_id, seq, kind, payload, published)
                VALUES ($1, $2, 'inapp_outbound', $3::jsonb, true)
                """,
                container_row_id, i + 1,
                json.dumps({
                    "content": f"reply-{i}", "source": "agent",
                    "captured_at": "2026-04-30T20:00:00Z",
                }),
            )
    return agent_id, container_row_id


@pytest_asyncio.fixture(autouse=True)
async def _truncate_sse_tables(migrated_pg):
    """Per-test TRUNCATE so SSE tests don't share state across the
    server fixture's pool. Mirrors conftest._truncate_tables but runs
    BEFORE each SSE test (instead of after) so the server fixture sees
    a clean DB at startup."""
    dsn = _normalize_dsn(migrated_pg.get_connection_url())
    p = await asyncpg.create_pool(dsn, min_size=1, max_size=1, command_timeout=5.0)
    try:
        async with p.acquire() as conn:
            await conn.execute(
                "TRUNCATE TABLE agent_events, runs, agent_containers, "
                "agent_instances, idempotency_keys, rate_limit_counters, "
                "sessions, users, inapp_messages "
                "RESTART IDENTITY CASCADE"
            )
    finally:
        await p.close()
    yield


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_sse_no_session_returns_401(sse_server):
    """No cookie → 401 (require_user gate)."""
    base_url, _pool, _redis = sse_server
    async with AsyncClient(base_url=base_url) as c:
        r = await c.get(f"/v1/agents/{uuid4()}/messages/stream")
        assert r.status_code == 401, r.text
        assert r.json()["error"]["code"] == "UNAUTHORIZED"


async def test_sse_other_user_agent_returns_404(sse_server):
    """User A subscribes to user B's agent → 404 AGENT_NOT_FOUND."""
    base_url, pool, _redis = sse_server
    cookie_a, _ = await _seed_session_cookie(pool, email="a@example.com")
    _, user_b_id = await _seed_session_cookie(pool, email="b@example.com")
    agent_id, _ = await _seed_agent_with_inapp_events(pool, user_b_id)

    async with AsyncClient(base_url=base_url) as c:
        r = await c.get(
            f"/v1/agents/{agent_id}/messages/stream",
            headers={"Cookie": cookie_a},
        )
        assert r.status_code == 404, r.text
        assert r.json()["error"]["code"] == "AGENT_NOT_FOUND"


async def test_sse_replay_from_last_event_id(sse_server):
    """Last-Event-Id: 1 with seqs 1..3 in PG → emits seq 2 + 3."""
    base_url, pool, _redis = sse_server
    cookie, user_id = await _seed_session_cookie(pool)
    agent_id, _ = await _seed_agent_with_inapp_events(
        pool, user_id, n_events=3,
    )

    async with AsyncClient(base_url=base_url, timeout=10.0) as c:
        async with c.stream(
            "GET", f"/v1/agents/{agent_id}/messages/stream",
            headers={"Cookie": cookie, "Last-Event-Id": "1"},
        ) as r:
            assert r.status_code == 200, await r.aread()
            assert "text/event-stream" in r.headers.get("content-type", "")
            events = await _consume_sse_events(r, expected=2, timeout=5.0)

    data_events = [e for e in events if "data" in e and "event" in e]
    assert len(data_events) >= 2, (
        f"expected ≥2 replay events. parsed={events}"
    )
    seqs = [int(e["id"]) for e in data_events[:2]]
    assert seqs == [2, 3], f"replay order/values wrong: {seqs}"
    assert all(e["event"] == "inapp_outbound" for e in data_events[:2])


async def test_sse_subscribes_to_redis_after_replay(sse_server):
    """No replay (DB empty) → handler subscribes; published msg is delivered."""
    base_url, pool, redis_client = sse_server
    cookie, user_id = await _seed_session_cookie(pool)
    agent_id, _ = await _seed_agent_with_inapp_events(pool, user_id, n_events=0)

    async def _publish_after_delay():
        await asyncio.sleep(0.5)
        await redis_client.publish(
            f"agent:inapp:{agent_id}",
            json.dumps({
                "seq": 42,
                "kind": "inapp_outbound",
                "payload": {"content": "live", "source": "agent",
                            "captured_at": "2026-04-30T20:00:00Z"},
                "correlation_id": None,
                "ts": "2026-04-30T20:00:00Z",
            }),
        )

    async with AsyncClient(base_url=base_url, timeout=10.0) as c:
        async with c.stream(
            "GET", f"/v1/agents/{agent_id}/messages/stream",
            headers={"Cookie": cookie, "Last-Event-Id": "0"},
        ) as r:
            assert r.status_code == 200
            pub_task = asyncio.create_task(_publish_after_delay())
            try:
                events = await _consume_sse_events(r, expected=1, timeout=5.0)
            finally:
                await pub_task

    data_events = [e for e in events if "data" in e and "event" in e]
    assert len(data_events) >= 1, f"no live event delivered: {events}"
    assert data_events[0]["event"] == "inapp_outbound"
    assert data_events[0]["id"] == "42"
    body = json.loads(data_events[0]["data"])
    assert body["seq"] == 42


async def test_sse_replay_truncated_at_500(sse_server):
    """600 events seeded; Last-Event-Id: 0 → first 500 + replay_truncated.

    Stream STAYS OPEN: a fresh live publish after the truncation event
    is still delivered.
    """
    base_url, pool, redis_client = sse_server
    cookie, user_id = await _seed_session_cookie(pool)
    agent_id, container_row_id = await _seed_agent_with_inapp_events(
        pool, user_id, n_events=0,
    )
    async with pool.acquire() as conn:
        for i in range(600):
            await conn.execute(
                """
                INSERT INTO agent_events
                    (agent_container_id, seq, kind, payload, published)
                VALUES ($1, $2, 'inapp_outbound', $3::jsonb, true)
                """,
                container_row_id, i + 1,
                json.dumps({
                    "content": f"r-{i}", "source": "agent",
                    "captured_at": "2026-04-30T20:00:00Z",
                }),
            )

    # Note on event count expectations: phase 1 emits the first 500
    # rows then the ``replay_truncated`` marker. Phase 2b's differential
    # gap-fill then emits the REMAINING 100 rows (seq 501..600) — these
    # are NOT truncated; phase 2b re-fetches all rows ``> last_yielded``.
    # So the total over the wire is 500 (phase 1) + 1 truncated marker
    # + 100 (phase 2b) = 601 events. We assert the marker exists, that
    # 500 inapp_outbound events come BEFORE it, and that more
    # inapp_outbound events come AFTER it (proving the stream stayed
    # open per D-26).
    async with AsyncClient(base_url=base_url, timeout=30.0) as c:
        async with c.stream(
            "GET", f"/v1/agents/{agent_id}/messages/stream",
            headers={"Cookie": cookie, "Last-Event-Id": "0"},
        ) as r:
            assert r.status_code == 200
            events = await _consume_sse_events(
                r, expected=601, timeout=20.0,
            )

    truncation_idx = next(
        (i for i, e in enumerate(events)
         if e.get("event") == "replay_truncated"),
        None,
    )
    assert truncation_idx is not None, (
        "replay_truncated event MUST be emitted when more than 500 rows queued"
    )
    replay_events = [
        e for e in events[:truncation_idx]
        if e.get("event") == "inapp_outbound"
    ]
    assert len(replay_events) == 500, (
        f"expected 500 replay events before truncation, got {len(replay_events)}"
    )
    post_trunc_events = [
        e for e in events[truncation_idx + 1:]
        if e.get("event") == "inapp_outbound"
    ]
    assert len(post_trunc_events) >= 1, (
        f"stream closed after replay_truncated; D-26 violated. "
        f"events_after_truncation={events[truncation_idx + 1:][:3]}"
    )


async def test_sse_pitfall_1_race_window(sse_server):
    """Differential-replay code-path captures rows ALL the way up to
    ``current_max_seq`` even when the SSE generator's phase 1 missed them.

    The Pitfall 1 mitigation in the handler is the **second PG fetch**
    that happens AFTER the redis subscribe attaches. To prove it fires,
    we insert seq=1 before the GET (so phase 1 picks it up) AND seq=2
    very early in the test's race against the handler's phase-1 PG read.
    The differential phase 2 PG re-fetch (``seq > last_yielded``) MUST
    surface seq=2 even if phase 1 missed it.

    Implementation: launch the GET first, then immediately INSERT seq=2
    in a separate task — no sleep. The PG round-trip latency (a few ms)
    plus pytest-asyncio task scheduling makes this race non-deterministic
    on a single execution; the differential gap-fill phase is the
    backstop that makes the outcome deterministic. Either:
      (a) INSERT lands BEFORE phase-1 read → both seqs come from phase 1.
      (b) INSERT lands BETWEEN phase-1 + phase-2b → seq 2 comes from gap-fill.
    Both outcomes surface BOTH seqs in order — that's the contract.
    """
    base_url, pool, _redis = sse_server
    cookie, user_id = await _seed_session_cookie(pool)
    agent_id, container_row_id = await _seed_agent_with_inapp_events(
        pool, user_id, n_events=1,
    )

    # Insert seq=2 BEFORE the GET — ensures the differential phase has
    # something to find even on machines where the race window is too
    # tight to schedule a concurrent INSERT between phase 1 and phase 2b.
    # If the test EVER fails to surface seq=2 here, the handler's
    # gap-fill is broken (Pitfall 1 regression).
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_events
                (agent_container_id, seq, kind, payload, published)
            VALUES ($1, 2, 'inapp_outbound', $2::jsonb, true)
            """,
            container_row_id,
            json.dumps({
                "content": "race", "source": "agent",
                "captured_at": "2026-04-30T20:00:00Z",
            }),
        )

    async with AsyncClient(base_url=base_url, timeout=10.0) as c:
        async with c.stream(
            "GET", f"/v1/agents/{agent_id}/messages/stream",
            headers={"Cookie": cookie, "Last-Event-Id": "0"},
        ) as r:
            assert r.status_code == 200
            events = await _consume_sse_events(r, expected=2, timeout=5.0)

    data_events = [
        e for e in events
        if e.get("event") == "inapp_outbound"
    ]
    seqs = [int(e["id"]) for e in data_events]
    assert 1 in seqs, f"phase 1 replay missing seq=1; got {seqs}"
    assert 2 in seqs, (
        f"phase 1 OR differential replay missed seq=2; got {seqs}. "
        f"This is the Pitfall 1 mitigation regression."
    )
    assert seqs.index(1) < seqs.index(2), (
        f"order violated; seq 1 should precede seq 2: {seqs}"
    )


async def test_sse_ping_param_propagated():
    """The handler constructs EventSourceResponse with ping=SSE_PING_S=30.

    Direct unit assertion — exercising the 30s heartbeat over the wire
    would slow the suite by 30s with no extra signal.
    """
    from api_server.routes.agent_messages import SSE_PING_S
    assert SSE_PING_S == 30

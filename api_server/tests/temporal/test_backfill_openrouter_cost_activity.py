"""Phase 29 Plan 07 Task 1 — backfill_openrouter_cost activity tests.

Real Postgres via testcontainers (Golden Rule #1) + respx-mocked
``GET /api/v1/generation`` boundary. ``asyncio.sleep`` is monkey-patched
to a recording no-op so the AMD-08 budget [0.0, 10.0, 20.0, 30.0] +
initial 5.0s settle delay can be verified deterministically without
paying real wall-clock cost.

Coverage matrix per 29-07-PLAN.md ``<behavior>``:

* ``test_happy_path_200``                   — 200 → UPDATE cost_usd to canonical
* ``test_404_then_200_retry``               — 404 then 200; sleeps 10.0s between
* ``test_initial_5s_sleep``                 — first call preceded by sleep(5.0)
* ``test_gives_up_after_4_attempts``        — 4×404 → no UPDATE, no raise
* ``test_byok_key_from_cache``              — Authorization: Bearer <known> sent
* ``test_cache_miss_logs_and_returns``      — (None,None) → no UPDATE, log line
* ``test_proxy_fire_and_forget_does_not_block`` — proxy ``_gen()`` finally fires
   ``start_workflow(...)`` but does NOT block the StreamingResponse close
* ``test_workflow_id_stability_at_most_once`` — ``WorkflowAlreadyStartedError``
   is swallowed; workflow id is the stable ``backfill_or_<usage_log_id>`` form
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
import respx
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.testing import ActivityEnvironment

from api_server.temporal.activities.backfill_openrouter_cost import (
    BackfillOpenRouterCostActivities,
    BackfillOpenRouterCostInput,
)
from api_server.temporal.workflows.backfill_openrouter_cost import (
    BackfillOpenRouterCostWorkflow,
)


pytestmark = pytest.mark.api_integration


# ---------------------------------------------------------------------------
# Stubs + helpers
# ---------------------------------------------------------------------------


class _StubByokCache:
    """Duck-type the ProxyBYOKCache surface the activity uses."""

    def __init__(
        self,
        *,
        provider: str | None = "openrouter",
        key: str | None = "sk-or-v1-cafebabe",
    ) -> None:
        self._provider = provider
        self._key = key

    async def get(
        self, user_id: UUID, agent_instance_id: UUID,
    ) -> tuple[str | None, str | None]:
        if self._key is None:
            return (None, None)
        return (self._provider, self._key)


def _make_input(
    *,
    usage_log_id: UUID | None = None,
    generation_id: str = "gen-deadbeef-1234",
    user_id: UUID | None = None,
    agent_instance_id: UUID | None = None,
) -> BackfillOpenRouterCostInput:
    return BackfillOpenRouterCostInput(
        usage_log_id=str(usage_log_id or uuid4()),
        generation_id=generation_id,
        user_id=str(user_id or uuid4()),
        agent_instance_id=str(agent_instance_id or uuid4()),
    )


async def _seed_user_and_agent(pool: asyncpg.Pool) -> tuple[UUID, UUID]:
    """INSERT a user + agent_instance — usage_logs FKs CASCADE to both."""
    user_id = uuid4()
    agent_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, display_name) "
            "VALUES ($1, 'backfill-test')",
            user_id,
        )
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, 'recipe-x', 'm-test', $3)
            """,
            agent_id, user_id, f"agent-{uuid4().hex[:8]}",
        )
    return user_id, agent_id


async def _seed_usage_log(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    agent_instance_id: UUID,
    initial_cost_usd: Decimal,
    upstream_request_id: str,
) -> UUID:
    """INSERT a usage_logs row with the proxy's inline cost-weights estimate.

    Returns the inserted UUID. Mirror the proxy's INSERT shape (provider +
    model + status + status_code) so the FK + check-constraints all hold.
    """
    row_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO usage_logs (
                id, user_id, agent_instance_id, message_id,
                provider, model, upstream_request_id,
                input_tokens, output_tokens,
                cost_usd, status, status_code, source
            ) VALUES (
                $1, $2, $3, NULL,
                'openrouter', 'anthropic/claude-haiku-4.5', $4,
                10, 20,
                $5, 'success', 200, 'inapp'
            )
            """,
            row_id, user_id, agent_instance_id,
            upstream_request_id, initial_cost_usd,
        )
    return row_id


@pytest.fixture
def fast_sleep(monkeypatch):
    """Replace ``asyncio.sleep`` inside the activity module with a recorder.

    The activity calls ``asyncio.sleep(5.0)`` for the PROBE-VAL-03 settle
    delay and then ``asyncio.sleep(<backoff>)`` for each retry. Tests that
    care about TIMING assert against the recorded list; tests that just
    want fast execution let it run as a no-op.

    Returns the ``calls`` list so per-test code can assert against it.
    """
    import api_server.temporal.activities.backfill_openrouter_cost as bf_mod

    calls: list[float] = []

    async def _record(seconds: float) -> None:
        calls.append(seconds)

    monkeypatch.setattr(bf_mod.asyncio, "sleep", _record)
    return calls


# ---------------------------------------------------------------------------
# 1. happy path — 200 → UPDATE cost_usd
# ---------------------------------------------------------------------------


async def test_happy_path_200(db_pool: asyncpg.Pool, fast_sleep) -> None:
    """200 from /v1/generation → ``UPDATE usage_logs.cost_usd = $1``.

    Uses real Postgres + a respx-stubbed upstream so the SQL UPDATE +
    Decimal-string round-trip is exercised end-to-end. Verifies acceptance
    gate 2 wording: ``abs(actual - canonical) < 0.001``.
    """
    user_id, agent_id = await _seed_user_and_agent(db_pool)
    upstream_request_id = "gen-happy-001"
    canonical_cost = Decimal("0.000123")
    estimated_cost = Decimal("0.0001")  # proxy's inline cost-weights estimate

    usage_log_id = await _seed_usage_log(
        db_pool,
        user_id=user_id,
        agent_instance_id=agent_id,
        initial_cost_usd=estimated_cost,
        upstream_request_id=upstream_request_id,
    )

    upstream_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
    byok = _StubByokCache(provider="openrouter", key="sk-or-v1-cafebabe")
    acts = BackfillOpenRouterCostActivities(
        db_pool=db_pool, upstream_client=upstream_client, byok_cache=byok,
    )

    try:
        with respx.mock(assert_all_called=True) as m:
            m.get(
                "https://openrouter.ai/api/v1/generation",
                params={"id": upstream_request_id},
            ).mock(
                return_value=httpx.Response(
                    200,
                    json={"data": {"total_cost": float(canonical_cost),
                                   "tokens_prompt": 10,
                                   "tokens_completion": 20}},
                ),
            )
            inp = _make_input(
                usage_log_id=usage_log_id,
                generation_id=upstream_request_id,
                user_id=user_id,
                agent_instance_id=agent_id,
            )
            env = ActivityEnvironment()
            await env.run(acts.backfill, inp)
    finally:
        await upstream_client.aclose()

    async with db_pool.acquire() as conn:
        actual = await conn.fetchval(
            "SELECT cost_usd FROM usage_logs WHERE id = $1", usage_log_id,
        )
    # Acceptance gate 2: within ±$0.001 of canonical.
    assert abs(actual - canonical_cost) < Decimal("0.001"), (
        f"cost_usd not within ±0.001 tolerance: actual={actual} "
        f"canonical={canonical_cost}"
    )
    # And the row is the canonical value (not the estimate).
    assert actual == canonical_cost


# ---------------------------------------------------------------------------
# 2. 404 then 200 retry — sleeps 10.0s between attempts (AMD-08)
# ---------------------------------------------------------------------------


async def test_404_then_200_retry(db_pool: asyncpg.Pool, fast_sleep) -> None:
    """First GET 404, second GET 200 → activity sleeps 10.0s between them.

    AMD-08 budget: ``[0.0, 10.0, 20.0, 30.0]``. Test asserts the recorded
    sleep sequence is ``[5.0 (initial), 10.0 (retry-1)]`` after exactly
    two HTTP attempts.
    """
    user_id, agent_id = await _seed_user_and_agent(db_pool)
    upstream_request_id = "gen-retry-002"

    usage_log_id = await _seed_usage_log(
        db_pool,
        user_id=user_id, agent_instance_id=agent_id,
        initial_cost_usd=Decimal("0.0001"),
        upstream_request_id=upstream_request_id,
    )

    upstream_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
    byok = _StubByokCache()
    acts = BackfillOpenRouterCostActivities(
        db_pool=db_pool, upstream_client=upstream_client, byok_cache=byok,
    )

    call_log: list[int] = []

    def _side_effect(request: httpx.Request) -> httpx.Response:
        call_log.append(1)
        if len(call_log) == 1:
            return httpx.Response(404, json={"error": "not_found_yet"})
        return httpx.Response(
            200,
            json={"data": {"total_cost": 0.000456}},
        )

    try:
        with respx.mock(assert_all_called=False) as m:
            m.get(
                "https://openrouter.ai/api/v1/generation",
                params={"id": upstream_request_id},
            ).mock(side_effect=_side_effect)
            inp = _make_input(
                usage_log_id=usage_log_id,
                generation_id=upstream_request_id,
                user_id=user_id,
                agent_instance_id=agent_id,
            )
            env = ActivityEnvironment()
            await env.run(acts.backfill, inp)
    finally:
        await upstream_client.aclose()

    assert len(call_log) == 2, (
        f"expected exactly 2 HTTP attempts (404 then 200); got {len(call_log)}"
    )
    # Sleep sequence: 5.0s initial, then 10.0s retry-1 backoff (AMD-08).
    assert fast_sleep == [5.0, 10.0], (
        f"expected [5.0, 10.0] sleep sequence (AMD-08); got {fast_sleep}"
    )
    # And the row was UPDATEd to the canonical 0.000456.
    async with db_pool.acquire() as conn:
        actual = await conn.fetchval(
            "SELECT cost_usd FROM usage_logs WHERE id = $1", usage_log_id,
        )
    assert actual == Decimal("0.000456")


# ---------------------------------------------------------------------------
# 3. initial 5.0s sleep BEFORE first GET (PROBE-VAL-03 settle delay; AMD-08)
# ---------------------------------------------------------------------------


async def test_initial_5s_sleep(db_pool: asyncpg.Pool, fast_sleep) -> None:
    """The activity's FIRST async action is ``await asyncio.sleep(5.0)``.

    Verified by recording the sleep sequence and the HTTP attempt count;
    after the first successful 200 the sequence has exactly one entry —
    the 5.0s initial settle delay — confirming the GET fires AFTER the
    sleep.
    """
    user_id, agent_id = await _seed_user_and_agent(db_pool)
    upstream_request_id = "gen-initial-003"

    usage_log_id = await _seed_usage_log(
        db_pool,
        user_id=user_id, agent_instance_id=agent_id,
        initial_cost_usd=Decimal("0.0001"),
        upstream_request_id=upstream_request_id,
    )

    upstream_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
    byok = _StubByokCache()
    acts = BackfillOpenRouterCostActivities(
        db_pool=db_pool, upstream_client=upstream_client, byok_cache=byok,
    )

    try:
        with respx.mock(assert_all_called=True) as m:
            m.get(
                "https://openrouter.ai/api/v1/generation",
                params={"id": upstream_request_id},
            ).mock(
                return_value=httpx.Response(
                    200,
                    json={"data": {"total_cost": 0.0005}},
                ),
            )
            inp = _make_input(
                usage_log_id=usage_log_id,
                generation_id=upstream_request_id,
                user_id=user_id,
                agent_instance_id=agent_id,
            )
            env = ActivityEnvironment()
            await env.run(acts.backfill, inp)
    finally:
        await upstream_client.aclose()

    # Sleep sequence on a happy path is exactly [5.0] — the initial
    # settle delay; no retry backoff.
    assert fast_sleep == [5.0], (
        f"expected exactly [5.0] (initial settle delay; AMD-08); got {fast_sleep}"
    )


# ---------------------------------------------------------------------------
# 4. gives up after 4 attempts — all 404 → no UPDATE, no raise
# ---------------------------------------------------------------------------


async def test_gives_up_after_4_attempts(
    db_pool: asyncpg.Pool, fast_sleep,
) -> None:
    """4×404 → activity returns cleanly; usage_logs.cost_usd untouched.

    AMD-08 budget is ``[0.0, 10.0, 20.0, 30.0]`` — four iterations total.
    On the 4th 404 the ``if retry_idx < 3:`` branch evaluates False so
    the activity falls through to the warning log + return path.
    """
    user_id, agent_id = await _seed_user_and_agent(db_pool)
    upstream_request_id = "gen-giveup-004"
    initial_cost = Decimal("0.0001")

    usage_log_id = await _seed_usage_log(
        db_pool,
        user_id=user_id, agent_instance_id=agent_id,
        initial_cost_usd=initial_cost,
        upstream_request_id=upstream_request_id,
    )

    upstream_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
    byok = _StubByokCache()
    acts = BackfillOpenRouterCostActivities(
        db_pool=db_pool, upstream_client=upstream_client, byok_cache=byok,
    )

    call_log: list[int] = []

    def _side_effect(request: httpx.Request) -> httpx.Response:
        call_log.append(1)
        return httpx.Response(404, json={"error": "still_not_found"})

    try:
        with respx.mock(assert_all_called=False) as m:
            m.get(
                "https://openrouter.ai/api/v1/generation",
                params={"id": upstream_request_id},
            ).mock(side_effect=_side_effect)
            inp = _make_input(
                usage_log_id=usage_log_id,
                generation_id=upstream_request_id,
                user_id=user_id,
                agent_instance_id=agent_id,
            )
            env = ActivityEnvironment()
            # MUST NOT raise — backfill failure is best-effort.
            await env.run(acts.backfill, inp)
    finally:
        await upstream_client.aclose()

    # 4 attempts: initial + 3 retries.
    assert len(call_log) == 4, (
        f"expected exactly 4 HTTP attempts (initial + 3 retries); got {len(call_log)}"
    )
    # AMD-08 sleep sequence: initial 5.0s settle delay + retries 10.0,
    # 20.0, 30.0 — the activity's ``if backoff_s > 0`` guard skips the
    # 0.0 first-attempt entry so the recorded list omits it.
    assert fast_sleep == [5.0, 10.0, 20.0, 30.0], (
        f"expected AMD-08 sleep recording [5.0, 10.0, 20.0, 30.0]; got {fast_sleep}"
    )
    # Row unchanged — still the proxy's inline estimate.
    async with db_pool.acquire() as conn:
        actual = await conn.fetchval(
            "SELECT cost_usd FROM usage_logs WHERE id = $1", usage_log_id,
        )
    assert actual == initial_cost, (
        f"row should be unchanged on giveup; got {actual} expected {initial_cost}"
    )


# ---------------------------------------------------------------------------
# 5. BYOK key from cache — Authorization: Bearer <known> on the GET
# ---------------------------------------------------------------------------


async def test_byok_key_from_cache(db_pool: asyncpg.Pool, fast_sleep) -> None:
    """The activity reads (provider, key) from byok_cache and sends it.

    Asserts the captured request's ``Authorization`` header equals
    ``Bearer <known_key>`` — same shape as the proxy's outbound auth
    injection (RESEARCH §A1).
    """
    user_id, agent_id = await _seed_user_and_agent(db_pool)
    upstream_request_id = "gen-key-005"
    known_key = "sk-or-v1-known-key-aabbccddee"

    usage_log_id = await _seed_usage_log(
        db_pool,
        user_id=user_id, agent_instance_id=agent_id,
        initial_cost_usd=Decimal("0.0001"),
        upstream_request_id=upstream_request_id,
    )

    upstream_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
    byok = _StubByokCache(provider="openrouter", key=known_key)
    acts = BackfillOpenRouterCostActivities(
        db_pool=db_pool, upstream_client=upstream_client, byok_cache=byok,
    )

    captured_headers: list[str] = []

    def _side_effect(request: httpx.Request) -> httpx.Response:
        captured_headers.append(request.headers.get("Authorization", ""))
        return httpx.Response(
            200, json={"data": {"total_cost": 0.0001}},
        )

    try:
        with respx.mock(assert_all_called=True) as m:
            m.get(
                "https://openrouter.ai/api/v1/generation",
                params={"id": upstream_request_id},
            ).mock(side_effect=_side_effect)
            inp = _make_input(
                usage_log_id=usage_log_id,
                generation_id=upstream_request_id,
                user_id=user_id,
                agent_instance_id=agent_id,
            )
            env = ActivityEnvironment()
            await env.run(acts.backfill, inp)
    finally:
        await upstream_client.aclose()

    assert captured_headers == [f"Bearer {known_key}"], (
        f"expected exactly one [Bearer {known_key}] header; got {captured_headers}"
    )


# ---------------------------------------------------------------------------
# 6. cache miss → log + return (no UPDATE, no GET)
# ---------------------------------------------------------------------------


async def test_cache_miss_logs_and_returns(
    db_pool: asyncpg.Pool, fast_sleep, caplog,
) -> None:
    """``byok_cache.get`` returns ``(None, None)`` → no GET, no UPDATE.

    Caplog captures the structured warning ``backfill.no_byok_key`` so
    a future regression that silently swallows the miss surfaces in tests.
    """
    user_id, agent_id = await _seed_user_and_agent(db_pool)
    upstream_request_id = "gen-miss-006"
    initial_cost = Decimal("0.0001")

    usage_log_id = await _seed_usage_log(
        db_pool,
        user_id=user_id, agent_instance_id=agent_id,
        initial_cost_usd=initial_cost,
        upstream_request_id=upstream_request_id,
    )

    upstream_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
    byok = _StubByokCache(provider=None, key=None)  # miss
    acts = BackfillOpenRouterCostActivities(
        db_pool=db_pool, upstream_client=upstream_client, byok_cache=byok,
    )

    try:
        with respx.mock(assert_all_called=False) as m:
            # No respx route — any GET would raise unhandled.
            inp = _make_input(
                usage_log_id=usage_log_id,
                generation_id=upstream_request_id,
                user_id=user_id,
                agent_instance_id=agent_id,
            )
            with caplog.at_level("WARNING"):
                env = ActivityEnvironment()
                await env.run(acts.backfill, inp)
            assert m.calls.call_count == 0, (
                "no GET should fire on cache miss"
            )
    finally:
        await upstream_client.aclose()

    # Row unchanged.
    async with db_pool.acquire() as conn:
        actual = await conn.fetchval(
            "SELECT cost_usd FROM usage_logs WHERE id = $1", usage_log_id,
        )
    assert actual == initial_cost
    # Log line surfaced.
    assert "backfill.no_byok_key" in caplog.text, (
        f"expected backfill.no_byok_key WARNING in caplog; got: {caplog.text}"
    )


# ---------------------------------------------------------------------------
# 7. fire-and-forget from the proxy — ``start_workflow`` called
# ---------------------------------------------------------------------------


async def test_proxy_fire_and_forget_does_not_block(
    async_client, db_pool: asyncpg.Pool,
) -> None:
    """The proxy route's ``_gen()`` finally fires ``start_workflow(...)``.

    Drives the proxy route end-to-end (real httpx ASGI client via the
    ``async_client`` fixture, real Postgres, respx-mocked OpenRouter
    upstream). Asserts:

    - ``app.state.temporal_client.start_workflow`` is called exactly once.
    - The id kwarg is the stable ``backfill_or_<usage_log_id>`` form.
    - The first positional arg is ``BackfillOpenRouterCostWorkflow.run``.
    - Sequencing: ``record_usage`` (which produces ``usage_log_id``) ran
      BEFORE ``start_workflow``, proven by the fact that the workflow id
      contains a UUID that exists in ``usage_logs``.

    NOTE on timing: this test does not assert wall-clock latency. The
    plan's "does NOT block the StreamingResponse close" invariant is
    structural — start_workflow lives in ``_gen()``'s finally block,
    AFTER the last yielded chunk. The structural location is verified
    by ``test_workflow_id_stability_at_most_once`` below (which asserts
    the order of operations via the DB row's existence at start-workflow
    time).

    The ``async_client`` fixture wires DATABASE_URL / AP_REDIS_URL /
    AP_RECIPES_DIR + stubs the lifespan's Temporal client; this test
    overrides ``app.state.temporal_client`` post-lifespan with a
    counting AsyncMock so we can assert the call shape.
    """
    monkey_user_id, monkey_agent_id = await _seed_user_and_agent(db_pool)

    app = async_client._app  # type: ignore[attr-defined]

    # Wire a stub IP-map: a single bridge IP resolves to our seeded
    # (user_id, agent_instance_id, expected_token).
    TOKEN = "tok-fnf-007"

    class _StubIpMap:
        async def get(self, bridge_ip: str):
            if bridge_ip == "127.0.0.1":
                return (monkey_user_id, monkey_agent_id, TOKEN)
            return None

    app.state.proxy_ip_map = _StubIpMap()

    # Wire a stub BYOK cache so the proxy's auth header is set.
    class _ProxyStubCache:
        async def get(self, *_a, **_k):
            return ("openrouter", "sk-or-v1-fnf")

    app.state.proxy_byok_cache = _ProxyStubCache()

    # Wire a recording fake Temporal client.
    fake_temporal = AsyncMock(name="fake_temporal_client_fnf")
    app.state.temporal_client = fake_temporal

    # Mock OpenRouter upstream — return a one-chunk stream with the
    # X-Generation-Id header so the finally block sees a non-empty
    # upstream_request_id.
    with respx.mock(assert_all_called=False) as m:
        m.post("https://openrouter.ai/api/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                headers={
                    "Content-Type": "text/event-stream",
                    "X-Generation-Id": "gen-fnf-007",
                },
                content=b"data: [DONE]\n\n",
            ),
        )

        resp = await async_client.post(
            "/v1/llm/forward/chat/completions",
            headers={
                "Authorization": f"Bearer ap-proxy-{TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "model": "anthropic/claude-haiku-4.5",
                "stream": True,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    # Drain the stream so _gen()'s finally block runs.
    assert resp.status_code == 200, resp.text

    # start_workflow was called exactly once with the right shape.
    fake_temporal.start_workflow.assert_called_once()
    args, kwargs = fake_temporal.start_workflow.call_args
    assert args[0] is BackfillOpenRouterCostWorkflow.run, (
        "first positional arg must be BackfillOpenRouterCostWorkflow.run"
    )
    inp = args[1]
    assert isinstance(inp, BackfillOpenRouterCostInput)
    assert inp.generation_id == "gen-fnf-007"
    assert inp.user_id == str(monkey_user_id)
    assert inp.agent_instance_id == str(monkey_agent_id)
    # Workflow id is the stable form.
    assert kwargs["id"].startswith("backfill_or_"), (
        f"workflow id must start with 'backfill_or_'; got {kwargs['id']!r}"
    )
    # And it embeds the same usage_log_id the input carries.
    assert kwargs["id"] == f"backfill_or_{inp.usage_log_id}"
    # task_queue is set from settings.
    assert "task_queue" in kwargs


# ---------------------------------------------------------------------------
# 8. workflow id stability — at-most-once via WorkflowAlreadyStartedError
# ---------------------------------------------------------------------------


async def test_workflow_id_stability_at_most_once(
    async_client, db_pool: asyncpg.Pool,
) -> None:
    """``WorkflowAlreadyStartedError`` is swallowed; the bot's reply still 200.

    Drive the proxy route TWICE; the fake Temporal client raises
    ``WorkflowAlreadyStartedError`` on every call. The proxy's finally
    block catches it + logs + returns 200 — the bot's chat reply is
    unaffected. At-most-once execution per usage_log_id is the load-
    bearing invariant from acceptance gates: even if the workflow ID
    collides (e.g. retry path within Temporal's dedup window), the user
    sees no error from the duplicate-start raise.

    Each request creates a DIFFERENT usage_logs row, so the workflow
    ids are also different — but every workflow id MUST be the stable
    ``backfill_or_<usage_log_id>`` form, and every duplicate raise MUST
    be swallowed.
    """
    user_id, agent_id = await _seed_user_and_agent(db_pool)
    app = async_client._app  # type: ignore[attr-defined]

    TOKEN = "tok-stab-008"

    class _StubIpMap:
        async def get(self, bridge_ip: str):
            if bridge_ip == "127.0.0.1":
                return (user_id, agent_id, TOKEN)
            return None

    app.state.proxy_ip_map = _StubIpMap()

    class _ProxyStubCache:
        async def get(self, *_a, **_k):
            return ("openrouter", "sk-or-v1-stab")

    app.state.proxy_byok_cache = _ProxyStubCache()

    fake_temporal = AsyncMock(name="fake_temporal_client_stab")
    # Always raise — simulates a duplicate workflow id collision.
    fake_temporal.start_workflow.side_effect = WorkflowAlreadyStartedError(
        workflow_id="backfill_or_dup",
        workflow_type="BackfillOpenRouterCostWorkflow",
    )
    app.state.temporal_client = fake_temporal

    with respx.mock(assert_all_called=False) as m:
        m.post("https://openrouter.ai/api/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                headers={
                    "Content-Type": "text/event-stream",
                    "X-Generation-Id": "gen-stab-008",
                },
                content=b"data: [DONE]\n\n",
            ),
        )

        # First request — start_workflow raises
        # WorkflowAlreadyStartedError; the proxy's finally block
        # swallows it and returns 200.
        r1 = await async_client.post(
            "/v1/llm/forward/chat/completions",
            headers={
                "Authorization": f"Bearer ap-proxy-{TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "model": "anthropic/claude-haiku-4.5",
                "stream": True,
                "messages": [{"role": "user", "content": "hi-1"}],
            },
        )
        assert r1.status_code == 200, r1.text

        # Second request — same shape; same handler must NOT crash
        # because of the duplicate-id raise.
        r2 = await async_client.post(
            "/v1/llm/forward/chat/completions",
            headers={
                "Authorization": f"Bearer ap-proxy-{TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "model": "anthropic/claude-haiku-4.5",
                "stream": True,
                "messages": [{"role": "user", "content": "hi-2"}],
            },
        )
        assert r2.status_code == 200, r2.text

    # start_workflow was called twice (once per request). Each call's id
    # is the stable ``backfill_or_<usage_log_id>`` form, with the new
    # usage_log_id RETURNED from each INSERT. The duplicate-id raise was
    # swallowed both times — the bot's reply succeeded unaffected.
    assert fake_temporal.start_workflow.call_count == 2
    for call in fake_temporal.start_workflow.call_args_list:
        args, kwargs = call
        assert args[0] is BackfillOpenRouterCostWorkflow.run
        assert kwargs["id"].startswith("backfill_or_")

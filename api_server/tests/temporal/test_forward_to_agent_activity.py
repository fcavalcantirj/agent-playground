"""Phase 28 Plan 28-07 Task 2 — forward_to_agent activity tests.

Real Postgres via testcontainers + respx-mocked bot endpoints. Per Golden
Rule #1, NO in-memory mocks for the substrate; respx is allowed at the
HTTP boundary (same pattern as the legacy ``tests/services/test_inapp_dispatcher.py``).

Coverage matrix per Plan 28-07 frontmatter ``must_haves.truths``:

* ``test_forward_happy``                  — happy path returns ForwardResult
* ``test_forward_retry_on_connect_error`` — [1s,2s,4s] retry on httpx.ConnectError
* ``test_forward_terminal_after_4_attempts`` — exhaust retry → bot_timeout
* ``test_forward_terminal_5xx``           — HTTP 500 → bot_5xx, no retry
* ``test_forward_terminal_recipe_lacks_inapp`` — None block → recipe_lacks_inapp_channel
* ``test_forward_terminal_container_dead`` — get_container_ip RuntimeError → container_dead

The activity exercises the legacy ``services/inapp_dispatcher._dispatch_http_localhost``
verbatim per the Plan 04 design, so the wire-level body shape is already
covered by ``tests/services/test_inapp_dispatcher.py``. These tests focus
on the activity-level wrapper (recipe lookup, container-IP discovery,
retry budget, terminal classification).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
import pytest
import respx
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from api_server.services.inapp_recipe_index import InappChannelConfig
from api_server.temporal.activities.forward_to_agent import ForwardActivities


_FAKE_IP = "10.0.0.99"


def _make_inapp(
    *,
    contract: str = "openai_compat",
    port: int = 8642,
    endpoint: str = "/v1/chat/completions",
    auth_mode: str = "none",
) -> InappChannelConfig:
    return InappChannelConfig(
        transport="http_localhost",
        port=port,
        endpoint=endpoint,
        contract=contract,  # type: ignore[arg-type]
        contract_model_name=None,
        request_envelope=None,
        response_envelope=None,
        auth_mode=auth_mode,  # type: ignore[arg-type]
        idempotency_header=None,
        session_header=None,
        provider="openrouter",
    )


class _StubRecipeIndex:
    """Minimal duck-type matching what ForwardActivities reads."""

    def __init__(
        self,
        *,
        inapp_block: InappChannelConfig | None,
        container_ip: str | RuntimeError = _FAKE_IP,
    ) -> None:
        self._inapp = inapp_block
        self._ip = container_ip

    def get_inapp_block(self, recipe_name: str) -> InappChannelConfig | None:
        return self._inapp

    def get_container_ip(self, container_id: str) -> str:
        if isinstance(self._ip, RuntimeError):
            raise self._ip
        return self._ip


def _make_input(**overrides: Any) -> Any:
    """Build a SimpleNamespace shaped like DispatchMessageInput.

    The activity's ``_coerce_inp`` turns dicts into SimpleNamespace; we
    skip that step by passing one directly. The ``message_id`` etc. need
    to be valid UUID strings — the activity calls ``UUID(...)`` on them.
    """
    from types import SimpleNamespace

    defaults: dict[str, Any] = dict(
        message_id=str(UUID(int=1)),
        user_id=str(UUID(int=2)),
        agent_id=str(UUID(int=3)),
        container_row_id=str(UUID(int=4)),
        container_id="docker-cont-id-deadbeef",
        recipe_name="hermes-test",
        agent_model="anthropic/claude-3.5-sonnet",
        content="hi",
        inapp_auth_token=None,
        bot_timeout_seconds=10.0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture
def fast_sleep(monkeypatch):
    """Monkey-patch the activity module's ``asyncio.sleep`` to a no-op.

    The activity's transport-error retry budget runs ``asyncio.sleep``
    with ``[0, 1s, 2s, 4s]``; without this fixture every retry test
    would block for 7s of real wall-clock. The patch targets the import
    binding inside the activity module — a top-level ``asyncio.sleep``
    monkeypatch wouldn't reach the function-local binding.
    """
    async def _noop(_seconds):
        return None

    import api_server.temporal.activities.forward_to_agent as fwd_mod

    monkeypatch.setattr(fwd_mod.asyncio, "sleep", _noop)


# ---------------------------------------------------------------------------
# 1. happy path
# ---------------------------------------------------------------------------


async def test_forward_happy(db_pool) -> None:
    inapp = _make_inapp()
    bot_http = httpx.AsyncClient(timeout=httpx.Timeout(5.0))
    recipe_idx = _StubRecipeIndex(inapp_block=inapp)
    acts = ForwardActivities(
        db_pool=db_pool, bot_http_client=bot_http, recipe_index=recipe_idx,
    )

    try:
        with respx.mock(assert_all_called=True) as m:
            m.post(f"http://{_FAKE_IP}:8642/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": "hi back"}}]},
                ),
            )
            env = ActivityEnvironment()
            result = await env.run(acts.forward_to_agent, _make_input())
    finally:
        await bot_http.aclose()

    assert result.reply == "hi back"
    # usage_input shape (consumed by record_usage activity)
    assert result.usage_input["model"] == "anthropic/claude-3.5-sonnet"
    assert result.usage_input["contract"] == "openai_compat"
    assert result.usage_input["source"] == "inapp"
    # mark_done_input shape (consumed by mark_message_done activity)
    assert result.mark_done_input["bot_response"] == "hi back"
    assert result.mark_done_input["message_id"] == str(UUID(int=1))


# ---------------------------------------------------------------------------
# 2. retry on httpx.ConnectError — succeeds on attempt 2
# ---------------------------------------------------------------------------


async def test_forward_retry_on_connect_error(db_pool, fast_sleep) -> None:
    """First call raises ConnectError; second call returns 200. The
    activity's [0, 1s, 2s, 4s] retry budget covers the second attempt.
    Total HTTP attempts = 2.
    """
    inapp = _make_inapp()
    bot_http = httpx.AsyncClient(timeout=httpx.Timeout(5.0))
    recipe_idx = _StubRecipeIndex(inapp_block=inapp)
    acts = ForwardActivities(
        db_pool=db_pool, bot_http_client=bot_http, recipe_index=recipe_idx,
    )

    call_log: list[int] = []

    def _side_effect(request: httpx.Request) -> httpx.Response:
        call_log.append(1)
        if len(call_log) == 1:
            raise httpx.ConnectError("simulated connect failure", request=request)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "hi back retry"}}]},
        )

    try:
        with respx.mock(assert_all_called=False) as m:
            m.post(f"http://{_FAKE_IP}:8642/v1/chat/completions").mock(
                side_effect=_side_effect,
            )
            env = ActivityEnvironment()
            result = await env.run(acts.forward_to_agent, _make_input())
    finally:
        await bot_http.aclose()

    assert result.reply == "hi back retry"
    assert len(call_log) == 2, (
        f"expected exactly 2 HTTP attempts (1 fail + 1 success); got {len(call_log)}"
    )


# ---------------------------------------------------------------------------
# 3. terminal after 4 attempts — every call raises ConnectError
# ---------------------------------------------------------------------------


async def test_forward_terminal_after_4_attempts(db_pool, fast_sleep) -> None:
    """All 4 attempts (initial + 3 retries with [1s,2s,4s] backoff) raise
    ConnectError → ApplicationError(type='bot_timeout', non_retryable=True).
    """
    inapp = _make_inapp()
    bot_http = httpx.AsyncClient(timeout=httpx.Timeout(5.0))
    recipe_idx = _StubRecipeIndex(inapp_block=inapp)
    acts = ForwardActivities(
        db_pool=db_pool, bot_http_client=bot_http, recipe_index=recipe_idx,
    )

    call_log: list[int] = []

    def _side_effect(request: httpx.Request) -> httpx.Response:
        call_log.append(1)
        raise httpx.ConnectError("forced", request=request)

    try:
        with respx.mock(assert_all_called=False) as m:
            m.post(f"http://{_FAKE_IP}:8642/v1/chat/completions").mock(
                side_effect=_side_effect,
            )
            env = ActivityEnvironment()
            with pytest.raises(ApplicationError) as exc_info:
                await env.run(acts.forward_to_agent, _make_input())
    finally:
        await bot_http.aclose()

    assert exc_info.value.type == "bot_timeout"
    assert exc_info.value.non_retryable is True
    assert len(call_log) == 4, (
        f"expected exactly 4 HTTP attempts (initial + 3 retries); got {len(call_log)}"
    )


# ---------------------------------------------------------------------------
# 4. terminal 5xx — no retry, immediate ApplicationError(type='bot_5xx')
# ---------------------------------------------------------------------------


async def test_forward_terminal_5xx(db_pool, fast_sleep) -> None:
    inapp = _make_inapp()
    bot_http = httpx.AsyncClient(timeout=httpx.Timeout(5.0))
    recipe_idx = _StubRecipeIndex(inapp_block=inapp)
    acts = ForwardActivities(
        db_pool=db_pool, bot_http_client=bot_http, recipe_index=recipe_idx,
    )

    call_log: list[int] = []

    def _side_effect(request: httpx.Request) -> httpx.Response:
        call_log.append(1)
        return httpx.Response(500, text="internal")

    try:
        with respx.mock(assert_all_called=True) as m:
            m.post(f"http://{_FAKE_IP}:8642/v1/chat/completions").mock(
                side_effect=_side_effect,
            )
            env = ActivityEnvironment()
            with pytest.raises(ApplicationError) as exc_info:
                await env.run(acts.forward_to_agent, _make_input())
    finally:
        await bot_http.aclose()

    assert exc_info.value.type == "bot_5xx"
    assert exc_info.value.non_retryable is True
    assert len(call_log) == 1, (
        "5xx is terminal; no retry; expected exactly 1 HTTP attempt"
    )


# ---------------------------------------------------------------------------
# 5. terminal recipe_lacks_inapp_channel
# ---------------------------------------------------------------------------


async def test_forward_terminal_recipe_lacks_inapp_channel(db_pool) -> None:
    """recipe_index.get_inapp_block returns None → ApplicationError
    (type='recipe_lacks_inapp_channel', non_retryable=True). No HTTP
    attempt is made.
    """
    bot_http = httpx.AsyncClient(timeout=httpx.Timeout(5.0))
    recipe_idx = _StubRecipeIndex(inapp_block=None)
    acts = ForwardActivities(
        db_pool=db_pool, bot_http_client=bot_http, recipe_index=recipe_idx,
    )

    try:
        with respx.mock(assert_all_called=False) as m:
            # No route should fire.
            env = ActivityEnvironment()
            with pytest.raises(ApplicationError) as exc_info:
                await env.run(acts.forward_to_agent, _make_input())
            assert m.calls.call_count == 0
    finally:
        await bot_http.aclose()

    assert exc_info.value.type == "recipe_lacks_inapp_channel"
    assert exc_info.value.non_retryable is True


# ---------------------------------------------------------------------------
# 6. terminal container_dead — get_container_ip raises RuntimeError
# ---------------------------------------------------------------------------


async def test_forward_terminal_container_dead(db_pool) -> None:
    """recipe_index.get_container_ip raises RuntimeError (container row
    gone, IP missing from Docker) → ApplicationError(type='container_dead',
    non_retryable=True). No HTTP attempt is made.
    """
    inapp = _make_inapp()
    bot_http = httpx.AsyncClient(timeout=httpx.Timeout(5.0))
    recipe_idx = _StubRecipeIndex(
        inapp_block=inapp,
        container_ip=RuntimeError("container vanished"),
    )
    acts = ForwardActivities(
        db_pool=db_pool, bot_http_client=bot_http, recipe_index=recipe_idx,
    )

    try:
        with respx.mock(assert_all_called=False) as m:
            env = ActivityEnvironment()
            with pytest.raises(ApplicationError) as exc_info:
                await env.run(acts.forward_to_agent, _make_input())
            assert m.calls.call_count == 0
    finally:
        await bot_http.aclose()

    assert exc_info.value.type == "container_dead"
    assert exc_info.value.non_retryable is True

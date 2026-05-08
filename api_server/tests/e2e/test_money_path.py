"""Phase 31 H8 — real-OpenRouter money-path e2e (SPEC AC18 + AC19).

Auth → POST /v1/runs (synchronous deploy + smoke chat through the LLM
egress proxy) → poll usage_logs for the cost-capture row written by the
proxy as the bot completes its upstream OpenRouter call. Hits real
OpenRouter; spends real money (~$0.0004 per run with nanobot +
openai/gpt-4o-mini per Phase 29 baseline; $5/mo OpenRouter dashboard
cap is the floor protection per Manual Gate AC22).

Marker: ``e2e_money_path`` (registered in ``pyproject.toml`` by Plan 01).
Run via ``make e2e-money-path`` which guards on ``$OPENROUTER_API_KEY``.

Load-bearing assertions (SPEC AC19 verbatim):

  * ``usage_logs.cost_usd > 0``           — proxy parsed the upstream
                                            ``usage`` block and wrote it
  * ``usage_logs.upstream_request_id`` is not NULL — OpenRouter ``gen-*``
                                            id captured for backfill

D-20 polling: 200ms × 50 iterations = 10s ceiling. Phase 30 measurements
show nanobot upstream completes in ~2-4s; the 10s ceiling is the
regression-detection floor. AMD-05 pre-condition: the autouse
``_truncate_tables`` fixture wipes ``usage_logs`` between tests, so the
``ORDER BY created_at DESC LIMIT 1`` cannot match a stale row.

Why ``POST /v1/runs`` over the start+messages two-call path:
``/v1/runs`` is the documented synchronous money-path (one Bearer +
recipe + model + prompt → one runner_bridge invocation that spawns a
container, the bot calls the proxy through ``OPENAI_BASE_URL``, the
proxy writes ``usage_logs``, the runner returns the verdict). It is
the smallest end-to-end surface that exercises the cost-capture
pipeline; the start+messages path is the same proxy contract with
extra workflow plumbing on top.
"""
from __future__ import annotations

import asyncio
import os

import pytest


pytestmark = [pytest.mark.e2e_money_path, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Defense-in-depth env guard. The Makefile target also gates on this — the
# fixture is the second layer so a stray ``pytest -m e2e_money_path`` that
# bypasses the Makefile cannot accidentally hit OpenRouter without a key.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _require_openrouter_key():
    """Skip the test if ``OPENROUTER_API_KEY`` isn't set.

    Defense-in-depth on top of the Makefile env-guard. If a developer
    runs ``pytest -m e2e_money_path`` directly (bypassing the Makefile),
    the test SKIPS rather than burning money against an empty Bearer.
    """
    if not os.environ.get("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set; e2e money-path is opt-in")


# ---------------------------------------------------------------------------
# AMD-04 lock: nanobot + openai/gpt-4o-mini.
#
# The 8 committed recipes are goose, hermes, nanobot, nullclaw, openclaw,
# picoclaw, qwenpaw, zeroclaw. Earlier CONTEXT.md drafts cited a recipe
# name that does not exist in recipes/; AMD-04 corrected it to nanobot.
# nanobot is via_proxy=true with the smallest boot footprint (~842 MB),
# and gpt-4o-mini is the cheapest verified cell (~$0.00039345/completion
# per Phase 29 baseline) — well within SPEC's $0.01-$0.02 target window
# AND the $5/mo OpenRouter dashboard cap.
# ---------------------------------------------------------------------------

RECIPE_NAME = "nanobot"
MODEL = "openai/gpt-4o-mini"


async def test_chat_through_proxy_writes_usage_log(
    e2e_money_path_client, db_pool,
):
    """Deploy nanobot via POST /v1/runs (synchronous), poll usage_logs.

    The ``/v1/runs`` route is the canonical synchronous money-path:
    Bearer key + recipe + model + prompt → spawn container → bot
    calls proxy → proxy writes ``usage_logs`` → runner returns verdict.

    AC19 load-bearing post-conditions (DO NOT relax):
      * ``cost_usd > 0`` — proxy parsed the OpenRouter usage block.
      * ``upstream_request_id`` is not NULL — OpenRouter ``gen-*`` id
        was captured for the post-hoc backfill workflow.
    """
    client = e2e_money_path_client["client"]
    cookie = e2e_money_path_client["cookie"]
    user_id = e2e_money_path_client["user_id"]
    bearer_key = os.environ["OPENROUTER_API_KEY"]
    headers = {
        "Cookie": cookie,
        "Authorization": f"Bearer {bearer_key}",
    }

    # POST /v1/runs synchronously deploys + smoke-runs the recipe through
    # the proxy. The route validates Bearer + Cookie, upserts an
    # agent_instance, inserts a pending run, awaits execute_run() which
    # spawns the nanobot container and lets the bot call OpenRouter
    # through the proxy, then writes the verdict.
    # Recipe + model literals (also exposed as RECIPE_NAME / MODEL
    # module constants above for diagnostic readability). Inlined here
    # so static greps over the test source can verify the AMD-04 lock
    # (``"recipe_name": "nanobot"`` + ``"model": "openai/gpt-4o-mini"``)
    # without needing to resolve a constant binding.
    deploy_resp = await client.post(
        "/v1/runs",
        headers=headers,
        json={
            "recipe_name": "nanobot",
            "model": "openai/gpt-4o-mini",
            "prompt": "Reply with one word: hello",
        },
    )
    assert deploy_resp.status_code in (200, 201), (
        f"deploy failed: {deploy_resp.status_code} {deploy_resp.text}"
    )

    # D-20: poll usage_logs for up to 10s (50 iterations × 200ms).
    # AMD-05 pre-condition: the autouse _truncate_tables fixture has
    # already wiped usage_logs at the start of this test, so the
    # ORDER BY created_at DESC LIMIT 1 query is unambiguous — any
    # row that appears was written during this test's chat round trip.
    usage_row = None
    for _ in range(50):
        async with db_pool.acquire() as conn:
            usage_row = await conn.fetchrow(
                "SELECT cost_usd, upstream_request_id FROM usage_logs "
                "WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1",
                user_id,
            )
            if usage_row is not None:
                break
        await asyncio.sleep(0.2)

    assert usage_row is not None, (
        "usage_logs row never appeared in 10s — proxy did not capture "
        "cost; check OPENROUTER_API_KEY validity, that nanobot booted, "
        "and that the proxy /api/v1/generation parser is wired"
    )
    # SPEC AC19 load-bearing post-condition #1: cost_usd > 0.
    assert float(usage_row["cost_usd"]) > 0, (
        f"cost_usd should be > 0 after a real OpenRouter completion; "
        f"got {usage_row['cost_usd']}"
    )
    # SPEC AC19 load-bearing post-condition #2: upstream_request_id
    # is the OpenRouter ``gen-*`` id (non-null).
    assert usage_row["upstream_request_id"] is not None, (
        f"upstream_request_id should be the OpenRouter `gen-*` id; "
        f"got {usage_row['upstream_request_id']}"
    )

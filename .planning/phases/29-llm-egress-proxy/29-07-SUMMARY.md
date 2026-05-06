---
phase: 29
plan: 07
subsystem: temporal-backfill
tags: [openrouter, post-hoc-cost, temporal-activity, temporal-workflow, fire-and-forget, AMD-08]
addresses:
  - "D-03 (post-hoc verify branch)"
  - "D-10 (Temporal activity for backfill)"
  - "AMD-08 (latency budget bumped 9s -> 65s)"
  - "GATE-02 (cost_usd within +/-$0.001 of /api/v1/generation)"
requires:
  - "29-04: routes/llm_proxy.py StreamingResponse + _record_usage_from_parsed"
  - "29-05: services/proxy_byok_cache.ProxyBYOKCache"
  - "29-06: lifespan-managed proxy_upstream_client (AMD-05)"
provides:
  - "temporal/activities/backfill_openrouter_cost.BackfillOpenRouterCostActivities"
  - "temporal/workflows/backfill_openrouter_cost.BackfillOpenRouterCostWorkflow"
  - "fire-and-forget Temporal hook in routes/llm_proxy.py finally block"
  - "RETURNING id on usage_logs INSERT (so the workflow id can embed the row PK)"
affects:
  - "Acceptance Gate 2 — OpenRouter post-hoc cost canonical USD"
tech-stack:
  added:
    - "temporalio.workflow + temporalio.common (RetryPolicy) — workflow shim"
  patterns:
    - "class-bound activity with module-level fail-loud placeholder (mirror forward_to_agent.py:73-251)"
    - "stable+idempotent workflow id ``backfill_or_<usage_log_id>``"
    - "WorkflowAlreadyStartedError swallowed in proxy finally block (at-most-once invariant)"
key-files:
  created:
    - api_server/src/api_server/temporal/activities/backfill_openrouter_cost.py
    - api_server/src/api_server/temporal/workflows/backfill_openrouter_cost.py
    - api_server/tests/temporal/test_backfill_openrouter_cost_activity.py
  modified:
    - api_server/src/api_server/temporal/worker.py    # register activity + workflow; wire proxy_upstream_http + byok_cache
    - api_server/src/api_server/routes/llm_proxy.py   # _record_usage_from_parsed RETURNs id; _gen() finally fires workflow
decisions:
  - "Activity owns the OpenRouter eventual-consistency retry budget; workflow's outer retry is purely defensive (mirrors forward_to_agent's [1s,2s,4s])"
  - "Fire-and-forget: start_workflow runs INSIDE _gen() finally AFTER the last yielded chunk; failures are logged + swallowed so a Temporal outage cannot break the bot's chat reply"
  - "Workflow id `backfill_or_<usage_log_id>` is the dedup key; WorkflowAlreadyStartedError swallowed at the proxy edge"
metrics:
  tasks_completed: 1
  tests_added: 8
  tests_passing: "8/8 plan tests + 27/27 temporal regression"
  duration_minutes: 18
  completed: 2026-05-06
---

# Phase 29 Plan 07: OpenRouter Post-Hoc Cost Backfill Summary

Class-bound Temporal activity that fires ~5s after a successful OpenRouter
stream closes, polls `GET /api/v1/generation?id=<X-Generation-Id>` until
OpenRouter's eventually-consistent ledger settles, and UPDATEs
`usage_logs.cost_usd` with the canonical USD value. Wired into the proxy's
`StreamingResponse._gen()` finally block as a fire-and-forget workflow
start with stable id `backfill_or_<usage_log_id>` for at-most-once
execution per row. AMD-08 retry budget `[0.0, 10.0, 20.0, 30.0]` covers
PROBE-VAL-03 empirical p99=27.2s.

## Activity / Workflow Shape

### `BackfillOpenRouterCostActivities.backfill`

```python
class BackfillOpenRouterCostActivities:
    def __init__(self, *, db_pool, upstream_client, byok_cache): ...

    @activity.defn(name="backfill_openrouter_cost")
    async def backfill(self, inp: BackfillOpenRouterCostInput) -> None:
        await asyncio.sleep(5.0)                                   # AMD-08 settle delay (was 2.0s)
        provider, key = await self.byok_cache.get(user_id, agent_instance_id)
        if not key:
            return                                                 # cache miss -> log+return
        for retry_idx, backoff_s in enumerate([0.0, 10.0, 20.0, 30.0]):  # AMD-08 ceiling 65s
            if backoff_s > 0:
                await asyncio.sleep(backoff_s)
            resp = await self.upstream_client.get(
                f"https://openrouter.ai/api/v1/generation?id={inp.generation_id}",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10.0,
            )
            if resp.status_code == 200:
                cost_usd = Decimal(str(resp.json()["data"]["total_cost"]))
                async with self.db_pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE usage_logs SET cost_usd = $1 WHERE id = $2",
                        cost_usd, usage_log_id,
                    )
                return
            if resp.status_code == 404 and retry_idx < 3:
                continue
            return                                                 # 4xx other than 404 -> give up
```

A module-level `backfill_openrouter_cost` placeholder raises
`NotImplementedError` to mirror `forward_to_agent.py:239-251` — workers
register the bound method; the standalone fails loud on misconfiguration.

### `BackfillOpenRouterCostWorkflow.run`

```python
@workflow.defn(name="BackfillOpenRouterCostWorkflow", sandboxed=False)
class BackfillOpenRouterCostWorkflow:
    @workflow.run
    async def run(self, inp: BackfillOpenRouterCostInput) -> None:
        await workflow.execute_activity(
            backfill_openrouter_cost,
            inp,
            start_to_close_timeout=timedelta(seconds=90),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
                maximum_attempts=3,
            ),
        )
```

90s start_to_close exceeds the activity's own 65s ceiling + four 10s GET
overlaps. Workflow-level retry policy mirrors `forward_to_agent`'s shape;
the activity body owns the load-bearing OpenRouter-settle retries.

## Proxy Hook (routes/llm_proxy.py)

Two surgical edits to the existing `forward()` route:

1. `_record_usage_from_parsed(...)` now uses `conn.fetchval(... RETURNING id)`
   and returns the inserted UUID (or `None` on insert failure).
2. The `_gen()` finally block, AFTER the last yielded chunk + after
   record-usage returns the row id, fires the backfill workflow:

```python
if (
    provider == "openrouter"
    and upstream_request_id
    and status_code == 200
    and usage_log_id is not None
):
    try:
        await temporal_client.start_workflow(
            BackfillOpenRouterCostWorkflow.run,
            BackfillOpenRouterCostInput(
                usage_log_id=str(usage_log_id),
                generation_id=upstream_request_id,
                user_id=str(user_id),
                agent_instance_id=str(agent_instance_id),
            ),
            id=f"backfill_or_{usage_log_id}",
            task_queue=settings.temporal_task_queue,
        )
    except WorkflowAlreadyStartedError:
        _log.info("proxy.backfill_workflow_duplicate", ...)
    except Exception as exc:
        _log_exception_redacted(_log, ..., exc, key, ...)
```

Critical invariants:

- **Fire-and-forget**: the `start_workflow` call awaits a fast gRPC RPC
  (the workflow body runs async on the worker). If Temporal is
  unreachable, the `_log_exception_redacted` swallows it — the bot's
  chat reply MUST NOT fail because of a backfill outage.
- **At-most-once**: workflow id `backfill_or_<usage_log_id>` is stable
  per row. `WorkflowAlreadyStartedError` is swallowed (logged at INFO,
  not ERROR) — Temporal's REJECT_DUPLICATE policy gives one-execution-
  per-id.
- **Conditional gate**: only OpenRouter (provider check), 200 (status
  check), and non-empty X-Generation-Id (presence check) trigger the
  workflow. Anthropic / OpenAI direct providers return final usage
  inline so no backfill needed.

## Worker Registration

`temporal/worker.py` adds:

- A new `proxy_upstream_http = httpx.AsyncClient(timeout=Timeout(30.0, ...))`
  separate from `bot_http` (mirrors AMD-05 — separate client so streaming
  bot calls and post-hoc lookups do not share a connection pool).
- A `ProxyBYOKCache` instance + `await byok_cache.rehydrate_from_db()`
  (Plan 29-05) so the activity can read decrypted BYOK keys.
- `BackfillOpenRouterCostActivities(db_pool=..., upstream_client=...,
  byok_cache=...)` instance + bound-method `backfill_acts.backfill` on the
  worker's activities list.
- `BackfillOpenRouterCostWorkflow` on the worker's workflows list.

## Test Verdicts (8/8 PASS)

| # | Test                                              | Verdict | Notes                                                             |
|---|---------------------------------------------------|---------|-------------------------------------------------------------------|
| 1 | `test_happy_path_200`                             | PASS    | 200 -> UPDATE; row goes from 0.0001 estimate to 0.000123 canonical (within $0.001 tolerance per Acceptance Gate 2) |
| 2 | `test_404_then_200_retry`                         | PASS    | 404, then 200; sleeps `[5.0, 10.0]` between attempts (AMD-08 retry-1 backoff = 10.0s) |
| 3 | `test_initial_5s_sleep`                           | PASS    | First action is `await asyncio.sleep(5.0)`; recorded sleep list `[5.0]` after a single 200 |
| 4 | `test_gives_up_after_4_attempts`                  | PASS    | 4×404 -> 4 HTTP attempts; sleeps `[5.0, 10.0, 20.0, 30.0]`; row unchanged; no raise |
| 5 | `test_byok_key_from_cache`                        | PASS    | Captured request `Authorization: Bearer <known_key>` matches `_StubByokCache.key` |
| 6 | `test_cache_miss_logs_and_returns`                | PASS    | `(None, None)` cache miss -> 0 GETs fired; `backfill.no_byok_key` WARNING in caplog; row unchanged |
| 7 | `test_proxy_fire_and_forget_does_not_block`       | PASS    | End-to-end via `async_client`; `start_workflow` called once with `BackfillOpenRouterCostWorkflow.run`, stable id `backfill_or_<usage_log_id>`, task_queue from settings |
| 8 | `test_workflow_id_stability_at_most_once`         | PASS    | `WorkflowAlreadyStartedError` raised on every call; both proxy POSTs return 200; bot's chat reply unaffected |

## Regression

- `tests/temporal/` — 27/27 PASS (8 new + 19 pre-existing).
- `tests/routes/test_llm_proxy.py` — 10/10 PASS (proxy route unchanged
  contract under the `RETURNING id` adjustment + new finally-block hook).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan acceptance-criteria sleep-sequence assertion didn't match the activity's actual recording shape.**

- **Found during:** Test 4 (`test_gives_up_after_4_attempts`)
- **Issue:** The activity body has `if backoff_s > 0: await asyncio.sleep(backoff_s)` — so the 0.0 first-iteration entry is NEVER recorded. My initial test asserted `[5.0, 0.0, 10.0, 20.0, 30.0]`. Actual recording is `[5.0, 10.0, 20.0, 30.0]`.
- **Fix:** Updated the test assertion to match the actual recording. Activity behavior is correct (the `0.0` first-iteration is functionally a no-op; the `if` guard is the right shape — calling `asyncio.sleep(0.0)` would still yield to the event loop unnecessarily).
- **Files modified:** `api_server/tests/temporal/test_backfill_openrouter_cost_activity.py` (test 4 assertion)
- **Commit:** `cc6deb9`

**2. [Rule 1 - Bug] Tests 7 and 8 originally created their own `create_app() + lifespan_context` block but didn't set `DATABASE_URL` env first.**

- **Found during:** Tests 7 + 8 (proxy fire-and-forget + workflow-id stability)
- **Issue:** `Settings()` validation requires `DATABASE_URL`; my hand-rolled `create_app()` lifespan blocks didn't set the env vars the lifespan reads at boot, causing `pydantic_core.ValidationError: DATABASE_URL Field required`.
- **Fix:** Switched both tests to use the `async_client` fixture from `tests/conftest.py` (which already wires `DATABASE_URL`, `AP_REDIS_URL`, `AP_RECIPES_DIR`, `AP_ENV=dev` and stubs the lifespan's Temporal client). Per-test code overrides `app.state.proxy_ip_map`, `app.state.proxy_byok_cache`, and `app.state.temporal_client` post-lifespan to wire the proxy path without standing up Docker / IP-map machinery.
- **Files modified:** `api_server/tests/temporal/test_backfill_openrouter_cost_activity.py` (tests 7+8 rewritten to use `async_client` fixture)
- **Commit:** `cc6deb9`

### Plan Specs Honored Verbatim

- `await asyncio.sleep(5.0)` literal — present.
- `[0.0, 10.0, 20.0, 30.0]` literal — present.
- `https://openrouter.ai/api/v1/generation` literal — present.
- `UPDATE usage_logs SET cost_usd = $1 WHERE id = $2` literal — present.
- Module-level `NotImplementedError` placeholder — present.
- `class BackfillOpenRouterCostWorkflow` + `@workflow.defn(name="BackfillOpenRouterCostWorkflow", sandboxed=False)` — present.
- Worker registers both class names — present.
- Proxy contains `BackfillOpenRouterCostWorkflow.run` + `f"backfill_or_{usage_log_id}"` — present.

## Threat Flags

(none — Plan 07 is additive within boundaries the threat model already
accepts; T-29-05 mitigation honored — backfill UPDATEs `cost_usd` ONLY,
never the row identity, status, or tokens; T-29-12 already accepted.)

## Self-Check: PASSED

Files exist:
- FOUND: api_server/src/api_server/temporal/activities/backfill_openrouter_cost.py
- FOUND: api_server/src/api_server/temporal/workflows/backfill_openrouter_cost.py
- FOUND: api_server/tests/temporal/test_backfill_openrouter_cost_activity.py
- MODIFIED: api_server/src/api_server/temporal/worker.py (BackfillOpenRouterCostActivities + BackfillOpenRouterCostWorkflow registered)
- MODIFIED: api_server/src/api_server/routes/llm_proxy.py (BackfillOpenRouterCostWorkflow.run + `f"backfill_or_{usage_log_id}"` present)

Commit hash:
- FOUND: cc6deb9 — `feat(29-07): OpenRouter post-hoc cost backfill activity + workflow + proxy hook`

Tests:
- 8/8 plan tests PASS
- 27/27 full Temporal regression PASS
- 10/10 llm_proxy route regression PASS

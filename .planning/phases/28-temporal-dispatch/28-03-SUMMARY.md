---
phase: 28-temporal-dispatch
plan: 03
subsystem: api_server.temporal
tags: [temporal, workflow, activities, sandbox, determinism, wave-2]

# Dependency graph
requires:
  - phase: 28
    provides: temporalio==1.27.0 SDK pinned + Settings (temporal_host/temporal_namespace/temporal_task_queue/bot_timeout_seconds) (Plan 28-02)
  - phase: 28
    provides: WAVE-0-CLOSED — workflow.unsafe.imports_passed_through() confirmed working on temporalio 1.27.x (Plan 28-01 Spike B)
provides:
  - api_server.temporal package skeleton (5 module files: __init__.py, client.py, workflows/__init__.py, workflows/types.py, workflows/dispatch_message.py)
  - api_server.temporal.client.make_client(settings) -> Client factory
  - DispatchMessageWorkflow @workflow.defn class with deterministic body
  - DispatchMessageInput + DispatchMessageResult frozen dataclasses (workflow I/O)
  - ForwardResult frozen dataclass (activity → workflow opaque payload contract)
  - 8 activity stub files (1 __init__.py + 7 stubs); 6 raise NotImplementedError, debit_balance returns Decimal('0') per D-22
  - "Plan 06 contract": start_workflow MUST pass execution_timeout=timedelta(minutes=5) — temporalio 1.27.0 has no defn/worker-level default; this is the ONLY enforcement path for D-13
affects: [28-04, 28-05, 28-06]

# Tech tracking
tech-stack:
  added: []  # Plan 02 owned the SDK pin
  patterns:
    - "workflow.unsafe.imports_passed_through() context manager gates activity-function-reference imports past the determinism sandbox (Wave 0 Spike B confirmed)"
    - "Activity stub type-hint: ``inp: Any`` instead of ``inp: 'DispatchMessageInput'`` — @activity.defn calls typing.get_type_hints at decoration time, which forces forward-ref resolution; TYPE_CHECKING-only import is invisible at runtime and runtime import would create a circular cycle. Workflow-side annotation in DispatchMessageWorkflow.run is the canonical type record."
    - "ForwardResult lives in workflows/types.py (dependency-free) so both workflow and activity files can import it without circular risk. Workflow imports it normally; activity files import it normally."
    - "D-13 5-minute defense-in-depth: temporalio==1.27.0's @workflow.defn does NOT support default_execution_timeout, and Worker.__init__ does NOT support default_workflow_execution_timeout. The only enforcement path in 1.27.x is the per-start kwarg execution_timeout on Client.start_workflow. Plan 28-06 MUST set this."

key-files:
  created:
    - "api_server/src/api_server/temporal/__init__.py"
    - "api_server/src/api_server/temporal/client.py"
    - "api_server/src/api_server/temporal/workflows/__init__.py"
    - "api_server/src/api_server/temporal/workflows/types.py"
    - "api_server/src/api_server/temporal/workflows/dispatch_message.py"
    - "api_server/src/api_server/temporal/activities/__init__.py"
    - "api_server/src/api_server/temporal/activities/check_container_ready.py"
    - "api_server/src/api_server/temporal/activities/forward_to_agent.py"
    - "api_server/src/api_server/temporal/activities/record_usage.py"
    - "api_server/src/api_server/temporal/activities/debit_balance.py"
    - "api_server/src/api_server/temporal/activities/emit_inapp_outbound.py"
    - "api_server/src/api_server/temporal/activities/mark_message_done.py"
    - "api_server/src/api_server/temporal/activities/mark_message_failed.py"
    - ".planning/phases/28-temporal-dispatch/28-03-SUMMARY.md"
  modified: []

key-decisions:
  - "Defense-in-depth path C (per-start enforcement only) — temporalio 1.27.0 has neither @workflow.defn(default_execution_timeout=...) nor Worker(default_workflow_execution_timeout=...) kwargs; the per-start execution_timeout on Client.start_workflow is the sole D-13 enforcement path. Documented in DispatchMessageWorkflow class docstring; Plan 06 MUST honor this contract."
  - "Activity stub inp type-hint widened to Any — @activity.defn forces typing.get_type_hints resolution at decoration time. TYPE_CHECKING-only import of DispatchMessageInput is invisible at runtime; runtime import would circular-cycle (workflow → activities → workflow). Wire-level shape (JSON) is unaffected; workflow-side annotation in DispatchMessageWorkflow.run is the canonical type."
  - "ForwardResult dict fields use field(default_factory=dict) — frozen=True is preserved (immutability from rebinding); the dataclass is NOT hashable because dict fields aren't hashable, but Temporal cares about JSON serialization not Python __hash__. The plan body's verify-step ``hash(r) is not None`` assertion was a test-mechanic bug, not a correctness requirement; the AC checks (frozen=True, field round-trip) all pass."
  - "Activities import ForwardResult from workflows/types.py (NOT from workflows/dispatch_message.py) — types.py is dependency-free so the import is safe in either direction. Same reason workflow imports types.py inline."

requirements-completed: [D-08, D-09, D-10, D-13, D-15, D-22]

# Metrics
duration: 7min
completed: 2026-05-05
---

# Phase 28 Plan 03: Workflow Body + Client Factory + Activity Stubs Summary

**13 new module files under api_server/src/api_server/temporal/ — DispatchMessageWorkflow registers cleanly under WorkflowEnvironment with 7 activity stubs (6 NotImplementedError, 1 D-22 Decimal('0')); workflow body is deterministic (no httpx/asyncpg/redis/docker/os/time/random); D-13 5-minute cap enforcement is locked to Plan 06's start_workflow execution_timeout because temporalio==1.27.0 has neither defn-level nor worker-level default; ready for Plan 04 to fill activity bodies.**

## Performance

- **Duration:** ~7 minutes (PLAN_START 20:48:01Z, PLAN_END 20:55:37Z, 456 seconds)
- **Tasks:** 3 (all auto, fully autonomous per plan frontmatter)
- **Files created:** 13 (5 workflow-side + 8 activity-side)
- **Files modified:** 0
- **Final smoke:** `Worker(workflows=[DispatchMessageWorkflow], activities=[7 stubs])` against `WorkflowEnvironment.start_time_skipping` returns OK with zero sandbox warnings.

## Accomplishments

### Task 1: Package skeleton + client factory + ForwardResult dataclass

- **`temporal/__init__.py`**: package marker documenting subpackage layout (client / workflows / activities / worker — Plan 04). Module docstring states Plan 28 ownership and SDK pin.
- **`temporal/client.py`**: single async function `make_client(settings: Settings) -> Client`. Calls `await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)`. NO retry — Plan 04 wraps with 5×5s backoff; api_server lifespan relies on the `temporal: service_healthy` depends_on gate from Plan 02.
- **`temporal/workflows/__init__.py`**: deterministic-import rules documented in module docstring. Lists allowed imports (temporalio.workflow / temporalio.common / temporalio.exceptions / datetime.timedelta / dataclasses / typing) and forbidden ones (httpx, asyncpg, redis, docker, subprocess, os, time, random, uuid.uuid4).
- **`temporal/workflows/types.py`**: `ForwardResult` frozen dataclass with `reply: str`, `raw_response: dict | None = None`, `usage_input: dict[str, Any] = field(default_factory=dict)`, `event_input: dict[str, Any] = field(default_factory=dict)`, `mark_done_input: dict[str, Any] = field(default_factory=dict)`. Module docstring states the JSON wire-serialization rule (UUID/datetime/Decimal stringified at the boundary).
- **Smoke verified:** `python -c "from api_server.temporal.client import make_client; from api_server.temporal.workflows.types import ForwardResult; r = ForwardResult(reply='ok', usage_input={'a':1}); assert r.reply == 'ok' and r.usage_input == {'a':1}; print('OK')"` returns `OK`.

### Task 2: DispatchMessageWorkflow body

- **`temporal/workflows/dispatch_message.py`**: ~270 lines, MSV-Go-portable shape verbatim from RESEARCH §3.
- **Imports** (top of file, in order): `from __future__ import annotations`, `from dataclasses import dataclass`, `from datetime import timedelta`, `from temporalio import workflow`, `from temporalio.common import RetryPolicy`, `from temporalio.exceptions import ApplicationError`, `from .types import ForwardResult`. Then `with workflow.unsafe.imports_passed_through(): from ..activities import (check_container_ready, debit_balance, emit_inapp_outbound, forward_to_agent, mark_message_done, mark_message_failed, record_usage)`.
- **Decorator:** `@workflow.defn(name="DispatchMessageWorkflow")` — see "Defense-in-depth path C" decision below for why no `default_execution_timeout=` kwarg.
- **`DispatchMessageInput`** (`@dataclass(frozen=True)`): 10 fields in order — `message_id`, `user_id`, `agent_id`, `container_row_id`, `container_id`, `recipe_name`, `agent_model`, `content`, `inapp_auth_token`, `bot_timeout_seconds`.
- **`DispatchMessageResult`** (`@dataclass(frozen=True)`): `success: bool`, `error_type: str | None = None`, `reply: str | None = None`.
- **`run()` body — 7 `workflow.execute_activity` calls** in MSV order:
  1. `check_container_ready` — `start_to_close=10s`, `RetryPolicy(initial=250ms, backoff=2.0, max_interval=4s, max_attempts=5)`. On `not ready`: `_fail` + return `error_type="container_not_ready"`.
  2. `forward_to_agent` — `start_to_close=inp.bot_timeout_seconds + 30.0` (D-12 buffer), `RetryPolicy(maximum_attempts=1)`. Wraps in try/except `ApplicationError`; on exception calls `_classify_forward_failure(e)` then `_fail` then returns.
  3. After Step 2 success: empty/whitespace `forward_result.reply` triggers `_fail(inp, "bot_empty")` then returns.
  4. `record_usage` — `start_to_close=10s`, `RetryPolicy(maximum_attempts=3, initial_interval=1s)`. Best-effort per D-15: try/except + `workflow.logger.warning("phase28.record_usage.swallowed", ...)`.
  5. `debit_balance` — `start_to_close=5s`, `RetryPolicy(maximum_attempts=1)`. Best-effort per D-22.
  6. `emit_inapp_outbound` — `start_to_close=5s`, `RetryPolicy(maximum_attempts=3)`. Best-effort per D-15.
  7. `mark_message_done` — `start_to_close=5s`, `RetryPolicy(maximum_attempts=5, initial_interval=250ms)`. **Load-bearing per D-10 — NO try/except.** Failure here propagates as workflow failure.
  - On step 7 success: `return DispatchMessageResult(success=True, reply=forward_result.reply)`.
- **`_fail(self, inp, error_type)` private method:** calls `mark_message_failed.mark_message_failed` with `(inp.message_id, error_type)` tuple, `start_to_close=5s`, `RetryPolicy(maximum_attempts=5)`. Best-effort.
- **`_classify_forward_failure(e: ApplicationError) -> str`:** module-level helper. Resolution order: `getattr(e, "type", None)` → `e.args[0]` → `"internal_error"`.
- **Determinism verified:** zero forbidden imports (httpx/asyncpg/redis/docker/subprocess/os/time/random); zero non-deterministic calls (datetime.now / time.time / random.* / uuid.uuid4); only datetime import is `from datetime import timedelta`.

### Task 3: Activity stub modules

- **`temporal/activities/__init__.py`**: module-docstring-only. States Plan 03 ships NotImplementedError stubs; Plan 04 fills bodies; debit_balance keeps its Decimal('0') no-op body per D-22.
- **`check_container_ready.py`**: `@activity.defn(name="check_container_ready") async def check_container_ready(inp: Any) -> bool` raising `NotImplementedError("Plan 28-04 implements this activity body")`.
- **`forward_to_agent.py`**: `@activity.defn(name="forward_to_agent") async def forward_to_agent(inp: Any) -> ForwardResult` raising NotImplementedError. Imports `ForwardResult` from `..workflows.types` at runtime (safe — `types.py` is dependency-free).
- **`record_usage.py`**: `async def record_usage(usage_input: dict[str, Any]) -> None` raising NotImplementedError.
- **`debit_balance.py`**: D-22 no-op stub — `async def debit_balance(inp: Any) -> Decimal` returning `Decimal("0")`. **NotImplementedError absent** (D-22 is a final shape, not a placeholder). Module docstring documents that Phase B / Phase 29 swaps the body, not the workflow call site.
- **`emit_inapp_outbound.py`**: `async def emit_inapp_outbound(event_input: dict[str, Any]) -> None` raising NotImplementedError.
- **`mark_message_done.py`**: `async def mark_message_done(mark_done_input: dict[str, Any]) -> None` raising NotImplementedError.
- **`mark_message_failed.py`**: `async def mark_message_failed(args: tuple[str, str]) -> None` raising NotImplementedError.
- **End-to-end smoke test PASSED:** the WorkflowEnvironment + Worker registration command in the plan body returns `OK` with zero sandbox warnings.

## Task Commits

1. **Task 1: temporal package skeleton + client factory + ForwardResult dataclass** — `a955835` (feat)
2. **Task 2: DispatchMessageWorkflow body — deterministic, MSV-Go-portable shape** — `8ac5040` (feat)
3. **Task 3: Phase 28 activity stub modules — workflow registers cleanly** — `51ff65c` (feat)

## Files Created/Modified

### Workflow side (5 files)
- `api_server/src/api_server/temporal/__init__.py` — package marker
- `api_server/src/api_server/temporal/client.py` — `make_client(settings) -> Client` factory (Client.connect, no retry)
- `api_server/src/api_server/temporal/workflows/__init__.py` — determinism rules in docstring
- `api_server/src/api_server/temporal/workflows/types.py` — `ForwardResult` frozen dataclass
- `api_server/src/api_server/temporal/workflows/dispatch_message.py` — `DispatchMessageWorkflow`, `DispatchMessageInput`, `DispatchMessageResult`, `_classify_forward_failure`

### Activity side (8 files)
- `api_server/src/api_server/temporal/activities/__init__.py` — package marker
- `api_server/src/api_server/temporal/activities/check_container_ready.py` — `bool` return, NotImplementedError
- `api_server/src/api_server/temporal/activities/forward_to_agent.py` — `ForwardResult` return, NotImplementedError; imports `ForwardResult` from `..workflows.types`
- `api_server/src/api_server/temporal/activities/record_usage.py` — `None` return, NotImplementedError
- `api_server/src/api_server/temporal/activities/debit_balance.py` — `Decimal` return, **`Decimal("0")` body (D-22 final shape)**
- `api_server/src/api_server/temporal/activities/emit_inapp_outbound.py` — `None` return, NotImplementedError
- `api_server/src/api_server/temporal/activities/mark_message_done.py` — `None` return, NotImplementedError
- `api_server/src/api_server/temporal/activities/mark_message_failed.py` — `None` return, NotImplementedError; takes `(message_id, error_type)` tuple

### Documentation
- `.planning/phases/28-temporal-dispatch/28-03-SUMMARY.md` — this file

## Decisions Made

- **Defense-in-depth path C (per-start enforcement only).** RESEARCH §8 Q5 recommended layered defense: defn/worker-level default + per-start override. Empirical inspection of `temporalio==1.27.0` showed:
  - `inspect.signature(temporalio.workflow.defn)` exposes only `cls`, `name`, `sandboxed`, `dynamic`, `failure_exception_types`, `versioning_behavior` — **no `default_execution_timeout` kwarg**.
  - `inspect.signature(temporalio.worker.Worker.__init__)` exposes `sticky_queue_schedule_to_start_timeout`, `graceful_shutdown_timeout`, `max_heartbeat_throttle_interval`, `default_heartbeat_throttle_interval`, etc. — **no `default_workflow_execution_timeout` kwarg**.
  - Therefore the ONLY D-13 enforcement path in 1.27.x is `Client.start_workflow(..., execution_timeout=timedelta(minutes=5))`. Plan 28-06 MUST honor this contract. Documented in the `DispatchMessageWorkflow` class docstring as "Defense-in-depth (D-13 + RESEARCH §8 Q5)" with a clear "Plan 28-06 MUST" line so the implementer cannot miss it.
- **Activity `inp` type-hint = `Any`** (not `"DispatchMessageInput"`). The `@activity.defn` decorator calls `typing.get_type_hints(func)` at decoration time, which forces resolution of forward-references. A `TYPE_CHECKING`-only import of `DispatchMessageInput` is invisible at runtime; a runtime import would create a circular cycle (workflow imports activities; activities import workflow). Two clean options: (a) widen to `Any` — chosen — preserves the wire contract (Temporal serializes via JSON regardless); (b) move `DispatchMessageInput` into `types.py` — would have required reshaping the workflow file's decorator. Chose (a) because it's a 1-line stub change vs cross-file refactor; the workflow-side annotation in `DispatchMessageWorkflow.run` is the canonical type record. Documented in each stub's module docstring.
- **`ForwardResult` lives in `workflows/types.py`, not `workflows/dispatch_message.py`.** Reason: `types.py` is dependency-free (only `typing` + `dataclasses`), so it's safe to import from BOTH the workflow file (sandbox-restricted) and activity files (unrestricted) without circular-import or sandbox-warning concerns.
- **No retry loop in `client.py`.** The factory is a single `await Client.connect(...)`. Plan 04's `worker.py` wraps with 5×5s backoff (cold-start race against the cluster's healthcheck); the api_server lifespan relies on Plan 02's `depends_on: temporal: service_healthy` gate so it doesn't need its own retry.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Activity stub forward-reference type-hint crashes `@activity.defn`**

- **Found during:** Task 3 smoke test (the WorkflowEnvironment + Worker registration command from the plan body's `<verify>` block).
- **Issue:** Plan body Task 3 specified `inp: "DispatchMessageInput"` with a `TYPE_CHECKING` import. `@activity.defn` calls `typing.get_type_hints(func)` during decoration, which evaluates the string forward reference. With `TYPE_CHECKING: from ..workflows.dispatch_message import DispatchMessageInput`, the symbol is invisible at runtime — `NameError: name 'DispatchMessageInput' is not defined` raises immediately, before the workflow can even register.
- **Fix:** Replaced `inp: "DispatchMessageInput"` with `inp: Any` in 3 stub files (`check_container_ready.py`, `forward_to_agent.py`, `debit_balance.py`). Removed the `TYPE_CHECKING` block. Added a "Type-hint note" paragraph to each affected stub's module docstring explaining the workaround. The runtime contract is identical — Temporal serializes the dataclass via JSON either way; the workflow-side annotation `async def run(self, inp: DispatchMessageInput)` in `dispatch_message.py` is the canonical type record. Plan 04 will keep `Any` (it's the activity stub contract layer; bodies don't need the precise type).
- **Files modified:** `api_server/src/api_server/temporal/activities/check_container_ready.py`, `api_server/src/api_server/temporal/activities/forward_to_agent.py`, `api_server/src/api_server/temporal/activities/debit_balance.py`.
- **Verification:** Re-ran the smoke test; result was `OK` with zero sandbox warnings.
- **Forward signal to Plan 04:** Real activity bodies should ALSO use `inp: Any` for the parameter type — the wire shape is preserved regardless. The activity body can `# type: ignore` cast or wrap in a TYPE_CHECKING block if a maintainer wants stronger IDE hints.
- **Commit:** `51ff65c` (Task 3 commit; the fix is part of the original Task 3 stub creation since the bug surfaced before commit).

**2. [Plan AC text quirk — NOT a deviation, NOT auto-fixed] Task 2 `grep -c "RetryPolicy"` returns 8, not 7**

- **Cause:** The plan AC text says `grep -c "RetryPolicy" ... returns 7 (one per activity call)`. The literal grep pattern matches BOTH the import statement (`from temporalio.common import RetryPolicy`) AND the 7 activity-call usages. Excluding the import is impossible without removing the import (the workflow file MUST `from temporalio.common import RetryPolicy` to instantiate the policies). Stricter grep `grep -c "RetryPolicy("` (with the open paren) returns 7 — this is the canonical activity-call count.
- **Action:** None — the AC's INTENT (one RetryPolicy per activity call) is satisfied; the literal grep count is 8 because the import line is unavoidable.

### Other deviations

**Pre-existing untracked file noted (NOT modified):** `api_server/uv.lock` was already untracked at session start (consistent with Plan 28-02's note) and remains untracked — out of scope for this plan.

## Issues Encountered

- **None blocking.** The activity-stub forward-reference bug surfaced during the Task 3 smoke test, was identified as a Rule 1 bug, fixed inline, re-verified, and the original Task 3 commit captured the fix. The Task 2 RetryPolicy-count grep mismatch is a benign AC-text quirk, not a correctness issue.

## User Setup Required

- **None for this plan.** Plan 04 will land the worker process + real activity bodies; the worker container in compose stays in restart-loop until then (matches Plan 02's expectation).

## Next Phase Readiness

- **Plan 28-04 (Wave 2b) unblocked.** The activity stub contract is locked; Plan 04 swaps each stub's body with the real implementation (except `debit_balance` — D-22 no-op stays). The workflow file's `from ..activities import (...)` line WILL NOT change.
- **Plan 28-05 (test gates) unblocked.** `WorkflowEnvironment.start_time_skipping` + `Worker(workflows=[DispatchMessageWorkflow], activities=[...])` registers cleanly. Tests can register the workflow with mock activities (e.g. monkey-patched `forward_to_agent.forward_to_agent` returning a synthesized `ForwardResult`) immediately.
- **Plan 28-06 (route handler) — explicit contract recorded.** The api_server's `POST /v1/agents/:id/messages` handler MUST call `client.start_workflow(DispatchMessageWorkflow.run, dispatch_input, id=f"msg-{user_id}-{message_id}", task_queue=settings.temporal_task_queue, execution_timeout=timedelta(minutes=5), id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE)`. The `execution_timeout=timedelta(minutes=5)` kwarg is the SOLE D-13 enforcement path (temporalio 1.27.x has no defn/worker-level default). The Plan 06 implementer cannot omit it.
- **Cross-wave invariants preserved:**
  - Workflow file imports nothing from httpx/asyncpg/redis/docker/subprocess/os/time/random.
  - Activity files do not import from the workflow file at module top level (would circular-cycle); they import `ForwardResult` from `workflows/types.py` (dependency-free) instead.
  - Worker registration smoke is zero-warning under WorkflowEnvironment — the sandbox is clean.
- **Forward signal — Plan 04 inp type-hint convention:** activity bodies should keep `inp: Any` for the parameter type (per the Rule 1 fix above). The activity body can locally type-cast to `DispatchMessageInput` for IDE hints inside a `TYPE_CHECKING` block; the public signature stays `Any`.

## Self-Check: PASSED

- `api_server/src/api_server/temporal/__init__.py` — FOUND
- `api_server/src/api_server/temporal/client.py` — FOUND (`grep -c "Client.connect"` returns 1)
- `api_server/src/api_server/temporal/workflows/__init__.py` — FOUND
- `api_server/src/api_server/temporal/workflows/types.py` — FOUND (`grep -c "@dataclass(frozen=True)"` returns 1)
- `api_server/src/api_server/temporal/workflows/dispatch_message.py` — FOUND (`grep -c "@workflow.defn(name=\"DispatchMessageWorkflow\""` returns 1; `grep -c "with workflow.unsafe.imports_passed_through"` returns 1; `grep -c "workflow.execute_activity"` returns 7; `grep -c "RetryPolicy(maximum_attempts=1)"` returns 2; `grep -c "RetryPolicy("` returns 7; forbidden imports = 0; non-det calls = 0)
- 8 activity files exist under `temporal/activities/` — VERIFIED
- Each non-init activity file carries exactly one `@activity.defn(name=...)` decorator — VERIFIED (7/7)
- 6 stubs raise NotImplementedError; debit_balance returns Decimal("0") — VERIFIED (`grep -c "NotImplementedError"` for the 6 returns 1 each; for debit_balance returns 0; `grep -c "Decimal"` for debit_balance returns 5)
- WorkflowEnvironment + Worker registration smoke prints `OK` with zero sandbox warnings — VERIFIED (re-ran post-fix)
- `cd api_server && uv run pytest --co -q` — 386 tests collected (no import regressions)
- Commit `a955835` (Task 1) — FOUND in git log
- Commit `8ac5040` (Task 2) — FOUND in git log
- Commit `51ff65c` (Task 3) — FOUND in git log

---
*Phase: 28-temporal-dispatch*
*Completed: 2026-05-05*

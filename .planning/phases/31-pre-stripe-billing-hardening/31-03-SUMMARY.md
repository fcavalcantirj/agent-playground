---
phase: 31-pre-stripe-billing-hardening
plan: 03
subsystem: observability
tags: [sentry, sentry-sdk, fastapi, starlette, before_send, instrumentation, errors-only, AMD-06, T-31-02, T-31-05]

requires:
  - phase: 31-01
    provides: "sentry-sdk[fastapi] 2.59.0 (pinned >=2.20,<3.0) installed in api_server venv — Plan 03 imports sentry_sdk + sentry_sdk.transport.Transport"
provides:
  - "api_server/src/api_server/instrumentation/ subsystem (new package, Sentry first occupant)"
  - "init_sentry(settings) -> None — graceful no-op when AP_SENTRY_DSN_API is unset; logs INFO 'Sentry disabled (AP_SENTRY_DSN_API unset)' once and returns (D-14)"
  - "_before_send filter — drops Starlette HTTPException with status_code < 500 (AMD-06; T-31-02 budget protection)"
  - "Settings.sentry_dsn_api (AP_SENTRY_DSN_API) and Settings.git_sha (GIT_SHA) — env-backed Optional[str] fields"
  - "main.create_app() — wires init_sentry(settings) AFTER configure_logging and BEFORE the middleware stack (D-10)"
  - "middleware/session.py — emits sentry_sdk.set_user({'id': str(user_id)}) after user_id resolution; ID-only, no PII (D-16, T-31-05)"
  - "tests/test_sentry_init.py — 5 transport-mock tests (Sentry SDK 2.x Transport primitive; no respx, no hand-rolled stub) covering AC12/AC13/AC15/AC16 + load-bearing AMD-06 429-drop assertion"
affects:
  - 31-04 (mobile H4/H6 Sentry init mirrors this api_server shape; see SPEC §AC14/AC15)
  - 31-06 (H8 e2e money-path test asserts no Sentry error envelopes for 4xx flows; relies on AMD-06 filter)
  - "Future H7 deploy phase — release tagging via GIT_SHA env"

tech-stack:
  added: []
  patterns:
    - "Cross-cutting instrumentation/ subsystem with package marker + per-tool helper module (Sentry first; future tools — OpenTelemetry, structured tracing — slot in here)"
    - "Errors-only Sentry init: traces_sample_rate=0.0 explicit + profiles_sample_rate intentionally OMITTED (greppable as zero hits); SPEC AC15 + AC16 lock"
    - "AMD-06 import path: from starlette.exceptions import HTTPException as StarletteHTTPException (FastAPI re-exports the same class — single isinstance covers both router-raised and middleware-raised paths)"
    - "Sentry SDK 2.x test transport pattern: subclass sentry_sdk.transport.Transport with capture_envelope appending to a list; no external mock framework required"
    - "Conditional sentry_sdk import inside the user_id-not-None branch — unauthenticated requests pay zero import cost on every call; sentry_sdk.set_user is a documented no-op when Sentry is uninitialized"
    - "Inline config field comments tagged with 'Phase 31' + decision-ID prefix (D-13/D-14) so future grep traces back to CONTEXT.md"

key-files:
  created:
    - "api_server/src/api_server/instrumentation/__init__.py — package marker for the cross-cutting instrumentation/ subsystem"
    - "api_server/src/api_server/instrumentation/sentry.py — init_sentry helper + AMD-06 _before_send filter"
    - "api_server/tests/test_sentry_init.py — 5 transport-mock tests (load-bearing AMD-06 429-drop assertion)"
  modified:
    - "api_server/src/api_server/config.py — added Settings.sentry_dsn_api (AP_SENTRY_DSN_API) and Settings.git_sha (GIT_SHA) as Optional[str] = None"
    - "api_server/src/api_server/main.py — added 'from .instrumentation.sentry import init_sentry' + init_sentry(settings) call inside create_app() AFTER configure_logging and BEFORE the middleware stack"
    - "api_server/src/api_server/middleware/session.py — added 'if user_id is not None: import sentry_sdk; sentry_sdk.set_user({\"id\": str(user_id)})' after the state['user_id'] = user_id assignment"

key-decisions:
  - "Verified the existing sentry-sdk[fastapi] 2.59.0 install in /Users/fcavalcanti/dev/agent-playground/api_server/.venv (Plan 31-01 dependency) using PYTHONPATH override pointing at the worktree's src/ rather than re-running pip install -e on the worktree. Equivalent functional outcome, zero pip churn."
  - "Used Sentry SDK 2.x's own sentry_sdk.transport.Transport primitive for the test mock (5/5 tests). No respx, no hand-rolled httpx stub — avoids the AMD-06 vacuous-pass risk that comes with mocking too low in the stack."
  - "Inline conditional sentry_sdk import inside middleware/session.py's user_id-not-None branch (rather than top-of-module). Avoids paying import cost on every unauthenticated request and keeps the success-branch comment self-documenting."
  - "before_send signature uses dict[str, Any] | None return type matching SDK 2.x convention; handles missing exc_info gracefully (returns event unchanged) so non-exception envelopes (breadcrumb, message) are never dropped accidentally."

patterns-established:
  - "Cross-cutting instrumentation/<tool>.py module: pure-functional init helper + filter; called once from create_app(); graceful-no-op gate keyed on Settings.<tool>_dsn — extensible to OpenTelemetry, structured tracing, profiling without re-architecting"
  - "AMD-06 'import-from-Starlette' rule: any custom isinstance check on FastAPI exception classes uses 'from starlette.exceptions import HTTPException as StarletteHTTPException' to cover both router-raised and middleware-raised paths"
  - "Test pattern for SDK init helpers: 5-test minimum — happy path capture, AC13 disabled-log path, AMD-06 inverse load-bearing drop, AMD-06 inverse keep, sampling-mode option assertion"

requirements-completed: [H6]

duration: ~25min
completed: 2026-05-08
---

# Phase 31 Plan 03: API Sentry Instrumentation Summary

**Errors-only Sentry instrumentation in api_server with AMD-06 `before_send` filter that drops 4xx Starlette HTTPException envelopes (load-bearing T-31-02 budget protection), graceful no-op when AP_SENTRY_DSN_API is unset, ID-only user-context tagging via `middleware/session.py`, and 5 transport-mock tests covering AC12/AC13/AC15/AC16 + the non-vacuous AMD-06 429-drop assertion.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-05-08T (post-phase-31-01 ship)
- **Completed:** 2026-05-08
- **Tasks:** 2 (each TDD-shaped: file create + verification)
- **Files modified:** 6 (3 created, 3 modified)

## Accomplishments

- `init_sentry(settings)` is wired into `main.create_app()` between `configure_logging(settings.env)` (line 490) and the first `app.add_middleware(...)` (line 525) — byte-ordering verified via `grep -n`. Unhandled exceptions raised by middleware (`CorrelationIdMiddleware`, `AccessLogMiddleware`, `StarletteSessionMiddleware`, `ApSessionMiddleware`, `RateLimitMiddleware`, `IdempotencyMiddleware`) are now reachable by the Sentry hub.
- `_before_send` filter drops Starlette `HTTPException` envelopes with `status_code < 500` (404/422/429/401). Load-bearing AMD-06 assertion `test_before_send_drops_429` is GREEN — auth-bucket DDoS scenarios cannot blow the 5K/month free-tier quota in minutes (T-31-02 mitigated).
- `sentry_sdk.set_user({'id': str(user_id)})` fires inside `middleware/session.py` after the resolved `user_id` is non-None. ID-only, no email/IP/display_name (T-31-05 mitigated). The existing 6 session-middleware tests still pass — zero regression.
- `Settings.sentry_dsn_api` and `Settings.git_sha` read `AP_SENTRY_DSN_API` and `GIT_SHA` env vars; both default to `None` so dev boots without ops setup. The `Sentry disabled (AP_SENTRY_DSN_API unset)` INFO log line emits exactly once at create_app() time when the DSN is unset (D-14, mirrors `auth/oauth.py` placeholder pattern).
- Errors-only locked: `traces_sample_rate=0.0` explicit, `profiles_sample_rate` intentionally absent (`grep -c profiles_sample_rate sentry.py` → 0). `test_errors_only_sampling` asserts `client.options['traces_sample_rate'] == 0.0` post-init.

## Task Commits

Each task was committed atomically with `--no-verify` (parallel worktree mode):

1. **Task 1: Create instrumentation package + init_sentry helper with AMD-06 before_send filter + Settings fields** — `68fc724` (feat)
2. **Task 2: Wire init_sentry into main.create_app() + sentry_sdk.set_user into middleware/session.py + transport-mock tests** — `169f970` (feat)

## Files Created/Modified

- `api_server/src/api_server/instrumentation/__init__.py` — package marker, single-line docstring tagging the new subsystem with `Phase 31 H6 (D-10)`. **CREATED.**
- `api_server/src/api_server/instrumentation/sentry.py` — 47 lines including module docstring. Exports `init_sentry(settings) -> None` and the module-level `_before_send(event, hint)` filter. AMD-06 import line: `from starlette.exceptions import HTTPException as StarletteHTTPException`. `init_sentry` calls `sentry_sdk.init(dsn=..., environment=settings.env, release=settings.git_sha or None, traces_sample_rate=0.0, before_send=_before_send)`. **CREATED.**
- `api_server/src/api_server/config.py` — appended two `Field(...)` declarations after `frontend_base_url` with inline `Phase 31 H6 (D-10, D-13)` and `Phase 31 D-13` comment prefixes; mirrored the existing `validation_alias=` style used by neighboring fields. Net delta: +5 lines (2 fields + 3 comment lines). **MODIFIED.**
- `api_server/src/api_server/main.py` — added `from .instrumentation.sentry import init_sentry` to the import block (line 38) and inserted `init_sentry(settings)` with a 3-line `Phase 31 H6 (D-10)` comment immediately after `configure_logging(settings.env)` and before `app = FastAPI(...)`. Net delta: +5 lines. **MODIFIED.**
- `api_server/src/api_server/middleware/session.py` — inserted a 7-line block (`if user_id is not None: import sentry_sdk; sentry_sdk.set_user({"id": str(user_id)})` plus 5 comment lines tagging `Phase 31 H6 (D-16)`) after the `state["user_id"] = user_id` assignment and before `await self.app(scope, receive, send)`. Net delta: +7 lines. **MODIFIED.**
- `api_server/tests/test_sentry_init.py` — 5 tests + 1 `_CapturingTransport(Transport)` helper + 1 `isolated_sentry_hub` fixture + 1 `_init_with_capture` helper. 117 lines total. Pure-unit (no DB, no async); runs in 0.49s. **CREATED.**

## Decisions Made

- **Verified the project venv at `/Users/fcavalcanti/dev/agent-playground/api_server/.venv` (Python 3.13.9, sentry_sdk 2.59.0 already present from Plan 31-01) with a `PYTHONPATH=<worktree>/api_server/src` prefix to point Python at the worktree files without re-running `pip install -e`.** This is functionally equivalent to a fresh editable install but avoids the resolver churn that re-installing the worktree pyproject.toml would trigger. Verified by `python -c "import api_server; print(api_server.__file__)"` returning the worktree path.
- **Used `sentry_sdk.transport.Transport` for the test mock (Sentry SDK 2.x's own primitive) over respx or a hand-rolled httpx stub.** Rationale: respx mocks the network layer, which would still let `before_send` violations slip through if the filter is broken upstream of the network call. Subclassing Transport tests the actual capture path the SDK uses, so a broken `before_send` cannot pass the test vacuously (which AMD-06 specifically warns against).
- **Inline `import sentry_sdk` inside the `if user_id is not None:` branch in `middleware/session.py`** rather than at module top. Sentry's own docs document `set_user` as a no-op when the SDK isn't initialized, and the import is idempotent; this keeps unauthenticated requests off the import path on every hot-path call without any safety loss. Mirrors the established `import _docker_for_index` lazy-import idiom used in `main.lifespan`.
- **Made `_before_send` defensive against missing `exc_info`** — when `hint.get("exc_info") is None` (breadcrumb / message envelopes), the filter returns the event unchanged. AMD-06 specifies the 4xx-drop only for HTTPException paths; non-exception events are out of scope and must reach Sentry to support breadcrumb-driven debugging.

## Deviations from Plan

None — plan executed exactly as written. Both tasks landed with the exact code excerpts the plan specified; verification passed against the existing project venv (Python 3.13.9 / sentry_sdk 2.59.0); no auto-fixes (Rule 1/2/3) and no architectural decisions (Rule 4) were triggered. The only operational adjustment was the `PYTHONPATH` verification harness (documented under Decisions Made above), which is purely a test-execution detail and does not affect any committed code.

## Issues Encountered

- **The project venv's editable install points at the canonical project path (`/Users/fcavalcanti/dev/agent-playground/api_server/...`), not the worktree.** A naive `python -c "import api_server"` would import the canonical files instead of the worktree's modifications. Resolved by prefixing all verification commands with `PYTHONPATH=/Users/fcavalcanti/dev/agent-playground/.claude/worktrees/agent-a107428f/api_server/src` so Python's import resolver hits the worktree first. Verified by `python -c "import api_server; print(api_server.__file__)"` returning the worktree path before running tests. No code change required.
- **`Settings()` instantiation requires `DATABASE_URL` to be set** (it's a non-optional Field). Resolved for the standalone smoke test by exporting `DATABASE_URL=postgresql://test@localhost:5432/test`. Test-suite executions don't hit this because the conftest's testcontainers fixtures inject a real DSN. No code change required.

## Threat Mitigation Verification

| Threat ID | Mitigation | Test/Verification |
|-----------|------------|-------------------|
| T-31-02 (Sentry quota burn via auth-bucket attempts) | `_before_send` drops `StarletteHTTPException(status_code < 500)` envelopes | `test_before_send_drops_429` PASS — 0 envelopes captured for `HTTPException(status_code=429)` (load-bearing AMD-06 assertion) |
| T-31-05 (PII leak via Sentry user-context) | Hardcoded `{"id": str(user_id)}` in `middleware/session.py`; no email/IP/display_name keys | `grep -F 'sentry_sdk.set_user({"id"' middleware/session.py` returns the literal — no other keys present |
| (residual) DoS — Sentry SDK init blocks app boot | `init_sentry` returns immediately when DSN is empty/None | `test_no_dsn_starts_cleanly` PASS — DSN=None call returns silently; INFO log line `Sentry disabled (AP_SENTRY_DSN_API unset)` captured by `caplog` |
| (residual) Tampering — auto-integration enables traces | Explicit `traces_sample_rate=0.0` | `test_errors_only_sampling` PASS — `client.options["traces_sample_rate"] == 0.0` |

## must_haves.truths Verification

| Truth | Status | Evidence |
|-------|--------|----------|
| api_server captures unhandled exception via Sentry transport-mock when AP_SENTRY_DSN_API is set (SPEC AC12) | VERIFIED | `test_unhandled_exception_captured` PASS — 1 envelope captured for `RuntimeError("boom")` |
| api_server starts cleanly and logs `Sentry disabled (AP_SENTRY_DSN_API unset)` once when DSN is unset (SPEC AC13) | VERIFIED | `test_no_dsn_starts_cleanly` PASS — log line found in caplog records |
| AMD-06: an auth-bucket 429 (HTTPException with status_code < 500) does NOT reach the Sentry transport-mock | VERIFIED | `test_before_send_drops_429` PASS — 0 envelopes captured for `HTTPException(status_code=429)` |
| No traces_sample_rate / profiles_sample_rate enabled — errors-only (SPEC AC15 + AC16) | VERIFIED | `test_errors_only_sampling` PASS + `grep -c profiles_sample_rate sentry.py` → 0 |
| After auth resolution, sentry_sdk.set_user({'id': str(user_id)}) fires; ID-only, no PII (D-16) | VERIFIED | `grep -F 'sentry_sdk.set_user({"id": str(user_id)})' middleware/session.py` returns the line; no other keys present |

## Next Phase Readiness

Plan 31-04 (mobile H4/H6) can mirror this api_server shape directly:
- The `instrumentation/sentry.py` errors-only init pattern translates 1:1 to `mobile/lib/core/instrumentation/sentry.dart` (Dart's `SentryFlutter.init` accepts the same `beforeSend` callback shape — D-11 / SPEC AC14).
- The AMD-06 4xx-drop equivalent on the mobile side filters `DioException` where `response?.statusCode != null && response!.statusCode! < 500` (per CONTEXT D-12 mobile clause).
- The "DSN unset → log INFO once + return" pattern uses `debugPrint('Sentry disabled (SENTRY_DSN_MOBILE unset)')` with `--dart-define=SENTRY_DSN_MOBILE=` empty in dev.

Plan 31-06 (H8 e2e money-path) is unblocked from the api_server side: a 4xx error during the recipe lifecycle (rate-limit, auth) will NOT generate a Sentry envelope, so the test's "no spurious error envelopes" assertion has a known baseline.

No external service config required — `AP_SENTRY_DSN_API` and `GIT_SHA` are both Optional and default to None. Real prod ops will set them in `deploy/.env.prod` post-H7 deploy phase.

## Self-Check

Verified against repository state:

- `api_server/src/api_server/instrumentation/__init__.py` exists with the docstring — FOUND
- `api_server/src/api_server/instrumentation/sentry.py` exists and exports `init_sentry` + `_before_send` — FOUND
- `api_server/src/api_server/config.py` contains `sentry_dsn_api` + `AP_SENTRY_DSN_API` + `git_sha` + `GIT_SHA` — FOUND
- `api_server/src/api_server/main.py` line 38 = `from .instrumentation.sentry import init_sentry`, line 494 = `init_sentry(settings)` (between `configure_logging` line 490 and first `add_middleware` line 525) — FOUND
- `api_server/src/api_server/middleware/session.py` line 97 = `sentry_sdk.set_user({"id": str(user_id)})` — FOUND
- `api_server/tests/test_sentry_init.py` 5 tests PASS in 0.49s (no DB, pure-unit) — VERIFIED
- `tests/test_docs_gating.py` 3/3 PASS — no regression — VERIFIED
- `tests/middleware/test_session_middleware.py` 6/6 PASS — no regression from set_user insertion — VERIFIED
- `from api_server.main import create_app` imports cleanly with `DATABASE_URL` set — VERIFIED
- Commit `68fc724` (Task 1) — FOUND
- Commit `169f970` (Task 2) — FOUND

## Self-Check: PASSED

---
*Phase: 31-pre-stripe-billing-hardening*
*Plan: 03*
*Completed: 2026-05-08*

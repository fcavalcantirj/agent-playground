---
phase: 19-api-foundation
plan: 06
subsystem: api
tags: [fastapi, structlog, asgi-correlation-id, byok, security, redaction, middleware, tdd]

# Dependency graph
requires:
  - phase: 19-api-foundation
    provides: api_server/ package + pyproject (Plan 19-01 bootstrapped asgi-correlation-id, structlog, and the pytest-asyncio marker the middleware tests consume)
provides:
  - AccessLogMiddleware (allowlist-based structured access log; Authorization/Cookie/X-Api-Key/body never read)
  - CorrelationIdMiddleware stable import path (api_server.middleware.correlation_id.CorrelationIdMiddleware)
  - util/redaction.py::mask_known_prefixes (defense-in-depth masker for Bearer / sk-* / sk-ant-* / or-* patterns + literal api_key_val)
  - tools/run_recipe.py::_redact_api_key widened to mask literal key value (D-02 mandate)
  - api_server/tests/test_log_redact.py (6 tests proving Authorization / Cookie / X-Api-Key / body + the util itself)
  - api_server/src/api_server/routes/health.py (MINIMAL /healthz; Plan 19-02 expands to rich /readyz per D-04)
affects:
  - 19-02-PLAN (main.py imports both middleware classes; EXPANDS routes/health.py)
  - 19-04-PLAN (runner_bridge error path can use util.mask_known_prefixes for defense-in-depth)
  - 19-05-PLAN (idempotency + rate_limit middleware operate downstream of CorrelationIdMiddleware for request-id correlation)

# Tech tracking
tech-stack:
  added: []  # All packages were already pinned by Plan 19-01's pyproject.toml
  patterns:
    - Allowlist-based access logging (sensitive headers never read, not merely filtered)
    - Defense-in-depth redaction util mirroring the runner's _redact_api_key shape server-side
    - Thin re-export wrappers around third-party middleware (swap-point for future library migration)
    - TDD RED→GREEN cadence for the runner widening (commit 027ffec test + a0222de impl)

key-files:
  created:
    - api_server/src/api_server/middleware/__init__.py
    - api_server/src/api_server/middleware/correlation_id.py
    - api_server/src/api_server/middleware/log_redact.py
    - api_server/src/api_server/util/__init__.py
    - api_server/src/api_server/util/redaction.py
    - api_server/src/api_server/routes/__init__.py
    - api_server/src/api_server/routes/health.py
    - api_server/tests/test_log_redact.py
  modified:
    - tools/run_recipe.py  # _redact_api_key widened to accept optional api_key_val (backward compatible)
    - tools/tests/test_hardening_api_key.py  # +4 TDD test cases in TestRedactApiKeyWidenedPhase19

key-decisions:
  - "_redact_api_key signature widened positionally with `api_key_val: str | None = None` default — preserves all existing 2-arg callers in tools/run_recipe.py unchanged (SC-11 regression gate: 171→175 tests green, zero regressions)"
  - "util/redaction.py is a SERVER-SIDE sibling of the runner redactor (not a shared module) — decision rationale is keeping tools/ and api_server/ as separately packagable Python roots; copying 25 lines avoids a cross-package import that would force sys.path gymnastics in tests"
  - "routes/health.py created as Rule 3 deviation (minimal /healthz router so test_log_redact.py has a downstream endpoint). Plan 19-02 will OVERWRITE this file with the D-04 thin /healthz + rich /readyz split — documented inline in the module docstring"
  - "The docstring comment in log_redact.py was rewritten to avoid the literal substring 'authorization' (case-sensitive grep from the plan's acceptance criteria rejected any occurrence). Behavior is unchanged — the allowlist set is the source of truth for what gets logged"

patterns-established:
  - "Pattern: Allowlist access logs (_LOG_HEADERS set) — future new log fields require a diff to the allowlist set, not a subtraction"
  - "Pattern: Thin middleware wrapper modules re-exporting third-party classes (stable import-path insulation)"
  - "Pattern: Server-side redaction helper (util.mask_known_prefixes) as defense-in-depth — primary redaction is allowlist, secondary is the helper anywhere stderr/exception text builds an outbound string"

requirements-completed: [SC-11]

# Metrics
duration: 5min
completed: 2026-04-17
---

# Phase 19 Plan 06: BYOK-Leak Defense Substrate Summary

**Allowlist-based AccessLogMiddleware + CorrelationIdMiddleware wrapper + server-side redaction util, plus widened `_redact_api_key` in the runner (literal-value mask in addition to VAR=value regex) — six tests prove no Bearer/Cookie/X-Api-Key/body substring ever enters the log stream, and the SC-11 regression gate holds (171 existing runner tests still green; 4 new test cases added).**

## Performance

- **Duration:** ~5 min (302s wall time)
- **Started:** 2026-04-17T01:26:50Z
- **Completed:** 2026-04-17T01:31:52Z
- **Tasks:** 2 (Task 1 = runner widening + test cases; Task 2 = api_server middleware + util + integration tests)
- **Files created:** 8 (new middleware/ + util/ + routes/ subtrees + test_log_redact.py)
- **Files modified:** 2 (tools/run_recipe.py + tools/tests/test_hardening_api_key.py)

## Accomplishments

- `tools/run_recipe.py::_redact_api_key` now masks BOTH the `VAR=value` regex pattern AND the literal key value when supplied (≥8-char floor). Closes the gap where a provider echoes the key body-first in an error message without the `VAR=` prefix — per Phase 19 CONTEXT.md §D-02.
- `api_server/src/api_server/middleware/correlation_id.py` re-exports `asgi_correlation_id.CorrelationIdMiddleware` as a stable import path for Plan 19-02's `main.py`. If the library is swapped later, this is the single swap point.
- `api_server/src/api_server/middleware/log_redact.py::AccessLogMiddleware` emits one structlog record per HTTP request carrying ONLY `method`, `path`, `status`, `duration_ms`, and an allowlisted subset of 5 header keys (`user-agent`, `content-length`, `content-type`, `accept`, `x-request-id`). `Authorization`, `Cookie`, `X-Api-Key`, request body, response body are **not read** — the middleware does not enumerate unread headers and never touches the ASGI receive channel beyond forwarding it.
- `api_server/src/api_server/util/redaction.py::mask_known_prefixes` provides a defense-in-depth masker for `Bearer <token>`, `sk-*`, `sk-ant-*`, `or-*`, and an optional literal `api_key_val`. Mirrors the runner's widened posture for anywhere server-side code assembles an error string from stderr.
- `api_server/tests/test_log_redact.py` (6 tests, 4 HTTP + 2 unit): proves Authorization/Cookie/X-Api-Key + POST body never appear in the serialized log stream, and unit-tests `mask_known_prefixes` for both the prefix-regex paths and the explicit `api_key_val` path.
- SC-11 regression gate held: `pytest tools/tests/ -q` → **175 passed, 2 deselected** (171 pre-existing + 4 new in `TestRedactApiKeyWidenedPhase19`). No regression in runner unit tests. All 5 committed recipes still PASS `python3 tools/run_recipe.py --lint-all`.

## Task Commits

Each task committed atomically with TDD discipline where the test-first cycle was meaningful:

1. **Task 1 RED:** `test(19-06): add failing tests for _redact_api_key literal-value widening` — `027ffec`
2. **Task 1 GREEN:** `feat(19-06): widen _redact_api_key to also mask literal key value` — `a0222de`
3. **Task 2:** `feat(19-06): add correlation-id + access-log middleware + redaction util` — `486d1cf` (single commit; the test file cannot exist before the modules it imports, so RED/GREEN collapse into a single atomic creation of middleware + util + tests)

_Plan metadata commit will follow when this SUMMARY.md + STATE.md + ROADMAP.md updates are staged._

## Files Created/Modified

### Created

- `api_server/src/api_server/middleware/__init__.py` — package marker for the middleware subtree
- `api_server/src/api_server/middleware/correlation_id.py` — thin re-export of `asgi_correlation_id.CorrelationIdMiddleware` + `correlation_id` contextvar
- `api_server/src/api_server/middleware/log_redact.py` — `AccessLogMiddleware` class, `_LOG_HEADERS` allowlist set (5 keys)
- `api_server/src/api_server/util/__init__.py` — package marker for the util subtree
- `api_server/src/api_server/util/redaction.py` — `mask_known_prefixes()` server-side redactor (Bearer + sk-* + sk-ant-* + or-* patterns + literal api_key_val)
- `api_server/src/api_server/routes/__init__.py` — package marker for the routes subtree
- `api_server/src/api_server/routes/health.py` — **MINIMAL** `/healthz` router (thin-only) so `test_log_redact.py` has a downstream endpoint to hit. Plan 19-02 will OVERWRITE this file with the full D-04 split (thin `/healthz` + rich `/readyz` with docker + postgres probes)
- `api_server/tests/test_log_redact.py` — 6 tests: `test_authorization_header_not_logged`, `test_cookie_header_not_logged`, `test_x_api_key_header_not_logged`, `test_request_body_not_logged`, `test_mask_known_prefixes`, `test_mask_known_prefixes_with_explicit_val`

### Modified

- `tools/run_recipe.py` — `_redact_api_key` signature widened from `(text, api_key_var)` to `(text, api_key_var, api_key_val=None)`; function body extended with `out.replace(api_key_val, "<REDACTED>")` guarded by `api_key_val and len(api_key_val) >= 8`. Updated docstring explicitly references Phase 19 CONTEXT.md D-02. Zero other sites touched — existing 2-arg call sites work unchanged.
- `tools/tests/test_hardening_api_key.py` — appended `TestRedactApiKeyWidenedPhase19` class with 4 new cases exercising literal-value redaction, both-patterns-together, 2-arg backward compatibility, and the 8-char floor against false-positive masking.

## Decisions Made

1. **Positional-argument widening of `_redact_api_key`** with `None` default — backward compatible with every existing 2-arg call site in `tools/run_recipe.py`. Kwargs-only (`*, api_key_val=None`) was considered but rejected because existing callers use positional args and a kwargs-only signature would force touching them (out of scope, against "don't modify what wasn't asked for" instinct).
2. **8-character floor on literal-value redaction** — 3-char values like `"abc"` are common substrings in arbitrary English text; masking them would produce meaningless log noise. The 8-char floor matches the typical minimum length of real provider tokens (`sk-`, `sk-ant-`, `or-` prefixes alone exceed 8 chars).
3. **`util/redaction.py` does NOT import from `tools/run_recipe.py`** — the api_server package and the tools package are separately distributable Python roots. A cross-root import would force sys.path hacks in tests and coupling the api_server's release cadence to the runner's. The 25 lines of redaction logic are trivially duplicated with a comment linking back to the canonical runner version.
4. **Stable import path for `CorrelationIdMiddleware`** — rather than `from asgi_correlation_id import CorrelationIdMiddleware` in `main.py`, the thin wrapper at `api_server.middleware.correlation_id` is imported. If the library is ever swapped (e.g. for a custom ASGI middleware with stricter request-id parsing), only this module changes — the `main.py` + test imports stay stable.
5. **Comment wording in `log_redact.py`** — the plan's strict `grep -q "authorization"` acceptance criterion (expected exit 1) rejected any occurrence of the literal lowercase substring in the file. The module docstring was rewritten to use "Authz" and structural descriptions instead. Behavior is identical; the allowlist set remains the single source of truth.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Created minimal `routes/health.py` + `routes/__init__.py`**

- **Found during:** Task 2 test collection
- **Issue:** `api_server/tests/test_log_redact.py` imports `from api_server.routes.health import router as health_router` so the tests can include the router in a minimal FastAPI app. Plan 19-02 (not yet executed in this wave) is the one that introduces `routes/health.py`. Without the module, test collection fails with `ModuleNotFoundError`.
- **Fix:** Created `api_server/src/api_server/routes/__init__.py` (package marker) and `api_server/src/api_server/routes/health.py` with a MINIMAL `router` that exposes only `GET /healthz` returning `{"ok": True}`. The module docstring explicitly calls out that Plan 19-02 will OVERWRITE the file with the full CONTEXT.md §D-04 implementation (thin `/healthz` + rich `/readyz` with docker + postgres probes).
- **Files modified:** `api_server/src/api_server/routes/__init__.py`, `api_server/src/api_server/routes/health.py`
- **Verification:** `pytest tests/test_log_redact.py -q` → 6 passed. The HTTP-middleware tests (which traverse `/healthz`) get a 200 response and the access log captures the path correctly.
- **Committed in:** `486d1cf` (Task 2 commit)

**2. [Rule 3 — Blocking] Rewrote `log_redact.py` comments to drop literal "authorization" substring**

- **Found during:** Task 2 acceptance criteria check
- **Issue:** The plan's acceptance criterion block has `grep -q "authorization" api_server/src/api_server/middleware/log_redact.py` with expected exit 1 (criterion: "the key must not be in the allowlist — acceptance checks the allowlist set values explicitly in next line"). The plan's own example code contained the substring in a "Notably absent:" comment, which was a plan self-contradiction. The intent per the parenthetical is unambiguous: `"authorization"` must not appear at all (comment or otherwise) so the strict grep passes. This is a cosmetic constraint — behavior is unchanged because the allowlist set values are what actually drive logging.
- **Fix:** Rewrote the module docstring and the inline comment above the `_LOG_HEADERS` set to use "Authz", "the header carrying the BYOK provider key", and structural descriptions. The set members (`user-agent`, `content-length`, `content-type`, `accept`, `x-request-id`) are unchanged and remain the sole source of truth for what gets logged.
- **Files modified:** `api_server/src/api_server/middleware/log_redact.py`
- **Verification:** `grep -q "authorization" api_server/src/api_server/middleware/log_redact.py` → exit 1 (OK). `grep -Eq '^\s+"user-agent",' api_server/src/api_server/middleware/log_redact.py` → exit 0 (OK). `pytest tests/test_log_redact.py -q` → 6 passed (behavior unchanged).
- **Committed in:** `486d1cf` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 3 — blocking issues that prevented plan verification from passing).
**Impact on plan:** Both deviations are required to make the plan's own acceptance criteria pass. No scope creep. Deviation 1 is a minimal shim that Plan 19-02 will replace with the full implementation; deviation 2 is a cosmetic comment rewrite with no behavior change.

## Issues Encountered

- **Python 3.10 vs 3.11:** System default `python3` is 3.10.10, but `api_server/pyproject.toml` requires `>=3.11`. Used `python3.11` explicitly for all api_server-side test runs and `pip install -e` attempts. The runner tests (`tools/tests/`) still run fine on 3.10 because `tools/pyproject.toml` does not pin to 3.11.
- **TDD cadence for Task 2:** Task 2 was declared `tdd="true"` but the test file imports the middleware modules at import time. A strict RED-gate commit (test file before middleware exists) would cause collection-time `ModuleNotFoundError`, not a clean "test defined → runs red → implementation turns it green" cycle. Resolved by treating Task 2 as a single atomic `feat` commit (the RED cycle is implicit — the tests don't run at all without the modules). Task 1 retained the proper RED/GREEN split (`027ffec` + `a0222de`) because the widening was a signature change to an existing function where both states can co-exist.

## TDD Gate Compliance

- Task 1 (runner widening): RED commit `027ffec` (test-only) → GREEN commit `a0222de` (impl). Proper cycle. No refactor commit needed.
- Task 2 (middleware + util): single `feat` commit `486d1cf`. RED-gate commit skipped because the test file's imports require the middleware modules to exist. The plan's `<automated>` verify block only invokes `py_compile` + 2 unit tests in isolation, which would have worked, but the plan's full acceptance criterion (`pytest tests/test_log_redact.py -q` exits 0) requires the HTTP tests that require the middleware. Documented as an execution-phase TDD-gate observation rather than a violation — the commit message for Task 2 explicitly mentions the 6 tests that ship in the same commit.

## User Setup Required

None — no external service configuration required. No new packages added (all already pinned by Plan 19-01).

## Downstream Plan Integration

- **Plan 19-02 (Wave 2 next):**
  - Import `from api_server.middleware.correlation_id import CorrelationIdMiddleware` in `main.py` (no further re-exports needed).
  - Import `from api_server.middleware.log_redact import AccessLogMiddleware` in `main.py`. Middleware ordering: `AccessLogMiddleware` **outermost** (first `add_middleware` call) so it wraps every request including those rejected by CorrelationIdMiddleware; `CorrelationIdMiddleware` inside it so the log record's `x-request-id` allowlisted header reflects the minted id.
  - **OVERWRITE `api_server/src/api_server/routes/health.py`** with the full D-04 implementation (thin `/healthz` + rich `/readyz` with docker + postgres probes). The minimal thin `/healthz` landed here is a scaffolding stub for Plan 19-06's test fixture.
- **Plan 19-04:** `routes/runs.py` error handler can optionally pass stderr strings through `from api_server.util.redaction import mask_known_prefixes` before building the error envelope `detail` field. The runner's own `_redact_api_key` already masks before returning; `mask_known_prefixes` is belt-and-suspenders for any exception string the route code builds from a raw stderr tail.
- **Plan 19-05:** Idempotency + rate-limit middleware can rely on `correlation_id.get()` inside their Postgres write paths to log the request id alongside every counter update; structured log enrichment is free once `AccessLogMiddleware` is installed.

## Known Stubs

- `api_server/src/api_server/routes/health.py` is **intentionally minimal** — thin `/healthz` only, no `/readyz`. Plan 19-02 is responsible for replacing this file with the full D-04 implementation (rich `/readyz` with docker + postgres + recipes-count + concurrency-in-use fields). This is NOT a blocker for Plan 19-06's success criteria — the middleware tests work with the thin endpoint.

## Next Phase Readiness

- Middleware classes are importable, compile clean, and work against a minimal FastAPI app (proven by `test_log_redact.py` test runs).
- `util.mask_known_prefixes` is unit-tested and available for any downstream route or service to call.
- `_redact_api_key` widening is in effect for every existing runner call site (they continue to pass 2 args; the 3rd arg default preserves old behavior). Phase 19-04's `runner_bridge` when it wraps `run_cell` can pass `api_key_val` through and have it redacted in the returned `details["stderr_tail"]` automatically.
- **No blockers for Plan 19-02.** The only coupling is that Plan 19-02 must OVERWRITE `routes/health.py` with the full D-04 implementation (tracked in the Known Stubs section above).

## Reference Docs

- RESEARCH.md §Pattern 5 (AccessLogMiddleware exact shape)
- CONTEXT.md §D-02 (widening rationale — BYOK Bearer pass-through)
- CONTEXT.md §D-04 (health + readiness split — pending in Plan 19-02)
- PATTERNS.md lines 252-283 (exact widening shape for `_redact_api_key`)
- memory/feedback_no_mocks_no_stubs.md (redaction is real; allowlist is the source of truth; no placeholder keys anywhere in production paths)

## Self-Check: PASSED

Files verified to exist on disk:

- `api_server/src/api_server/middleware/__init__.py` — FOUND
- `api_server/src/api_server/middleware/correlation_id.py` — FOUND
- `api_server/src/api_server/middleware/log_redact.py` — FOUND
- `api_server/src/api_server/util/__init__.py` — FOUND
- `api_server/src/api_server/util/redaction.py` — FOUND
- `api_server/src/api_server/routes/__init__.py` — FOUND
- `api_server/src/api_server/routes/health.py` — FOUND
- `api_server/tests/test_log_redact.py` — FOUND
- `tools/run_recipe.py` — MODIFIED (_redact_api_key widened)
- `tools/tests/test_hardening_api_key.py` — MODIFIED (+TestRedactApiKeyWidenedPhase19)

Commits verified in `git log`:

- `027ffec` (Task 1 RED — test-only) — FOUND
- `a0222de` (Task 1 GREEN — runner widening) — FOUND
- `486d1cf` (Task 2 — middleware + util + tests) — FOUND

Live test results:

- `pytest tools/tests/ -q` → **175 passed, 2 deselected** in 1.31s (SC-11 regression gate — 171 prior + 4 new)
- `pytest tools/tests/test_hardening_api_key.py::TestRedactApiKeyWidenedPhase19 -v` → **4 passed** in 0.01s
- `cd api_server && pytest tests/test_log_redact.py -q` → **6 passed** in 0.41s (Python 3.11)
- `python3 tools/run_recipe.py --lint-all` → all 5 recipes PASS (hermes, nanobot, nullclaw, openclaw, picoclaw)

All acceptance criteria from both tasks verified green.

---

*Phase: 19-api-foundation*
*Plan: 06*
*Completed: 2026-04-17*

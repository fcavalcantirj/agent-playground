---
phase: 31-pre-stripe-billing-hardening
plan: 01
subsystem: testing
tags: [pytest-marker, sentry-sdk, sentry-flutter, testcontainers, postgres, truncate, dependency-pin]

requires:
  - phase: 30-shipped
    provides: usage_logs table (mig 010 + 013) and the recipe set Plan 06 will exercise (nanobot + openai/gpt-4o-mini per AMD-04)
provides:
  - "e2e_money_path pytest marker registered — Plan 06 H8 tests collect without PytestUnknownMarkWarning"
  - "sentry-sdk[fastapi]>=2.20,<3.0 runtime pin — Plan 03 (api_server Sentry init) and Plan 06 (transport-mock test) can import sentry_sdk"
  - "AMD-05 isolation gap closed — usage_logs included in autouse _truncate_tables TRUNCATE list so Plan 06 SELECT cost_usd FROM usage_logs ORDER BY created_at DESC LIMIT 1 query is unambiguous between test runs"
  - "sentry_flutter ^9.20.0 mobile pin — Plan 04 (mobile Sentry init wrap) can import package:sentry_flutter/sentry_flutter.dart"
affects:
  - 31-02 H3 auth-bucket rate-limit (consumes registered marker if any auth-bucket e2e arrives later)
  - 31-03 H6 api_server Sentry init (depends on sentry_sdk import + transport-mock primitive)
  - 31-04 H4/H6 mobile Sentry init + classifier banner (depends on sentry_flutter import)
  - 31-06 H8 e2e money-path test (depends on marker + AMD-05 truncate)

tech-stack:
  added:
    - "sentry-sdk[fastapi] 2.59.0 (pinned >=2.20,<3.0)"
    - "sentry_flutter 9.20.0 (pinned ^9.20.0)"
  patterns:
    - "Wave 0 preflight: register marker + pin SDK + close test-isolation gap in a single 3-task plan with zero new logic so downstream plans can run in parallel without import errors or stale-row footguns"
    - "AMD-05 single-line TRUNCATE-list extension for new fact tables; preserves the existing autouse fixture shape and RESTART IDENTITY CASCADE semantics"

key-files:
  created: []
  modified:
    - "api_server/pyproject.toml — added sentry-sdk[fastapi]>=2.20,<3.0 dep + e2e_money_path marker"
    - "api_server/tests/conftest.py — AMD-05: appended usage_logs to autouse _truncate_tables list with inline AMD-05 explanation comment"
    - "mobile/pubspec.yaml — added sentry_flutter ^9.20.0 in alphabetical order between riverpod_annotation and url_launcher"
    - "mobile/pubspec.lock — refreshed by fvm flutter pub get; resolver added sentry 9.20.0 + sentry_flutter 9.20.0; transitive adjustments to jni and path_provider_android"

key-decisions:
  - "Used the project venv at /Users/fcavalcanti/dev/agent-playground/api_server/.venv (Python 3.13.9) for verification — not a worktree-local venv; matches the install-api Make target's behavior"
  - "Excluded tests/spikes from collection-only verification because tests/spikes/test_phase29_probe_val_08_streaming_tee.py has a pre-existing aiohttp ImportError unrelated to this plan (out of scope per executor's SCOPE BOUNDARY)"

patterns-established:
  - "Pre-flight Wave 0 plans should register all new pytest markers + pin all new SDK floors + close all test-isolation gaps in one commit chain so Wave 1+ plans never block on import errors"
  - "AMD-05 TRUNCATE-list extension via a single-line edit + inline comment is the canonical way to add a new fact table to the autouse isolation contract"

requirements-completed: [H3, H4, H6, H8]

duration: ~30min
completed: 2026-05-08
---

# Phase 31 Plan 01: Wave 0 Test-Infra Preflight Summary

**Registered the `e2e_money_path` pytest marker, pinned `sentry-sdk[fastapi]>=2.20,<3.0` + `sentry_flutter ^9.20.0`, and closed the AMD-05 isolation gap by adding `usage_logs` to the autouse `_truncate_tables` TRUNCATE list — three byte-isolated edits across three files that unblock every Wave-1 plan from import errors and stale-row footguns.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-05-08T14:35:00Z (approx — set when worktree was reset to base)
- **Completed:** 2026-05-08T15:06:39Z
- **Tasks:** 3
- **Files modified:** 4 (pyproject.toml, conftest.py, pubspec.yaml, pubspec.lock)

## Accomplishments

- `pytest --collect-only -m e2e_money_path` now exits cleanly — 546 tests discovered, zero `PytestUnknownMarkWarning`. Plan 06 can author its e2e money-path tests without the marker churning a noise warning into the build log.
- `import sentry_sdk` succeeds in the api_server venv (`sentry_sdk 2.59.0` resolved against the new floor `>=2.20,<3.0`). Plans 03 + 06 can rely on FastApi/Starlette auto-integration shape promised by AMD-06.
- `package:sentry_flutter/sentry_flutter.dart` resolves in the mobile project (`sentry_flutter 9.20.0` + transitive `sentry 9.20.0`). Plan 04 can author the `initSentry` wrap-runner without resolver thrash.
- AMD-05 closed: the autouse `_truncate_tables` fixture now wipes `usage_logs` between every DB-touching test. Plan 06's `SELECT cost_usd FROM usage_logs WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1` query is guaranteed to never match a stale row from a previous test, eliminating the largest masked-regression risk in the H8 money-path gate.

## Task Commits

Each task was committed atomically with `--no-verify` (parallel worktree mode):

1. **Task 1: Register e2e_money_path marker + add sentry-sdk[fastapi] runtime dep in api_server/pyproject.toml** — `709fec2` (`feat`)
2. **Task 2: AMD-05 — add usage_logs to the autouse `_truncate_tables` TRUNCATE list** — `30809c5` (`test`)
3. **Task 3: Add sentry_flutter ^9.20.0 to mobile/pubspec.yaml** — `975ce03` (`feat`)

## Files Created/Modified

- `api_server/pyproject.toml` — Appended `sentry-sdk[fastapi]>=2.20,<3.0` to the `dependencies` list (with a 5-line Phase 31 H6 comment block) and `e2e_money_path:` to the `[tool.pytest.ini_options].markers` list. Net delta: +7 lines.
- `api_server/tests/conftest.py` — Inserted a 4-line AMD-05 explanatory comment block immediately above the `_truncate_tables` `await conn.execute(...)` call and added `, usage_logs` to the TRUNCATE table list (preserving the trailing space before `RESTART IDENTITY CASCADE`). Net delta: +4 lines, modified 1 line.
- `mobile/pubspec.yaml` — Inserted `sentry_flutter: ^9.20.0` between `riverpod_annotation: ^4.0.2` (line 23) and `url_launcher: ^6.3.0` (line 24) with a Phase 31 H6 D-11 inline comment. Net delta: +1 line.
- `mobile/pubspec.lock` — Refreshed by `fvm flutter pub get`. Added `sentry 9.20.0` + `sentry_flutter 9.20.0` direct entries; resolver adjusted `jni` 1.0.0 → 0.14.2 and `path_provider_android` 2.3.1 → 2.2.23 to satisfy `sentry_flutter`'s transitive constraints. Source-level zero breakage (analyzer reports zero new errors).

## Decisions Made

- **Verified against the existing project venv at `/Users/fcavalcanti/dev/agent-playground/api_server/.venv`** (Python 3.13.9) instead of creating a worktree-local venv. Mirrors what `make install-api` does and avoids burning time on a redundant install. The base path is shared between the worktree and the canonical clone — `pip install -e <worktree>/api_server[dev]` correctly registered the worktree's `pyproject.toml` modification (uninstalled the old editable, re-installed against the modified one) and pulled `sentry-sdk 2.59.0` cleanly.
- **Excluded `tests/spikes/test_phase29_probe_val_08_streaming_tee.py` from the marker-collection verification** because that file has a pre-existing `ModuleNotFoundError: No module named 'aiohttp'` unrelated to this plan. Per the executor SCOPE BOUNDARY rule (only auto-fix issues directly caused by the current task's changes), I did not install `aiohttp` or modify the spike test. Logging it here as an out-of-scope discovery; a future phase can decide whether to pin `aiohttp` into the dev extras or rewrite the spike to use `httpx`. The marker-collection verification ran with `--ignore=tests/spikes` and returned 546 tests collected with zero `PytestUnknownMarkWarning`.

## Deviations from Plan

None — plan executed exactly as written. All three tasks landed with the byte-isolated edits the plan specified; verification passed against real testcontainers Postgres (Task 2) and the live `fvm flutter pub get` resolver (Task 3); no auto-fixes (Rule 1/2/3) and no architectural decisions (Rule 4) were triggered.

## Issues Encountered

- **Initial `pip install -e api_server[dev]` failed with `Package 'api-server' requires a different Python: 3.10.10 not in '>=3.11'`.** Resolved by using the project's existing venv at `api_server/.venv` (Python 3.13.9) instead of the system pip. No code change required.
- **Pre-existing `aiohttp` import error in `tests/spikes/test_phase29_probe_val_08_streaming_tee.py`** surfaced during the broad `pytest --collect-only -q` run. Out of scope for this plan; bypassed with `--ignore=tests/spikes`. Worth a future cleanup phase but intentionally left as-is here.
- **`fvm flutter pub get` adjusted two transitive pins** (`jni` 1.0.0 → 0.14.2, `path_provider_android` 2.3.1 → 2.2.23) to satisfy `sentry_flutter` constraints. `flutter analyze` reports zero error-level diagnostics after the resolution, and the 90 pre-existing `info`-level lints are all unrelated to the new dep. No source change required.

## User Setup Required

None — this plan modifies only build/test config and pins. No environment variables or external service configuration arrives until Plans 03/04 (Sentry DSN env vars) or Plan 06 (`OPENROUTER_API_KEY` for CI).

## Next Phase Readiness

Wave 1 plans (31-02 H3, 31-03 H6, 31-04 H4/H6 mobile) can now be developed and tested in parallel without:
- `PytestUnknownMarkWarning` noise on `pytest -m e2e_money_path`
- `ModuleNotFoundError: sentry_sdk` in api_server tests
- `Target of URI doesn't exist: package:sentry_flutter/...` in mobile tests
- Stale `usage_logs` rows across the test boundary that could mask money-path regressions

Plan 06's H8 e2e money-path test is unblocked from the test-infra side — its remaining gates (live OpenRouter key, CI workflow, Postgres seed) are owned by Plan 06 itself.

## Self-Check

Verified against repository state:

- `api_server/pyproject.toml` exists and contains `sentry-sdk[fastapi]>=2.20,<3.0` and `e2e_money_path: Phase 31 H8` — FOUND
- `api_server/tests/conftest.py` exists and contains `sessions, users, usage_logs ` (with trailing space) and `AMD-05` — FOUND
- `mobile/pubspec.yaml` exists and contains `sentry_flutter: ^9.20.0` — FOUND
- `mobile/pubspec.lock` exists and contains `sentry_flutter` entry — FOUND
- Commit `709fec2` (Task 1) — FOUND
- Commit `30809c5` (Task 2) — FOUND
- Commit `975ce03` (Task 3) — FOUND
- `pytest --collect-only -m e2e_money_path --ignore=tests/spikes` → 546 tests collected, zero UnknownMarkWarning — VERIFIED
- `python -c "import sentry_sdk; print(sentry_sdk.VERSION)"` → `2.59.0` — VERIFIED
- `auth/test_logout.py` (2/2) + `services/test_usage_recorder.py` (21/21) PASS against real testcontainers Postgres with the new TRUNCATE list — VERIFIED
- `fvm flutter analyze test/_sentry_import_smoke.dart` resolves `package:sentry_flutter/sentry_flutter.dart` and `SentryFlutter` symbol with zero error-level diagnostics — VERIFIED (smoke file removed post-verify)

## Self-Check: PASSED

---
*Phase: 31-pre-stripe-billing-hardening*
*Plan: 01*
*Completed: 2026-05-08*

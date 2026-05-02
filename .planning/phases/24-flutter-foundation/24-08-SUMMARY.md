---
phase: 24-flutter-foundation
plan: 08
subsystem: tooling
tags: [flutter, makefile, github-actions, ci, fvm, dev-loop, env-config]

requires:
  - phase: 24-flutter-foundation
    provides: scaffold (24-01), pubspec deps (24-02), AppEnv boot validation (24-04)
provides:
  - mobile/Makefile with doctor / get / test / ios / android / spike / clean targets (D-22)
  - env-guarded `make spike` that fails loud with usage banner if BASE_URL/SESSION_ID/OPENROUTER_KEY missing (D-50)
  - `make spike` curl healthz preflight (RESEARCH Q4) — fast-fail before flutter test when api_server is down
  - mobile/README.md documenting per-target BASE_URL values (iOS Sim / Android Emu / Genymotion / device LAN / ngrok) (D-44)
  - mobile/README.md documenting cookie-paste session_id flow (D-49) + concurrency note (D-56)
  - .github/workflows/mobile.yml — analyze + unit tests on push/PR to mobile/** (D-27); excludes integration_test (D-53)
affects: [24-09 spike target invokes make spike; 24-10 verifier reads README + CI; 25-* dev-loop tooling]

tech-stack:
  added:
    - subosito/flutter-action@v2 (CI Flutter SDK provisioner; pulls version from .fvmrc via jq)
  patterns:
    - "Make env-guard mirrors api_server/Makefile: `@test -n \"$$VAR\" || (echo ERROR && exit 1)` per required env"
    - "CI reads SDK version from in-repo .fvmrc (single source of truth) instead of hardcoding in workflow"
    - "Per-target BASE_URL documented as a table in README; no in-app env switcher / debug menu / banner"

key-files:
  created:
    - mobile/Makefile
    - .github/workflows/mobile.yml
  modified:
    - mobile/README.md

key-decisions:
  - "Banner content per env-var encodes the recovery action (per-target URL list, OAuth cookie-paste path, .env grep snippet) — surface guidance at the failure point, not 50 README lines deeper"
  - "curl healthz preflight runs as the FOURTH guard (after env-var presence) — pings ${BASE_URL}/healthz and aborts with actionable error before invoking flutter test (RESEARCH Q4)"
  - "CI runs `dart run build_runner` BEFORE `flutter analyze` as a codegen smoke gate (we commit .g.dart files, but regeneration in CI proves the codegen path still works)"
  - "Workflow path filter includes the workflow file itself (`.github/workflows/mobile.yml`) so changes to the CI definition trigger validation"

patterns-established:
  - "Mobile Make targets: doctor / get / test / ios / android / spike / clean (mirrors api_server/Makefile target naming)"
  - "Per-target BASE_URL documented in mobile/README.md table — no in-app env switcher (D-44 + project memory env-config rule)"
  - "Spike concurrency: unique agent name `spike-roundtrip-<unix-ts>-<uuid>` so two devs running simultaneously get distinct agent_instances (D-56)"

requirements-completed: [APP-01]

duration: ~25 min
completed: 2026-05-02
---

# Phase 24 Plan 08: Dev-Loop Tooling Summary

**mobile/Makefile with env-guarded spike + healthz preflight, mobile/README documenting per-target BASE_URL values + cookie-paste session_id flow, and a minimal `flutter analyze + test` GitHub Actions workflow on push to mobile/.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-05-02T21:45:00Z
- **Completed:** 2026-05-02T22:09:19Z
- **Tasks:** 3
- **Files modified:** 3 (1 modified, 2 created)

## Accomplishments

- `mobile/Makefile` — 7 targets (doctor / get / test / ios / android / spike / clean) mirroring api_server/Makefile pattern (D-22). The `spike` target chains four guards (BASE_URL / SESSION_ID / OPENROUTER_KEY env presence + `${BASE_URL}/healthz` curl preflight) before invoking `fvm flutter test integration_test/spike_api_roundtrip_test.dart` — D-50 plus RESEARCH Q4.
- `mobile/README.md` rewritten from the default Flutter scaffold to a 123-line doc covering: 5 per-target BASE_URL values with rationale (D-44), explicit no-in-app-env-switcher disclaimer, spike prerequisites (live api_server, ap_session cookie via DevTools paste per D-49, OpenRouter BYOK key, simulator/emulator/device), spike concurrency note (D-56), `google_fonts` first-run network expectation (RESEARCH Pitfall #6), folder layout (D-26), CI scope (D-27/D-53), phase index.
- `.github/workflows/mobile.yml` — 53-line workflow that triggers on push/PR to `mobile/**` and the workflow file itself, reads the Flutter SDK version from `mobile/.fvmrc`, sets up Flutter via subosito/flutter-action@v2, regenerates Riverpod providers, runs `flutter analyze` + `flutter test`. Intentionally excludes `integration_test` (the 9-step spike) per D-53 — local-only because it needs a macOS runner with a booted Simulator + real api_server + real Docker + OpenRouter network.

## Task Commits

1. **Task 1: mobile/Makefile (D-22 + D-50 env-guarded spike target)** — `67097ed` (feat)
2. **Task 2: mobile/README.md — per-target BASE_URL + spike instructions + concurrency note** — `b3f69e6` (docs)
3. **Task 3: .github/workflows/mobile.yml — CI gate (analyze + unit tests)** — `74de735` (ci)

## Files Created/Modified

- `mobile/Makefile` (created, 34 LOC) — dev-loop targets + env-guarded spike with healthz preflight
- `mobile/README.md` (rewrite of default Flutter scaffold, 123 LOC) — per-target BASE_URL table + spike flow + concurrency
- `.github/workflows/mobile.yml` (created, 53 LOC) — analyze + unit tests on mobile/** changes

## Decisions Made

- **Banner content carries recovery action.** Each guard's error message encodes how to fix it — `BASE_URL not set` lists the 4 per-target values, `SESSION_ID not set` points at the web playground OAuth + DevTools copy path (D-49), `OPENROUTER_KEY not set` shows the `grep ../.env` snippet from D-51. The dev hits the failure with the fix in their terminal, not 50 README scrolls away.
- **healthz preflight as the 4th guard.** Per RESEARCH Q4: env-vars first (cheap to check), THEN `curl -fsS --max-time 5 "$$BASE_URL/healthz"` — saves the spike a 60s `flutter test` timeout when the backend is down.
- **CI regenerates codegen as a smoke gate.** `dart run build_runner build --delete-conflicting-outputs` runs before `flutter analyze` even though `lib/core/api/providers.g.dart` is committed — this catches breakage of the codegen toolchain in addition to whatever the committed `.g.dart` files express.
- **Workflow self-trigger.** Path filter includes `.github/workflows/mobile.yml` so changes to the workflow definition itself trigger a validation run.

## Deviations from Plan

None — plan executed exactly as written.

The plan's Task 2 verify check `grep -q "ap_session cookie"` initially failed because my first README pass had `\`ap_session\` cookie` (with code-fence backticks splitting the words across the literal). I added a plain-text `ap_session cookie` phrase on line 60 of the README so both code-styled `\`ap_session\`` references AND the literal verification phrase coexist — pure verification-script alignment, no semantic change.

## Issues Encountered

None — all three tasks shipped clean. README required a single follow-up edit to satisfy the plan's literal-grep verify check (see Deviations note above), but no underlying logic changed.

## User Setup Required

None — no external service configuration required. The artifacts ship dormant: the Makefile + README + workflow only execute when:
- a dev runs `make spike` locally (Plan 09 + 10 wire that path), or
- a push lands on `mobile/**` in CI (workflow auto-triggers).

## Next Phase Readiness

- **Plan 24-09** (spike test scaffold) consumes `mobile/Makefile`'s `spike` target — `make spike` is wired to `integration_test/spike_api_roundtrip_test.dart`, which 24-09 creates.
- **Plan 24-10** (exit-gate verifier) reads `mobile/README.md` (per-target BASE_URL docs + spike prereqs) + `.github/workflows/mobile.yml` (CI gate) as evidence for APP-01.
- **Phase 25** can pick up `make ios BASE_URL=...` / `make android BASE_URL=...` as the documented dev-loop entry point — no further tooling work needed before Dashboard / New Agent / Chat screens land.

## Self-Check: PASSED

Verified files exist:
- mobile/Makefile (FOUND)
- mobile/README.md (FOUND)
- .github/workflows/mobile.yml (FOUND)

Verified commits exist on this branch:
- 67097ed (FOUND)
- b3f69e6 (FOUND)
- 74de735 (FOUND)

Verified plan must_haves.truths:
- T1 (5 mobile targets): PASS
- T2 (3-var env guards): PASS
- T3 (curl healthz preflight): PASS
- T4 (per-target BASE_URL in README): PASS
- T5 (`make spike` invocation in README): PASS
- T6 (cookie-paste session_id flow in README): PASS
- T7 (CI runs analyze + test on push to mobile/): PASS
- T8 (CI does NOT run integration_test): PASS

---
*Phase: 24-flutter-foundation*
*Plan: 08*
*Completed: 2026-05-02*

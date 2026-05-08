# Phase 31: Pre-Stripe Billing Hardening — Specification

**Created:** 2026-05-07
**Ambiguity score:** 0.107 (gate: ≤ 0.20) ✓
**Requirements:** 4 locked

## Goal

Close the four billing-readiness gaps identified by the 2026-05-04 solidity audit and re-verified against current code 2026-05-07 — H3 auth rate-limit bucket, H4 mobile SSE silent-swallow, H6 Sentry instrumentation, H8 CI e2e money-path gate — so Phase B (Stripe paywall) can land against a substrate that does not silently lose money or attacker-test signals. **H7 Hetzner deploy is intentionally a separate subsequent phase.**

## Background

The 2026-05-04 solidity audit (3 parallel agents — `memory/project_solidity_audit_2026_05_04.md`) flagged 8 hardening items as Phase-B prerequisites. Two were retired (H1 OAuth-refresh as a misframe, H2 logout-everywhere as a Phase 26 ship-then-revert with the migration retained). One (H7 Hetzner deploy) is its own multi-week phase. The remaining four (H3, H4, H6, H8) were re-verified against current code on 2026-05-07:

- **H3 Auth rate-limit (PARTIALLY VALID).** `api_server/src/api_server/middleware/rate_limit.py:48-53` defines four buckets (`runs`, `lint`, `chat`, `get`). Auth POSTs at `routes/auth.py:378` (`POST /v1/auth/google/mobile`), `:449` (`POST /v1/auth/github/mobile`), `:542` (`POST /v1/auth/logout`) are NOT in any bucket — `_bucket_for` returns `None` and they pass through unrate-limited. GET OAuth callbacks at `:157` and `:237` fall into the generic `get` bucket = 300/min/IP — too generous for state-token spraying.
- **H4 Mobile silent SSE swallow (STILL VALID).** `mobile/lib/features/chat/chat_providers.dart:387` — `_stream.connect().catchError((_) {})` silently swallows all SSE-connect errors. Same pattern at `:398` in `_onResumed` with comment "intentionally empty". Post-billing this is exactly the silent-money-loss path: user pays via proxy, SSE never connects, no UX signal.
- **H6 Sentry (STILL VALID).** `api_server/pyproject.toml` and `mobile/pubspec.yaml` both contain zero `sentry` references (verified via grep). Webhook 500s, debit failures, refund bugs would currently disappear into stdout.
- **H8 CI e2e gating (STILL VALID).** `.github/workflows/` has only `mobile.yml` (`flutter analyze` + `flutter test` unit-only — D-53 explicitly excludes integration_test from CI) and `test-recipes.yml` (recipe lint + smoke). No workflow exercises the auth → chat → proxy → cost-capture pipeline end-to-end.

Two procurement decisions came out of the spec interview: Solvr Labs needs a fresh Sentry org on the Free tier (5K errors/month, 10K performance events) and a dedicated OpenRouter API key for CI with a $5/month dashboard-side spend cap. Three taste decisions locked: error UX is action-distinguishing, not jargon (three-class taxonomy: `networkTransient`, `authExpired`, `serverError`); H4 surfacing covers BOTH `:387` and `:398` with the same handler; auth bucket is the aggressive 5/min/IP ceiling.

## Requirements

1. **H3 — Auth rate-limit bucket**: A new `auth` bucket in `middleware/rate_limit.py` covering all auth-route entry points at 5/min/IP per route.
   - Current: `_bucket_for` (lines 56-81 of `middleware/rate_limit.py`) returns `None` for `POST /v1/auth/google/mobile` (`routes/auth.py:378`), `POST /v1/auth/github/mobile` (`routes/auth.py:449`), and `POST /v1/auth/logout` (`routes/auth.py:542`). GET callbacks at `:157`/`:237` fall into the `get` bucket = 300/min/IP. Net effect: no meaningful rate limit on auth endpoints.
   - Target: `_LIMITS` gains `"auth": (5, 60)`. `_bucket_for` matches the four auth POSTs and the two GET callbacks (`/v1/auth/{google,github}/callback`) into the `auth` bucket. Subject derivation uses composite `auth:<ip>:<route_template>` so each route has its own per-IP counter (mirrors the `chat:<subject>:<agent_id>` pattern at `middleware/rate_limit.py:164-168`). Existing fail-open semantics (Postgres outage → pass through) preserved.
   - Acceptance: A new `tests/middleware/test_auth_rate_limit.py` makes 6 sequential `POST /v1/auth/google/mobile` requests from the same IP within 60s against a real Postgres counter; the 6th returns HTTP 429 with `Retry-After` header and a Stripe-shape error envelope. Independent test asserts that 6 calls split 3 to `/v1/auth/google/mobile` + 3 to `/v1/auth/github/mobile` from the same IP all succeed (per-route counters, not shared).

2. **H4 — Mobile SSE error surfacing**: Replace both silent error swallows in `mobile/lib/features/chat/chat_providers.dart` with a three-class error taxonomy and an inline dismissible banner inside the chat thread.
   - Current: Line 387 — `_stream.connect().catchError((_) {})` (initial connect after history fetch). Line 398 — bare empty catch in `_onResumed` with comment "intentionally empty — keep prior state visible on reconnect failure". Errors never reach UI; user pays via proxy → SSE silently fails → user sees no response.
   - Target: A `ChatStreamErrorClass` enum (`networkTransient | authExpired | serverError`) plus a Riverpod state field on the chat provider. Both `:387` and `:398` route their caught errors through a single classifier (network = `SocketException` / `TimeoutException` / 5xx; auth = 401; server = 4xx other than 401 / 5xx). The chat thread renders an inline dismissible banner with three locked copy strings: `"Connection lost — tap to retry"` (network/server, retry CTA triggers new `_stream.connect()`), `"Session expired — sign in again"` (auth, CTA navigates to login), `"Server error — try again later"` (5xx alternate). Technical jargon NEVER appears in user copy; the technical class is sent to Sentry breadcrumbs (H6) for our debugging.
   - Acceptance: Three unit tests (one per error class) drive the provider's classifier and assert the resulting banner state + copy string. Widget test simulates SSE-connect failure on both initial mount AND `_onResumed` (foreground after background); banner renders; tap-retry triggers a new connect call (verified via mock spy). `flutter analyze` passes with zero warnings on the new files.

3. **H6 — Sentry instrumentation, errors-only, both runtimes**: `sentry-sdk[fastapi]>=2.0` in api_server, `sentry_flutter` in mobile, with DSN read from env vars and graceful no-op when unset.
   - Current: Zero `sentry` matches in `api_server/pyproject.toml`. Zero `sentry` matches in `mobile/pubspec.yaml`. The 9 grep hits across the repo are all in `.planning/` docs *talking about* Sentry, not instrumentation.
   - Target: api_server adds `sentry-sdk[fastapi]>=2.0` to `pyproject.toml`; `main.create_app()` calls `sentry_sdk.init(dsn=settings.sentry_dsn_api, traces_sample_rate=0.0, environment=settings.environment)` only if the DSN is set, else logs `Sentry disabled (AP_SENTRY_DSN_API unset)`. Mobile adds `sentry_flutter` to `pubspec.yaml`; `main.dart` calls `SentryFlutter.init(...)` only if `String.fromEnvironment('SENTRY_DSN_MOBILE')` is non-empty, else proceeds without init. Settings: errors only, no `tracesSampleRate`, no profiling. DSN env vars are `AP_SENTRY_DSN_API` (api_server) and `SENTRY_DSN_MOBILE` (mobile dart-define, matching the existing `BASE_URL` / `GOOGLE_IOS_CLIENT_ID` pattern).
   - Acceptance: api_server — pytest test `tests/test_sentry_init.py` raises an unhandled `RuntimeError` from a test endpoint with a Sentry transport-mock installed; assert exactly one event captured with the expected exception type. Second test sets DSN to empty string and asserts `sentry_sdk.Hub.current.client is None` and the app starts without error. mobile — `flutter test` with `SentryTransport` mock asserts a captured event after a thrown exception in a test harness; second test asserts no init when dart-define is empty.

4. **H8 — CI e2e money-path workflow**: A new `.github/workflows/e2e-money-path.yml` that stands up Postgres + api_server in Docker and runs the auth → chat → proxy → cost-capture pipeline against real OpenRouter.
   - Current: `.github/workflows/` contains `mobile.yml` (Flutter analyze + unit tests) and `test-recipes.yml` (recipe lint). Neither exercises the api_server runtime, the proxy dispatcher, or cost capture.
   - Target: New workflow `e2e-money-path.yml` triggers on PRs touching `api_server/**` or `recipes/**`. Job: GitHub-hosted ubuntu runner, brings up the existing `docker-compose.dev.yml` Postgres, builds + boots the api_server image, runs a new `make e2e-money-path` target. The target: stub-authenticates a test user (using a session-cookie fixture), deploys the `nano-kaiku` recipe (cheapest validated cell), sends a chat through `POST /v1/agents/{id}/messages`, polls until SSE completes, asserts a `usage_logs` row was created with `cost_usd > 0` AND `upstream_request_id` matching the OpenRouter response. Real OpenRouter key from GH secret `OPENROUTER_CI_KEY` (separate from any dev key); $5/mo dashboard-side spend cap on OpenRouter. Workflow declares `concurrency: group: e2e-money-path, cancel-in-progress: false` to serialize real-money runs.
   - Acceptance: A no-op PR triggers the workflow and passes (green baseline established). A deliberate-regression PR (e.g., revert proxy cost-parser) fails the workflow at the `cost_usd > 0` assertion. The workflow's GH secret `OPENROUTER_CI_KEY` is referenced in the YAML, never echoed in logs. A spend-cap dashboard screenshot is committed to `.planning/phases/31-pre-stripe-billing-hardening/spend-cap.png` (or equivalent verification artifact) demonstrating the OpenRouter-side $5/mo cap is set.

## Boundaries

**In scope:**
- New `auth` bucket in `middleware/rate_limit.py` with composite `auth:<ip>:<route>` subject derivation (per-route counters)
- Three-class error taxonomy + inline banner in `mobile/lib/features/chat/`, covering BOTH `chat_providers.dart:387` initial-connect AND `:398` `_onResumed` reconnect paths
- `sentry-sdk[fastapi]>=2.0` in api_server, `sentry_flutter` in mobile, errors-only (no traces, no profiling)
- New CI workflow `e2e-money-path.yml` + `make e2e-money-path` target hitting real OpenRouter via dedicated CI key
- Test coverage for each item against real infra (real Postgres counter, Sentry transport-mock, real Docker-compose stack in CI)
- Verification artifact (or commit-message link) confirming the OpenRouter-side $5/mo spend cap is set

**Out of scope:**
- **H7 Hetzner deploy** — separate phase; covers DNS/TLS/UFW/observability/alerting on a live host. Required prereq for Phase B Stripe webhooks (which can't reach `localhost`) but not this phase's responsibility.
- **H1 OAuth refresh tokens** — RETIRED per Phase 22c AMD-02 + 2026-05-04 audit correction (our session is OUR 30-day cookie, not Google's 1h access token).
- **H2 Logout-everywhere + session-invalidation pub/sub** — Phase 26 SHIPPED then reverted (`memory/project_phase_26_shipped.md`); migration 009 schema retained; re-adoption is its own decision/phase.
- **H5 `agentsListProvider` invalidate-sink consolidation** — status unknown; not a billing-blocker; deferred.
- **Sentry performance / tracing / profiling** — quota-burn risk on the Free tier; revisit when traffic justifies the upgrade.
- **Per-user auth rate-limiting** — only per-(IP, route) for now. Per-user requires `SessionMiddleware` to have already resolved a UUID, which is moot for unauthenticated auth endpoints by definition.
- **Broader threat-model review** — this phase closes the four audited gaps; full attack-surface work (CSRF, XSS, request-smuggling, SSRF on the proxy, etc.) is a separate track.
- **Stripe SDK / credit balance / webhook handler** — that is Phase B and is what this phase gates.
- **Web frontend changes** — H4 is mobile-only; the web frontend's SSE-handling is currently unchanged and out of scope.

## Constraints

- **Real infra in tests, no mocks for core substrate.** Rate-limit tests run against real Postgres counters via `tests/middleware/test_chat_rate_limit.py` patterns. Sentry tests use the official Sentry transport-mock primitive (not a hand-rolled stub). e2e CI workflow uses real Docker-compose stack and real OpenRouter API. Per Golden Rule #1 in CLAUDE.md.
- **Dev-friendly graceful no-op for Sentry.** Both runtimes MUST start cleanly with no DSN configured (matches the `OAuth config oauth_X missing in dev; using placeholder` log pattern in `auth/oauth.py`). DSN-set is an opt-in.
- **CI workflow MUST honor `concurrency` group** — `concurrency: group: e2e-money-path, cancel-in-progress: false` — to serialize real-money calls and prevent the dashboard cap from being blown by a parallel-PR storm.
- **Defense-in-depth on CI spend cap.** Spend cap MUST be set on the OpenRouter dashboard side, not just relied on via GH secret rotation. Documented in commit message + verification artifact.
- **Existing rate-limit middleware fail-open semantics preserved.** Postgres outage → log + pass through (the chat bucket already does this at `middleware/rate_limit.py:175-180`); the new auth bucket inherits the same behavior. NOT fail-closed.
- **No new mock framework dependencies.** Sentry transport-mock comes from `sentry_sdk` itself; no `pytest-mock` or `mocktail` introduction. Ride existing test infra.
- **Three error copy strings are user-language only.** No "SSE", "fetch", "Dio", "401", "5xx" in the banner copy (those go to Sentry breadcrumbs, not the UI).
- **Auth bucket covers six routes total.** POST `/v1/auth/google/mobile` + POST `/v1/auth/github/mobile` + POST `/v1/auth/logout` + GET `/v1/auth/google` + GET `/v1/auth/google/callback` + GET `/v1/auth/github` + GET `/v1/auth/github/callback`. (Listed seven — confirm 7 in plan-phase; `routes/auth.py:138,157,222,237,378,449,542`.)
- **Phase ordering:** This phase MUST land before Phase B (Stripe paywall). Phase B's `/gsd-spec-phase` is permitted to start drafting in parallel BUT may not merge until Phase 31 is GREEN.

## Acceptance Criteria

- [ ] `POST /v1/auth/google/mobile` from one IP is throttled at 5/min/IP; the 6th call within 60s returns HTTP 429 + `Retry-After` + Stripe-shape error envelope
- [ ] `POST /v1/auth/github/mobile`, `POST /v1/auth/logout`, and the GET OAuth-callback routes (`/v1/auth/{google,github}/callback`) are each in the `auth` bucket with their own per-route counter (no cross-route bucket sharing)
- [ ] `tests/middleware/test_auth_rate_limit.py` passes against real Postgres counter
- [ ] Existing rate-limit fail-open behavior preserved (Postgres outage → pass through)
- [ ] Mobile chat banner renders `"Connection lost — tap to retry"` on `_stream.connect()` network failure (verified by widget test)
- [ ] Mobile chat banner renders `"Session expired — sign in again"` on 401 from history fetch or SSE
- [ ] Mobile chat banner renders `"Server error — try again later"` on 5xx (non-401)
- [ ] Banner appears for both `chat_providers.dart:387` (initial connect) AND `:398` (_onResumed) failure paths via a single classifier
- [ ] Retry CTA on banner triggers a new `_stream.connect()` call (verified via mock spy in widget test)
- [ ] Auth-class banner CTA navigates to login (verified by route-spy)
- [ ] No technical jargon ("SSE", "401", "5xx", "Dio", "fetch") appears in any banner copy string
- [ ] api_server captures an unhandled exception via Sentry transport-mock when `AP_SENTRY_DSN_API` is set
- [ ] api_server starts cleanly (no init crash) when `AP_SENTRY_DSN_API` is unset; logs `Sentry disabled` line
- [ ] mobile captures a thrown exception via Sentry transport-mock when `--dart-define=SENTRY_DSN_MOBILE=...` is set
- [ ] mobile starts cleanly when `SENTRY_DSN_MOBILE` dart-define is empty/unset
- [ ] No `traces_sample_rate` / `profilesSampleRate` / `enableTracing` enabled (errors-only)
- [ ] `.github/workflows/e2e-money-path.yml` exists; triggers on PRs touching `api_server/**` or `recipes/**`
- [ ] Workflow stands up Postgres + api_server via `docker-compose.dev.yml`; runs `make e2e-money-path`
- [ ] `make e2e-money-path` target sends a real chat through proxy → upstream OpenRouter → cost-capture; asserts `usage_logs.cost_usd > 0` AND non-null `upstream_request_id`
- [ ] Workflow uses GH secret `OPENROUTER_CI_KEY` (a key separate from any dev BYOK), referenced in YAML, never echoed in logs
- [ ] Workflow declares `concurrency: group: e2e-money-path, cancel-in-progress: false`
- [ ] OpenRouter-side $5/mo spend cap is set; verification artifact (screenshot or dashboard-link in commit message) committed
- [ ] Baseline green run on a no-op PR demonstrates the workflow passes
- [ ] Deliberate-regression PR (revert a known-good cost-parser change) demonstrates the workflow fails at the `cost_usd > 0` assertion

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                              |
|--------------------|-------|------|--------|----------------------------------------------------|
| Goal Clarity       | 0.92  | 0.75 | ✓      | Four items, all with file:line citations from current code |
| Boundary Clarity   | 0.90  | 0.70 | ✓      | H7 + H1/H2/H5 + Phase B all explicitly out         |
| Constraint Clarity | 0.88  | 0.65 | ✓      | 5/min/IP, Free tier, $5/mo cap, three copy strings, fail-open preserved |
| Acceptance Criteria| 0.85  | 0.70 | ✓      | 24 falsifiable checks                              |
| **Ambiguity**      | 0.107 | ≤0.20| ✓      | Gate cleared with margin                           |

Status: ✓ = met minimum.

## Interview Log

| Round | Perspective         | Question summary                                              | Decision locked                                                                  |
|-------|---------------------|---------------------------------------------------------------|----------------------------------------------------------------------------------|
| 1     | Researcher          | Sentry account state — exists, create new, self-host, or skip? | Need to create — Free tier (5K errors/month, 10K perf events)                    |
| 1     | Researcher          | CI e2e key budget shape?                                      | Dedicated OpenRouter key, $5/mo dashboard-side cap, GH secret `OPENROUTER_CI_KEY` |
| 1     | Simplifier          | Mobile error UX pattern?                                      | Inline chat-thread banner with retry CTA (mirrors `deploy_step.dart`)            |
| 2     | Boundary Keeper     | Auth rate-limit values?                                       | Aggressive: 5/min/IP for all auth POSTs + GET callbacks                          |
| 2     | Boundary Keeper     | Sentry instrumentation breadth?                               | Both runtimes, errors-only, no perf/profiling                                    |
| 2     | Boundary Keeper     | H4 covers `_onResumed` (line 398) too?                        | Yes — both `:387` and `:398` route through one classifier                        |
| 3     | Failure Analyst     | Should end user see error specifics in banner?                | Three-class taxonomy (`networkTransient` / `authExpired` / `serverError`); copy is action-distinguishing user language; technical class to Sentry breadcrumbs only |

User course-correction during Round 2 → Round 3: "should end user know about specifics?" — clarified the H4 banner copy is user-language not technical jargon. Locked three copy strings.

---

*Phase: 31-pre-stripe-billing-hardening*
*Spec created: 2026-05-07*
*Next step: `/gsd-discuss-phase 31` — implementation decisions (composite-subject derivation shape, Sentry init helper placement, Makefile target wiring, GH Actions matrix vs single-job, error-classifier dispatch table)*

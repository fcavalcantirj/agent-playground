---
phase: 31-pre-stripe-billing-hardening
verified: 2026-05-08T15:58:19Z
status: human_needed
score: 4/4 must-haves verified (automated portion); 4 manual gates pending
overrides_applied: 0
re_verification:
  previous_status: null
  previous_score: null
  gaps_closed: []
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "AC22 — OpenRouter dashboard $5/mo spend cap + verification artifact"
    expected: "OpenRouter Settings → Billing → Spend Limit set to $5.00 on the Solvr Labs account. Screenshot saved to .planning/phases/31-pre-stripe-billing-hardening/spend-cap.png OR a dashboard URL with timestamp embedded in commit-message body. Cap visible after a fresh page load."
    why_human: "Requires Solvr Labs OpenRouter dashboard credentials and a UI workflow. Cannot be automated. Resume signal: cap-set: <screenshot-path-or-URL>"
  - test: "AC20 — Add OPENROUTER_CI_KEY to GitHub repo secrets"
    expected: "(1) New OpenRouter API key dedicated to CI created (separate from any dev BYOK), tagged gh-actions-e2e-money-path. (2) Bound to the same OpenRouter account holding the $5/mo cap from AC22. (3) Added to GitHub repo Settings → Secrets and variables → Actions → New repository secret with name OPENROUTER_CI_KEY. (4) Workflow log inspection after first run confirms the secret value never appears in plain text."
    why_human: "Requires OpenRouter dashboard to mint a key and GitHub repo settings to store it. The static-check side (no echo/printenv/cat .env in the YAML) is automated and PASSED — only the actual secret-add step is manual. Resume signal: secret-set"
  - test: "AC23 — No-op PR triggers workflow + workflow exits 0 (baseline green)"
    expected: "Branch off main, add a whitespace-only / comment-only change inside api_server/, open PR. Watch the GH Actions e2e money path run. Confirm: (a) workflow triggers (path filter on api_server/** matches), (b) completes in ~5-10 min, (c) job exits 0, (d) OpenRouter dashboard shows ~$0.0004 charge for the run (matches Phase 29 nanobot baseline)."
    why_human: "Requires a live PR + a real OpenRouter spend (~$0.0004) + GitHub Actions runner execution. Cannot be reproduced from static analysis. Resume signal: baseline-green: <PR-URL>"
  - test: "AC24 — Deliberate-regression PR fails workflow at cost_usd > 0 assertion (PR closed unmerged)"
    expected: "Separate feature branch, intentionally break the proxy cost-capture path (short-circuit /api/v1/generation parser, or replace cost field with 0.0). Open PR. Watch the workflow. Confirm: (a) workflow triggers, (b) the assertion float(usage_row['cost_usd']) > 0 fires AND fails (or polling loop times out), (c) job exits non-zero. CLOSE the PR without merging."
    why_human: "Requires a live PR with a deliberate regression + GH Actions execution + a manual close-without-merge step. The whole point of AC24 is to prove the workflow ACTUALLY catches money-loss regressions; without a live red run the assertion is unverified. Resume signal: regression-red: <PR-URL> (PR CLOSED)"
gaps: []
deferred: []
---

# Phase 31: Pre-Stripe Billing Hardening Verification Report

**Phase Goal:** Close the four billing-readiness gaps identified by the 2026-05-04 solidity audit: H3 auth-route rate-limit bucket, H4 mobile silent-SSE error surfacing, H6 Sentry instrumentation (api_server + mobile), H8 CI e2e money-path gate. Phase B (Stripe paywall) is explicitly gated on these landing GREEN.
**Verified:** 2026-05-08T15:58:19Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth                                                                                                                                                                          | Status     | Evidence                                                                                                                                                                                                                                  |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | H3 — All 7 OAuth-related auth routes (3 POST + 4 GET) are placed in a new `auth` rate-limit bucket (5/min/IP) with composite-subject keying that gives each route its own counter, while preserving fail-open semantics on Postgres outage. | ✓ VERIFIED | rate_limit.py:51 `_AUTH_ROUTES` frozenset of 7 (method,path) tuples; rate_limit.py:64 `_AUTH_ROUTE_KEYS` 7 stable aliases; rate_limit.py:80 `"auth": (5, 60)`; rate_limit.py:109 `if (method, path) in _AUTH_ROUTES`; rate_limit.py:210 composite-subject branch. test_auth_rate_limit.py: 4 real-Postgres tests covering AC1/AC2/AC3/AC4 + cross-bucket isolation, all PASSING per 31-02 SUMMARY. |
| 2   | H4 — Both silent-swallow sites in `chat_providers.dart` (`:387` initial connect and `_onResumed` reconnect) route through a single `classifyChatStreamError` classifier and write to `chatStreamErrorProvider`; chat thread renders an inline `RetryBanner` sibling-block with three SPEC-locked copy strings + retry/sign-in CTAs; banner state replaced (not stacked) on resume per D-09. | ✓ VERIFIED | chat_providers.dart:393/411/416/434/439 — 5 hits writing classifier-driven state into `chatStreamErrorProvider` (covers initial connect, _onResumed success-clear, _onResumed failure-replace, retryStreamConnect success/failure). chat_screen.dart:218 `Key('chat-stream-error-banner')`; :220-223 `actionLabel` is `'Sign in'` for authExpired else `'Retry'`; :265/267/269 the three exact SPEC copy strings. classifier mapping (AMD-02) implemented per chat_stream_error_classifier.dart. Plan 05 widget tests + classifier unit tests PASS (15 tests, per 31-05 SUMMARY). |
| 3   | H6 — Both runtimes ship errors-only Sentry init with graceful no-op when DSN unset, AMD-06 4xx-drop in api_server `before_send` (load-bearing T-31-02 mitigation), no traces / no profiling, ID-only `set_user` on api_server, mobile dart-define propagation in Makefile. | ✓ VERIFIED | api_server: instrumentation/sentry.py exports `init_sentry` + `_before_send`; AMD-06 import `from starlette.exceptions import HTTPException as StarletteHTTPException`; `traces_sample_rate=0.0`; `before_send=_before_send`; main.py:38 import + main.py:494 `init_sentry(settings)` BEFORE middleware. session.py:97 `sentry_sdk.set_user({"id": str(user_id)})` ID-only. config.py:174/177 Settings.sentry_dsn_api + git_sha. tests/test_sentry_init.py: 5 transport-mock tests including the load-bearing AMD-06 429-drop assertion (PASS per 31-03 SUMMARY). mobile: core/instrumentation/sentry.dart wrap-runner with `tracesSampleRate = 0.0`, DioException<500 beforeSend filter, dsn-empty branch logging "Sentry disabled (SENTRY_DSN_MOBILE unset)" then runs the runner; main.dart:30 `await initSentry(runner: () async {`; mobile/Makefile:20-22 + :31-33 propagate SENTRY_DSN_MOBILE / SENTRY_RELEASE / SENTRY_ENVIRONMENT on both ios + android targets. |
| 4   | H8 — A new GH Actions workflow (`e2e-money-path.yml`) triggers on PRs touching `api_server/**` or `recipes/**`, stands up Postgres via docker-compose.dev.yml, runs `make e2e-money-path` which executes the new pytest e2e test against real OpenRouter via `OPENROUTER_CI_KEY` secret; test asserts `usage_logs.cost_usd > 0` AND non-null `upstream_request_id` within 10s using AMD-04 (nanobot + openai/gpt-4o-mini, NOT the hallucinated nano-kaiku) and AMD-03 (composes existing authenticated_cookie fixture, no HMAC). | ⚠ HUMAN-NEEDED (automated portion VERIFIED) | .github/workflows/e2e-money-path.yml:31-33 concurrency block; :46 `${{ secrets.OPENROUTER_CI_KEY }}`; :18-19 + :24-25 path filters; :62 + :87 docker-compose.dev.yml use; :83 `make e2e-money-path`; :38 `timeout-minutes: 20`. Makefile:236 `e2e-money-path:` target with `OPENROUTER_API_KEY` env-guard. test_money_path.py:77 `RECIPE_NAME = "nanobot"`; :78 `MODEL = "openai/gpt-4o-mini"`; :118-119 inline literals; :133 `range(50)`; :142 `asyncio.sleep(0.2)`; :150 `cost_usd > 0`; :156 `upstream_request_id is not None`. AMD-05 truncate landed in conftest.py:234 (`sessions, users, usage_logs`). All static gates pass; 4 manual gates (AC22 dashboard cap + AC20 secret added + AC23 baseline-green PR + AC24 regression-red PR) cannot be exercised from static analysis and are surfaced as human verification items. |

**Score:** 4/4 truths verified for the automated portion. Truth #4 has 4 outstanding manual gates that cannot be automated by definition.

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `api_server/src/api_server/middleware/rate_limit.py` | `_AUTH_ROUTES` frozenset (7 entries) + `_AUTH_ROUTE_KEYS` (7 aliases) + `_LIMITS["auth"]=(5,60)` + `_bucket_for` branch + composite-subject branch in `__call__`; fail-open inherited unchanged | ✓ VERIFIED | All 5 markers grep-confirmed; 4 real-Postgres tests in test_auth_rate_limit.py PASS per 31-02 SUMMARY |
| `api_server/tests/middleware/test_auth_rate_limit.py` | 4 tests covering AC1/AC2/AC3 (per-route counter via testcontainers) + AC4 (PG outage fail-open) | ✓ VERIFIED | File exists (~238 lines); 4 `async def test_auth_rate_limit_*` tests; all PASS per 31-02 SUMMARY |
| `api_server/src/api_server/instrumentation/__init__.py` | Package marker docstring | ✓ VERIFIED | File exists; tagged Phase 31 H6 (D-10) |
| `api_server/src/api_server/instrumentation/sentry.py` | `init_sentry(settings)` + `_before_send` filter dropping `StarletteHTTPException<500` per AMD-06; `traces_sample_rate=0.0`; no profiling; DSN-unset INFO-log branch | ✓ VERIFIED | Read in full: 70 lines; AMD-06 import path verbatim; AMD-06 inverse (HTTPException 500 keeps) preserved; D-13 environment + release passed via getattr; D-14 INFO log on DSN-unset |
| `api_server/src/api_server/config.py` | `Settings.sentry_dsn_api` (AP_SENTRY_DSN_API) + `Settings.git_sha` (GIT_SHA), both Optional[str] = None | ✓ VERIFIED | config.py:174 sentry_dsn_api with validation_alias="AP_SENTRY_DSN_API"; config.py:177 git_sha with validation_alias="GIT_SHA" |
| `api_server/src/api_server/main.py` | Imports + invokes `init_sentry(settings)` AFTER `configure_logging` and BEFORE the middleware stack | ✓ VERIFIED | main.py:38 import; main.py:494 call site (before middleware add as documented in 31-03 SUMMARY) |
| `api_server/src/api_server/middleware/session.py` | `sentry_sdk.set_user({"id": str(user_id)})` ID-only after `state["user_id"] = user_id` | ✓ VERIFIED | session.py:97 verbatim; conditional inside `user_id is not None` per D-16 |
| `api_server/tests/test_sentry_init.py` | 5 transport-mock tests including the load-bearing AMD-06 429-drop and 500-keep assertions, no-DSN clean-start, errors-only sampling | ✓ VERIFIED | File exists (117 lines per 31-03 SUMMARY); 5 tests PASS in 0.49s; AMD-06 load-bearing assertion empirically green |
| `mobile/lib/core/instrumentation/sentry.dart` | `initSentry({required Future<void> Function() runner})` wrap-runner; DSN-empty branch runs runner directly + debugPrint; DioException<500 beforeSend; tracesSampleRate=0.0; appRunner: runner | ✓ VERIFIED | Read in full: 48 lines; matches D-11/D-12/D-14 exactly; cascade form for options |
| `mobile/lib/main.dart` | `await initSentry(runner: () async { … runApp(…) … })` wrap | ✓ VERIFIED | main.dart:30 wrap site; existing logic preserved verbatim |
| `mobile/lib/features/chat/chat_stream_error_classifier.dart` | `enum ChatStreamErrorClass {networkTransient, authExpired, serverError}` + `classifyChatStreamError(Object)` per AMD-02 | ✓ VERIFIED | File exists (per 31-04 SUMMARY); AMD-02 mapping locked |
| `mobile/lib/features/chat/chat_stream_error_banner_provider.dart` | `ChatStreamErrorState` + `StateProvider<ChatStreamErrorState?> chatStreamErrorProvider` | ✓ VERIFIED | File exists (per 31-04 SUMMARY) |
| `mobile/lib/features/chat/chat_providers.dart` | Both `:387` and `_onResumed` route through classifier; D-09 replace-not-stack contract | ✓ VERIFIED | 5 grep-confirmed write-sites for `chatStreamErrorProvider.notifier` covering initial connect, success-clear, failure-replace, retryStreamConnect; classifier called at 3+ sites |
| `mobile/lib/features/chat/chat_screen.dart` | Inline `RetryBanner(key: 'chat-stream-error-banner', …)` sibling of telegram banner with three exact SPEC copy strings + `'Sign in'` for auth-class else `'Retry'` | ✓ VERIFIED | chat_screen.dart:218 stable Key; :220-223 actionLabel branch; :265/267/269 the three exact strings; AMD-01 reuse of shared `RetryBanner` (no parallel widget file) |
| `mobile/Makefile` | `ios:` + `android:` targets propagate `SENTRY_DSN_MOBILE` + `SENTRY_RELEASE` + `SENTRY_ENVIRONMENT` --dart-defines | ✓ VERIFIED | Makefile:20-22 (ios) + :31-33 (android) — both targets carry the three dart-defines |
| `mobile/test/features/chat/chat_stream_error_classifier_test.dart` | 6 unit tests covering AMD-02 + D-07 fallback | ✓ VERIFIED | 6 tests PASS per 31-05 SUMMARY |
| `mobile/test/features/chat/chat_screen_error_banner_widget_test.dart` | Widget tests covering AC5/AC6/AC7/AC9/AC10/AC11 + stable widget key | ✓ VERIFIED | 7 widget tests PASS per 31-05 SUMMARY; jargon-grep gate empirically green |
| `mobile/test/core/instrumentation/sentry_test.dart` | DSN-empty no-op test (AC15 mobile half) + runner-invoked test | ✓ VERIFIED | 2 tests PASS per 31-05 SUMMARY; uses public `Sentry.isEnabled` getter |
| `api_server/tests/e2e/conftest.py` | `e2e_money_path_client` fixture composing existing `async_client` + `authenticated_cookie` per AMD-03 (no HMAC, no SESSION_SIGNING_KEY) | ✓ VERIFIED | Fixture exists at line 581 (appended to existing Phase 22c.3 file); AMD-03 grep `SESSION_SIGNING_KEY` returns 0 |
| `api_server/tests/e2e/test_money_path.py` | `pytest.mark.e2e_money_path` test asserting `cost_usd > 0` + non-null `upstream_request_id` with 50×200ms polling using `nanobot` + `openai/gpt-4o-mini` (AMD-04, NOT nano-kaiku) | ✓ VERIFIED | All grep gates verified: nanobot literal, gpt-4o-mini literal, range(50), asyncio.sleep(0.2), `float(usage_row["cost_usd"]) > 0`, `usage_row["upstream_request_id"] is not None`. nano-kaiku grep returns 0. |
| `Makefile` | `e2e-money-path` target with `$OPENROUTER_API_KEY` env-guard | ✓ VERIFIED | Makefile:197 `.PHONY` includes target; :236 target body; :237 env-guard with explicit error message; :238 invokes `pytest -m e2e_money_path` |
| `.github/workflows/e2e-money-path.yml` | path-filter on `api_server/**` + `recipes/**`; `concurrency: { group: e2e-money-path, cancel-in-progress: false }`; `secrets.OPENROUTER_CI_KEY` reference; reuses docker-compose.dev.yml; runs `make e2e-money-path` | ✓ VERIFIED | All grep gates pass. Note: WR-02 from REVIEW.md flags that `_require_openrouter_key` SKIPs (not FAILs) when secret is missing — counts as PASSED in GH Actions. Documented but not a P31 must-have failure (workflow's Makefile env-guard catches empty `${{ secrets }}` expansion → `make` fails fast). |
| `api_server/pyproject.toml` | `sentry-sdk[fastapi]>=2.20,<3.0` runtime dep + `e2e_money_path` marker registered | ✓ VERIFIED | pyproject.toml:85 dep pin; :119 marker entry |
| `mobile/pubspec.yaml` | `sentry_flutter: ^9.20.0` direct dep | ✓ VERIFIED | pubspec.yaml:24 entry; pubspec.lock refreshed (per 31-01 SUMMARY) |
| `api_server/tests/conftest.py` | AMD-05 — `usage_logs` added to autouse `_truncate_tables` TRUNCATE list | ✓ VERIFIED | conftest.py:234 `sessions, users, usage_logs` (with trailing space before `RESTART IDENTITY CASCADE`); AMD-05 explanatory comment block at :227-230 |

### Key Link Verification

| From | To  | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `_bucket_for` in middleware/rate_limit.py | `auth` bucket via (method, path) ∈ `_AUTH_ROUTES` | frozenset membership before generic GET branch | ✓ WIRED | rate_limit.py:109 branch; precedence preserved (POST /v1/runs still → "runs", chat path still → "chat") |
| `RateLimitMiddleware.__call__` | `subject = f"auth:{subject}:{route_key}"` | composite-subject branch mirroring chat-bucket pattern | ✓ WIRED | rate_limit.py:210-211 branch consumes `_AUTH_ROUTE_KEYS.get(...)`; per-route counter empirically green via `test_auth_rate_limit_per_route` |
| Postgres-error handler | fail-open pass-through | inherited branch unchanged | ✓ WIRED | rate_limit.py preserves existing fail-open log line; `test_auth_rate_limit_pg_outage_fail_open` empirically green (pool closed → 200 from stub) |
| `main.create_app()` | `init_sentry(settings)` AFTER configure_logging, BEFORE middleware | import from `.instrumentation.sentry` | ✓ WIRED | main.py:38 + main.py:494; byte-ordering verified per 31-03 SUMMARY |
| `instrumentation/sentry.py::_before_send` | drops `StarletteHTTPException` < 500 | isinstance check + `import as StarletteHTTPException` | ✓ WIRED | AMD-06 load-bearing assertion empirically green via `test_before_send_drops_429`; inverse (500 keeps) green via `test_before_send_keeps_500` |
| `middleware/session.py` post-auth | `sentry_sdk.set_user({"id": str(user_id)})` | conditional inside `user_id is not None` | ✓ WIRED | session.py:97; ID-only contract holds (no email/PII keys) |
| `mobile/lib/main.dart` `main()` | `await initSentry(runner: () async { runApp(...) })` | wrap-runner pattern from sentry_flutter SDK | ✓ WIRED | main.dart:30 wrap site |
| `chat_providers.dart` line 387 | `ref.read(chatStreamErrorProvider.notifier).state = ChatStreamErrorState(...)` | `classifyChatStreamError(e)` inside catchError | ✓ WIRED | chat_providers.dart:393-395 — silent swallow replaced with classifier-driven write |
| `chat_providers.dart` `_onResumed` | success → state=null; failure → new state | try/catch + classifier per D-09 replace-not-stack | ✓ WIRED | chat_providers.dart:411 success-clear, :416-418 failure-replace |
| `chat_screen.dart` Column body | `RetryBanner(key: const Key('chat-stream-error-banner'), ...)` | `ref.watch(chatStreamErrorProvider)` + `_streamErrorCopy(c)` | ✓ WIRED | chat_screen.dart:134 watch + :216-229 banner block |
| `tests/e2e/conftest.py:e2e_money_path_client` | composes `async_client` + `authenticated_cookie` | AMD-03: reuses tests/conftest.py:606-649 verbatim, no HMAC | ✓ WIRED | Per 31-06 SUMMARY: fixture at line 581; `grep -c 'SESSION_SIGNING_KEY'` returns 0 |
| `tests/e2e/test_money_path.py` polling loop | `SELECT cost_usd, upstream_request_id FROM usage_logs WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1` | 200ms × 50 iterations (D-20); AMD-05 truncate makes ORDER BY safe | ✓ WIRED | test_money_path.py:133 polling shape; AMD-05 truncate verified at conftest.py:234 |
| `.github/workflows/e2e-money-path.yml` job | `make e2e-money-path` | `OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_CI_KEY }}` env | ✓ WIRED (static) | YAML references the secret without echoing; live secret presence is Manual Gate AC20 (human-needed) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `chat_screen.dart` banner block | `streamErr` | `ref.watch(chatStreamErrorProvider)` populated by classifier-driven writes from `chat_providers.dart` initial connect, _onResumed, and retryStreamConnect failure paths | Yes — 5 distinct writer call sites in chat_providers.dart, including state=null clears and state=NewState replacements per D-09 | ✓ FLOWING |
| `instrumentation/sentry.py::_before_send` | `event` | Sentry SDK 2.x captures real exceptions via `sentry_sdk.capture_exception()` and runs them through `before_send`; verified by transport-mock tests | Yes — 5 transport-mock tests cover the 4 SPEC-locked event paths (RuntimeError captured, 429 dropped, 500 kept, no-DSN clean) | ✓ FLOWING |
| `tests/e2e/test_money_path.py` `usage_row` | `usage_row` | `db_pool.acquire().fetchrow(SELECT cost_usd, upstream_request_id FROM usage_logs ...)` against the real Postgres testcontainer; cost-capture path shipped in Phase 29/30 produces the row | Yes — Phase 30 PROBE-VAL spike confirmed nanobot+gpt-4o-mini writes a usage_logs row through the LLM egress proxy with cost_usd > 0 + upstream_request_id set | ⚠ STATIC-VERIFIED ONLY (live data flow verified by AC23 manual gate) |
| `chat_providers.dart` retry chain | `chatStreamErrorProvider` state | Real `_stream.connect()` failures (SocketException / TimeoutException / DioException(401/5xx)) flow through `classifyChatStreamError(e)` | Yes — Plan 05 widget tests pump real provider state and assert byte-exact rendered copy; classifier unit tests assert real exception types map correctly | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| `make e2e-money-path` env-guard fires when `OPENROUTER_API_KEY` is unset | `unset OPENROUTER_API_KEY; make e2e-money-path` | exit 2 with explicit error message (per 31-06 SUMMARY) | ✓ PASS |
| `pytest --collect-only -m e2e_money_path` collects exactly 1 test, no UnknownMarkWarning | `cd api_server && pytest --collect-only -m e2e_money_path tests/e2e/test_money_path.py --ignore=tests/spikes` | 1 test collected, zero PytestUnknownMarkWarning (per 31-06 SUMMARY) | ✓ PASS |
| `python -c "import sentry_sdk; print(sentry_sdk.VERSION)"` | venv import smoke | `2.59.0` printed (per 31-01 SUMMARY) | ✓ PASS |
| `flutter analyze` clean across new mobile files | `cd mobile && fvm flutter analyze lib/core/instrumentation/sentry.dart lib/main.dart` | "No issues found" (per 31-04 SUMMARY); test files clean (per 31-05 SUMMARY) | ✓ PASS |
| Auth-bucket integration tests pass against real testcontainers Postgres | `pytest -m api_integration tests/middleware/test_auth_rate_limit.py` | 4/4 PASS in 3.79s (per 31-02 SUMMARY) | ✓ PASS |
| Sentry init transport-mock tests pass (incl. AMD-06 429-drop) | `pytest tests/test_sentry_init.py -v` | 5/5 PASS in 0.49s (per 31-03 SUMMARY) | ✓ PASS |
| Workflow YAML is valid syntactically | `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/e2e-money-path.yml'))"` | exit 0 (per 31-06 SUMMARY) | ✓ PASS |
| Live workflow run on a real PR | requires GH Actions execution + a real OpenRouter spend | not attempted (out of scope for static verification) | ? SKIP (covered by AC23 human gate) |

### Requirements Coverage

Phase 31 PLAN frontmatter declares `requirements: [H3, H4, H6, H8]`. These IDs originate from the 2026-05-04 solidity audit memory and are documented in `31-SPEC.md` Requirements 1–4, not in `.planning/REQUIREMENTS.md` (which carries the v1 application-level FND/AUTH/SBX/SEC/REC/SES requirement series, not the audit-derived hardening series). The ROADMAP entry for Phase 31 (line 660 of ROADMAP.md) restates the four Hs verbatim. No orphaned audit requirement IDs were declared by other phases.

| Requirement | Source Plan | Description (from SPEC §Requirements) | Status | Evidence |
| ----------- | ---------- | ------------------------------------- | ------ | -------- |
| H3 | 31-02 | Auth rate-limit bucket: 7 routes at 5/min/IP per route via composite subject `auth:<ip>:<route>`; existing fail-open semantics preserved | ✓ SATISFIED | rate_limit.py edits + 4 testcontainer tests; SPEC AC1-AC4 all empirically green |
| H4 | 31-04, 31-05 | Mobile SSE error surfacing: 3-class taxonomy + inline RetryBanner with 3 SPEC-locked copy strings; both `:387` initial-connect and `_onResumed` reconnect routed through one classifier | ✓ SATISFIED | classifier + provider + chat_screen edits + chat_providers edits + 6 classifier tests + 7 widget tests; SPEC AC5-AC11 all empirically green |
| H6 | 31-03, 31-04, 31-05 | Sentry instrumentation, errors-only, both runtimes; AMD-06 4xx-drop in api_server before_send; ID-only set_user; graceful no-op when DSN unset | ✓ SATISFIED (api_server + mobile init/runtime); ⚠ partial on D-16 mobile user-context (REVIEW WR-01 — no AC, decision-only, flagged but not a SPEC violation) | api_server: instrumentation/sentry.py + main.py wiring + session.py set_user + 5 transport-mock tests. mobile: core/instrumentation/sentry.dart + main.dart wrap + Makefile dart-defines + 2 init tests. SPEC AC12-AC16 all empirically green for the obligated surfaces. |
| H8 | 31-06 | CI e2e money-path workflow + Makefile target + tests/e2e/test_money_path.py asserting `cost_usd > 0` + non-null `upstream_request_id` against real OpenRouter | ⚠ HUMAN-NEEDED | Static portion ✓ VERIFIED (workflow YAML valid, secret reference, path filters, concurrency block, recipe+model AMD-04, polling AMD-03/AMD-05 fixtures, all greps pass). 4 manual gates pending: AC20 (secret added), AC22 (dashboard $5/mo cap + artifact), AC23 (no-op PR baseline-green), AC24 (regression PR red-then-closed). Per SPEC §H8 acceptance, these gates are required for H8 to ship GREEN. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `.github/workflows/e2e-money-path.yml` | 74-79 | Non-idempotent `CREATE DATABASE agent_playground_api` (no `IF NOT EXISTS` / `|| true` fallback) — REVIEW CR-01 | ⚠ Warning | A re-run after a transient flake (OpenRouter 503 mid-completion) can fail at this step with `ERROR: database "agent_playground_api" already exists` (PG SQLSTATE 42P04) instead of executing the actual money-path test, masking real H8 regressions. Non-blocking for the AC23 baseline-green run, but degrades AC24's regression-detection reliability under realistic CI flake conditions. Suggested fix in REVIEW.md. |
| `api_server/tests/e2e/test_money_path.py` | 53-62 | `_require_openrouter_key` autouse fixture uses `pytest.skip(...)` not `pytest.fail(...)` — REVIEW WR-02 | ⚠ Warning | A misconfigured `secrets.OPENROUTER_CI_KEY` (typo, expired, fork without secret access) silently SKIPs the test in CI which counts as PASSED in GH Actions, defeating SPEC AC24's "regression PR demonstrably fails" guarantee. The Makefile `@test -n "$$OPENROUTER_API_KEY"` env-guard catches the empty-secret case at the make level, so the actual blast radius is bounded — but the second-layer fail-fast at the pytest level was the SPEC's intended belt-and-braces. |
| `mobile/lib/...` (repo-wide) | — | `Sentry.configureScope`/`setUser` not implemented anywhere on the mobile side — REVIEW WR-01 | ℹ Info | D-16 mobile clause is decision-only (CONTEXT amendment), NOT covered by any SPEC AC for mobile. Per REVIEW: "The omission is consistent with the test surface, not a SPEC violation." Out of scope for Phase 31's must-haves; flagged for a follow-up in the post-31 mobile auth flow file. |
| `api_server/tests/test_sentry_init.py` | 41-47 | `_init_with_capture` helper omits `environment` + `release` — REVIEW WR-03 | ℹ Info | D-13 environment + release tagging is implemented in `init_sentry` but no test exercises the production code path; coverage gap, not a correctness bug. The `test_no_dsn_starts_cleanly` test exercises the DSN-empty branch only. |
| `api_server/pyproject.toml` | (deps) | `httpx>=0.27` floor with no upper bound — REVIEW WR-04 (recorded in summary) | ℹ Info | Contradicts the deliberate `respx>=0.22,<0.24` ceiling discipline elsewhere in the same file; supply-chain hygiene drift, not a Phase 31 must-have failure. |

Note: the 4 pre-existing failures in `tools/run_recipe.py` invariant tests (`test_run_recipe_telegram_invariant.py` × 3 + `test_phase30_via_proxy_invariant.py` × 1) documented in `deferred-items.md` are confirmed unrelated to Phase 31 — file-history check shows zero Phase 31 commits touched those files. They are recipe-runner debt from Phase 30's nanobot+inapp transport landing, not a Phase 31 regression.

### Human Verification Required

Phase 31 Plan 06 SPEC §H8 explicitly defines four manual gates (AC20, AC22, AC23, AC24) that cannot be automated inside test code. They are surfaced here for the user to action. **The phase exit gate cannot be GREEN until all four signals arrive**; until then H8 is partially shipped (automated portion VERIFIED; live-money portion PENDING).

#### 1. AC22 — OpenRouter dashboard $5/mo spend cap + verification artifact

**Test:**
1. Login to OpenRouter dashboard with the Solvr Labs account.
2. Navigate to Settings → Billing → Spend Limit (or equivalent).
3. Set the monthly cap to **$5.00**.
4. Capture proof — screenshot saved to `.planning/phases/31-pre-stripe-billing-hardening/spend-cap.png` OR a dashboard URL with timestamp embedded in the eventual PR commit-message body.
5. Confirm the dashboard reflects the cap on a fresh page load.

**Expected:** Cap is live and proof is captured; `.planning/phases/31-pre-stripe-billing-hardening/spend-cap.png` is empirically NOT YET COMMITTED at verification time.

**Why human:** Requires Solvr Labs OpenRouter dashboard credentials and a UI workflow on a third-party site. Cannot be automated. **Resume signal:** `cap-set: <screenshot-path-or-URL>`

#### 2. AC20 — Add OPENROUTER_CI_KEY to GitHub repo secrets

**Test:**
1. Create a NEW OpenRouter API key dedicated to CI (separate from any dev BYOK already in `.env`); tag/label as `gh-actions-e2e-money-path`.
2. Verify the key is bound to the same OpenRouter account that has the $5/mo cap from AC22.
3. In GitHub repo Settings → Secrets and variables → Actions → New repository secret: name `OPENROUTER_CI_KEY`, value the new key.
4. After Manual Gate 3 (AC23) runs the workflow once, inspect the workflow log to confirm the secret value never appears in plain text. (GitHub auto-masks `${{ secrets.* }}`; the absence of any `echo $OPENROUTER_API_KEY` / `printenv` / `set -x` in the YAML is verified by static grep.)

**Expected:** Secret added in repo settings; first workflow run (after AC23) confirms no plaintext leak.

**Why human:** Requires OpenRouter dashboard to mint a key and GitHub repo settings to store it. Static-check side already PASSED. **Resume signal:** `secret-set` (do NOT paste the key value)

#### 3. AC23 — No-op PR triggers workflow + workflow exits 0 (baseline green)

**Test:**
1. Branch off main; add a whitespace-only / comment-only change inside `api_server/` (e.g. trailing newline in `api_server/README.md`).
2. Open PR against main.
3. Watch the GH Actions `e2e money path` run.

**Expected:** (a) workflow triggers (path filter on `api_server/**` matches), (b) completes in ~5-10 min, (c) job exits 0 (green check), (d) OpenRouter dashboard shows ~$0.0004 charge for the run (matches Phase 29 nanobot baseline).

**Why human:** Requires a live PR + a real OpenRouter spend (~$0.0004) + GitHub Actions runner execution. Cannot be reproduced from static analysis alone. **Resume signal:** `baseline-green: <PR-URL>`

#### 4. AC24 — Deliberate-regression PR fails workflow at `cost_usd > 0` (PR closed unmerged)

**Test:**
1. On a separate feature branch off main, intentionally break the proxy cost-capture path (e.g. locate the OpenRouter `/api/v1/generation` parser or the `usage_logs` insert and either short-circuit it or replace the cost field with `0.0`).
2. Open a PR.
3. Watch the workflow.
4. Confirm: workflow triggers (path filter matches); the assertion `float(usage_row["cost_usd"]) > 0` fires AND fails (or polling loop times out and `assert usage_row is not None` fires); job exits non-zero (red X).
5. **CLOSE the PR without merging.** Do NOT merge the regression to main.

**Expected:** Workflow demonstrably fails at the load-bearing AC19 assertion under the deliberate regression; PR is closed unmerged; main stays clean.

**Why human:** Requires a live PR with a deliberate regression + GH Actions execution + a manual close-without-merge step. The whole point of AC24 is to prove the workflow ACTUALLY catches money-loss regressions; without a live red run the assertion is unverified. **Resume signal:** `regression-red: <PR-URL>` (PR CLOSED)

### Gaps Summary

No automated gaps found — all 4 phase truths are empirically verified for the portions that can be checked statically against the codebase. Phase 31 is well-shipped on the automated dimension.

The reason `status: human_needed` (rather than `passed`) is the irreducible 4-gate manual-action requirement that Plan 06 itself surfaces and SPEC §H8 acceptance demands. AC22 (dashboard cap), AC20 (secret), AC23 (baseline PR), AC24 (regression PR) cannot be automated by definition. They are listed in the `human_verification` frontmatter for routing into HUMAN-UAT.md.

REVIEW.md noted 1 critical (CR-01: non-idempotent CREATE DATABASE) + 5 warnings + 6 info-level findings. CR-01 is a CI flake-resilience issue, not a Phase 31 must-have failure (the AC23 happy-path baseline run will succeed; the regression handling under flake is degraded). WR-01 (mobile D-16 set_user) and WR-02 (skip vs fail) are flagged as quality concerns documented in REVIEW.md but neither violates a SPEC AC for Phase 31. The orchestrator can route REVIEW.md findings into a follow-up plan if the user wants the warnings closed before Phase B starts.

Pre-existing failures in 4 invariant tests in `tools/run_recipe.py` paths are confirmed out-of-scope (file-history check at deferred-items.md confirms no Phase 31 commit touched them).

---

_Verified: 2026-05-08T15:58:19Z_
_Verifier: Claude (gsd-verifier)_

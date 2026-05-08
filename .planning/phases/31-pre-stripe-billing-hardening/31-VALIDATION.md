---
phase: 31
slug: pre-stripe-billing-hardening
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-07
---

# Phase 31 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source of truth for AC mapping: `31-RESEARCH.md` §Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (api_server)** | pytest 8 + pytest-asyncio + httpx + asyncpg + testcontainers[postgres,redis] |
| **Framework (mobile)** | flutter_test (SDK) + dio + sentry_flutter SentryTransport |
| **Config file (api)** | `api_server/pyproject.toml` (markers + pytest options) |
| **Config file (mobile)** | `mobile/analysis_options.yaml` (very_good_analysis 10) |
| **Quick run (api)** | `cd api_server && pytest -q -m "not api_integration and not e2e_money_path"` |
| **Quick run (mobile)** | `cd mobile && flutter test` |
| **Full suite (api)** | `make test-api-integration` (testcontainers Postgres) |
| **Phase-gate (paid)** | `make e2e-money-path` — real OpenRouter, run once per phase merge |
| **Estimated runtime (quick)** | ~30s api + ~25s mobile |
| **Estimated runtime (full)** | ~3-5 min api + ~10s mobile |
| **Estimated runtime (e2e money-path)** | ~60-120s + ~$0.0004/run |

---

## Sampling Rate

- **After every task commit:** Run quick suite (`pytest -q -m "not api_integration and not e2e_money_path"` for api work, `flutter test` for mobile work)
- **After every plan wave:** Run full suite (`make test-api-integration` + `flutter test`)
- **Before `/gsd-verify-work`:** Full suite green AND `make e2e-money-path` green once
- **Max feedback latency:** 30s for quick suite; 5min for full suite

---

## Per-Task Verification Map

24 acceptance criteria from `31-SPEC.md` mapped to verification surface (full table in `31-RESEARCH.md` §Phase Requirements → Test Map).

| AC | Requirement | Test Type | Automated Command | Test File | Status |
|----|-------------|-----------|-------------------|-----------|--------|
| H3-AC1 | 6th `/v1/auth/google/mobile` → 429 + `Retry-After` + envelope | D2 integration | `pytest tests/middleware/test_auth_rate_limit.py::test_auth_rate_limit_6th_in_60s_returns_429 -m api_integration` | `api_server/tests/middleware/test_auth_rate_limit.py` (NEW) | ❌ W0 |
| H3-AC2 | Per-route counters (3 google + 3 github = 6 succeed) | D2 integration | `…::test_auth_rate_limit_per_route -m api_integration` | (same) | ❌ W0 |
| H3-AC3 | Real-Postgres counter | D2 integration | covered by AC1+AC2 (testcontainers) | (same) | ❌ W0 |
| H3-AC4 | Postgres-outage fail-open preserved | D7 reliability | `…::test_auth_rate_limit_pg_outage_fail_open` | (same) | ❌ W0 |
| H4-AC5 | Banner `"Connection lost — tap to retry"` on connect failure | D1 unit + D2 widget | `flutter test test/features/chat/chat_stream_error_classifier_test.dart`<br>`flutter test test/features/chat/chat_screen_error_banner_widget_test.dart` | NEW | ❌ W0 |
| H4-AC6 | Banner `"Session expired — sign in again"` on 401 | D1 unit + D2 widget | (same) | NEW | ❌ W0 |
| H4-AC7 | Banner `"Server error — try again later"` on 5xx | D1 unit + D2 widget | (same) | NEW | ❌ W0 |
| H4-AC8 | Both `:387` + `:398` route through one classifier | D2 widget | `…::test_classifier_invoked_from_both_paths` | NEW | ❌ W0 |
| H4-AC9 | Retry CTA fires `_stream.connect()` (mock spy) | D2 widget | `…::test_retry_cta_calls_connect` | NEW | ❌ W0 |
| H4-AC10 | Auth-class CTA navigates to login (route spy) | D2 widget | `…::test_auth_cta_navigates_to_login` | NEW | ❌ W0 |
| H4-AC11 | No technical jargon in banner copy | D3 contract | grep test on copy constants in classifier file | covered by classifier test | ❌ W0 |
| H6-AC12 | api_server captures unhandled exception (transport mock) | D2 integration | `pytest tests/test_sentry_init.py::test_unhandled_exception_captured` | `api_server/tests/test_sentry_init.py` (NEW) | ❌ W0 |
| H6-AC13 | api_server starts cleanly when DSN unset | D7 reliability | `…::test_no_dsn_starts_cleanly` | (same) | ❌ W0 |
| H6-AC14 | mobile captures via `SentryTransport` mock | D2 integration | `flutter test test/core/instrumentation/sentry_test.dart` | `mobile/test/core/instrumentation/sentry_test.dart` (NEW) | ❌ W0 |
| H6-AC15 | mobile starts cleanly when dart-define empty | D7 reliability | `…::test_dart_define_empty_no_init` | (same) | ❌ W0 |
| H6-AC16 | No `traces_sample_rate` / profiling enabled | D3 contract | `…::test_errors_only_sampling` (asserts `client.options['traces_sample_rate'] == 0.0`) | covered by AC12 + AC14 | ❌ W0 |
| H6-AMD06 | Auth-bucket 429 NOT captured (before_send drops <500) | D2 integration | `…::test_before_send_drops_429` | covered by AC12 | ❌ W0 |
| H8-AC17 | `e2e-money-path.yml` triggers on `api_server/**` + `recipes/**` | D3 contract | static YAML inspection (yq or grep) | `.github/workflows/e2e-money-path.yml` (NEW) | ❌ W0 |
| H8-AC18 | Workflow boots Postgres + api_server via `docker-compose.dev.yml` | D6 / D8 | workflow run logs (manual gate after merge) | (workflow log) | manual |
| H8-AC19 | `make e2e-money-path` writes usage_logs row with `cost_usd > 0` + non-null `upstream_request_id` | D4 e2e | `make e2e-money-path` (real OpenRouter) | `api_server/tests/e2e/test_money_path.py` (NEW) | ❌ W0 |
| H8-AC20 | Uses `OPENROUTER_CI_KEY` GH secret, never echoed | D6 security | manual log inspection | manual gate | manual |
| H8-AC21 | `concurrency: { group: e2e-money-path, cancel-in-progress: false }` | D3 contract | `yq` lint or grep on YAML | static check | ❌ W0 |
| H8-AC22 | $5/mo OpenRouter cap + verification artifact | D6 security | manual screenshot/dashboard-link in commit | manual gate | manual |
| H8-AC23 | No-op PR triggers workflow + passes (baseline green) | D4 e2e | live PR with whitespace-only change | manual gate | manual |
| H8-AC24 | Deliberate-regression PR fails at `cost_usd > 0` | D4 e2e | live PR reverting cost-parser | manual gate | manual |

*Status: ⬜ pending · ✅ green · ❌ W0 (Wave 0 creates) · 🟡 manual gate · ⚠️ flaky*

---

## Wave 0 Requirements

Files created in Wave 0 to satisfy ❌ entries above:

- [ ] `api_server/tests/middleware/test_auth_rate_limit.py` — H3-AC1..AC4
- [ ] `api_server/tests/test_sentry_init.py` — H6-AC12, AC13, AC16, AMD06
- [ ] `api_server/tests/e2e/test_money_path.py` — H8-AC19
- [ ] `api_server/tests/e2e/conftest.py` — `e2e_money_path_client` fixture (composes `async_client` + `authenticated_cookie`)
- [ ] `mobile/test/features/chat/chat_stream_error_classifier_test.dart` — D-07 / AMD-02 unit tests + AC11 jargon-grep
- [ ] `mobile/test/features/chat/chat_screen_error_banner_widget_test.dart` — H4-AC5..AC10
- [ ] `mobile/test/core/instrumentation/sentry_test.dart` — H6-AC14, AC15
- [ ] `.github/workflows/e2e-money-path.yml` — H8-AC17, AC21
- [ ] `Makefile` — `e2e-money-path` target (D-17)
- [ ] `api_server/pyproject.toml` — register `e2e_money_path` marker
- [ ] (AMD-05) `api_server/tests/conftest.py` — add `usage_logs` to `_truncate_tables` autouse list

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| OpenRouter dashboard $5/mo cap is set | H8-AC22 | Dashboard lives outside the repo; no API to query the cap programmatically | Login to OpenRouter; navigate to Settings → Billing → Spend Limit; set monthly cap to $5; screenshot or capture dashboard URL; commit reference in PR commit message body |
| GH secret `OPENROUTER_CI_KEY` is set in repo settings | H8-AC20 | GH UI; not committable | Repo Settings → Secrets and variables → Actions → New repository secret `OPENROUTER_CI_KEY` |
| No-op PR triggers green workflow run | H8-AC23 | Requires a live PR | Open whitespace-only PR on `api_server/README.md`; observe `e2e money path` workflow runs and is green |
| Deliberate-regression PR fails workflow | H8-AC24 | Requires intentional regression | Open PR reverting a known-good cost-parser change; observe `e2e money path` fails at `cost_usd > 0` assertion |
| Sentry org + DSN procurement | H6 (whole) | External SaaS sign-up | Create Solvr Labs org on Sentry Free tier; create two projects (`agent-playground-api`, `agent-playground-mobile`); set `AP_SENTRY_DSN_API` + `SENTRY_DSN_MOBILE` in `.env` (and as GH secrets when H7 deploy lands) |

---

## Validation Sign-Off

- [ ] All 24 SPEC ACs have automated `<verify>` OR Wave 0 dependency declared above
- [ ] Sampling continuity: no 3 consecutive plan tasks without an automated verify reference
- [ ] Wave 0 creates the 11 files listed above before any source-modifying task runs
- [ ] No watch-mode flags in any test command
- [ ] Feedback latency < 30s for quick suite
- [ ] `nyquist_compliant: true` set in frontmatter once plan-checker validates coverage

**Approval:** pending

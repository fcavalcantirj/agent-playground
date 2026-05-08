---
phase: B-stripe
slug: paywall
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-08
---

# Phase B — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Pre-populated from `B-stripe-RESEARCH.md` § "Validation Architecture". Planner refines per-task rows during plan-phase; executor flips status flags during execute-phase.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (api_server)** | pytest 8.x + pytest-asyncio + testcontainers (Postgres) + respx + Temporal `WorkflowEnvironment` (Phase 28 fixture) |
| **Framework (mobile)** | flutter_test + http_mock_adapter + golden_toolkit |
| **Config file (api_server)** | `api_server/pyproject.toml` `[tool.pytest.ini_options]` |
| **Config file (mobile)** | `mobile/test/` + `mobile/integration_test/` |
| **Quick run command** | `cd api_server && uv run pytest tests/test_billing_*.py -x` |
| **Full suite command (api_server)** | `cd api_server && uv run pytest -m 'not e2e_money_path and not phase_b_e2e'` |
| **Full suite command (mobile)** | `cd mobile && flutter test` |
| **Phase B e2e gate** | `make e2e-phase-b-stripe` (NEW Make target — runs against real Stripe TEST mode + signed-fixture webhooks) |
| **Estimated runtime (quick)** | ~10 seconds |
| **Estimated runtime (full api)** | ~3 minutes |
| **Estimated runtime (e2e gate)** | ~5 minutes |

---

## Sampling Rate

- **After every task commit:** Run `cd api_server && uv run pytest tests/test_billing_*.py -x` (api_server tasks) OR `cd mobile && flutter test test/features/billing/ test/features/usage/` (mobile tasks)
- **After every plan wave:** Run `cd api_server && uv run pytest -m 'not e2e_money_path and not phase_b_e2e' && cd ../mobile && flutter test`
- **Before phase exit gate:** `make e2e-phase-b-stripe` GREEN against real Stripe TEST mode AND `make e2e-money-path` (Phase 31 H8) GREEN (regression gate — Phase B must not break Phase 31's money path)
- **Max feedback latency:** 60 seconds for the per-task sampling

---

## Per-Task Verification Map

> **Pre-populated from RESEARCH.md § Validation Architecture.** Planner fills concrete Task IDs + Plan numbers + Wave assignments during plan-phase. Executor flips ⬜ → ✅ as tasks land.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | D-01 (users.tier enum + backfill) | T-B-01 | Enum-constrained tier flips never produce invalid states | unit (alembic round-trip) | `pytest tests/test_migration_014_phase_b.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-04 (webhook is sole tier writer) | T-B-04 | Tier flip path is signature-verified; no other route mutates tier | integration | `pytest tests/test_billing_webhook.py::test_subscription_created_flips_tier -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-05 Pro slot cap (5) at agent.create | — | Tier cap enforced before insert; no race past cap | unit | `pytest tests/test_tier_enforcement.py::test_pro_caps_at_5 -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-05 Pro retention 30d filter on messages.list | — | Retention window applied at query time | unit | `pytest tests/test_messages_list.py::test_retention_window_pro -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-09 prune_messages workflow | — | Daily cron deletes >7d for free / >30d for pro / never for ultra | integration (Temporal WorkflowEnvironment + Postgres testcontainer) | `pytest tests/test_prune_messages_workflow.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-12 Pre-flight 402 (tier='ultra' AND balance < 1) | — | Negative balance also caught (predicate `< 1`) | integration | `pytest tests/test_llm_proxy_402.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-13 Debit only on success | — | Failed forward → no ledger row | integration | `pytest tests/test_debit_balance_activity.py::test_no_debit_on_failure -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-14 All 7 webhook events handled idempotently (post-AMD-05) | T-B-W1 | Replay protection via stripe_event_id UNIQUE | integration (signed fixtures fire same event twice; assert exactly one side-effect) | `pytest tests/test_billing_webhook.py::test_idempotent_redelivery -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-15 cancel_at_period_end → grace then auto-pause 4 oldest | — | Period-end flip kicks 4 oldest agents to paused | integration | `pytest tests/test_pro_downgrade.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-17 Atomic ledger debit+balance update in same tx | T-B-LR | Concurrent debits don't double-deduct | unit + integration (Postgres testcontainer; concurrent debits) | `pytest tests/test_ledger_atomic.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-17 Reconcile drift detection | — | Corrupted cache emits Sentry event | integration | `pytest tests/test_reconcile_ledger_workflow.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-21 Mobile 402 modal flow | — | 402 always shows blocking modal with Top-Up CTA | widget test | `flutter test test/features/billing/insufficient_credits_modal_test.dart` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-21 Mobile webview redirect interception | — | success_url / cancel_url intercepted; webview closes; balance polls | manual + integration_test | `flutter test integration_test/billing_webview_test.dart` | ❌ W0 | ⬜ pending — manual primary |
| TBD | TBD | TBD | D-22 Webhook signature verification (AMD-04 service pattern) | T-B-W1 | Bad sig → 400; good sig → process | unit (signed fixtures) | `pytest tests/test_billing_webhook.py::test_signature_required -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-25 (exit gate) Free → Ultra → message → debit → drained → 402 | — | Full money-path E2E green | e2e | `make e2e-phase-b-stripe` | ❌ W5 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

These artifacts must exist before Wave 1 starts coding (per RESEARCH.md § Validation Architecture):

- [ ] `tests/conftest.py` extension — `stripe_client_test` fixture (StripeClient pointed at stripe-mock OR real TEST per pytest mark)
- [ ] `tests/_fixtures/stripe_webhooks/` directory — signed fixture files for each event in D-14 (post-AMD-05: 7 events)
- [ ] `tests/_fixtures/sign_webhook.py` — helper that produces `Stripe-Signature` header from raw payload + secret (per AMD-02 — stripe-mock has no webhook simulation)
- [ ] `api_server/Makefile` target `e2e-phase-b-stripe` (mirrors `e2e-money-path` from Phase 31)
- [ ] `pytest.ini` marker `phase_b_e2e` (so default suite excludes real-Stripe runs)
- [ ] `.github/workflows/e2e-phase-b.yml` running `make e2e-phase-b-stripe` against `secrets.AP_STRIPE_TEST_API_KEY` + `secrets.AP_STRIPE_TEST_WEBHOOK_SECRET`
- [ ] Webhook URL exposure for CI: GH Actions runs deploy api_server container locally, uses `stripe trigger` to fire events at `localhost:8000/v1/billing/webhook`
- [ ] Stripe-mock service in `docker-compose.dev.yml` for local unit-test runs (port 12111)
- [ ] Mobile pubspec adds `flutter_inappwebview: ^6.1.5` (per AMD-03)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Stripe Checkout webview UX (smoothness; back-button handling; iOS/Android parity) | D-21 | Native webview behaviors are device-/OS-specific; emulator coverage incomplete | `B-HUMAN-UAT.md` walks: Free user → upgrade to Ultra → Stripe Checkout in-app webview (TEST card `4242 4242 4242 4242`) → return to chat → balance updated → send message → modal at 402 |
| Live Stripe TEST account state (Customer records lazy-create correctly; Products mapped to env vars correctly) | D-10 / D-11 | Requires real Stripe TEST dashboard inspection | Confirm `stripe_customer_id` populates only on Pro-subscribe or Ultra top-up click; not on signup or any other path |
| Promo code redemption (D-24) | D-24 | Marketing-side artifact: codes minted in Stripe dashboard | Mint a 50%-off-once code in Stripe TEST → run upgrade flow → assert ledger captures discounted amount |
| Webhook delivery via `stripe listen` against deploy stack on macOS | D-19 / D-22 | macOS dev split-brain trap (per `feedback_no_native_uvicorn_with_deploy_stack.md`) | Manual UAT step verifies `stripe listen --forward-to http://localhost:8000/v1/billing/webhook` against the deploy api_server container (NOT native uvicorn) |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s for quick / 300s for full
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

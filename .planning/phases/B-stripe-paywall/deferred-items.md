# Phase B-stripe-paywall — Deferred Items

Out-of-scope discoveries surfaced during execution. None of these are
introduced by Phase B work; per the scope-boundary rule, they're logged
here rather than fixed in-flight.

## Pre-existing test failures on `main` (verified 2026-05-09 via stash + re-run)

The following 5 tests fail on `main` (commit b9e4c70) BEFORE any Phase B
Wave 1 changes are applied — i.e. they are pre-existing bugs unrelated
to migration 014, Settings extension, StripeClient, billing_packs, or
ledger.py:

1. `tests/test_main_lifespan_inapp.py::test_lifespan_attaches_two_inapp_tasks`
2. `tests/auth/test_cross_user_isolation.py::test_two_users_see_only_their_own_agents`
3. `tests/auth/test_oauth_mobile.py::test_github_public_email_returns_session`
4. `tests/auth/test_oauth_mobile.py::test_github_private_email_falls_back_to_emails_endpoint`
5. `tests/auth/test_oauth_mobile.py::test_github_invalid_token_returns_401`

These persist after Plan B-stripe-02 lands. Should be triaged in a
separate cleanup phase or assigned to whatever subsystem owner discovers
their root cause.

## Pre-existing dirty file in working tree

`mobile/lib/features/dashboard/dashboard_providers.dart` is `M` (modified
but uncommitted) on `main` at the start of Phase B-stripe-02. NOT
touched by this plan; left as-is per executor rules.

## Pre-existing failure surfaced during Plan B-stripe-08 (2026-05-09)

`tests/routes/test_llm_proxy.py::test_d09_no_inline_falls_back_to_cost_weights`
asserts `cost_usd == Decimal('0.00004500')` (the pre-Phase-B value when
`cost_weights.ap_multiplier = 1.0`). Migration 014 (Plan B-stripe-02,
commit `235b34e`) bumped every pre-existing seed row's multiplier to
1.15 per D-08. The test's expected value was never updated, so it now
fails with actual `Decimal('0.00005175')` (= 0.00004500 × 1.15).

- Verified pre-existing via `git stash` + re-run on `main` at commit
  `331a44f` (BEFORE Plan 08's llm_proxy.py edit).
- Plan B-stripe-08 does NOT modify this code path; the new pre-flight
  402 block lives at section 2.5, well above the `_record_usage_from_parsed`
  function this test exercises.
- Fix is one-line (update expected to `Decimal('0.00005175')`), but
  out-of-scope per executor scope-boundary rule.

Triage suggestion: a Phase B follow-up plan that audits every existing
test asserting against `cost_weights`-derived `cost_usd` numbers and
updates them for the 1.15× multiplier shift in one batch.

Two sibling tests share the same root cause and were also confirmed
pre-existing via stash + re-run on commit `331a44f`:

- `tests/routes/test_llm_proxy.py::test_d09_anthropic_does_not_use_inline_path`
- `tests/routes/test_llm_proxy.py::test_d09_openai_direct_does_not_use_inline_path`

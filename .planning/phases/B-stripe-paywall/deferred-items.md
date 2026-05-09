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

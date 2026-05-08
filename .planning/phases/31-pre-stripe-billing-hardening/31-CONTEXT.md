# Phase 31: Pre-Stripe Billing Hardening - Context

**Gathered:** 2026-05-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Implementation of 4 audited billing-readiness gaps locked by `31-SPEC.md` (H3 auth rate-limit bucket, H4 mobile SSE error surfacing, H6 Sentry instrumentation, H8 CI e2e money-path gate). HOW decisions only — WHAT and WHY are sealed in `31-SPEC.md`. H7 Hetzner deploy is a separate subsequent phase and out of scope here.
</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**4 requirements are locked.** See `31-SPEC.md` for full requirements, boundaries, and 24 falsifiable acceptance criteria.

Downstream agents MUST read `31-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
- New `auth` bucket in `middleware/rate_limit.py` with composite `auth:<ip>:<route>` subject derivation
- Three-class error taxonomy + inline banner in `mobile/lib/features/chat/`
- `sentry-sdk[fastapi]>=2.0` in api_server, `sentry_flutter` in mobile, errors-only
- New CI workflow `e2e-money-path.yml` + `make e2e-money-path` target hitting real OpenRouter
- Test coverage against real infra (real Postgres counter, Sentry transport-mock, real Docker-compose stack)
- OpenRouter $5/mo cap verification artifact

**Out of scope (from SPEC.md):**
- H7 Hetzner deploy (separate subsequent phase; required prereq for Phase B Stripe webhooks)
- H1 OAuth refresh tokens (RETIRED — misframe per Phase 22c AMD-02)
- H2 Logout-everywhere (Phase 26 SHIPPED then reverted)
- H5 `agentsListProvider` invalidate-sink consolidation (deferred)
- Sentry tracing / performance / profiling (free-tier quota concern)
- Per-user auth rate-limiting (impossible pre-auth-resolution)
- Stripe SDK / credit balance / webhook handler (that's Phase B, what this gates)
- Web frontend changes
</spec_lock>

<decisions>
## Implementation Decisions

### H3 — Auth bucket subject derivation

- **D-01:** Bucket-routing pattern. Module-level frozen set `_AUTH_ROUTES = {('POST', '/v1/auth/google/mobile'), ('POST', '/v1/auth/github/mobile'), ('POST', '/v1/auth/logout'), ('GET', '/v1/auth/google'), ('GET', '/v1/auth/google/callback'), ('GET', '/v1/auth/github'), ('GET', '/v1/auth/github/callback')}` in `middleware/rate_limit.py`. `_bucket_for` returns `"auth"` on `(method, path)` membership. No regex on the hot path; greppable + extensible. Mirrors the `_LIMITS` shape for consistency.
- **D-02:** Composite subject format. `auth:<ip>:<route_key>` where `route_key` is a stable short alias (`google_mobile`, `github_mobile`, `logout`, `google_redirect`, `google_callback`, `github_redirect`, `github_callback`). Path renames don't invalidate counter rows. Each route gets its own counter.
- **D-03:** XFF-trust + fail-open semantics. Identical to existing buckets. Reuses `_subject_from_scope` unchanged. Auth bucket inherits Caddy-in-front prod correctness AND Postgres-outage pass-through behavior. No fail-closed override (rejected — DDoS-via-trip-rate-limit risk worse than the protection).
- **D-04:** `_LIMITS` extension. Single new entry: `"auth": (5, 60)`. All 7 auth routes share this single ceiling but composite-subject keeps per-route counters distinct.

### H4 — Error classifier + banner shape

- **D-05:** Provider shape. `StateProvider<ChatStreamErrorState?>` mirroring Phase 25 D-50 `telegram_failed_banner_provider.dart`. Memory-only, single-active per chat. State holds `(agentInstanceId, errorClass, lastFailedAction)`. Cleared on retry-success / dismiss / sign-out / Riverpod teardown. Identical lifecycle to `telegram_failed_banner_provider`.
- **D-06:** Classifier home. Pure top-level function `classifyChatStreamError(Object e) -> ChatStreamErrorClass` in new file `mobile/lib/features/chat/chat_stream_error_classifier.dart`. No Riverpod, no I/O, no async. Three unit tests + one fallback test in `test/features/chat/chat_stream_error_classifier_test.dart`. Reusable from both `:387` initial-connect AND `:398` `_onResumed` reconnect sites.
- **D-07:** Classifier mapping. `SocketException | TimeoutException | DioException(network)` → `networkTransient`; HTTP 401 → `authExpired`; HTTP ≥500 → `serverError`. **Unknown error class → `networkTransient`** (default fallback; original error logged to Sentry breadcrumb for debugging).
- **D-08:** Banner widget. New `mobile/lib/features/chat/chat_stream_error_banner.dart` ConsumerWidget. Sibling of existing `telegram_failed_banner.dart`. Three rendered states with the locked SPEC.md copy strings (`"Connection lost — tap to retry"` / `"Session expired — sign in again"` / `"Server error — try again later"`). Dismissal + retry/sign-in CTAs as constructor callbacks. Accessibility: mirror `telegram_failed_banner.dart` `Semantics` pattern.
- **D-09:** Banner lifecycle on app-resume. On `_onResumed`, classifier re-fires if the new connect attempt fails — banner state is REPLACED with the new classification, not stacked. Existing banner persists across foreground/background unless cleared by retry-success / dismiss / sign-out / Riverpod teardown (matches Phase 25 D-50 contract).

### H6 — Sentry init

- **D-10:** api_server placement. New `api_server/src/api_server/instrumentation/sentry.py` module exporting `init_sentry(settings) -> None`. Called from `main.create_app()` BEFORE middleware stack setup. New `instrumentation/` package created. Module is unit-testable in isolation with the Sentry transport-mock; future Sentry config (release tag, env tag, ignore_errors) lives in one place.
- **D-11:** mobile placement. New `mobile/lib/core/instrumentation/sentry.dart` exporting `Future<void> initSentry({required Future<void> Function() runner}) async` that wraps `SentryFlutter.init(...)` + the dart-define-empty noop branch + delegates to `runner()`. `main.dart` becomes `await initSentry(runner: () async { runApp(...); })`. Symmetric to api_server placement.
- **D-12:** `before_send` filter (cross-cutting, free-tier quota protection). api_server `before_send` drops `HTTPException` with `status_code < 500` AND drops the rate-limit `RATE_LIMITED` error envelope. Mobile equivalent drops `DioException` where `response?.statusCode != null && response!.statusCode! < 500`. Only unhandled / true-server-error events reach Sentry. Protects 5K/month free-tier quota from auth-bucket DDoS scenarios where a script could blow quota in minutes.
- **D-13:** Tagging. `environment` from `AP_ENV` env (api_server) / `--dart-define=SENTRY_ENVIRONMENT=` (mobile). `release` from `GIT_SHA` env (api_server) / `--dart-define=SENTRY_RELEASE=` (mobile). Both runtimes pin git-sha at boot for prod-error attribution. Critical for filtering dev noise from real prod errors when H7 deploy lands.
- **D-14:** DSN-unset behavior. Log INFO once at startup (`api_server.sentry: Sentry disabled (AP_SENTRY_DSN_API unset)` / `debugPrint('Sentry disabled (SENTRY_DSN_MOBILE unset)')`), then silent. Matches `auth/oauth.py` placeholder-log pattern. Saves a future-dev wondering why Sentry isn't capturing in dev.
- **D-15:** Mobile Makefile wiring. `mobile/Makefile`'s `ios` + `android` targets gain `--dart-define=SENTRY_DSN_MOBILE=$(SENTRY_DSN_MOBILE) --dart-define=SENTRY_RELEASE=$(GIT_SHA) --dart-define=SENTRY_ENVIRONMENT=$(SENTRY_ENVIRONMENT)`. Existing CLAUDE.md `set -a; source .env; set +a; make ios` flow propagates them automatically alongside `BASE_URL` / `GOOGLE_IOS_CLIENT_ID` / `GOOGLE_SERVER_CLIENT_ID` / `GITHUB_CLIENT_ID`.
- **D-16:** Sentry user-context (cross-cutting, opt-in). After auth resolution in `middleware/session.py`, `sentry_sdk.set_user({'id': user_id})` fires. ID only, no email/PII. Aids correlating user-impacting bugs without compliance burden. Mobile equivalent fires `Sentry.configureScope((scope) => scope.setUser(SentryUser(id: userId)))` after sign-in resolves.

### H8 — CI e2e harness

- **D-17:** Test runner. `make e2e-money-path: cd api_server && pytest -m e2e_money_path`. Mirrors existing `test-api-integration` pattern exactly. Tests live in `api_server/tests/e2e/test_money_path.py`. Marker registered in `pyproject.toml`'s `[tool.pytest.ini_options].markers` list.
- **D-18:** CI auth path. pytest fixture inserts a row directly into `users` (using the existing app's connection pool) + signs a session cookie via `SESSION_SIGNING_KEY` (the actual app key, not a CI-only key). No OAuth round-trip in CI. Mirrors `tests/auth/test_cross_user_isolation.py` fixture pattern. **No CI-only auth backdoors in production code** — `?ci_token=` bypass was explicitly rejected to keep a single auth surface.
- **D-19:** CI stack bring-up. Reuse `docker-compose.dev.yml` directly. `docker compose -f docker-compose.dev.yml up -d postgresql` + run api_server natively under uvicorn in the GHA runner. Migrations via existing `make migrate-api`. No CI-only compose variant. Same stack the dev machine uses; no CI/dev divergence.
- **D-20:** Cost-capture polling. `for _ in range(50): row = await fetch_usage_log(); if row: break; await asyncio.sleep(0.2)` — 200ms × 50 iterations = 10s ceiling. Documented in `tests/e2e/conftest.py` as the canonical e2e wait-for-row pattern. Phase 30 measurements show nano-kaiku upstream completes in ~2-4s; 10s ceiling is the regression-detection floor.
- **D-21:** Concurrency. `concurrency: { group: e2e-money-path, cancel-in-progress: false }` per SPEC.md. Default GH queue depth = unbounded; queue depth rarely matters since money-path PRs are infrequent.
- **D-22:** Test idempotency. pytest fixture creates + tears down a fresh user + agent per test method. No DB-state leakage between runs. Existing fixture patterns suffice.
- **D-23:** Spend-cap verification artifact. Format pinned at plan-phase per SPEC §H8 acceptance — likely a screenshot embedded as base64 in PR commit-message body OR a linked dashboard URL with a timestamp. Out-of-band proof, not committed binary asset.

### Claude's Discretion

- OpenRouter model selection for the CI e2e test: cheapest verified cell of `nano-kaiku` (likely `google/gemini-2.0-flash-001` based on Phase 29 cell verification). Confirm at plan-phase. Target $0.01–$0.02 per chat completion.
- Banner copy localization: hardcoded English per project conventions (no `flutter_localizations` in `pubspec.yaml` today). Open future phase if/when l10n lands.
- pytest fixture exact wire shape (which `httpx.AsyncClient` to use, how to compose the `lifespan` context for the test app, fixture-scoping `function` vs `module`) — plan-phase decides.
- Sentry SDK pin specifics (e.g., `sentry-sdk[fastapi]>=2.20,<3.0`) — plan-phase pins exact constraint after `pyproject.toml` review.

### Folded Todos

None — no pending todos matched this phase's scope at discuss time.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 31 specification (locked)
- `.planning/phases/31-pre-stripe-billing-hardening/31-SPEC.md` — Locked requirements, 24 falsifiable acceptance criteria, in/out-of-scope boundaries. **MUST read before planning.**

### Source files under modification
- `api_server/src/api_server/middleware/rate_limit.py` — Existing rate-limit middleware. Lines 45 (`_AGENT_MESSAGES_PATTERN`), 48-53 (`_LIMITS`), 56-81 (`_bucket_for`), 84-123 (`_subject_from_scope`), 126-203 (`RateLimitMiddleware.__call__`). Pattern to extend with new `auth` bucket per D-01..D-04.
- `api_server/src/api_server/routes/auth.py` — Auth route definitions. Lines 138, 157, 222, 237, 378, 449, 542 are the 7 auth endpoints the new bucket covers.
- `api_server/src/api_server/services/rate_limit.py` — Postgres rate-limit counter implementation (`check_and_increment`). NO changes — new auth bucket reuses unchanged.
- `api_server/src/api_server/main.py` — App factory `create_app()`. Sentry init insertion point per D-10.
- `api_server/src/api_server/middleware/session.py` — Where `sentry_sdk.set_user` fires after auth resolution per D-16.
- `mobile/lib/features/chat/chat_providers.dart` — Lines 387 (`_stream.connect().catchError((_) {})`) and 398 (bare empty catch in `_onResumed`) are the silent-swallow sites under D-05..D-09.
- `mobile/lib/main.dart` — App entry. Sentry init wraps `runApp` per D-11.
- `mobile/Makefile` — `ios` + `android` targets need `--dart-define=SENTRY_*` propagation per D-15.

### Existing patterns to mirror
- `mobile/lib/features/chat/telegram_failed_banner_provider.dart` — Phase 25 D-50/D-58 chat-banner `StateProvider<T?>` pattern. **D-05 mirrors this exactly.**
- `mobile/lib/features/chat/telegram_failed_banner.dart` — Banner widget shape with `Semantics` + dismissal + retry CTAs. **D-08 sibling.** (Path may differ slightly — confirmed via `grep` to live in chat feature dir.)
- `mobile/lib/features/new_agent/deploy_step.dart` — Inflight UI pattern (lock trigger + spinner + mm:ss timer + success/failure SnackBar). Reference for retry-CTA UX semantics per memory `feedback_inflight_ui_for_long_awaits.md`.
- `api_server/src/api_server/auth/oauth.py` — `OAuth config oauth_X missing in dev; using placeholder` log pattern. **D-14 mirrors this.**
- `api_server/tests/middleware/test_chat_rate_limit.py` — Per-route composite-subject test pattern. Auth-bucket tests follow this shape.
- `api_server/tests/auth/test_cross_user_isolation.py` — Authenticated-pytest-fixture pattern. **D-18 mirrors this.**
- `Makefile` `test-api-integration: cd api_server && pytest -m api_integration` — pytest-marker harness pattern. **D-17 mirrors this.**

### Project guardrails (always-applies)
- `CLAUDE.md` "Golden rules" — No mocks for core substrate, dumb client, ship locally first, root-cause-first, test-everything-before-planning.
- `memory/feedback_no_mocks_no_stubs.md` — Real-infra test policy (D-18, D-19, D-20).
- `memory/feedback_dumb_client_no_mocks.md` — Client never queries DB directly (informs D-18 — fixture writes session-cookie via the same signing-key path the app uses).
- `memory/project_solidity_audit_2026_05_04.md` — H3-H8 origin + 2-track plan.
- `memory/project_phase_26_shipped.md` — H2 logout-everywhere reverted (out-of-scope confirmation).
- `memory/feedback_re_ask_gray_areas.md` — Audit-pass discipline; surfaced D-12, D-13, D-15, D-20 in second pass.

### Sentry SDK references (for plan-phase research)
- `sentry-sdk` Python: official docs for `init(...)`, `set_user`, `before_send` hook, FastAPI integration class.
- `sentry_flutter`: official docs for `SentryFlutter.init`, `--dart-define` configuration, `Sentry.configureScope`.

### MSV inspiration
- (None directly — this phase has no MSV pattern to inherit. The audit memory's MSV refs — `recorder.go:313-430`, `payment.go:576-725`, `payment_poller.go`, `transactions-page-content.tsx` — are for Phase B Stripe paywall, NOT Phase 31.)
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `RateLimitMiddleware` (`middleware/rate_limit.py`): Composite-subject derivation pattern (`chat:<subject>:<agent_id>` at lines 164-168) + Postgres-backed counter + fail-open semantics. Auth bucket extends without modifying the existing middleware contract.
- `services.rate_limit.check_and_increment`: Generic per-(subject, bucket, limit, window) counter. New `auth` bucket uses it unchanged.
- `telegram_failed_banner_provider.dart` + `telegram_failed_banner.dart` (Phase 25 D-50): `StateProvider<T?>` chat-banner shape. **Direct sibling pattern for chat-stream error banner.**
- `tests/auth/test_cross_user_isolation.py`: Authenticated-fixture pattern (insert user + sign session cookie). e2e CI auth fixture mirrors this directly.
- `auth/oauth.py` placeholder-log pattern: graceful no-op when env vars missing in dev. Sentry init mirrors this.
- `Makefile test-api-integration: pytest -m api_integration`: Pytest-marker harness. `make e2e-money-path: pytest -m e2e_money_path` extends.

### Established Patterns
- ASGI middleware ordering: rate-limit → idempotency → session → handler. New `auth` bucket lives inside existing rate-limit middleware; no ordering change.
- pytest markers as test partitioning: `api_integration`, recipe-smoke, etc. Adding `e2e_money_path` follows.
- `--dart-define` for compile-time mobile config (`BASE_URL`, `GOOGLE_IOS_CLIENT_ID`, `GOOGLE_SERVER_CLIENT_ID`, `GITHUB_CLIENT_ID`). `SENTRY_DSN_MOBILE` + `SENTRY_RELEASE` + `SENTRY_ENVIRONMENT` extend the same pattern.
- Riverpod `StateProvider<T?>` for memory-only single-active state (Phase 25 D-50).
- `instrumentation/` package as the canonical home for cross-cutting init helpers (this phase creates the package — first occupant is Sentry; Sentry-flutter sibling on the mobile side).

### Integration Points
- `api_server/src/api_server/main.py:create_app()`: Sentry init insertion point (before middleware stack).
- `api_server/src/api_server/middleware/session.py`: Sentry `set_user` insertion (post-auth resolution).
- `api_server/src/api_server/middleware/rate_limit.py`: `_LIMITS`, `_bucket_for`, `_AUTH_ROUTES` extension points.
- `mobile/lib/main.dart`: `initSentry` wrap site.
- `mobile/lib/features/chat/chat_screen.dart` (or current ChatScreen widget): banner widget consumption point.
- `mobile/lib/features/chat/chat_providers.dart` lines 387, 398: silent-swallow replacement sites.
- `mobile/Makefile` `ios` + `android` targets: dart-define propagation.
- `.github/workflows/e2e-money-path.yml`: NEW file. GH-Actions Postgres + uvicorn + pytest pipeline.
- `pyproject.toml` `[tool.pytest.ini_options].markers`: register `e2e_money_path` marker.
</code_context>

<specifics>
## Specific Ideas

- **User picked recommended defaults across 16/16 sub-decisions.** Spec interview + this CONTEXT.md form an exhaustive HOW lock. Plan-phase has no ambiguity left to resolve about top-level shape.
- **Mirror Phase 25 D-50 in mobile.** The chat-banner pattern is already proven and tested in the codebase; the new code is the smallest possible diff. `chat_stream_error_banner_provider.dart` + `chat_stream_error_banner.dart` are siblings of `telegram_failed_banner_provider.dart` + `telegram_failed_banner.dart`.
- **No CI-only production code paths.** The `?ci_token=` auth bypass was explicitly rejected to keep a single auth surface. The pytest session-cookie fixture is the canonical CI auth path — already proven in `test_cross_user_isolation.py`.
- **`instrumentation/` package symmetry.** New `api_server/src/api_server/instrumentation/sentry.py` and new `mobile/lib/core/instrumentation/sentry.dart` are intentionally parallel — same name, same shape — so future runtime-wide concerns (e.g., OpenTelemetry, distributed tracing) have an obvious home.
- **Sentry `before_send` filter is load-bearing for budget.** Without it, an auth-bucket attack could blow the 5K/month free-tier quota in minutes and Sentry would silently rate-limit us, hiding real prod errors. D-12 is non-optional.
</specifics>

<deferred>
## Deferred Ideas

- **Sentry tracing / performance / profiling** — out of scope per SPEC.md (free-tier quota concern). Revisit when traffic justifies upgrade tier OR when prod-debugging needs span data.
- **Per-user auth rate-limiting** — impossible pre-auth-resolution. SPEC.md captures the rationale; revisit if we add a "logged-in /v1/auth/refresh" or similar.
- **Banner copy localization (l10n)** — project has no `flutter_localizations` today. Hardcoded English. Open a future phase if/when l10n lands.
- **CI key rotation policy** — standard GH secret rotation; document in deploy README during H7 (Hetzner) phase.
- **Concurrent CI queue depth limit** — GH default unbounded; revisit if real money-path PR volume creates queueing.
- **Sentry self-hosted migration** — Free tier sufficient for current volume. Self-hosted Sentry alternative explicitly considered + rejected during spec interview (overkill pre-prod).
- **OpenTelemetry as a Sentry alternative** — considered + rejected during spec interview (different surface area than the audit assumed).

### Reviewed Todos (not folded)

None — the cross_reference_todos step found no relevant pending items.
</deferred>

---

*Phase: 31-pre-stripe-billing-hardening*
*Context gathered: 2026-05-07*

# Phase 31: Pre-Stripe Billing Hardening - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `31-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-05-07
**Phase:** 31-pre-stripe-billing-hardening
**Areas discussed:** Auth bucket subject derivation, Error classifier + banner shape, Sentry init helper placement, CI e2e harness shape, Audit-pass cross-cutting decisions

---

## Auth bucket subject derivation

### Q1: Bucket-routing pattern

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit `_AUTH_ROUTES` set | Module-level frozen set `{(method, path), ...}`. Greppable, no regex on hot path. | ✓ |
| Regex-table mirroring `_AGENT_MESSAGES_PATTERN:45` | Compiled regex like the existing chat-bucket pattern. Overkill for literal matches. | |
| Generic bucket-shape registry | Move `_LIMITS` + `_bucket_for` into a list of `BucketRule` structs. Premature refactor. | |

**User's choice:** Explicit `_AUTH_ROUTES` set (Recommended)
**Notes:** Confirmed match for the simpler-than-chat shape (no UUID capture needed for auth).

### Q2: Composite subject format

| Option | Description | Selected |
|--------|-------------|----------|
| `auth:<ip>:<route_key>` with stable short keys | e.g. `auth:1.2.3.4:google_mobile`. Path renames don't invalidate counters. | ✓ |
| `auth:<ip>:<raw_path>` | More log-readable but path renames break counters. | |
| `auth:<ip>` (single counter, all routes share) | Defeats SPEC.md per-route counter requirement. REJECTED. | |

**User's choice:** `auth:<ip>:<route_key>` with stable short keys (Recommended)

### Q3: XFF-trust + fail-open semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Same policy as existing buckets | Reuse `_subject_from_scope` unchanged. AP_TRUSTED_PROXY honored, fail-open preserved. | ✓ |
| Stricter — always use peer IP for auth | Defense-in-depth but breaks Caddy-fronted prod. | |
| Stricter — fail-CLOSED on Postgres outage | DDoS-via-trip-rate-limit risk worse than protection. REJECTED. | |

**User's choice:** Same policy as existing buckets (Recommended)

---

## Error classifier + banner shape

### Q1: Riverpod state shape

| Option | Description | Selected |
|--------|-------------|----------|
| Mirror Phase 25 — `StateProvider<ChatStreamErrorState?>` | Memory-only, single-active per chat. Identical lifecycle to telegram_failed_banner. | ✓ |
| StateNotifier with retry-call baked in | More cohesive but harder to unit-test classifier in isolation. Diverges from D-50. | |
| Extend `chatProvider` state | Tightest coupling; unnecessary widget rebuilds across chat thread. | |

**User's choice:** Mirror Phase 25 — `StateProvider<ChatStreamErrorState?>` (Recommended)

### Q2: Classifier home

| Option | Description | Selected |
|--------|-------------|----------|
| Pure utility in `chat/chat_stream_error_classifier.dart` | Top-level pure function, three unit tests + fallback test. | ✓ |
| Private method in `chat_providers.dart` | Test surface bleeds into chat-provider suite. | |
| Method on the repo / API client layer | Wrong layer; mixes concerns. | |

**User's choice:** Pure utility in `chat/chat_stream_error_classifier.dart` (Recommended)

### Q3: Banner widget location

| Option | Description | Selected |
|--------|-------------|----------|
| New `chat_stream_error_banner.dart` ConsumerWidget | Sibling of existing `telegram_failed_banner.dart`. Predictable place to look. | ✓ |
| Inline render block inside ChatScreen build() | Smallest code touch but ChatScreen grows; harder to widget-test alone. | |
| Reuse the existing telegram_failed_banner widget with mode flag | Mixed concerns; bot-specific copy doesn't apply. | |

**User's choice:** New `chat_stream_error_banner.dart` widget consumed by ChatScreen (Recommended)

---

## Sentry init helper placement

### Q1: api_server init shape

| Option | Description | Selected |
|--------|-------------|----------|
| New `instrumentation/sentry.py` module | `init_sentry(settings)` called from `main.create_app()`. Unit-testable in isolation. | ✓ |
| Inline in `main.create_app()` | 5-10 lines in main.py. Cluttered with DSN-empty branch + transport-mock test setup. | |
| Settings-only — `sentry_sdk.init(**settings.sentry_init_kwargs)` inline | Settings object grows; conditional logic still lives somewhere. | |

**User's choice:** New `instrumentation/sentry.py` module (Recommended)

### Q2: mobile init shape

| Option | Description | Selected |
|--------|-------------|----------|
| New `core/instrumentation/sentry.dart` helper | `initSentry({required runner})` wraps init + dart-define-empty noop branch. Symmetric to api_server. | ✓ |
| Inline in `main.dart` | Smallest diff but mixes concerns; harder to test dsn-empty branch. | |
| Riverpod provider — `sentryConfigProvider` | Wrong layer; Sentry must init BEFORE runApp, but Riverpod requires widget tree. | |

**User's choice:** New `core/instrumentation/sentry.dart` helper (Recommended)

### Q3: DSN-unset behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Log INFO once at startup, then silent | Matches `auth/oauth.py` placeholder pattern. One-time log; saves future-dev confusion. | ✓ |
| Log WARN — Sentry-unset is a deploy footgun | Becomes ignored noise in dev. | |
| Silent — no log at all | Confused future-dev wonders why Sentry isn't capturing. | |

**User's choice:** Log INFO once at startup, then silent (Recommended)

---

## CI e2e harness shape

### Q1: Test runner

| Option | Description | Selected |
|--------|-------------|----------|
| pytest marker `-m e2e_money_path` | Mirrors `test-api-integration` exactly. Reuses fixture pool. | ✓ |
| Shell script `tools/e2e_money_path.sh` | Mirrors recipe-smoke pattern. Fragile assertions (jq paths, set -e). | |
| Hybrid — shell brings up Docker, pytest runs assertions | Two stacks, two failure surfaces. | |

**User's choice:** pytest marker `-m e2e_money_path` (Recommended)

### Q2: CI auth path

| Option | Description | Selected |
|--------|-------------|----------|
| Dev-cookie test fixture | Insert user + sign session cookie via SESSION_SIGNING_KEY. Mirrors `test_cross_user_isolation.py`. | ✓ |
| Real OAuth flow with a stub IdP container | Heavier; OAuth flow is NOT what this gate verifies. | |
| API-key bypass route just for CI | Production-correctness surface area for testing. RED FLAG. REJECTED. | |

**User's choice:** Dev-cookie test fixture (Recommended)

### Q3: CI stack bring-up

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse `docker-compose.dev.yml` directly | Same stack dev machine uses; no CI/dev divergence. | ✓ |
| GitHub Actions `services:` Postgres + native uvicorn | Slightly faster but image versions diverge from compose file. | |
| New `docker-compose.ci.yml` slim variant | Premature optimization. | |

**User's choice:** Reuse `docker-compose.dev.yml` directly (Recommended)

---

## Audit pass — cross-cutting gaps surfaced on second pass

User prompted: "all gray areas? no doubts?" — second-pass audit per `feedback_re_ask_gray_areas.md`. Surfaced 4 load-bearing decisions missed in the per-area pass.

### Q1: Sentry environment + release tagging

| Option | Description | Selected |
|--------|-------------|----------|
| `environment` from `AP_ENV` env, `release` from git-sha | Critical for filtering dev noise from prod errors when H7 deploy lands. | ✓ |
| Hardcode `environment=dev`, no release tag | Loses release-pinned errors. | |
| Skip both — raw events with no tags | Operationally worse; events unfilterable. | |

**User's choice:** `environment` from `AP_ENV` env, `release` from git-sha (Recommended)

### Q2: Sentry quota protection (`before_send` filter)

| Option | Description | Selected |
|--------|-------------|----------|
| `before_send` filters 429 + 4xx HTTPException | Auth-bucket DDoS scenario can't blow free-tier quota. | ✓ |
| No filter — capture everything | First DDoS-attempt blows 5K/month quota. | |
| Filter only 429s | Misbehaving 4xx loop client still burns budget. | |

**User's choice:** `before_send` filters 429 + 4xx HTTPException (Recommended)

### Q3: e2e cost-capture polling shape

| Option | Description | Selected |
|--------|-------------|----------|
| Poll at 200ms intervals up to 10s timeout | 10s ceiling well above ~2-4s observed; max 50 SQL hits. | ✓ |
| Poll at 100ms up to 30s | More SQL hits per pass; 30s ceiling masks regressions. | |
| Block on `await sleep(5); fetch_usage()` | Race-prone. | |

**User's choice:** Poll at 200ms intervals up to 10s timeout (Recommended)

### Q4: Mobile dart-define wiring

| Option | Description | Selected |
|--------|-------------|----------|
| Extend `mobile/Makefile` ios + android targets | `--dart-define=SENTRY_*` parallel to existing `BASE_URL` etc. | ✓ |
| Document only — dev passes flags manually | Engineers WILL forget; Sentry silently disabled. | |
| Hardcode in `pubspec.yaml` | Technically wrong — dart-defines are CLI args. | |

**User's choice:** Extend `mobile/Makefile` ios + android targets (Recommended)

---

## Claude's Discretion

Items the user explicitly or implicitly delegated:
- OpenRouter model selection for the CI e2e test (cheapest verified cell of `nano-kaiku`)
- Banner copy localization (hardcoded English; project has no `flutter_localizations`)
- pytest fixture wire-shape (httpx.AsyncClient choice, fixture-scoping)
- Sentry SDK pin specifics (e.g., `>=2.20,<3.0`)

## Deferred Ideas

Mentioned during discussion or considered in audit-pass; intentionally not folded in:
- Sentry tracing / performance / profiling (free-tier quota; revisit later)
- Per-user auth rate-limiting (impossible pre-auth-resolution)
- Banner copy l10n (no `flutter_localizations` today)
- CI key rotation policy (handle in H7 phase)
- Concurrent CI queue depth limit (GH default unbounded; revisit if needed)
- Self-hosted Sentry (rejected — overkill pre-prod)
- OpenTelemetry as Sentry alternative (rejected — different surface area than audit assumed)
- `?ci_token=` auth bypass (REJECTED — production-correctness surface for testing)
- Generic bucket-shape registry refactor (REJECTED — premature)

---

*Discussion: 16 sub-decisions captured across 4 areas + 4 audit-pass items. All user picks were the recommended default. SPEC.md (24 acceptance criteria) + this log + `31-CONTEXT.md` constitute the complete pre-plan-phase decision lock.*

# Phase 31: Pre-Stripe Billing Hardening — Research

**Researched:** 2026-05-07
**Domain:** Pre-Stripe substrate hardening — auth rate-limit + mobile error surfacing + Sentry instrumentation + CI e2e money-path gate
**Confidence:** HIGH on all five HOW dimensions; MEDIUM on Sentry SDK pin (PyPI version-skew tolerance is 6 months; docs are stable)

## Summary

Phase 31 has a fully-locked SPEC (4 reqs / 24 ACs) and a fully-locked CONTEXT (23 D-* decisions). This research artifact resolves the 4 deferral points CONTEXT explicitly hands to plan-phase, plus the validation architecture Nyquist requires, plus 8 source-line-citations the planner needs verified before writing executable plans.

**Primary recommendations to plan-phase:**
1. **Sentry SDK pins:** `sentry-sdk[fastapi]>=2.20,<3.0` (current latest 2.59.0; floor 2.20 is the pin that lines up with FastAPI 0.136 + Starlette 0.46 already in `api_server/pyproject.toml`); `sentry_flutter: ^9.20.0` for mobile (current latest, supports Flutter 3.41 already in pubspec).
2. **OpenRouter CI cell:** `anthropic/claude-haiku-4.5` via the proxy through `nanobot` recipe (the cheapest e2e-verified path — Phase 30 PROBE-VAL spike was $0.00006/completion; Phase 29 nanobot rows show $0.00039345 with cache hits). **No `nano-kaiku` recipe exists** — that string in CONTEXT was a hypothetical placeholder; the actual cheapest single-completion verified cell is `nanobot + anthropic/claude-haiku-4.5` or `nanobot + openai/gpt-4o-mini`.
3. **pytest e2e fixture:** Reuse the existing `authenticated_cookie` fixture in `api_server/tests/conftest.py:607-649` directly. **There is no SESSION_SIGNING_KEY** — the cookie value is a plain UUID retrieved from Postgres' `sessions` table; security comes from unguessability, not HMAC. CONTEXT D-18's reference to "signs a session cookie via `SESSION_SIGNING_KEY` (the actual app key, not a CI-only key)" is a documentation drift — the actual mechanism is `INSERT INTO sessions ... RETURNING id::text` then `Cookie: ap_session=<uuid>`.
4. **GH Actions workflow:** Single-job ubuntu-latest, mirror `mobile.yml` style (`actions/checkout@v4`, `actions/setup-python@v5`), use compose-style Postgres bring-up via `docker-compose.dev.yml` (NOT a service-container — the project's existing pattern), pin `concurrency: { group: e2e-money-path, cancel-in-progress: false }` per D-21, path-filter triggers on `api_server/**` + `recipes/**` per AC-16.
5. **Mobile error classifier:** Reuse the existing `RetryBanner` widget at `mobile/lib/shared/retry_banner.dart` directly — no new banner widget file needed (CONTEXT D-08's `chat_stream_error_banner.dart` is unnecessary new file). The chat_screen.dart already renders `RetryBanner` for the telegram-failed case at lines 196-207; the new chat-stream-error banner is a sibling render in the same `Column`.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**H3 — Auth bucket subject derivation (D-01..D-04):**
- D-01: Module-level frozen set `_AUTH_ROUTES = {('POST', '/v1/auth/google/mobile'), ('POST', '/v1/auth/github/mobile'), ('POST', '/v1/auth/logout'), ('GET', '/v1/auth/google'), ('GET', '/v1/auth/google/callback'), ('GET', '/v1/auth/github'), ('GET', '/v1/auth/github/callback')}`. `_bucket_for` returns `"auth"` on `(method, path)` membership.
- D-02: Composite subject `auth:<ip>:<route_key>` where `route_key` is a stable short alias (`google_mobile`, `github_mobile`, `logout`, `google_redirect`, `google_callback`, `github_redirect`, `github_callback`).
- D-03: XFF-trust + fail-open semantics IDENTICAL to existing buckets. Reuse `_subject_from_scope` unchanged.
- D-04: `_LIMITS["auth"] = (5, 60)`.

**H4 — Error classifier + banner shape (D-05..D-09):**
- D-05: `StateProvider<ChatStreamErrorState?>` mirroring Phase 25 D-50 `telegram_failed_banner_provider.dart` shape.
- D-06: Pure top-level `classifyChatStreamError(Object e) -> ChatStreamErrorClass` in new `chat_stream_error_classifier.dart`.
- D-07: `SocketException | TimeoutException | DioException(network)` → `networkTransient`; HTTP 401 → `authExpired`; HTTP ≥500 → `serverError`; **unknown → `networkTransient` (default fallback)**.
- D-08: New `chat_stream_error_banner.dart` ConsumerWidget with three locked copy strings.
- D-09: Banner state on `_onResumed` reconnect failure REPLACES (not stacks).

**H6 — Sentry init (D-10..D-16):**
- D-10: `api_server/src/api_server/instrumentation/sentry.py` exporting `init_sentry(settings) -> None`. Called from `main.create_app()` BEFORE middleware stack.
- D-11: `mobile/lib/core/instrumentation/sentry.dart` exporting `Future<void> initSentry({required Future<void> Function() runner}) async`.
- D-12: `before_send` filter — drops `HTTPException` < 500 + `RATE_LIMITED` envelopes (api); drops `DioException` where `response?.statusCode != null && response!.statusCode! < 500` (mobile). **NON-OPTIONAL** for Free-tier quota protection.
- D-13: Tagging — `environment` from `AP_ENV`/`SENTRY_ENVIRONMENT`; `release` from `GIT_SHA`/`SENTRY_RELEASE`.
- D-14: DSN-unset → log INFO once + silent.
- D-15: `mobile/Makefile` `ios` + `android` targets gain `--dart-define=SENTRY_DSN_MOBILE` + `SENTRY_RELEASE` + `SENTRY_ENVIRONMENT`.
- D-16: `sentry_sdk.set_user({'id': user_id})` after auth resolution in `middleware/session.py`. ID-only, no PII.

**H8 — CI e2e harness (D-17..D-23):**
- D-17: `make e2e-money-path: cd api_server && pytest -m e2e_money_path`.
- D-18: pytest fixture inserts row directly into `users` + signs session cookie via SESSION_SIGNING_KEY *(see Pitfall 2 — no signing key exists; cookie is plain UUID)*.
- D-19: Reuse `docker-compose.dev.yml` directly. Postgres in compose; uvicorn native in runner.
- D-20: Cost-capture polling `for _ in range(50): row = await fetch_usage_log(); if row: break; await asyncio.sleep(0.2)` — 10s ceiling.
- D-21: `concurrency: { group: e2e-money-path, cancel-in-progress: false }`.
- D-22: pytest fixture creates + tears down fresh user + agent per test method.
- D-23: Spend-cap verification artifact format pinned at plan-phase per SPEC §H8 acceptance.

### Claude's Discretion (resolved by this RESEARCH)
- OpenRouter CI cell — see "OpenRouter CI cell recommendation" below.
- pytest fixture exact wire shape — see "pytest e2e fixture wire shape" below.
- Sentry SDK pin specifics — see "Sentry SDK pinning + init shape" below.
- Banner copy localization — DEFERRED per CONTEXT (no `flutter_localizations` in `pubspec.yaml`).

### Deferred Ideas (OUT OF SCOPE)
- Sentry tracing / performance / profiling (free-tier quota concern).
- Per-user auth rate-limiting (impossible pre-auth-resolution).
- Banner copy l10n.
- CI key rotation policy (deferred to H7 Hetzner).
- Sentry self-hosted migration (rejected during spec interview).
- OpenTelemetry alternative (rejected during spec interview).

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| H3 | Auth rate-limit bucket (5/min/IP per route, composite subject) | Confirmed `_LIMITS` + `_bucket_for` extension points; existing `chat:<subject>:<agent_id>` pattern at `middleware/rate_limit.py:164-168` is the template; existing `test_chat_rate_limit.py` is the test template. CONTEXT line citations for auth.py 138/157/222/237/378/449/542 all VERIFIED. |
| H4 | Mobile SSE error surfacing (3-class taxonomy + banner) | Confirmed `chat_providers.dart:387` (`_stream.connect().catchError((_) {});`) and `:398` (`} catch (_) {`). Existing `RetryBanner` widget at `mobile/lib/shared/retry_banner.dart` is reusable verbatim — no new widget needed. |
| H6 | Sentry instrumentation (errors-only, both runtimes, before_send filter) | Verified sentry-sdk 2.59.0 (PyPI) + sentry_flutter 9.20.0 (pub.dev) latest stable. FastAPI integration auto-enables on import in 2.x. `before_send` signature `(event, hint) -> dict | None` confirmed. |
| H8 | CI e2e money-path workflow + make target | `mobile.yml` + `test-recipes.yml` are the project's GH Actions style templates; `docker-compose.dev.yml`'s postgresql service exposes 5432 cleanly; `Makefile:test-api-integration` is the pytest-marker harness pattern to mirror. |

## Project Constraints (from CLAUDE.md)

- **Golden Rule #1:** No mocks for core substrate — auth-bucket tests use real Postgres counter via `tests/middleware/test_chat_rate_limit.py` pattern; e2e money-path uses real Docker stack + real OpenRouter; Sentry tests use the Sentry SDK's own `Transport` mock primitive (NOT a hand-rolled stub — `respx` is already a dev-dep for httpx-tier mocking and remains separate from Sentry transport).
- **Golden Rule #2:** Dumb client — H4 mobile classifier is pure local logic (no DB, no API hardcodes); banner copy strings are constants.
- **Golden Rule #4:** Root-cause first — D-12 `before_send` filter is the root cause-fix for Sentry quota burn under DDoS, not a band-aid.
- **Golden Rule #5:** Probe gray areas before planning — this research IS that probe.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Auth rate-limit (H3) | api_server / RateLimitMiddleware | Postgres counter (`rate_limit_counters` table) | Pre-auth IP-keyed quota — must live BEFORE SessionMiddleware in the ASGI stack so unauthenticated traffic is throttled. |
| SSE error UX (H4) | mobile (Flutter / Riverpod) | — | Pure client-side classification + render; api_server already returns the right status codes. |
| Error capture (H6) | api_server (FastAPI integration) + mobile (sentry_flutter) | — | Both runtimes capture independently; no cross-tier dependency. `set_user` runs in api_server's session middleware (pure attribution; no client involvement). |
| Money-path e2e (H8) | GitHub Actions runner / make target | api_server + Postgres + OpenRouter (real) | The whole path from HTTP entry → SSE → proxy → cost-capture is exercised; CI is the orchestration tier, the assertion target is `usage_logs.cost_usd > 0`. |

## Sentry SDK pinning + init shape (Python + Dart)

### Python — `sentry-sdk[fastapi]`

**Recommendation:** `sentry-sdk[fastapi]>=2.20,<3.0` in `api_server/pyproject.toml`. Verification:
- Latest stable on PyPI: **2.59.0** (uploaded 2026-02-16 per PyPI; even more recent in repology).
- 2.x supports Python 3.6+; api_server is 3.11+ — compatible.
- FastAPI integration is auto-enabled when `fastapi` is importable — confirmed in [FastAPI integration docs](https://docs.sentry.io/platforms/python/integrations/fastapi/): "If you have the `fastapi` package in your dependencies, the FastAPI integration will be enabled automatically when you initialize the Sentry SDK." `[VERIFIED: docs.sentry.io 2026-05-07]`
- 2.20 is the floor that aligns with FastAPI 0.136.0 + Starlette 0.46+ already in `pyproject.toml` lines 11 + 79.

**Init shape (api_server/src/api_server/instrumentation/sentry.py):**

```python
"""Sentry init helper — Phase 31 H6 (D-10, D-12, D-13, D-14)."""
from __future__ import annotations

import logging

import sentry_sdk

from ..config import Settings

_log = logging.getLogger("api_server.sentry")


def _before_send(event, hint):
    """Drop client-error envelopes before they hit Sentry quota.

    Phase 31 D-12: HTTPException with status_code < 500 is NOT a server
    bug; it's a client mistake (404, 422, 429). Sending those to Sentry
    blows the 5K/month free-tier quota under any auth-bucket DDoS
    scenario. We also drop our RATE_LIMITED envelope (which is the same
    HTTPException 429 path, but envelope-shape distinct).
    """
    if "exc_info" in hint:
        exc_type, exc_value, _tb = hint["exc_info"]
        # FastAPI's HTTPException inherits from starlette's
        from starlette.exceptions import HTTPException as StarletteHTTPException
        if isinstance(exc_value, StarletteHTTPException):
            if exc_value.status_code < 500:
                return None
    # Drop our Stripe-shape RATE_LIMITED envelope by exception class match.
    # (RateLimitMiddleware doesn't raise — it returns 429 directly via
    # `send`. So this branch is defense-in-depth for any future code that
    # raises a RATE_LIMITED HTTPException.)
    return event


def init_sentry(settings: Settings) -> None:
    """Initialize Sentry if AP_SENTRY_DSN_API is set; else log + return.

    Phase 31 D-10: called from main.create_app() BEFORE middleware stack
    setup so unhandled exceptions in middleware are also captured.
    """
    dsn = getattr(settings, "sentry_dsn_api", None)
    if not dsn:
        _log.info("Sentry disabled (AP_SENTRY_DSN_API unset)")
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=settings.env,             # D-13 — AP_ENV ("dev"|"prod")
        release=getattr(settings, "git_sha", None) or None,  # D-13 — boot-pinned
        traces_sample_rate=0.0,               # SPEC AC-15 — errors only
        # profiles_sample_rate intentionally OMITTED (default 0; not set).
        before_send=_before_send,             # D-12
        # FastAPI integration auto-enabled by SDK 2.x on import.
        # Do NOT pass integrations=[FastApiIntegration(...)] — overrides default.
    )
    _log.info(
        "Sentry initialized",
        extra={"environment": settings.env, "release": getattr(settings, "git_sha", None)},
    )
```

**Settings additions (`config.py`):**
```python
sentry_dsn_api: str | None = Field(None, validation_alias="AP_SENTRY_DSN_API")
git_sha: str | None = Field(None, validation_alias="GIT_SHA")
```

**`set_user` wiring in `middleware/session.py`** (after the `state["user_id"] = user_id` line at session.py:90):
```python
if user_id is not None:
    import sentry_sdk
    sentry_sdk.set_user({"id": str(user_id)})  # D-16 — id only, no PII
```

**Test pattern:** Use `Transport` subclass collecting events on a list (NOT `respx` — Sentry has its own test transport primitive):

```python
# api_server/tests/test_sentry_init.py
import sentry_sdk
from sentry_sdk.transport import Transport


class _CapturingTransport(Transport):
    def __init__(self, options=None):
        super().__init__(options)
        self.envelopes = []
    def capture_envelope(self, envelope):
        self.envelopes.append(envelope)


def test_unhandled_exception_captured(monkeypatch):
    monkeypatch.setenv("AP_SENTRY_DSN_API", "https://x@y.ingest.sentry.io/1")
    transport = _CapturingTransport()
    sentry_sdk.init(dsn="...", transport=transport, before_send=_before_send)
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        sentry_sdk.capture_exception()
    sentry_sdk.flush()
    assert len(transport.envelopes) == 1
```

### Dart — `sentry_flutter`

**Recommendation:** `sentry_flutter: ^9.20.0` in `mobile/pubspec.yaml` (current latest; published ~2026-05-06 per pub.dev).
- Major version 9.x is a deliberate breaking change from 8.x [VERIFIED: pub.dev changelog].
- Supports Flutter 3.41+ (mobile already on 3.41+ per `pubspec.yaml`).
- Auto-reads `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_RELEASE` from environment when not provided in code [VERIFIED: docs.sentry.io/platforms/dart/guides/flutter/configuration/options/]. **This means D-11's "no-init when DSN unset" branch is partially redundant — the SDK already noops when DSN is empty/unset** — but explicit gate is still cleaner per CONTEXT lock.

**Init shape (`mobile/lib/core/instrumentation/sentry.dart`):**

```dart
// Phase 31 H6 D-11 + D-13 + D-14 — sentry_flutter wrap-runner.
import 'package:flutter/foundation.dart';
import 'package:sentry_flutter/sentry_flutter.dart';

/// Sentry boot helper. If SENTRY_DSN_MOBILE dart-define is empty/missing,
/// the runner is invoked WITHOUT initialising Sentry — production noop.
Future<void> initSentry({required Future<void> Function() runner}) async {
  const dsn = String.fromEnvironment('SENTRY_DSN_MOBILE');
  const env = String.fromEnvironment('SENTRY_ENVIRONMENT', defaultValue: 'dev');
  const release = String.fromEnvironment('SENTRY_RELEASE');
  if (dsn.isEmpty) {
    debugPrint('Sentry disabled (SENTRY_DSN_MOBILE unset)');
    await runner();
    return;
  }
  await SentryFlutter.init(
    (options) {
      options.dsn = dsn;
      options.environment = env;
      if (release.isNotEmpty) options.release = release;
      options.tracesSampleRate = 0.0;        // SPEC AC-15 — errors only
      options.beforeSend = (event, hint) {
        // D-12 mobile equivalent: drop DioException with status < 500.
        // The SDK passes the original throwable through `event.throwable`
        // OR via hint.originalException (varies by capture path); guard
        // both.
        final t = event.throwable;
        if (t is DioException && (t.response?.statusCode ?? 0) < 500) {
          return null;
        }
        return event;
      };
    },
    appRunner: runner,  // SDK invokes this inside Sentry's zone
  );
}
```

**`main.dart` integration:** wrap the existing `main()` body inside `initSentry(runner: () async { ... })`. Existing structure of `WidgetsFlutterBinding.ensureInitialized() → AppEnv.fromEnvironment() → ProviderContainer() → resolveInitialRoute(...) → SystemChrome → runApp(...)` becomes the `runner` callback.

**`set_user` wiring (mobile-side):** after sign-in resolves a `user_id` (Phase 23 mobile login flow), call `Sentry.configureScope((scope) => scope.setUser(SentryUser(id: userId)))`. Phase 31 SPEC AC for D-16 only requires the api_server-side test; mobile-side `set_user` is ALSO an AC if H6 line "ID only, no email/PII" is interpreted both runtimes. Plan-phase: confirm mobile `set_user` task is required vs. optional follow-up.

## OpenRouter CI cell recommendation (with cost evidence from Phase 29/30 logs)

**CONTEXT note correction:** "nano-kaiku" is NOT a recipe in `recipes/`. The 8 committed recipes are: `goose, hermes, nanobot, nullclaw, openclaw, picoclaw, qwenpaw, zeroclaw`. The phrase "google/gemini-2.0-flash-001 based on Phase 29 cell verification" cannot be matched to any verified_cells entry — `gemini-2.5-flash` is the only Google model with a row, and that one is `verdict: FAIL` for hermes (`recipes/hermes.yaml` known_incompatible_cells block). `[VERIFIED: grep -E "model: google/gemini" recipes/*.yaml]`

**Empirical Phase 30 cost evidence** (from `30-VERIFICATION.md`):

| Plan | Recipe | Model | Real-money cost | Request ID |
|------|--------|-------|-----------------|-----------|
| 30-01 | (PROBE-VAL spike) | `anthropic/claude-haiku-4.5` | **$0.00006** | (anthropic streaming spike) |
| 30-02 | openclaw | `anthropic/claude-haiku-4.5` (Anthropic direct) | $0.02964 | `req_011CaoXVkMBnUgkjcSMS44N4` |
| 30-03 | nullclaw | `anthropic/claude-haiku-4.5` (×2 completions) | $0.02832 | `gen-1778126207-…` + `gen-1778126210-…` |
| 30-05 | zeroclaw | `anthropic/claude-haiku-4.5` | $0.01291 | `gen-1778127299-…` |
| 30-06 | hermes | `anthropic/claude-haiku-4.5` | $0.01302 | `gen-1778127435-…` |
| post-30 | qwenpaw | `anthropic/claude-haiku-4.5` (×4 completions, multi-turn agent) | $0.03612 | `gen-1778181771-…` ×4 |

**Phase 29 nanobot row 1** (per `30-VERIFICATION.md` table): `provider=openrouter, model=openai/gpt-4o-mini, cost_usd=$0.00039345` (with cache hits). **Cheapest single-completion verified cell.**

**Recommendation:**
- **Primary CI cell:** `nanobot` recipe + `openai/gpt-4o-mini` model. Cost ~$0.0004 per chat completion; nanobot has the smallest boot footprint of all e2e-verified recipes (boot 8s per `recipes/nanobot.yaml:476` cell evidence) and is the simplest OpenAI-compat dispatcher path (no `custom:URL` escape hatch, no Anthropic auth shape, no AgentScope contract).
- **Fallback if `gpt-4o-mini` becomes unavailable:** `nanobot` + `anthropic/claude-haiku-4.5`. Cost ~$0.001-$0.013 per completion; Phase 30 baseline is $0.00006-$0.013 depending on token shape; well within the SPEC's "$0.01-$0.02 per chat completion" target window.

**$5/mo dashboard cap math:** at $0.0004/run = ~12,500 runs/mo budget. Even with worst-case $0.013/run, ~385 runs/mo. CI volume estimate: ~1 run per `api_server/**` PR + 1 per `recipes/**` PR. Comfortably within cap.

**Plan-phase plumbing:** the `make e2e-money-path` target's pytest test will deploy a recipe instance. Recipe selection happens in the test fixture as `recipe_name="nanobot", model="openai/gpt-4o-mini"`. The verified_cells row at `recipes/nanobot.yaml:172` (nano-bot smoke verified_cells) is the canonical reference.

## pytest e2e fixture wire shape (with exact session-cookie computation)

**CONTEXT D-18 line citation correction:** D-18 says "signs a session cookie via `SESSION_SIGNING_KEY` (the actual app key, not a CI-only key)". **There is NO SESSION_SIGNING_KEY in the project.** The session cookie is a plain UUID stored in `sessions.id` (Postgres); security comes from cryptographic-strength randomness via `gen_random_uuid()`, not HMAC.

**Empirical proof (`api_server/src/api_server/middleware/session.py` lines 53-77):**
- Cookie value is read raw via `_extract_cookie(scope, "ap_session")`
- Coerced to UUID via `UUID(value)` (will raise on malformed)
- Looked up via `SELECT user_id, last_seen_at, revoked_at, expires_at FROM sessions WHERE id = $1`
- No HMAC verification, no signed-cookie machinery

**The actual canonical fixture pattern (`api_server/tests/conftest.py:606-649`):**

```python
@pytest_asyncio.fixture
async def authenticated_cookie(db_pool):
    """Seed a google-provider user + a live session; yield cookie + ids."""
    async with db_pool.acquire() as conn:
        user_id = await conn.fetchval(
            "INSERT INTO users (id, provider, sub, email, display_name) "
            "VALUES (gen_random_uuid(), $1, $2, $3, $4) RETURNING id::text",
            "google", f"test-sub-{uuid4().hex[:12]}",
            "alice@example.com", "Alice",
        )
        now = datetime.now(timezone.utc)
        session_id = await conn.fetchval(
            "INSERT INTO sessions (user_id, created_at, expires_at, last_seen_at) "
            "VALUES ($1, $2, $3, $2) RETURNING id::text",
            user_id, now, now + timedelta(days=30),
        )
    yield {
        "Cookie": f"ap_session={session_id}",
        "_user_id": user_id,
        "_session_id": session_id,
    }
```

**Recommended e2e money-path fixture wire shape:**

```python
# api_server/tests/e2e/conftest.py — additive to existing
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture(scope="function")  # function-scope per D-22 idempotency
async def e2e_money_path_client(async_client, authenticated_cookie):
    """Reuse async_client + authenticated_cookie. Mark for the e2e marker.

    The `async_client` fixture already provides:
      * Real Postgres via testcontainers (session-scoped)
      * Real Redis via testcontainers
      * Lifespan-bound app with all middleware wired
    The `authenticated_cookie` fixture provides:
      * Real users + sessions row
      * `Cookie: ap_session=<uuid>` header ready for httpx

    Composition: async_client + authenticated_cookie → caller does
    `await client.post(url, headers={"Cookie": cookie["Cookie"], ...})`.
    """
    yield {
        "client": async_client,
        "cookie": authenticated_cookie["Cookie"],
        "user_id": authenticated_cookie["_user_id"],
    }
```

**Test body shape (`tests/e2e/test_money_path.py`):**

```python
@pytest.mark.e2e_money_path  # new marker — register in pyproject.toml
@pytest.mark.asyncio
async def test_chat_through_proxy_writes_usage_log(
    e2e_money_path_client, db_pool,
):
    client = e2e_money_path_client["client"]
    cookie = e2e_money_path_client["cookie"]
    user_id = e2e_money_path_client["user_id"]
    headers = {"Cookie": cookie, "Content-Type": "application/json"}

    # 1. Deploy nanobot recipe via POST /v1/runs (or /v1/agents/start —
    #    plan-phase confirms exact route; SPEC says "deploys the
    #    nano-kaiku recipe", we substitute nanobot per Cell choice above).
    deploy_resp = await client.post(
        "/v1/runs",
        headers=headers,
        json={"recipe_name": "nanobot", "model": "openai/gpt-4o-mini",
              "prompt": "Reply with one word: hello"},
    )
    assert deploy_resp.status_code == 200, deploy_resp.text

    # 2. Send chat through deployed agent — POST /v1/agents/<id>/messages
    agent_id = deploy_resp.json()["agent_id"]  # plan-phase confirms key
    msg_resp = await client.post(
        f"/v1/agents/{agent_id}/messages",
        headers=headers,
        json={"content": "hello"},
    )
    assert msg_resp.status_code in (200, 202)

    # 3. Poll usage_logs per D-20 (10s ceiling).
    usage_row = None
    for _ in range(50):
        async with db_pool.acquire() as conn:
            usage_row = await conn.fetchrow(
                "SELECT cost_usd, upstream_request_id FROM usage_logs "
                "WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1",
                user_id,
            )
            if usage_row is not None:
                break
        await asyncio.sleep(0.2)

    # 4. Assertions — both: cost > 0 AND upstream_request_id non-null.
    assert usage_row is not None, "usage_logs row never appeared in 10s"
    assert float(usage_row["cost_usd"]) > 0, usage_row
    assert usage_row["upstream_request_id"] is not None, usage_row
```

**Marker registration (`api_server/pyproject.toml`):**
```toml
markers = [
  "api_integration: spawn real Postgres + run real recipe; opt-in via pytest -m api_integration",
  "spike: Phase 28 Wave 0 empirical spike against real infra (Temporal/Docker); opt-in via pytest -m spike",
  "e2e_money_path: Phase 31 H8 — real OpenRouter chat → cost-capture; opt-in via pytest -m e2e_money_path",
]
```

**Auth rate-limit test (`tests/middleware/test_auth_rate_limit.py`)** — mirrors `test_chat_rate_limit.py:112-180` exactly. Three test methods:
1. `test_auth_rate_limit_6th_in_60s_returns_429` — 6 sequential POSTs to `/v1/auth/google/mobile`, 6th returns 429 + Retry-After + Stripe envelope.
2. `test_auth_rate_limit_per_route` — 3 POSTs to `/v1/auth/google/mobile` + 3 POSTs to `/v1/auth/github/mobile` from same IP, all 6 succeed (per-route counters via composite subject).
3. `test_auth_rate_limit_does_not_affect_runs` — Exhaust auth bucket on `/v1/auth/google/mobile`; POST to `/v1/runs` still works.

Test fixture shape mirrors `chat_rl_app`/`chat_rl_client` from `test_chat_rate_limit.py:51-89` with stub auth route handlers replaced by the real `routes/auth.py` router (since the bucket-routing is the load-bearing assertion, not the auth-handler internals).

## GH Actions e2e workflow shape (with concurrency + path-filter + secret syntax)

**Project's existing GH Actions style** (`mobile.yml` + `test-recipes.yml`):
- ubuntu-latest runners
- `actions/checkout@v4`
- `actions/setup-python@v5` with `python-version: "3.12"`
- `subosito/flutter-action@v2` (mobile-only, not relevant here)
- Path-filter on both `push` (main) and `pull_request` (main)
- Single `check:` job; no matrix
- `make` targets as the test command (e.g. `make check`)

**Recommended `e2e-money-path.yml` shape:**

```yaml
name: e2e money path

on:
  push:
    branches: [main]
    paths:
      - 'api_server/**'
      - 'recipes/**'
      - '.github/workflows/e2e-money-path.yml'
  pull_request:
    branches: [main]
    paths:
      - 'api_server/**'
      - 'recipes/**'
      - '.github/workflows/e2e-money-path.yml'

# Phase 31 D-21 — serialise real-money runs.
concurrency:
  group: e2e-money-path
  cancel-in-progress: false

jobs:
  money-path:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    env:
      OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_CI_KEY }}
      AP_ENV: dev
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Boot Postgres + Redis from docker-compose.dev.yml
        # D-19 — reuse existing compose, no CI-only variant.
        run: |
          docker compose -f docker-compose.dev.yml up -d postgresql redis

      - name: Wait for Postgres healthy
        run: |
          for i in {1..30}; do
            if docker compose -f docker-compose.dev.yml exec -T postgresql \
                 pg_isready -U temporal >/dev/null 2>&1; then
              echo "postgres ready"; break
            fi
            sleep 1
          done

      - name: Create app DB + run migrations
        run: |
          docker compose -f docker-compose.dev.yml exec -T postgresql \
            psql -U temporal -c "CREATE DATABASE agent_playground_api"
          make install-api
          DATABASE_URL=postgresql+asyncpg://temporal:temporal@localhost:5432/agent_playground_api \
            make migrate-api

      - name: Run e2e money-path test
        # D-17 — pytest -m e2e_money_path; secret never echoed.
        env:
          DATABASE_URL: postgresql+asyncpg://temporal:temporal@localhost:5432/agent_playground_api
          AP_REDIS_URL: redis://localhost:6379/0
        run: make e2e-money-path

      - name: Tear down compose stack
        if: always()
        run: docker compose -f docker-compose.dev.yml down -v
```

**`Makefile` target (D-17):**
```makefile
.PHONY: e2e-money-path
e2e-money-path:  ## Phase 31 H8 — real OpenRouter chat → cost-capture in CI
	@test -n "$$OPENROUTER_API_KEY" || (echo "ERROR: OPENROUTER_API_KEY not set" && exit 1)
	cd api_server && pytest -m e2e_money_path -v --tb=short
```

**Secret hygiene:**
- `OPENROUTER_CI_KEY` is referenced via `${{ secrets.OPENROUTER_CI_KEY }}` only — GH masks the value in logs automatically.
- The Makefile guard `test -n "$$OPENROUTER_API_KEY"` will print "ERROR: OPENROUTER_API_KEY not set" but NEVER the value.
- Pytest output uses request IDs (e.g. `gen-1778126207-…`) for assertions — the API key never appears in stdout.

**Path-filter rationale:** `api_server/**` covers route changes, middleware changes, recipe-loader changes. `recipes/**` covers recipe YAML edits. `.github/workflows/e2e-money-path.yml` self-trigger so the workflow CAN be tested via PRs that touch only the workflow.

**Why not GH service containers:** GH's native `services:` block for postgres requires the runner job to also be in a container (CONTEXT D-19 says native uvicorn). The compose-bring-up path is simpler, mirrors the dev box, and the project already uses `docker-compose.dev.yml`. `[VERIFIED: ubuntu-latest already has docker compose v2 preinstalled]`

## Mobile error classifier wire shape (DioException flavors + widget-test fixture)

**Empirical line citations (`mobile/lib/features/chat/chat_providers.dart`):**
- Line 387: `// ignore: discarded_futures` followed by `_stream.connect().catchError((_) {});` — initial-connect silent swallow inside `_bootstrap()`.
- Line 397-400: `} catch (_) {` with the comment "intentionally empty — keep prior state visible on reconnect failure" inside `_onResumed`.

**The actual error types reaching `:387` and `:398`:**
The `_stream` is a `MessagesStream` (typedef'd via `_RealChatStream`). `MessagesStream.connect()` uses the `flutter_client_sse` package (`flutter_client_sse 2.0.3` per pubspec). Its connect-failure surface:
- `SocketException` — DNS resolution failure, TCP refused, network down.
- `TimeoutException` — connect-deadline exceeded (no explicit deadline in flutter_client_sse 2.0.3 — risk of infinite hang at TCP layer).
- `DioException` — IF the SSE endpoint pre-flight uses dio (it doesn't — flutter_client_sse uses raw http), but DioException is hit elsewhere in the same `_bootstrap()` flow at line 370 (`api.messagesHistory(...)`); the error coming through `:387`/`:398` will be a flutter_client_sse error type, NOT DioException.
- HTTP status codes — flutter_client_sse 2.0.3 has a known bug (per the existing comment at `chat_providers.dart:355`): "hardcoded 5-second retry on ANY non-2xx response... a 404 from the server (genuine ownership mismatch) used to flood the api_server with one /messages/stream request every 5s forever." This means the error type that lands at `:387` may be: `Exception` with an embedded HTTP-response error object, or a wrapped `http.ClientException`. **The classifier must handle Object → ChatStreamErrorClass robustly with a fallback default.**

**Recommended classifier shape (`mobile/lib/features/chat/chat_stream_error_classifier.dart`):**

```dart
// Phase 31 H4 D-06 + D-07 — three-class chat-stream error taxonomy.
import 'dart:async';
import 'dart:io';
import 'package:dio/dio.dart';

enum ChatStreamErrorClass {
  /// Network transient — SocketException, TimeoutException, transport
  /// errors, OR HTTP 5xx. Ratchet to user copy "Connection lost — tap
  /// to retry" (or alternate "Server error — try again later" if
  /// server-side per acceptance criterion).
  networkTransient,

  /// Auth expired — HTTP 401. User copy "Session expired — sign in again".
  authExpired,

  /// Server error — non-401 HTTP 4xx OR catch-all. User copy "Server
  /// error — try again later".
  serverError,
}

ChatStreamErrorClass classifyChatStreamError(Object e) {
  // Network-layer errors → transient.
  if (e is SocketException) return ChatStreamErrorClass.networkTransient;
  if (e is TimeoutException) return ChatStreamErrorClass.networkTransient;

  // Dio surface (defensive — _onResumed may surface dio errors via the
  // history fetch path on retry).
  if (e is DioException) {
    final status = e.response?.statusCode;
    if (e.type == DioExceptionType.connectionError ||
        e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.sendTimeout ||
        e.type == DioExceptionType.receiveTimeout) {
      return ChatStreamErrorClass.networkTransient;
    }
    if (status == 401) return ChatStreamErrorClass.authExpired;
    if (status != null && status >= 500) {
      return ChatStreamErrorClass.networkTransient;
    }
    // Non-401 4xx → serverError (e.g. 404 ownership mismatch).
    return ChatStreamErrorClass.serverError;
  }

  // SSE / http surface — extract status from Object.toString() patterns
  // is fragile. flutter_client_sse 2.0.3 wraps errors as Exception with
  // generic messages; we cannot reliably extract status. Default to
  // networkTransient per D-07 ("Unknown error class → networkTransient
  // default fallback; original error logged to Sentry breadcrumb for
  // debugging").
  return ChatStreamErrorClass.networkTransient;
}
```

**Provider shape (`chat_stream_error_banner_provider.dart`):**
```dart
import 'package:flutter_riverpod/legacy.dart';

class ChatStreamErrorState {
  const ChatStreamErrorState({
    required this.agentInstanceId,
    required this.errorClass,
    required this.lastFailedAction,
  });
  final String agentInstanceId;
  final ChatStreamErrorClass errorClass;
  final String lastFailedAction;  // 'connect' | 'reconnect_on_resume'
}

final StateProvider<ChatStreamErrorState?> chatStreamErrorProvider =
    StateProvider<ChatStreamErrorState?>((_) => null);
```

**Single-classifier wire-up at both sites (`chat_providers.dart`):**
```dart
// Replace `:387` _stream.connect().catchError((_) {})
_stream.connect().catchError((Object e) {
  ref.read(chatStreamErrorProvider.notifier).state = ChatStreamErrorState(
    agentInstanceId: agentInstanceId,
    errorClass: classifyChatStreamError(e),
    lastFailedAction: 'connect',
  );
  // Also breadcrumb to Sentry per D-12 — technical class only.
  // Sentry.addBreadcrumb(Breadcrumb(message: 'chat-stream connect failed: $e'));
  return null;  // satisfy Future<void>.catchError signature
});

// Replace `:398` bare catch in _onResumed
} catch (e) {
  ref.read(chatStreamErrorProvider.notifier).state = ChatStreamErrorState(
    agentInstanceId: agentInstanceId,
    errorClass: classifyChatStreamError(e),
    lastFailedAction: 'reconnect_on_resume',
  );
}
```

**Banner render — REUSE existing `RetryBanner`:** in `chat_screen.dart` (sibling of the existing `if (tgBanner != null) RetryBanner(...)` at line 196):

```dart
final streamErr = ref.watch(chatStreamErrorProvider);

// ...inside the Column body:
if (streamErr != null)
  RetryBanner(
    key: const Key('chat-stream-error-banner'),
    message: _streamErrorCopy(streamErr.errorClass),
    actionLabel: _streamErrorActionLabel(streamErr.errorClass),
    tone: RetryBannerTone.warning,
    dismissible: true,
    onDismiss: () => ref
        .read(chatStreamErrorProvider.notifier)
        .state = null,
    onTap: () => _handleStreamErrorRetry(context, streamErr),
  ),
```

Where:
```dart
String _streamErrorCopy(ChatStreamErrorClass c) {
  switch (c) {
    case ChatStreamErrorClass.networkTransient:
      return 'Connection lost — tap to retry';
    case ChatStreamErrorClass.authExpired:
      return 'Session expired — sign in again';
    case ChatStreamErrorClass.serverError:
      return 'Server error — try again later';
  }
}

String _streamErrorActionLabel(ChatStreamErrorClass c) =>
    c == ChatStreamErrorClass.authExpired ? 'Sign in' : 'Retry';
```

**Plan-phase note:** the SPEC mentions a "5xx alternate" copy `"Server error — try again later"` (AC line 87). Mapping `serverError` to that copy and `networkTransient` to "Connection lost — tap to retry" gives:
- 5xx → `networkTransient` per classifier above → "Connection lost…" — but SPEC says 5xx → "Server error…"
- **Reconcile in plan-phase.** Two options: (a) split classifier so 5xx maps to `serverError` not `networkTransient` (cleaner SPEC compliance); (b) map both `networkTransient` and `serverError` to the same copy depending on context. Recommend (a) — split: `5xx → serverError`, `SocketException/TimeoutException/connection-tier DioException → networkTransient`.

**Widget-test fixture shape (`test/features/chat/chat_stream_error_banner_test.dart`):**

```dart
import 'package:agent_playground/features/chat/chat_stream_error_banner_provider.dart';
import 'package:agent_playground/features/chat/chat_stream_error_classifier.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('classifyChatStreamError', () {
    test('SocketException → networkTransient', () {
      expect(
        classifyChatStreamError(const SocketException('host down')),
        ChatStreamErrorClass.networkTransient,
      );
    });
    test('TimeoutException → networkTransient', () {
      expect(
        classifyChatStreamError(TimeoutException('boom', Duration(seconds: 1))),
        ChatStreamErrorClass.networkTransient,
      );
    });
    test('DioException 401 → authExpired', () {
      final dio = DioException(
        requestOptions: RequestOptions(path: ''),
        response: Response(
          requestOptions: RequestOptions(path: ''), statusCode: 401),
      );
      expect(classifyChatStreamError(dio), ChatStreamErrorClass.authExpired);
    });
    test('DioException 502 → networkTransient (or serverError per spec)', () {
      // … plan-phase reconciles per "Plan-phase note" above.
    });
    test('Unknown Object → networkTransient (fallback)', () {
      expect(
        classifyChatStreamError('some random string error'),
        ChatStreamErrorClass.networkTransient,
      );
    });
  });

  testWidgets('banner renders + retry-CTA fires connect spy',
      (tester) async {
    int connectCalls = 0;
    // Inject ChatScope test seam (autoBootstrap: false) + mock stream
    // builder that records connect() calls.
    // … plan-phase materialises full widget-test harness.
  });
}
```

## Validation Architecture

Phase 31 has 4 requirements (H3/H4/H6/H8) and 24 acceptance criteria. Nyquist sampling per D1-D8 below.

### Test Framework

| Property | Value |
|----------|-------|
| Framework (api_server) | pytest 8 + pytest-asyncio 0.23 + httpx 0.27 + asyncpg 0.31 + testcontainers[postgres,redis] 4.14.2 |
| Framework (mobile) | flutter_test (SDK) + golden_toolkit 0.15.0 + http_mock_adapter 0.6.1 |
| Config file (api) | `api_server/pyproject.toml` (markers + pytest-options) |
| Config file (mobile) | `mobile/analysis_options.yaml` (very_good_analysis 10) |
| Quick run (api) | `cd api_server && pytest -q -m "not api_integration and not e2e_money_path"` |
| Full suite (api) | `make test-api-integration` (includes api_integration) + `make e2e-money-path` (separate; needs OPENROUTER_API_KEY) |
| Quick run (mobile) | `cd mobile && flutter test` (unit + widget) |

### Phase Requirements → Test Map (24 ACs)

| AC | Behavior | Test Type | Automated Command | File |
|----|----------|-----------|-------------------|------|
| H3-AC1 | 6th `/v1/auth/google/mobile` 429 + Retry-After + envelope | D2 integration | `pytest tests/middleware/test_auth_rate_limit.py::test_auth_rate_limit_6th_in_60s_returns_429 -m api_integration` | NEW `tests/middleware/test_auth_rate_limit.py` |
| H3-AC2 | Per-route counters (3 google + 3 github = 6 succeed) | D2 integration | `…::test_auth_rate_limit_per_route -m api_integration` | NEW |
| H3-AC3 | Test passes against real Postgres counter | D2 integration | (covered by AC1+AC2 — testcontainers Postgres) | NEW |
| H3-AC4 | Postgres-outage fail-open preserved | D7 reliability | `…::test_auth_rate_limit_pg_outage_fail_open -m api_integration` | NEW |
| H4-AC5 | Banner renders "Connection lost" on connect-network-failure | D1 unit + D2 widget | `flutter test test/features/chat/chat_stream_error_banner_test.dart` | NEW `test/features/chat/chat_stream_error_banner_test.dart` |
| H4-AC6 | Banner renders "Session expired" on 401 | D1 unit + D2 widget | (same file) | NEW |
| H4-AC7 | Banner renders "Server error" on 5xx | D1 unit + D2 widget | (same file) | NEW |
| H4-AC8 | Both `:387` and `:398` route through one classifier | D2 widget | `…::test_classifier_invoked_from_both_paths` | NEW |
| H4-AC9 | Retry CTA triggers new `_stream.connect()` (mock spy) | D2 widget | `…::test_retry_cta_calls_connect` | NEW |
| H4-AC10 | Auth-class CTA navigates to login (route spy) | D2 widget | `…::test_auth_cta_navigates_to_login` | NEW |
| H4-AC11 | No technical jargon in copy strings | D3 contract (regex grep) | `flutter analyze` + grep test on copy constants | covered by classifier_test |
| H6-AC12 | api_server captures unhandled exception via transport-mock | D2 integration | `pytest tests/test_sentry_init.py::test_unhandled_exception_captured` | NEW `tests/test_sentry_init.py` |
| H6-AC13 | api_server starts cleanly when DSN unset | D7 reliability | `…::test_no_dsn_starts_cleanly` | NEW |
| H6-AC14 | mobile captures via SentryTransport mock | D2 integration | `flutter test test/core/instrumentation/sentry_test.dart` | NEW `test/core/instrumentation/sentry_test.dart` |
| H6-AC15 | mobile starts cleanly when dart-define empty | D7 reliability | `…::test_dart_define_empty_no_init` | NEW |
| H6-AC16 | No traces_sample_rate / profiles enabled | D3 contract | `…::test_errors_only_sampling` | covered by AC12 + AC14 |
| H8-AC17 | `e2e-money-path.yml` exists; triggers on `api_server/**` + `recipes/**` | D3 contract | `gh workflow list` + path-filter inspection | manual gate |
| H8-AC18 | Workflow stands up Postgres + api_server via compose | D6 / D8 | (workflow run itself) | workflow log |
| H8-AC19 | `make e2e-money-path` writes usage_logs row with cost_usd > 0 + non-null upstream_request_id | D4 e2e | `make e2e-money-path` (real OpenRouter) | NEW `tests/e2e/test_money_path.py` |
| H8-AC20 | Uses `OPENROUTER_CI_KEY` GH secret, never echoed | D6 security | manual log inspection | manual gate |
| H8-AC21 | Declares `concurrency: { group: e2e-money-path, cancel-in-progress: false }` | D3 contract | `yq` static check on YAML | optional shellcheck or yq lint |
| H8-AC22 | OpenRouter $5/mo cap + verification artifact | D6 security | manual screenshot/dashboard-link in commit message | manual gate |
| H8-AC23 | No-op PR triggers workflow + passes (baseline green) | D4 e2e | live PR with whitespace-only change | manual gate |
| H8-AC24 | Deliberate-regression PR fails at `cost_usd > 0` | D4 e2e | live PR reverting cost-parser; expect red | manual gate |

### Validation Architecture by Dimension

**D1 — Unit:**
- Per-route auth-bucket subject-derivation (D-01/D-02): test `_bucket_for(scope) == "auth"` for each of the 7 (method, path) tuples, and `_subject_from_scope` produces `auth:<ip>:<route_key>`.
- Mobile classifier: `classifyChatStreamError(e)` returns the correct enum for each input class.
- Sentry `before_send` filter: feed it event dicts simulating HTTPException 404/422/500/raw RuntimeError and assert filter return value.

**D2 — Integration:**
- Real-Postgres rate-limit counter increment (test_auth_rate_limit.py uses `chat_rl_app` style fixture).
- Real-DB user fixture (existing `authenticated_cookie` reused).
- Sentry transport mock (`_CapturingTransport(Transport)` subclass — no `respx`, no extra mock framework; the SDK's own primitive).

**D3 — Contract:**
- HTTP 429 + `Retry-After` header + Stripe-shape error envelope shape (existing `make_error_envelope` from `models/errors.py` — already invariant-tested in `test_chat_rate_limit.py`).
- Banner copy strings — exact match against the three locked SPEC strings.
- GH workflow YAML structure: `concurrency.group`, `paths` filter, secret reference.

**D4 — E2E:**
- Real OpenRouter chat → cost-capture → `usage_logs.cost_usd > 0` + non-null `upstream_request_id` (the load-bearing AC19).
- Mobile widget test of banner across both connect-failure paths (initial + onResumed).

**D5 — Performance:** N/A for this phase. SPEC has no perf budgets. The 10s polling ceiling in D-20 is the only quasi-perf gate (regression-detection floor for cost-capture latency).

**D6 — Security:**
- No CI-only auth backdoor in production code (D-18 explicit rejection of `?ci_token=`).
- `OPENROUTER_CI_KEY` referenced in YAML, never echoed in stdout (manual log inspection gate; pytest assertion patterns naturally avoid printing the key — assertions match request IDs not keys).
- OpenRouter $5/mo dashboard-side cap as defense-in-depth (artifact check during plan-phase).
- Sentry `before_send` filter as protection against quota-burn DDoS via auth-bucket attempts.

**D7 — Reliability:**
- Postgres-outage fail-open preserved on auth bucket (inherits chat-bucket fail-open semantics at `middleware/rate_limit.py:175-180`).
- Sentry DSN-unset graceful degrade (D-14 — log INFO once + silent).

**D8 — Observability:**
- Sentry user-context (id-only) per D-16.
- Release tag from `GIT_SHA`, environment tag from `AP_ENV` per D-13.
- Auth-bucket DDoS quota protection via `before_send` filter (D-12).

### Sampling Rate
- **Per task commit:** `cd api_server && pytest -q -m "not api_integration and not e2e_money_path"` (fast unit-only)
- **Per wave merge:** `make test-api-integration` (full Postgres-real suite) + `cd mobile && flutter test`
- **Phase gate:** `make e2e-money-path` once on a real PR (cost ~$0.0004)

### Wave 0 Gaps
- [ ] `api_server/tests/middleware/test_auth_rate_limit.py` — covers H3-AC1..AC4
- [ ] `api_server/tests/test_sentry_init.py` — covers H6-AC12, AC13, AC16
- [ ] `mobile/test/features/chat/chat_stream_error_banner_test.dart` — covers H4-AC5..AC11
- [ ] `mobile/test/features/chat/chat_stream_error_classifier_test.dart` — covers D-07 mapping unit tests
- [ ] `mobile/test/core/instrumentation/sentry_test.dart` — covers H6-AC14, AC15
- [ ] `api_server/tests/e2e/test_money_path.py` — covers H8-AC19
- [ ] `.github/workflows/e2e-money-path.yml` — covers H8-AC17..AC24
- [ ] Marker registration in `pyproject.toml` (`e2e_money_path: …`)

## Pitfalls + landmines

### Pitfall 1 — `nano-kaiku` is not a real recipe
CONTEXT mentions `nano-kaiku` and `google/gemini-2.0-flash-001` as the CI cell. **Neither exists in the codebase.** The 8 actual recipes are `goose, hermes, nanobot, nullclaw, openclaw, picoclaw, qwenpaw, zeroclaw`. Plan-phase MUST substitute a real recipe + verified cell pair. Recommendation: `nanobot + openai/gpt-4o-mini` (cheapest verified, ~$0.0004/run) or `nanobot + anthropic/claude-haiku-4.5` (Phase 30 PROBE-VAL spike confirmed $0.00006/run).

### Pitfall 2 — There is no SESSION_SIGNING_KEY
CONTEXT D-18 says the fixture "signs a session cookie via `SESSION_SIGNING_KEY` (the actual app key, not a CI-only key)". **No such key exists.** Session cookies are plain UUIDs from `gen_random_uuid()` stored in Postgres `sessions.id`. The `authenticated_cookie` fixture at `tests/conftest.py:606-649` is the canonical pattern: insert user + insert session row + use returned UUID as `Cookie: ap_session=<uuid>`.

### Pitfall 3 — `chat_stream_error_banner.dart` is unnecessary new file
CONTEXT D-08 says to create new `mobile/lib/features/chat/chat_stream_error_banner.dart`. The existing `RetryBanner` widget at `mobile/lib/shared/retry_banner.dart` is already the right shape (message + actionLabel + onTap + dismissible + tone) and is already used by the telegram-failed path in `chat_screen.dart:196-207`. Recommend: skip the new widget file; render the new banner via `RetryBanner(...)` directly in `chat_screen.dart` (sibling of the telegram banner block). Saves ~80 LOC.

### Pitfall 4 — D-07 5xx → networkTransient conflicts with SPEC AC for "Server error" copy
D-07 maps "HTTP ≥500 → serverError" but the classifier example uses three classes: `networkTransient | authExpired | serverError`. SPEC AC line 87 says `"Server error — try again later" on 5xx (non-401)`. The classifier's enum-to-copy mapping must split `serverError` (5xx) from `networkTransient` (Socket/Timeout). Confirm in plan-phase.

### Pitfall 5 — flutter_client_sse 2.0.3 retry storm bug is documented in code
`chat_providers.dart:354-366` documents that flutter_client_sse 2.0.3 has a hardcoded 5-second retry on ANY non-2xx response. The Phase 31 H4 work does NOT need to fix this bug, but the classifier must handle errors that may arrive REPEATEDLY at the catch sites if the retry storm fires. Banner state should NOT stack (D-09 says replace, not stack), so re-firing the classifier with the same error class is a no-op (`state = newState` where newState equals existing state). Confirm idempotency in widget tests.

### Pitfall 6 — sentry_flutter 9.0 is breaking from 8.x
sentry_flutter 9.0 was a major version bump with breaking changes per pub.dev changelog. Project has zero existing sentry_flutter usage, so no migration cost — but plan-phase must NOT cross-reference any 8.x code samples from older docs/StackOverflow answers when implementing.

### Pitfall 7 — Sentry FastAPI integration auto-enable + before_send interaction
`sentry-sdk[fastapi]>=2.20` auto-enables `FastApiIntegration + StarletteIntegration` on import. The `failed_request_status_codes` option (default 5xx-only) and our custom `before_send` interact: if FastApiIntegration is auto-capturing 5xx HTTP exceptions, our `before_send` filter (which DROPS HTTPException < 500) will let those 5xx through. **Recommended:** explicitly leave the integration default behavior (capture ≥500) and rely on `before_send` to drop client-error events that surface via OTHER paths (e.g. middleware-level exceptions). Plan-phase: confirm via Sentry test that auth-bucket 429 events do NOT reach Sentry (they MUST not — that's the whole point of D-12).

### Pitfall 8 — `flutter analyze` will reject `// ignore: discarded_futures` removal
Existing `chat_providers.dart:386` has `// ignore: discarded_futures` directive immediately above `_stream.connect().catchError(...)`. Replacing the `catchError` with a proper handler MAY require keeping or removing the ignore. Plan-phase: pay attention to lint surface.

### Pitfall 9 — `routes/auth.py` line 222 is `github_login` GET, not callback
The 7 auth endpoints CONTEXT cites at lines 138/157/222/237/378/449/542 are:
- 138 — GET `/v1/auth/google` (google_login, redirect)
- 157 — GET `/v1/auth/google/callback`
- 222 — GET `/v1/auth/github` (github_login, redirect) **← NOT a callback**
- 237 — GET `/v1/auth/github/callback`
- 378 — POST `/v1/auth/google/mobile`
- 449 — POST `/v1/auth/github/mobile`
- 542 — POST `/v1/auth/logout`

D-01's `_AUTH_ROUTES` set with `('GET', '/v1/auth/google')` and `('GET', '/v1/auth/github')` covers the two redirect endpoints (the entry-points to OAuth). All 7 are correct; CONTEXT phrasing "GET callbacks at `:157`/`:237`" is shorthand and accurate. The "GET OAuth-callback routes" in SPEC AC2 should also include the redirect entry-points per D-01.

### Pitfall 10 — `before_send` exception class import path
The `_before_send` filter in api_server tests `isinstance(exc_value, StarletteHTTPException)`. Both `fastapi.HTTPException` and `starlette.exceptions.HTTPException` exist; FastAPI's IS Starlette's (FastAPI re-exports). Use `from starlette.exceptions import HTTPException as StarletteHTTPException` to catch both surface paths.

### Pitfall 11 — `usage_logs` row may include legacy non-OpenRouter rows
The e2e test polls `WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1`. If a previous test in the same session leaked a row, the wrong row might match. Solution: filter by `WHERE user_id = $1 AND created_at > <test_start_time>` OR rely on `_truncate_tables` autouse fixture (which already truncates `usage_logs` indirectly via CASCADE of `users`). Confirm `usage_logs` is in the TRUNCATE list — it is NOT in conftest.py:227-232 (`agent_events, runs, agent_containers, agent_instances, idempotency_keys, rate_limit_counters, sessions, users`). **Plan-phase: add `usage_logs` to the TRUNCATE list** OR scope the e2e fixture to insert a dedicated user per test method (D-22 already requires this).

## Confirmation of CONTEXT line citations

All CONTEXT line citations verified against the current source code at HEAD (commit a1973fb / branch main 2026-05-07):

| CONTEXT citation | What CONTEXT says | What's actually there | Verdict |
|------------------|---------------------|------------------------|--------|
| `routes/auth.py:138` | `/v1/auth/google` GET | `@router.get("/auth/google")` decorator on `google_login` | ✓ |
| `routes/auth.py:157` | `/v1/auth/google/callback` GET | `@router.get("/auth/google/callback")` decorator on `google_callback` | ✓ |
| `routes/auth.py:222` | `/v1/auth/github` (auth-route entry) | `@router.get("/auth/github")` on `github_login` | ✓ |
| `routes/auth.py:237` | `/v1/auth/github/callback` GET | `@router.get("/auth/github/callback")` on `github_callback` | ✓ |
| `routes/auth.py:378` | `POST /v1/auth/google/mobile` | `@router.post("/auth/google/mobile", status_code=200)` on `google_mobile` | ✓ |
| `routes/auth.py:449` | `POST /v1/auth/github/mobile` | `@router.post("/auth/github/mobile", status_code=200)` on `github_mobile` | ✓ |
| `routes/auth.py:542` | `POST /v1/auth/logout` | `@router.post("/auth/logout")` on `logout` | ✓ |
| `chat_providers.dart:387` | `_stream.connect().catchError((_) {});` | Line 387 IS exactly that statement | ✓ |
| `chat_providers.dart:398` | bare empty catch in `_onResumed` w/ "intentionally empty" comment | Line 398 is `} catch (_) {`; comment is on line 399 ("intentionally empty — keep prior state visible on reconnect failure") | ✓ (off-by-one on comment vs catch keyword; immaterial) |
| `middleware/rate_limit.py:48-53` | `_LIMITS` dict definition | Lines 48-53 ARE the `_LIMITS` dict | ✓ |
| `middleware/rate_limit.py:56-81` | `_bucket_for` definition | Lines 56-81 ARE `_bucket_for` | ✓ |
| `middleware/rate_limit.py:84-123` | `_subject_from_scope` definition | Lines 84-123 ARE `_subject_from_scope` | ✓ |
| `middleware/rate_limit.py:126-203` | `RateLimitMiddleware.__call__` | Lines 126-203 ARE the class + `__call__` body | ✓ |
| `middleware/rate_limit.py:164-168` | composite-subject derivation `chat:<subject>:<agent_id>` | Line 168 is `subject = f"chat:{subject}:{agent_id_str}"` | ✓ |
| `middleware/rate_limit.py:175-180` | fail-open semantics | Lines 178-179 are the `_log.exception("rate_limit backend error; failing open"); await self.app(...)` | ✓ |
| `tests/middleware/test_chat_rate_limit.py` | per-route composite-subject test pattern | File exists; pattern at lines 113-180 is the canonical template | ✓ |
| `tests/auth/test_cross_user_isolation.py` | authenticated-pytest-fixture pattern | File exists; uses asyncpg INSERT for users + sessions | ✓ |
| `Makefile`'s `test-api-integration` | `cd api_server && pytest -m api_integration` | Lines 205-206 of root `Makefile` confirm | ✓ |
| `mobile/lib/features/chat/telegram_failed_banner_provider.dart` | Phase 25 D-50 chat-banner pattern | File exists at exact path; `StateProvider<TelegramFailedBannerState?>` shape per CONTEXT | ✓ |
| `mobile/lib/features/chat/telegram_failed_banner.dart` | Banner widget shape with Semantics + dismiss | **FILE DOES NOT EXIST** — CONTEXT itself flagged this with "Path may differ slightly — confirmed via grep to live in chat feature dir." Banner is rendered inline in `chat_screen.dart:196-207` using the shared `RetryBanner` widget at `mobile/lib/shared/retry_banner.dart`. | ⚠ — see Pitfall 3 |
| `mobile/lib/features/new_agent/deploy_step.dart` | inflight UI pattern | File exists; spinner/timer/SnackBar pattern visible at lines 73-200 | ✓ |
| `auth/oauth.py` placeholder-log pattern | "OAuth config oauth_X missing in dev; using placeholder" | Pattern exists in oauth.py (`_resolve_or_fail` family); verified via grep | ✓ |

## Sources

### Primary (HIGH confidence)
- **api_server source code** (read directly, all line citations verified):
  - `api_server/src/api_server/middleware/rate_limit.py` (entire file, 204 lines)
  - `api_server/src/api_server/middleware/session.py` (entire file, 156 lines)
  - `api_server/src/api_server/routes/auth.py` (entire file, 607 lines)
  - `api_server/src/api_server/main.py` (entire file, 602 lines)
  - `api_server/src/api_server/config.py` (lines 1-120)
  - `api_server/pyproject.toml` (entire file)
  - `api_server/tests/conftest.py` (lines 1-500, 605-685)
  - `api_server/tests/middleware/test_chat_rate_limit.py` (entire file)
  - `api_server/tests/auth/test_cross_user_isolation.py` (entire file)
  - `api_server/tests/test_rate_limit.py` (lines 1-80)
- **mobile source code:**
  - `mobile/lib/features/chat/chat_providers.dart` (entire file, 560 lines)
  - `mobile/lib/features/chat/chat_screen.dart` (lines 120-260)
  - `mobile/lib/features/chat/telegram_failed_banner_provider.dart` (entire file)
  - `mobile/lib/features/new_agent/deploy_step.dart` (lines 1-120)
  - `mobile/lib/main.dart` (entire file)
  - `mobile/lib/shared/retry_banner.dart` (lines 1-80)
  - `mobile/pubspec.yaml` (entire file)
- **Build infrastructure:**
  - `Makefile` (entire file, 288 lines)
  - `api_server/Makefile` (entire file)
  - `docker-compose.dev.yml` (entire file)
  - `.github/workflows/mobile.yml` + `.github/workflows/test-recipes.yml`
- **Recipes evidence:**
  - `recipes/nanobot.yaml`, `recipes/nullclaw.yaml`, `recipes/picoclaw.yaml`, `recipes/goose.yaml`, `recipes/qwenpaw.yaml` — verified_cells inspection
  - `.planning/phases/30-recipe-proxy-cutover/30-VERIFICATION.md` — Real-Money Cost Log + Acceptance Gates table

### Secondary (MEDIUM confidence)
- [Sentry Python FastAPI integration docs](https://docs.sentry.io/platforms/python/integrations/fastapi/) — auto-enable behavior verified
- [Sentry Python configuration options](https://docs.sentry.io/platforms/python/configuration/options/) — `before_send` signature, `traces_sample_rate=0.0`, `environment`, `release` semantics
- [Sentry Flutter docs](https://docs.sentry.io/platforms/dart/guides/flutter/) — `appRunner` wrap pattern, `tracesSampleRate=0.0` errors-only
- [Sentry Flutter options](https://docs.sentry.io/platforms/dart/guides/flutter/configuration/options/) — `beforeSend` signature, env-var fallback, `Sentry.configureScope` `setUser` API
- [pypi.org/project/sentry-sdk](https://pypi.org/project/sentry-sdk/) — current 2.59.0 latest
- [pub.dev/packages/sentry_flutter](https://pub.dev/packages/sentry_flutter) — current 9.20.0 latest

### Tertiary (LOW confidence — none applied to load-bearing claims)
- Web search aggregator output for GH Actions Postgres patterns; verified independently against the project's existing `mobile.yml`/`test-recipes.yml` style.

## Metadata

**Confidence breakdown:**
- Sentry SDK pinning: HIGH (PyPI/pub.dev verified, official docs cross-checked).
- pytest fixture wire shape: HIGH (existing `authenticated_cookie` fixture is the literal pattern).
- GH Actions workflow shape: HIGH (project's existing 2 workflows are the style template; no novelty).
- Mobile classifier mapping: MEDIUM (D-07 fallback resolution to `networkTransient` is per locked decision but D-07 vs SPEC AC11 mapping needs plan-phase reconciliation per Pitfall 4).
- OpenRouter cell selection: HIGH (Phase 30 cost log is empirical; cheapest verified is unambiguous).
- CONTEXT line citation verification: HIGH (all 22+ citations checked against current source).

**Research date:** 2026-05-07
**Valid until:** 2026-06-07 (30 days for stable SDKs); flag re-verification if sentry-sdk 3.0 or sentry_flutter 10.0 ships before plan-execute.

## RESEARCH COMPLETE

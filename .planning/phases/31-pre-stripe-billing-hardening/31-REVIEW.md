---
phase: 31-pre-stripe-billing-hardening
reviewed: 2026-05-08T15:50:43Z
depth: standard
files_reviewed: 25
files_reviewed_list:
  - api_server/pyproject.toml
  - api_server/tests/conftest.py
  - api_server/src/api_server/middleware/rate_limit.py
  - api_server/tests/middleware/test_auth_rate_limit.py
  - api_server/src/api_server/instrumentation/__init__.py
  - api_server/src/api_server/instrumentation/sentry.py
  - api_server/src/api_server/config.py
  - api_server/src/api_server/main.py
  - api_server/src/api_server/middleware/session.py
  - api_server/tests/test_sentry_init.py
  - api_server/tests/e2e/conftest.py
  - api_server/tests/e2e/test_money_path.py
  - mobile/pubspec.yaml
  - mobile/lib/core/instrumentation/sentry.dart
  - mobile/lib/features/chat/chat_stream_error_classifier.dart
  - mobile/lib/features/chat/chat_stream_error_banner_provider.dart
  - mobile/lib/main.dart
  - mobile/lib/features/chat/chat_providers.dart
  - mobile/lib/features/chat/chat_screen.dart
  - mobile/Makefile
  - mobile/test/features/chat/chat_stream_error_classifier_test.dart
  - mobile/test/features/chat/chat_screen_error_banner_widget_test.dart
  - mobile/test/core/instrumentation/sentry_test.dart
  - Makefile
  - .github/workflows/e2e-money-path.yml
findings:
  critical: 1
  warning: 5
  info: 6
  total: 12
status: resolved
resolved:
  CR-01: 9968f33 — make CREATE DATABASE idempotent (`|| true`)
  WR-01: c939ac0 — wire mobile D-16 Sentry user-context on sign-in/out
  WR-02: ae4efe0 — pytest.skip → pytest.fail on missing OPENROUTER_API_KEY
  WR-03: e5f1ae3 — add D-13 environment + release assertion test
  WR-04: 4f9db9d — pin httpx upper bound (<0.30)
  WR-05: e88fdcc — derive _AUTH_ROUTES from _AUTH_ROUTE_KEYS
deferred_info:
  IN-01: config typo (`mobile/lib/Makefile` vs `mobile/Makefile`) — orchestrator-side, not code
  IN-02: redundant `or None` retained — purposeful empty-string-to-None conversion
  IN-03: `_streamErrorCopy` duplication retained — deliberate drift-detection per test comment
  IN-04: mobile `profilesSampleRate` defense-in-depth — SDK defaults to 0
  IN-05: `/v1/runs` 200/201 assertion — endpoint is documented synchronous
  IN-06: `_onResumed` idempotent banner-clear — perf-cosmetic
---

# Phase 31: Code Review Report

**Reviewed:** 2026-05-08T15:50:43Z
**Depth:** standard
**Files Reviewed:** 25
**Status:** issues_found

## Summary

Phase 31 implements four billing-readiness gaps (H3 auth rate-limit, H4 chat-stream error UX, H6 Sentry observability, H8 e2e money-path CI). The code is **largely correct against the locked SPEC + AMDs** — the load-bearing AMD-06 (`_before_send` drops `StarletteHTTPException < 500`), AMD-02 (5-class classifier mapping), AMD-03 (e2e fixture composes existing `async_client` + `authenticated_cookie` verbatim, NO HMAC), AMD-04 (nanobot + `openai/gpt-4o-mini`), AMD-05 (`usage_logs` added to autouse TRUNCATE), AMD-06 (`StarletteHTTPException` import path), T-31-01 fail-open semantics, D-16 server-side `set_user` ID-only, and the three byte-exact banner copy strings are all correctly implemented.

Three classes of issues remain:

1. **One Critical** — the GitHub Actions workflow's `CREATE DATABASE` step is non-idempotent and will hard-fail on the second push to a re-runnable PR (compose-volume reuse between attempts) without an `IF NOT EXISTS` guard or `|| true` fallback.
2. **Five Warnings** — D-16 mobile equivalent (`Sentry.configureScope` user-context tag) is **not implemented anywhere in the mobile tree**, leaving the audit-mandated user-context bridge half-done; the `_init_with_capture` test helper omits `environment`/`release`, weakening D-13 coverage; the e2e money-path test's autouse `_require_openrouter_key` fixture marks the test SKIPPED (not FAILED) when the CI secret is missing, which can silently green a PR; the `pyproject.toml` deps grew a runtime `httpx>=0.27` floor with no upper bound, contradicting the deliberate `respx>=0.22,<0.24` ceiling discipline; `_AUTH_ROUTES` + `_AUTH_ROUTE_KEYS` are two parallel structures that can drift.
3. **Six Info-level** — minor cosmetic / documentation items (config-listed `mobile/lib/Makefile` does not exist; redundant `or None`; duplicated `_streamErrorCopy` helper between production + test; residual SDK-defaults question for `profilesSampleRate`).

## Critical Issues

### CR-01: e2e-money-path workflow `CREATE DATABASE` step is non-idempotent

**File:** `.github/workflows/e2e-money-path.yml:74-79`
**Issue:** The "Create app database + run migrations" step runs:

```yaml
- name: Create app database + run migrations
  run: |
    docker compose -f docker-compose.dev.yml exec -T postgresql \
      psql -U temporal -c "CREATE DATABASE agent_playground_api"
    make install-api
    make migrate-api
```

`CREATE DATABASE agent_playground_api` raises `ERROR: database "agent_playground_api" already exists` (PG SQLSTATE 42P04) on any second run that reuses the postgres container's volume. While `cancel-in-progress: false` plus `down -v` in the teardown step normally clears the volume, **a workflow re-run after a transient failure (e.g. OpenRouter 503 mid-completion)** can leave the volume in place because the prior run's teardown was preempted. The next attempt fails at this step with no useful error context, masking real H8 regressions.

GH Actions also re-runs failed steps via the "Re-run jobs" UI button without nuking the runner — same failure.

This is non-blocking for the green-path PR baseline (AC23) but fails the very first regression-test run after a flake (AC24).

**Fix:**
```yaml
- name: Create app database + run migrations
  run: |
    docker compose -f docker-compose.dev.yml exec -T postgresql \
      psql -U temporal -tc "SELECT 1 FROM pg_database WHERE datname='agent_playground_api'" \
      | grep -q 1 || \
    docker compose -f docker-compose.dev.yml exec -T postgresql \
      psql -U temporal -c "CREATE DATABASE agent_playground_api"
    make install-api
    make migrate-api
```

Or more simply:
```yaml
    docker compose -f docker-compose.dev.yml exec -T postgresql \
      psql -U temporal -c "CREATE DATABASE agent_playground_api" || true
```

The `|| true` swallows the duplicate-DB error specifically; alembic's `upgrade head` is already idempotent.

## Warnings

### WR-01: D-16 mobile user-context wire-up is missing

**File:** `mobile/lib/core/instrumentation/sentry.dart` (referenced; gap is repo-wide)
**Issue:** CONTEXT D-16 says: *"Mobile equivalent fires `Sentry.configureScope((scope) => scope.setUser(SentryUser(id: userId)))` after sign-in resolves."* A `grep -r 'Sentry.configureScope\|setUser' mobile/lib` returns **zero hits**. The api_server-side D-16 wire-up (`middleware/session.py:91-97`) is correctly implemented, but the mobile half is unimplemented. Post-Phase-B, when a user-impacting bug surfaces only on mobile, Sentry events arrive without a user tag and the support workflow falls back to crash-message-string fuzzing — exactly the burden D-16 was meant to eliminate.

Note: this is NOT covered by SPEC's listed Acceptance Criteria (AC11-AC16 cover api_server Sentry init only; mobile ACs are AC14/AC15/AC16 covering DSN-empty branch, errors-only sampling, and basic capture). D-16's mobile clause is decision-only, not a falsifiable AC. **The omission is consistent with the test surface, not a SPEC violation.** Flagging because the audit memory `feedback_re_ask_gray_areas.md` exact pattern: a decision lands in CONTEXT but never sprouts an AC, then ships half-done.

**Fix:** Add to the mobile post-sign-in flow (likely `mobile/lib/features/auth/` or wherever `oauth.dart`'s success callback lives — outside Phase 31's reviewed file set, so confirm path):

```dart
import 'package:sentry_flutter/sentry_flutter.dart';

// inside the post-sign-in success branch
await Sentry.configureScope(
  (scope) => scope.setUser(SentryUser(id: userId)),
);
```

Pair with a `Sentry.configureScope((s) => s.setUser(null))` clear on sign-out / cookie expiration to mirror the api_server's per-request scope reset.

### WR-02: e2e money-path `_require_openrouter_key` SKIPs (not FAILs) on missing secret

**File:** `api_server/tests/e2e/test_money_path.py:53-62`
**Issue:** The autouse fixture:
```python
@pytest.fixture(autouse=True)
def _require_openrouter_key():
    if not os.environ.get("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set; e2e money-path is opt-in")
```

uses `pytest.skip(...)` rather than `pytest.fail(...)`. In a GHA workflow whose entire reason for existing is to gate PR merges on a real OpenRouter call, a skipped test is **counted as PASSED by GH Actions** — a misconfigured `secrets.OPENROUTER_CI_KEY` (typo, expired, repo fork without secret access) will green every run silently, defeating SPEC AC24 (deliberate-regression PR demonstrates the workflow fails).

The `make e2e-money-path` Makefile target already env-guards the key (`@test -n "$$OPENROUTER_API_KEY"` with `exit 1`), so locally the missing-key path FAILs. But CI uses `make e2e-money-path` which inherits `OPENROUTER_API_KEY` from the workflow env — if `secrets.OPENROUTER_CI_KEY` is empty/unset, the env var is set to the empty string in some shells, and `test -n ""` returns false → make fails fast → good. **However**, GHA's `${{ secrets.OPENROUTER_CI_KEY }}` expansion to an unset secret produces an empty string, which the Makefile catches. The pytest-side `pytest.skip` is the second layer of defense and **should be `pytest.fail`** for CI parity.

**Fix:**
```python
@pytest.fixture(autouse=True)
def _require_openrouter_key():
    if not os.environ.get("OPENROUTER_API_KEY"):
        # AC24 floor: a missing/empty CI secret must FAIL, never silently SKIP.
        # Local opt-in path is gated by the `make e2e-money-path` env-guard +
        # the `e2e_money_path` pytest marker (not run by default test-api).
        pytest.fail(
            "OPENROUTER_API_KEY not set. In CI: secrets.OPENROUTER_CI_KEY is "
            "missing or empty. Locally: this test is opt-in via "
            "`make e2e-money-path` which env-guards the key."
        )
```

The marker `e2e_money_path` is already excluded from default `pytest` runs (the marker is registered but `pytest.ini`'s `[tool.pytest.ini_options]` does NOT auto-include it), so changing skip→fail does not regress unit-test runs.

### WR-03: `_init_with_capture` helper omits `environment` + `release` — D-13 untested

**File:** `api_server/tests/test_sentry_init.py:41-47`
**Issue:** The helper `_init_with_capture(transport)` calls:
```python
sentry_sdk.init(
    dsn="https://test@example.ingest.sentry.io/1",
    transport=transport,
    traces_sample_rate=0.0,
    before_send=_before_send,
)
```

It does NOT exercise the `environment` + `release` tagging that D-13 mandates (the `init_sentry()` production code does pass them). `test_no_dsn_starts_cleanly` verifies the no-init branch; no test verifies the actual `init_sentry(_S(env="prod", git_sha="abc123"))` shape produces a client with `client.options["environment"] == "prod"` and `client.options["release"] == "abc123"`.

This is a coverage gap, not a correctness bug — `init_sentry` itself looks right. But CONTEXT.md flags D-13 as *"Critical for filtering dev noise from real prod errors when H7 deploy lands."* If a future refactor accidentally drops `environment=` from the init call, no test catches it.

**Fix:** Add a test that exercises `init_sentry` directly (not the bypass `_init_with_capture` shim):
```python
def test_init_sentry_tags_environment_and_release(isolated_sentry_hub, monkeypatch):
    """D-13 — environment + release land on the client options."""
    monkeypatch.setenv("AP_SENTRY_DSN_API", "https://test@example.ingest.sentry.io/1")
    monkeypatch.setenv("AP_ENV", "prod")
    monkeypatch.setenv("GIT_SHA", "deadbeef")
    from api_server.config import get_settings
    init_sentry(get_settings())
    client = sentry_sdk.get_client()
    assert client.options["environment"] == "prod"
    assert client.options["release"] == "deadbeef"
```

### WR-04: `httpx>=0.27` runtime pin has no upper bound

**File:** `api_server/pyproject.toml:54`
**Issue:**
```toml
"httpx>=0.27",
```

vs. the surrounding deps which uniformly carry an upper bound (e.g. `redis>=5.2,<8`, `sentry-sdk[fastapi]>=2.20,<3.0`, `respx>=0.22,<0.24`). The dev-deps comment block at line 99-107 explicitly documents that **httpx 0.28 broke `respx 0.21`** (the symptom that forced the floor bump). A future automatic minor httpx bump (0.29, 0.30) could repeat the same break against authlib's transitive httpx pin.

The CONTEXT mentions Plan 22c-09 promoted httpx from dev→runtime; the RESEARCH for that plan presumably pinned a working range that has since drifted to "any 0.27+".

**Fix:** Add the upper bound discipline used elsewhere in the file:
```toml
"httpx>=0.27,<0.30",
```

Or, to mirror the `redis>=5.2,<8` pattern explicitly: pin major + permitted minor bump only, with a deviation comment when bumping.

### WR-05: `_AUTH_ROUTES` and `_AUTH_ROUTE_KEYS` are parallel structures that can drift

**File:** `api_server/src/api_server/middleware/rate_limit.py:51-72`
**Issue:** Two structures encode the same 7-route set:

```python
_AUTH_ROUTES: frozenset[tuple[str, str]] = frozenset({
    ("POST", "/v1/auth/google/mobile"),
    # ... 6 more
})

_AUTH_ROUTE_KEYS: dict[tuple[str, str], str] = {
    ("POST", "/v1/auth/google/mobile"): "google_mobile",
    # ... 6 more
}
```

A new auth route added to one but not the other produces silent misbehavior:
- Added to `_AUTH_ROUTES` only → `_AUTH_ROUTE_KEYS.get(..., "unknown")` returns `"unknown"`, which means **all new auth routes share the `auth:<ip>:unknown` counter row**, undermining the per-route ceiling D-02 promises.
- Added to `_AUTH_ROUTE_KEYS` only → `_bucket_for` returns `None`, no rate limit applied.

The split is a code-smell with a subtle correctness tail. CONTEXT D-01 picks the frozenset for "no regex on the hot path; greppable + extensible" but D-02 then needs the dict — making the dict the actual source of truth.

**Fix:** Collapse to a single structure and derive `_AUTH_ROUTES` from its keys:
```python
_AUTH_ROUTE_KEYS: dict[tuple[str, str], str] = {
    ("POST", "/v1/auth/google/mobile"):   "google_mobile",
    ("POST", "/v1/auth/github/mobile"):   "github_mobile",
    ("POST", "/v1/auth/logout"):          "logout",
    ("GET",  "/v1/auth/google"):          "google_redirect",
    ("GET",  "/v1/auth/google/callback"): "google_callback",
    ("GET",  "/v1/auth/github"):          "github_redirect",
    ("GET",  "/v1/auth/github/callback"): "github_callback",
}
_AUTH_ROUTES: frozenset[tuple[str, str]] = frozenset(_AUTH_ROUTE_KEYS.keys())
```

`_bucket_for`'s membership check stays O(1); no semantic change; drift impossible.

## Info

### IN-01: Config lists `mobile/lib/Makefile` but file is at `mobile/Makefile`

**File:** `<config>` block; actual path `mobile/Makefile`
**Issue:** The reviewer config's `files:` list includes `mobile/lib/Makefile` which does not exist (`ls mobile/lib/Makefile` → No such file or directory). The actual makefile is at `mobile/Makefile` and IS in the diff. Reviewed the correct file by inference. Flagging so future workflow runs don't pass a non-existent path through filtering.

**Fix:** Update the `/gsd-code-review` orchestrator's file-discovery to canonicalize `mobile/lib/Makefile` → `mobile/Makefile`, OR fix the upstream commit's planning artifact that suggested the wrong path.

### IN-02: Redundant `or None` in `init_sentry`

**File:** `api_server/src/api_server/instrumentation/sentry.py:59`
**Issue:**
```python
release=getattr(settings, "git_sha", None) or None,
```

The `or None` is a no-op: `getattr(..., None)` already returns `None` when the attribute is absent, and `None or None == None`. The intent was likely `getattr(...) or None` to convert empty-string `""` to `None` (sentry-sdk treats empty release strings differently from unset). If that's the intent, the current code is correct because `"" or None == None`, so the redundancy is purposeful — but a comment would help.

**Fix:** Either drop the `or None` (if intent is just default), or comment it:
```python
# `or None`: convert "" → None so empty-string GIT_SHA env doesn't tag a blank release.
release=getattr(settings, "git_sha", None) or None,
```

### IN-03: `_streamErrorCopy` is duplicated across production + widget test

**Files:** `mobile/lib/features/chat/chat_screen.dart:262-271` and `mobile/test/features/chat/chat_screen_error_banner_widget_test.dart:24-33`
**Issue:** The three SPEC-locked copy strings appear in two places:

```dart
// chat_screen.dart
String _streamErrorCopy(ChatStreamErrorClass c) { ... }

// chat_screen_error_banner_widget_test.dart (mirror harness)
String _streamErrorCopy(ChatStreamErrorClass c) { ... }
```

Both are byte-identical. The test file's comment **explicitly acknowledges this**: *"If chat_screen.dart drifts, the AC5/6/7 byte-exact text-find assertions fail."* — i.e. duplication is intentional drift-detection.

This is an accepted tradeoff (per the test comment). Flagging only because for future maintainers the alternative — extract to `chat_stream_error_classifier.dart` as a `String streamErrorCopy(ChatStreamErrorClass)` top-level — would let the widget test assert against the SAME function, eliminating drift risk without losing any AC coverage. The current shape is fine; the alt is mildly cleaner.

**Fix (optional):** Move `_streamErrorCopy` next to the `ChatStreamErrorClass` enum in `chat_stream_error_classifier.dart`, export as `streamErrorCopy`, import + call from both `chat_screen.dart` and the widget test. AC5/6/7's `find.text(...)` still asserts the rendered string, so drift detection is intact.

### IN-04: `profilesSampleRate` not explicitly set to 0 in mobile init

**File:** `mobile/lib/core/instrumentation/sentry.dart:26-46`
**Issue:** SPEC AC15+AC16: "errors only — NO traces_sample_rate, NO profiles_sample_rate." The init sets `tracesSampleRate = 0.0` explicitly but does NOT touch `profilesSampleRate`. sentry_flutter 9.x defaults `profilesSampleRate = 0.0` (profiling is opt-in), so the current code IS errors-only by default — but AC16's explicit guarantee "no profiles" is enforced by SDK default, not by code. A future SDK major bump that flipped the default would silently turn profiling on.

Compare api_server side: `traces_sample_rate=0.0` is explicit; `profiles_sample_rate` is also implicit (defaults to 0).

**Fix (defense-in-depth, optional):**
```dart
options
  ..dsn = dsn
  ..environment = env
  ..tracesSampleRate = 0.0   // SPEC AC15
  ..profilesSampleRate = 0.0 // SPEC AC16 — defense-in-depth vs SDK default flip
  ..beforeSend = ...
```

Same for the api_server `sentry_sdk.init(profiles_sample_rate=0.0, ...)`. Cosmetic but matches the "errors-only" SPEC literally.

### IN-05: e2e money-path test uses `client.post("/v1/runs", ...)` which may return 202

**File:** `api_server/tests/e2e/test_money_path.py:114-125`
**Issue:**
```python
deploy_resp = await client.post("/v1/runs", ...)
assert deploy_resp.status_code in (200, 201), ...
```

`/v1/runs` is described in CONTEXT as "synchronously deploys + smoke-runs" — but other agent-related endpoints in this codebase use 202 Accepted for async job kickoff (e.g. `agent_messages_route` returns 202 in the chat fixture stub). If `/v1/runs` ever flips to async (e.g. plan to put run-completion behind a Temporal workflow), this assertion silently rejects the new contract.

Not a current bug — the route is documented synchronous. Future-coupling risk only.

**Fix (optional):** Make the assertion narrower OR future-proof:
```python
assert deploy_resp.status_code in (200, 201, 202), ...
```

Then verify the cost-capture assertion separately (which is already the test's load-bearing post-condition), so an async deploy would still be exercised correctly through the same poll-for-usage_logs ceiling.

### IN-06: `_onResumed` always overwrites banner state, even when nothing changed

**File:** `mobile/lib/features/chat/chat_providers.dart:404-422`
**Issue:** On every `AppLifecycleState.resumed`, `_onResumed`:
1. Calls `_stream.disconnect()`
2. Tries `_stream.connect()`
3. On success: `chatStreamErrorProvider.notifier.state = null` — even if it was ALREADY null

The `state = null` write is harmless (Riverpod state writes are idempotent for value equality), but it triggers a Riverpod listener fire to anything watching `chatStreamErrorProvider`. In practice the only watcher is `chat_screen.dart:134` which reads it to gate banner rendering; an extra rebuild of an already-null banner is a no-op render. Cosmetic perf; not worth changing.

D-09 says "Existing banner persists across foreground/background unless cleared by retry-success / dismiss / sign-out / Riverpod teardown." The current code clears on EVERY resume-with-success, which is broader than D-09 strictly mandates but matches its spirit (latest connect wins).

**Fix (optional, cosmetic):**
```dart
if (ref.read(chatStreamErrorProvider) != null) {
  ref.read(chatStreamErrorProvider.notifier).state = null;
}
```

Saves one Riverpod notify per resume. Probably not worth the LOC.

---

_Reviewed: 2026-05-08T15:50:43Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

---
date: 2026-05-02
git_sha: 072cf7c1183c371b7166007964c5a76227704e5d
flutter_sdk_version: 3.41.0
recipe: zeroclaw
model: anthropic/claude-haiku-4-5
base_url: http://localhost:8000
target: iOS Simulator (iPhone 16e, iOS 26.4.1)
verdict: PASS
---

# Flutter Foundation — D-46 round-trip spike

Phase 24 exit gate (D-53). Runs the full 9-step deploy → send → SSE-reply
→ parity → idempotency → resume → stop sequence end-to-end against the
live local api_server + Postgres + Redis + zeroclaw agent container +
real OpenRouter, driven from a real iOS Simulator running the Flutter
foundation built across plans 24-01..24-08.

## Reproducibility

```bash
# Stack: Hetzner-mirror local compose (api_server + postgres + redis + caddy)
cd deploy && docker compose \
  -f docker-compose.prod.yml -f docker-compose.local.yml \
  --env-file .env.prod up -d

# Sign in once via the web playground OAuth (Phase 22c-oauth-google),
# copy ap_session UUID from DevTools → Cookies → http://localhost:8000.
SESSION_ID=<bare-uuid>

# Boot iOS Simulator on the matching iOS runtime (Xcode 26.4 SDK
# requires iOS 26.4 simulator runtime — `xcodebuild -downloadPlatform iOS`
# if missing; ~8.5 GB).
xcrun simctl boot "iPhone 16e (26.4)"
open -a Simulator

# Run the spike from mobile/.
cd mobile && make spike \
  BASE_URL=http://localhost:8000 \
  SESSION_ID=$SESSION_ID \
  OPENROUTER_KEY=$(grep '^OPENROUTER_API_KEY=' ../.env.local | cut -d= -f2-)
```

## Result

```
00:34 +0: 9-step round-trip — D-46 (Phase 24 exit gate)
...
00:52 +1: 9-step round-trip — D-46 (Phase 24 exit gate)
00:53 +1: All tests passed!
```

Single test, single agent_instance (`spike-roundtrip-<unix-ts>-<short-hex>`),
~13s wall-clock for the 9 in-test steps (excluding ~30s Xcode build +
~3s pub get on first invocation).

## D-46 step narrative — observed output

### Step 1 — `POST /v1/runs` (BYOK + recipe=zeroclaw + model=anthropic/claude-haiku-4-5)

* api_server response 200 OK
* `{ agent_instance_id: <uuid> }` returned
* Cookie injected via `AuthInterceptor` (`Cookie: ap_session=<uuid>`)
* BYOK injected via per-call `Authorization: Bearer <key>`
* Smoke probe upstream confirms key validity end-to-end
  before any container spawn

### Step 2 — `POST /v1/agents/:id/start` (channel='inapp', BYOK)

* api_server response 202 Accepted
* `agent_containers` row inserted, `container_id` returned
* zeroclaw container spawned via `tools/run_recipe.py` →
  `docker run -d --network deploy_default ...` (the `--network` arg is the
  fix landed in the substrate commit immediately preceding this spike;
  without it the dispatcher's `get_container_ip` raises
  `ip_lookup_failed`)
* zeroclaw `pre_start_command` runs: `zeroclaw onboard --quick --force --provider openrouter --ap`
* daemon launches: `zeroclaw daemon` listening on `:42617/webhook`

### Step 3 — `GET /v1/agents/:id/messages/stream` (SSE connect)

* `MessagesStream.connect` injects `Cookie: ap_session=<uuid>` (from the
  test-supplied cookieProvider) and an empty initial Last-Event-Id
* SSE handshake completes; events start flowing
* `flutter_client_sse` correctly tracks `event.id` per RESEARCH Pitfall #2

### Step 4 — `POST /v1/agents/:id/messages` (Idempotency-Key)

* uuid v4 minted client-side via `package:uuid`
* api_server response 202 Accepted, `{ message_id: <uuid> }`
* `inapp_messages` row inserted in status=pending; dispatcher picks up

### Step 5 — SSE delivers `inapp_outbound`

* dispatcher forwards content to `http://<container_ip>:42617/webhook`
  (zeroclaw native contract; idempotency header forwarded as
  `X-Idempotency-Key`)
* zeroclaw calls OpenRouter (anthropic/claude-haiku-4-5) and returns
  the assistant reply on the webhook response
* Outbox pump publishes `inapp_outbound` to Redis Pub/Sub
* SSE handler delivers JSON envelope:
  `{ seq, kind: "inapp_outbound", payload: { source: "agent",
     content: "I'll check what 'spike roundtrip' refers to ...",
     captured_at }, correlation_id, ts }`
* `MessagesStream.lastEventId` is now non-null (Plan 24-05 wrapper)

### Step 6 — `GET /v1/agents/:id/messages?limit=10` parity

* History returns ASC oldest→newest as 2 ChatMessage rows (user + assistant),
  both with the same `inapp_message_id` (one inapp_messages row → 2
  history rows)
* `assistants.last.content` byte-equals `extractAssistantContent(SSE.data)`
  after unwrapping the SSE envelope's `payload.content` field
* Phase 23 D-08 cross-channel parity invariant honored

### Step 7 — Idempotency replay

* Re-`POST /v1/agents/:id/messages` with the SAME Idempotency-Key UUID
* api_server response 202, returns the **same** `message_id`
* `IdempotencyMiddleware` cache replay confirmed (Phase 23 D-09)

### Step 8 — Last-Event-Id resume

* `MessagesStream.disconnect()` preserves `lastEventId` (Plan 24-05 invariant)
* `MessagesStream.connect()` re-attaches with `Last-Event-Id: <last-seq>`
* Send a fresh post → wait for next `inapp_outbound` past resume cursor
* Zero duplicates of the cursor event in the resumed stream

### Step 9 — `POST /v1/agents/:id/stop`

* api_server response 200 OK; container gracefully stopped (SIGTERM →
  graceful_shutdown_s budget → force-rm if needed)
* `agent_containers` row updated to stopped status; `agent_instances`
  row preserved per D-48
* `Authorization: Bearer <key>` REQUIRED on `/stop` per Phase 21
  session-ownership gate; spike fixed `ApiClient.stop` signature
  to demand this.

## Foundation invariants empirically validated

| D-#  | Invariant                                                                | Step(s) |
|------|--------------------------------------------------------------------------|---------|
| D-31 | Hand-written typed dio over 13 endpoints                                 | 1,2,4,6,7,9 |
| D-32 | Sealed `Result<T>` { Ok, Err } with exhaustive switch                    | every  |
| D-33 | `flutter_client_sse` SSE wire                                            | 3,5,8  |
| D-34 | Manual `fromJson`/`toJson` on plain Dart classes                         | 1,2,4,6 |
| D-35 | `AuthInterceptor` injects `Cookie: ap_session=<uuid>` per request        | every  |
| D-36 | `Idempotency-Key` (uuid v4) on `postMessage`                             | 4,7    |
| D-37 | dio 10s connect / 30s receive (regular); SSE no receive timeout          | 5      |
| D-38 | Stripe-shape `ApiError` envelope decoded; spike's `expectOk` redacts     | n/a here |
| D-39 | No auto-retry — caller surfaces `Err` to test, the test decides          | every  |
| D-40 | BYOK Authorization: Bearer on `runs()` + `start()` + `stop()` (D-40 amended) | 1,2,9 |
| D-41 | Every dio method accepts CancelToken                                     | every  |
| D-42 | `messagesHistory` paginates via `limit` (default 200, max 1000)          | 6      |
| D-43 | `AppEnv.fromEnvironment` fails loud on empty/malformed BASE_URL          | boot   |
| D-44 | No in-app debug menu / env switcher anywhere — `--dart-define BASE_URL` only | n/a (spike-time) |
| D-46 step 6 | History byte-equals SSE delivery (Phase 23 D-08 cross-channel parity)   | 6 |
| D-46 step 7 | Idempotency-Key replay returns SAME message_id (Phase 23 D-09)          | 7 |
| D-46 step 8 | Last-Event-Id resume — zero duplicates                                  | 8 |
| D-49 | Cookie-paste session_id flow (no native OAuth in P24)                    | every  |
| D-52 | Cookie + Authorization redacted (last 8 chars) in dev logs               | spike-side |

## Deviations captured

1. **D-47 recipe**: spike uses `zeroclaw` (prebuilt
   `ghcr.io/zeroclaw-labs/zeroclaw:latest`, distroless, ~67MB) instead of
   plan-spec'd `nullclaw`. Reason: nullclaw requires upstream Zig
   cross-compile build (~5+ min cold build); zeroclaw pulls in seconds and
   has the same `inapp` channel surface validated by Phase 22c.3-01.
   Round-3 substitution mirroring 22c.3 precedent. The recipe slot is
   parametric — Phase 25 deploy UX will let users pick any of
   hermes/nanobot/openclaw/zeroclaw/nullclaw.

2. **D-40 amendment**: `ApiClient.stop()` now requires `byokOpenRouterKey`
   (Authorization: Bearer header). Plan said BYOK is "only on runs() and
   start() — never on other methods" but the api_server's `/stop`
   endpoint requires Bearer as the Phase 21 session-ownership gate
   (value not forwarded to runner). Updated D-40 in CONTEXT.md is a
   follow-up; for now the deviation is committed in
   `mobile/lib/core/api/api_client.dart` + tested in
   `mobile/test/api/api_client_test.dart`.

3. **Substrate fixes** (committed separately, not Phase 24's concern but
   blocked the spike from running until landed):
   * `tools/run_recipe.py` — `docker run -d` was missing `--network`,
     so spawned containers landed on bridge instead of `deploy_default`
   * `tools/Dockerfile.api` — google-auth dep was missing from the
     pip install layer (only in pyproject.toml)
   * `deploy/docker-compose.prod.yml` — added `AP_DOCKER_NETWORK=deploy_default`
     so the runner picks up the right network

## Operational notes (mobile/README.md cross-reference)

* iOS Simulator iOS 26.4.1 runtime required by Xcode 26.4 SDK. If only
  iOS 26.2 is installed, `xcodebuild -showdestinations` returns zero
  eligible destinations and `make spike` fails before reaching the test
  body. Fix: `xcodebuild -downloadPlatform iOS` (~8.5 GB).
* Docker Desktop volume wipes drop the postgres state — re-run
  `alembic upgrade head` (or the deploy.sh path) before the next spike.
* Two simultaneous spike runs use distinct agent names
  (`spike-roundtrip-<ts>-<hex>`); concurrency cap is the dev box's
  `AP_MAX_CONCURRENT_RUNS` setting (default 2).

## Phase 24 exit gate

Per D-53 this spike PASS unblocks Phase 25 planning.
`spikes/flutter-api-roundtrip.md` with `verdict: PASS` is the literal
string match Phase 25's plan-checker uses; the metadata frontmatter
captures the reproducibility tuple.

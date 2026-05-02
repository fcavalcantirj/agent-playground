# Phase 24: Flutter Foundation — Context

**Gathered:** 2026-05-02
**Status:** Ready for planning

<domain>
## Phase Boundary

A Flutter native app at `mobile/` boots on iOS Simulator + Android Emulator,
hits `GET /healthz` via a hand-written typed dio client over a runtime-configured
base URL, renders the Solvr Labs theme (monochrome, corner radius 0, Inter +
JetBrains Mono), and a checked-in spike at `spikes/flutter-api-roundtrip.md`
proves the **deploy + send + SSE reply + Last-Event-ID resume + GET /messages
parity + auth-cookie injection** round-trip end-to-end against the running
Phase 23 backend BEFORE Phase 25's screens plan seals (Golden Rule #5).

**No screens (Dashboard / NewAgent / Chat) ship in Phase 24** — they're Phase
25's work. The placeholder screen is a single `Scaffold` calling `/healthz`
through the real theme + real router + real client. **No debug menu, no debug
overlay, no env banner, no developer-only chrome of any kind.** The app shell
ships in production-ready shape; debugging happens via `dart:developer log()`
+ IDE inspector.

The full Phase 23 backend surface is reused as-is: existing endpoints
(`/v1/runs`, `/v1/agents/:id/start`, `/v1/agents/:id/messages` block-and-fast-ack,
SSE `/messages/stream`, `/v1/agents`, `/v1/agents/:id/messages` history,
`/v1/recipes`, `/v1/models`, `/v1/users/me`, `/v1/auth/{google,github}/mobile`).
**The mobile app does NOT introduce a `/chat` endpoint — that name from APP-03
in REQUIREMENTS.md is superseded by Phase 23 D-14.**

</domain>

<decisions>
## Implementation Decisions

### Project scaffold & repo layout

- **D-01:** **Project root: `mobile/`** — top-level sibling of `api_server/`, `frontend/`, `recipes/`, etc. Same git repo. Spike artifact + CONTEXT chain stay co-located.
- **D-02:** **Bundle/applicationId: `com.solvrlabs.agentplayground`.** Brand-aligned, codename-preserving, future rebrand-safe. Used for both iOS bundle ID and Android applicationId.
- **D-03:** **App display name: `Solvr Labs`** (10 chars, fits both platforms' home-screen labels). Independent of bundle ID. User-facing brand per `mobile-mvp-decisions.md`.
- **D-04:** **OAuth deep-link custom URL scheme: `solvrlabs://`.** Brand-aligned, full word reduces collision risk. Callbacks at `solvrlabs://oauth/google` (unused — google_sign_in is native, no callback) and `solvrlabs://oauth/github` (used by flutter_appauth). Registered in iOS `Info.plist` `CFBundleURLTypes` + Android `AndroidManifest.xml` intent-filter. **Phase 23 D-24 deferred this naming to Phase 24's spec — settled here.**
- **D-05:** **Flutter SDK pinned via FVM** (`Flutter Version Manager`). Latest stable 3.x channel at scaffold time. Commit `.fvmrc`; gitignore `.fvm/flutter_sdk` symlink. Mirrors `api_server/`'s `uv` discipline. `fvm install` is a one-time per-machine setup.
- **D-06:** **iOS minimum: iOS 13.0. Android minimum: API 23 (Android 6 / Marshmallow).** Both are Flutter's current scaffolding defaults. Covers ~99.5% of devices. Don't raise floors prematurely.
- **D-07:** **Both `mobile/ios/` and `mobile/android/` directories committed to git.** Required for OAuth deep-link intent filters (D-04), ATS exemptions (D-12), Android cleartext config (D-13), signing config (D-09).
- **D-08:** **.gitignore the standard Flutter set:** `/build`, `/.dart_tool`, `/.flutter-plugins`, `/.flutter-plugins-dependencies`, `mobile/ios/Pods/`, `mobile/ios/.symlinks`, `mobile/ios/Flutter/Flutter.framework`, `mobile/android/.gradle`, `mobile/android/local.properties`, `mobile/.fvm/flutter_sdk`. **Commit `pubspec.lock`** (matches no-mocks/reproducibility ethos + FVM SDK pinning).
- **D-09:** **Code signing: personal team / debug only.** Phase 24 ships nothing to App Store / TestFlight. Xcode Personal Team for iOS; debug keystore for Android. Release signing certs / fastlane / TestFlight provisioning belong to a future release-readiness phase. Captured deferred.
- **D-10:** **App version: `0.1.0+1` in `pubspec.yaml`.** Phase 25 bumps to `0.2.0+2`. Build number monotonic. Aligns with the project's milestone-based versioning.
- **D-11:** **Localization (l10n) deferred.** No `flutter_localizations` setup in Phase 24. MVP is en-US only. Captured as deferred for any non-en demo or release work.

### Native platform setup (load-bearing for HTTP-to-host dev path)

- **D-12:** **iOS App Transport Security: whitelist `localhost` and `NSAllowsLocalNetworking=true` in `Info.plist`.** Without this, dio calls to `http://localhost:8000` and `http://192.168.x.x:8000` silently fail on iOS. Production HTTPS still enforced for non-exempted domains. Standard Flutter dev pattern.
- **D-13:** **Android cleartext HTTP via `network_security_config.xml` scoped to debug builds only.** Ship `mobile/android/app/src/debug/res/xml/network_security_config.xml` permitting cleartext for `localhost` + `10.0.2.2` + `192.168.x.x` + `10.x.x.x` ranges. Production AndroidManifest blocks cleartext as default. Mirrors iOS ATS approach — dev builds work, release builds enforce HTTPS.
- **D-14:** **Orientation locked to portrait.** All Phase 25 mockups are portrait (375x812). Removes a class of layout-rotation bugs before they exist.
- **D-15:** **OAuth deep link uses custom URL scheme only (not Universal Links / App Links).** No HTTPS domain ownership required (we don't have a deploy domain). `google_sign_in` is fully native (no callback URL needed). `flutter_appauth` for GitHub uses `solvrlabs://oauth/github`. Universal Links + App Links are a future hardening once a verified domain exists. Captured deferred.
- **D-16:** **No build flavors (single debug+release build).** Env switching is per-call via `--dart-define` (D-44). Flavors add Gradle complexity for prod environments we don't yet have. Captured deferred.
- **D-17:** **System UI overlay style: light background, dark icons** (`SystemUiOverlayStyle.dark`). Set once in `main.dart`. Matches the monochrome theme (`#FAFAF7` background).
- **D-18:** **iOS entitlements: default Keychain only — no Keychain Sharing entitlement.** `flutter_secure_storage` works without a sharing group. Add Keychain Sharing later only if we ship app extensions. Simpler signing config for Phase 24.
- **D-19:** **Apple Privacy Manifest (`PrivacyInfo.xcprivacy`) deferred.** Apple requires it for App Store submission only. Flutter plugins that need them already bundle their own. Capture as deferred for release-readiness.
- **D-20:** **Push notifications, crash reporting (Sentry/Crashlytics), analytics — all deferred.** Out of MVP per `mobile-mvp-decisions.md`. Captured as deferred for a polish/release phase.
- **D-21:** **Accessibility floor captured here, enforced in Phase 25.** Conventions: minimum touch target 44×44 (iOS HIG) / 48×48 (Material), `Semantics` labels on icon-only buttons, theme contrast verified. Phase 24 has no real screens to audit; Phase 25 UI checker enforces.

### Tooling, lints, CI

- **D-22:** **`mobile/Makefile`** with targets: `make doctor` (`fvm flutter doctor`), `make get` (`fvm flutter pub get`), `make ios` / `make android` (run on simulator/emulator), `make test` (unit tests), `make spike` (D-50). Mirrors `api_server/Makefile` pattern. Single discovery point for dev loop.
- **D-23:** **Lints: `very_good_analysis`** (Very Good Ventures' strict ruleset). Stricter than Flutter's default `flutter_lints`. Same philosophy as `api_server`'s strict `ruff` config.
- **D-24:** **`dart format` line length: 80** (default). `very_good_analysis` aligns; community-standard for diff readability.
- **D-25:** **Logging: `dart:developer log()`** (Dart stdlib, IDE-aware). No third-party logger pkg. Sufficient for dev-only logs during MVP. `print()` flagged by linter.
- **D-26:** **Folder layout under `lib/`: feature-based.** `lib/core/` for cross-cutting (api client, theme, env config, result type, secure storage, logging). `lib/shared/` for reusable widgets/utilities. `lib/features/dashboard/`, `lib/features/new_agent/`, `lib/features/chat/` are placeholder dirs in Phase 24 (Phase 25 fills them). Riverpod community convention.
- **D-27:** **Mobile CI: a minimal GitHub Actions workflow** that runs `fvm flutter analyze && fvm flutter test` on every push to `mobile/`. ~30 LOC. No simulator runs (those need macOS runners + real devices). Spike runs locally only (D-53).
- **D-28:** **PR template: reuse the existing repo `.github/PULL_REQUEST_TEMPLATE.md`.** Mobile-specific PR template deferred until patterns emerge.
- **D-29:** **Pre-commit hooks: reuse the repo's existing strategy.** Extend it to also `fvm flutter analyze` mobile/ changes if a hook system exists; otherwise rely on CI (D-27).
- **D-30:** **App icon + native splash deferred.** Use Flutter's default icon + native splash. Real Solvr Labs logo/icon packaging belongs to a polish phase. Captured deferred.

### API client (hand-written over dio)

- **D-31:** **Hand-written typed client over dio.** ~10 endpoints × ~10–25 LOC each = 150–300 LOC across one file (`lib/core/api/api_client.dart` or split per-resource: `agents_api.dart`, `messages_api.dart`, `auth_api.dart`, `models_api.dart`, `recipes_api.dart`). Zero codegen toolchain. Simplest path that works given:
  - SSE forces hand-written `messagesStream` regardless;
  - `Result<T>` return type is incompatible with retrofit/openapi-generator's throw-on-error model;
  - 10 endpoints is below codegen's break-even point;
  - Matches the manual-JSON + sealed-Result picks (D-32, D-34).
- **D-32:** **`Result<T>` type: hand-rolled Dart 3 sealed class.** `sealed class Result<T> { Ok(T); Err(ApiError); }` with exhaustive `switch`. ~30 LOC including `ApiError` variants (network, timeout, http_4xx with parsed Stripe envelope, http_5xx, unauthorized). Zero deps.
- **D-33:** **SSE library: `flutter_client_sse`.** Locked by Phase 23 D-13. Supports `Last-Event-ID` resume, custom headers (we inject `Cookie: ap_session` on connect), reconnection. Pinned to whatever version is current at scaffold time.
- **D-34:** **JSON serialization: manual `fromJson` / `toJson` on plain Dart classes.** ~10–15 DTOs × 5–15 LOC each = trivial. No `build_runner`, no codegen step in CI, no `*.g.dart` noise in PRs.
- **D-35:** **Auth cookie injection: dio `Interceptor`** at `lib/core/api/auth_interceptor.dart`. On every outbound request, read `session_id` from `flutter_secure_storage` (iOS Keychain / Android EncryptedSharedPreferences) and set `Cookie: ap_session=<id>`. On 401, clear stored session + emit auth-required event for the router (Phase 25 wires the OAuth route per Phase 23 D-26). No `cookie_jar` package — we control exactly one cookie.
- **D-36:** **Idempotency-Key generation: `uuid` package, v4 per Send press.** `Uuid().v4()` once when user taps Send. Stored on the in-flight message until ack. If the call fails and the user retries the same message bubble, reuse the same key (`IdempotencyMiddleware` replays cached 202 response per Phase 23 D-09). Phase 25 retry UX builds on this.
- **D-37:** **dio timeouts: 10s connect / 30s receive on regular endpoints; SSE has NO receive timeout.** SSE stream method explicitly disables receive timeout (intentionally long-lived). 30s receive covers `/v1/runs` smoke + `/v1/agents/:id/start` container-spawn slow path.
- **D-38:** **Error envelope decoding: typed `ApiError` mirroring backend's Stripe-shape.** `ApiError(code: ErrorCode, message: String, param: String?, requestId: String?)`. `ErrorCode` is a Dart enum mirroring backend's `ErrorCode` (see `api_server/src/api_server/errors.py`). Phase 25 UI can render specific copy per code.
- **D-39:** **No auto-retry in dio.** Caller surfaces `Err` to the UI and decides. Session-write path uses Idempotency-Key for safe user-driven retry; SSE stream uses `flutter_client_sse` reconnection. Auto-retry inside dio would duplicate non-idempotent ops or hide real failures.
- **D-40:** **OpenRouter BYOK key: defined in the typed client method signature; entry UX deferred to Phase 25.** `runs(...)` and `start(...)` accept optional `byokOpenRouterKey` parameter; if present, sent as `Authorization: Bearer <key>`. Spike (D-45) passes a hardcoded key from `--dart-define OPENROUTER_KEY` (D-49). Phase 25 wires the actual entry UX (settings screen or first-deploy modal).
- **D-41:** **CancelToken support on every dio call.** Riverpod auto-cancels on dispose. Without this, SSE leaks per Chat-screen visit.
- **D-42:** **Pagination on `messagesHistory(...)`: optional `limit` parameter (default 200, max 1000).** Mirrors backend D-04 exactly. No offset/cursor (locked-out per `mobile-mvp-decisions.md` deferred ideas).
- **D-43:** **Environment validation at boot: fail loud if `BASE_URL` is empty/malformed.** App constructor validates with `Uri.tryParse`; if invalid, throws `StateError('Set --dart-define BASE_URL=http://...')`. Crash points at the fix immediately. No silent fallback masking config errors.

### Env-config switch (deliberately minimal)

- **D-44:** **`--dart-define BASE_URL=...` at `flutter run` / `flutter build`.** App reads `String.fromEnvironment('BASE_URL', defaultValue: 'http://localhost:8000')` once at boot. **No in-app debug menu, no runtime switcher, no persistence layer for the origin, no in-app visibility widget.** The dev sets the URL externally per target. Per-target docs in `mobile/README.md`:
  - iOS Simulator: `BASE_URL=http://localhost:8000`
  - Android Emulator: `BASE_URL=http://10.0.2.2:8000` (NOT localhost — that maps to the emulator itself)
  - Real device on same wifi: `BASE_URL=http://<lan-ip>:8000`
  - ngrok: `BASE_URL=https://<id>.ngrok-free.app`
  - ngrok tunnel automation is a manual operator concern — out of scope for the app.

### Spike scope (Golden Rule #5 gate for Phase 25)

- **D-45:** **Spike code at `mobile/integration_test/spike_api_roundtrip_test.dart`** (Flutter's standard integration-test location, runs on simulator/emulator with `flutter test integration_test/`). Markdown artifact at `spikes/flutter-api-roundtrip.md` (matches existing repo convention). The integration_test code stays as a regression test post-spike.
- **D-46:** **Spike scenario: full round-trip end-to-end against a live local `api_server`.** Steps:
  1. `POST /v1/runs` with BYOK + recipe=nullclaw + model=anthropic/claude-haiku-4-5 + name=`spike-roundtrip-<unix-ts>-<short-uuid>` → assert 200 with `agent_instance_id`.
  2. `POST /v1/agents/:id/start` with `{channel: 'inapp', channel_inputs: {}}` → assert 202 within 60s.
  3. Connect SSE on `GET /v1/agents/:id/messages/stream` (Cookie injected) → assert connection establishes.
  4. `POST /v1/agents/:id/messages` with `Idempotency-Key` (uuid v4) + body `{content: 'spike roundtrip'}` → assert 202 + `message_id`.
  5. SSE delivers a non-empty assistant reply within bot timeout → assert content non-empty.
  6. `GET /v1/agents/:id/messages?limit=10` → assert BOTH user+assistant rows present, ordered ASC, assistant content **byte-equal** to SSE-delivered content (cross-channel parity per Phase 23 D-08).
  7. `POST /v1/agents/:id/messages` with **same** Idempotency-Key → assert returns the **same** `message_id` (replay cached, per Phase 23 D-09).
  8. Cancel the SSE connection mid-stream; reconnect with `Last-Event-ID = <last id received>` → assert subsequent events arrive **without duplicates** (D-13 reconnect contract).
  9. `POST /v1/agents/:id/stop` → assert 200/202 (cleanup, frees container).
- **D-47:** **Recipe + model: `nullclaw` + `anthropic/claude-haiku-4-5`** (or current Haiku model ID at spike time). Real combo, exercises agent container path + real LLM round-trip. Pinned in the markdown for reproducibility.
- **D-48:** **Cleanup: `POST /v1/agents/:id/stop` at end; agent_instance + inapp_messages rows left for inspection.** Re-running creates a NEW agent_instance via UPSERT-on-name (unique names — D-46 step 1). Nothing accumulates indefinitely; dev DB is reset between sessions.
- **D-49:** **Spike obtains a valid `session_id` via the manual cookie-paste path:** sign in once via the existing browser OAuth flow at the web playground (Phase 22c-oauth-google ships this), copy `ap_session` cookie value from browser DevTools, hand to the spike via `--dart-define SESSION_ID=<uuid>`. Spike's interceptor reads `SESSION_ID` from environment and injects as `Cookie: ap_session=<id>`. **Real session, real middleware, real cross-user isolation.** Phase 25 replaces this with native `google_sign_in` calling `POST /v1/auth/google/mobile`.
- **D-50:** **Spike invocation: `make spike` target in `mobile/Makefile`.** Wraps `fvm flutter test integration_test/spike_api_roundtrip_test.dart --dart-define BASE_URL=$BASE_URL --dart-define SESSION_ID=$SESSION_ID --dart-define OPENROUTER_KEY=$OPENROUTER_KEY`. Fails loud with a usage banner if any env var missing.
- **D-51:** **BYOK key source: `--dart-define OPENROUTER_KEY=<key>`** mirrored from a local `.env` (gitignored). `mobile/.env.example` documents the variable. The actual key lives in the dev's local `.env` (gitignored) and gets passed via `make spike OPENROUTER_KEY=$(grep OPENROUTER_KEY ../.env | cut -d= -f2)` or similar.
- **D-52:** **Failure-mode capture: print step + step description + status code + response body + request headers (Cookie/Authorization redacted to last 8 chars).** Mirrors `api_server`'s log redaction policy. Enables post-mortem from a single CI log.
- **D-53:** **Phase 24 exit gate: spike PASS is a HARD requirement.** Verifier checks: scaffold runs (APP-01), theme renders (APP-02), client surfaces all endpoints (APP-03), env switch works (APP-04), AND `spikes/flutter-api-roundtrip.md` records PASS with reproducibility metadata (APP-05). **Phase 25's plan-checker enforces "Phase 24 spike PASSED" as a precondition.** Spike runs **local only** — not in CI (requires real api_server + real Docker + OpenRouter network access + iOS Simulator or Android Emulator).
- **D-54:** **Spike artifact format: manual capture after a green run** (matches existing `spikes/` convention). Markdown YAML frontmatter captures reproducibility metadata: `date`, `git_sha`, `flutter_sdk_version`, `recipe`, `model`, `base_url`, `target` (sim/emulator/device), `verdict: PASS`. Body narrates the 9 steps with observed output.
- **D-55:** **Spike time-box: half-day max.** If the spike grows past that, the foundation isn't ready — fix the foundation, not the spike. The spike is the gate.
- **D-56:** **Concurrency: each spike run uses a unique agent name** (`spike-roundtrip-<unix-ts>-<short-uuid>`). Two simultaneous spike runs (e.g. two devs) get distinct `agent_instances`. Hard concurrency limit is the dev box's container concurrency cap (config); document the failure mode in `mobile/README.md`.

### Carry-forward from Phase 23 (locked, not re-litigated)

- **D-13/Phase 23:** Mobile receives chat replies via SSE on `GET /v1/agents/:id/messages/stream` (Last-Event-ID resume). `flutter_client_sse` package.
- **D-14/Phase 23:** Mobile sends via `POST /v1/agents/:id/messages` (body `{content}`, returns 202+message_id). **No `/chat` endpoint** — REQUIREMENTS.md APP-03's `POST /v1/agents/:id/chat` wording is superseded.
- **D-15/Phase 23:** OAuth via `google_sign_in` + `flutter_appauth` only. No WebView, no rolled-own.
- **D-17/Phase 23:** Sessions ride `Cookie: ap_session=<uuid>` header. BYOK keeps `Authorization: Bearer`.
- **D-22/Phase 23:** Deploy = `POST /v1/runs` → `POST /v1/agents/:id/start` (2 calls).
- **D-26/Phase 23:** 401 → route to OAuth (no refresh-token logic).
- **D-28/Phase 23:** Mobile deploys with `{channel: 'inapp', channel_inputs: {}}`.
- **D-34/Phase 23:** Cold-start auth check uses `GET /v1/users/me`.
- **APP-01 defaults:** Riverpod (state), go_router (navigation), dio (HTTP). Override only with documented rationale.
- **APP-02 theme:** monochrome (`#1F1F1F` foreground / `#FAFAF7` background mirroring solvr/frontend OKLCH values), corner radius `0`, `Inter` (Google Fonts) for sans-serif body, `JetBrains Mono` for mono. Light mode is canonical; dark mode optional later (deferred).
- **Golden Rules:** No mocks/stubs (real local api_server for spike); dumb client (no client-side catalogs — recipes from `/v1/recipes`, models from `/v1/models`); root cause first; spike before sealing plan.

### Claude's Discretion

- Exact split of `lib/core/api/` (one file vs per-resource).
- Whether to use `riverpod_annotation` + `riverpod_generator` for Riverpod 2 codegen, or hand-write providers (likely codegen — community standard).
- Exact `ThemeData` field-by-field setup (colors locked; widget defaults at planner's discretion).
- Whether `mobile/.env.example` lives at `mobile/.env.example` or `mobile/dotenv.example` (cosmetic).
- Internal naming of the spike's helper functions.
- dio adapter choice (default `IOHttpClientAdapter` is fine; `cronet_http` for HTTP/2 on Android is a future optimization).
- Whether to log every request/response in dev mode via the interceptor (default: yes, with redaction; planner picks).
- Riverpod-managed singleton dio vs constructor-injected (likely Riverpod-managed via a `ProviderScope` override; planner picks).
- Exact `ErrorCode` enum values mirrored from backend (planner reads `api_server/src/api_server/errors.py` and mirrors).

### Folded Todos

None — `gsd-tools list-todos` returned 0.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level locked decisions
- `.planning/PROJECT.md` — Mission, OAuth-only auth, Hetzner+Docker model, mobile-first MVP framing.
- `.planning/REQUIREMENTS.md` — APP-01..APP-05 (note: APP-03's `/v1/agents/:id/chat` URL is superseded by Phase 23 D-14; mobile uses `POST /v1/agents/:id/messages`).
- `.planning/notes/mobile-mvp-decisions.md` — Locked architectural decisions for the mobile MVP milestone.
- `.planning/seeds/streaming-chat.md` — Token-level streaming roadmap (additive, post-MVP).
- `CLAUDE.md` — Golden rules (no mocks/stubs; dumb client; ship locally; root-cause-first; spike before planning).
- `MEMORY.md` — Auto-memory feedback rules (no mocks/stubs, dumb client, code-we'll-reuse, test-everything-before-planning).

### Prior phase contracts (load-bearing — D-numbered decisions referenced above)
- `.planning/phases/23-backend-mobile-api-chat-proxy-persistence-auth-shim/23-CONTEXT.md` — Phase 23 D-01..D-34 (chat-send/SSE/auth contracts mobile reuses).
- `.planning/phases/23-backend-mobile-api-chat-proxy-persistence-auth-shim/23-PHASE-SUMMARY.md` — Phase 23 ship summary (49/49 verifier PASS).
- `.planning/phases/22c.3-inapp-chat-channel/22c.3-CONTEXT.md` — Inapp dispatcher + outbox + SSE substrate.
- `.planning/phases/22c.3.1-runner-inapp-wiring/` — `agent_containers` rows + e2e harness.
- `.planning/phases/22c-oauth-google/22c-CONTEXT.md` — OAuth contracts (`require_user`, `ApSessionMiddleware`, `upsert_user`, `mint_session`); the browser flow that mints the spike's session cookie (D-49).

### Backend endpoints the typed client MUST surface
- `api_server/src/api_server/routes/runs.py` — `POST /v1/runs` (UPSERT agent_instance + smoke). Mobile reuses (Phase 23 D-22).
- `api_server/src/api_server/routes/agent_lifecycle.py` — `POST /v1/agents/:id/start`, `POST /v1/agents/:id/stop`. Mobile reuses with `channel='inapp'` (Phase 23 D-28).
- `api_server/src/api_server/routes/agent_messages.py` — `POST /v1/agents/:id/messages` (fast-ack, Idempotency-Key REQUIRED per Phase 23 D-09); SSE `GET /v1/agents/:id/messages/stream`; `GET /v1/agents/:id/messages?limit=N` history.
- `api_server/src/api_server/routes/agents.py` (or `routes/runs.py:list_agents`) — `GET /v1/agents` extended with `status` + `last_activity` (Phase 23 D-10/D-27).
- `api_server/src/api_server/routes/recipes.py` — `GET /v1/recipes`. Mobile fetches recipe catalog from this (no Flutter-side hardcoded list — Golden Rule #2).
- `api_server/src/api_server/routes/models.py` — `GET /v1/models` OpenRouter passthrough proxy (Phase 23 D-18..D-20).
- `api_server/src/api_server/routes/auth.py` — `POST /v1/auth/google/mobile`, `POST /v1/auth/github/mobile` (Phase 23 D-16). Phase 25 uses; Phase 24 spike does NOT (uses cookie-paste per D-49).
- `api_server/src/api_server/routes/users.py` — `GET /v1/users/me`. Mobile cold-start uses (Phase 23 D-34); the placeholder screen in Phase 24 may use this OR `/healthz` for the simplest call.
- `api_server/src/api_server/routes/health.py` — `GET /healthz` returns `{"ok": true}`. Phase 24 placeholder screen target.
- `api_server/src/api_server/middleware/session.py` — `ApSessionMiddleware` (cookie-header transport per Phase 23 D-17).
- `api_server/src/api_server/middleware/idempotency.py` — `IdempotencyMiddleware`; replay semantics per Phase 23 D-09.
- `api_server/src/api_server/errors.py` — `ErrorCode` enum + `make_error_envelope()`. Mobile mirrors `ErrorCode` in Dart per D-38.

### Theme reference (Solvr Labs design language source)
- `/Users/fcavalcanti/dev/solvr/frontend/app/globals.css` — OKLCH values for `--background` / `--foreground` / `--primary` / `--muted` etc. that the Flutter `ThemeData` mirrors (light mode only — `:root` block lines 6-39). `--radius: 0rem` translates to corner radius 0 across all Flutter widgets.
- `/Users/fcavalcanti/dev/solvr/frontend/` — broader visual reference for the `>_ SOLVR_LABS` mark and JetBrains Mono usage patterns.

### External / package documentation
- Flutter SDK pinning via FVM: <https://fvm.app/>
- Riverpod 2: <https://riverpod.dev/>
- go_router: <https://pub.dev/packages/go_router>
- dio: <https://pub.dev/packages/dio>
- flutter_client_sse: <https://pub.dev/packages/flutter_client_sse>
- google_sign_in (Flutter): <https://pub.dev/packages/google_sign_in>
- flutter_appauth: <https://pub.dev/packages/flutter_appauth>
- flutter_secure_storage: <https://pub.dev/packages/flutter_secure_storage>
- shared_preferences: <https://pub.dev/packages/shared_preferences> (used for non-sensitive prefs only — currently no use in Phase 24)
- uuid: <https://pub.dev/packages/uuid>
- google_fonts (for Inter + JetBrains Mono delivery): <https://pub.dev/packages/google_fonts>
- very_good_analysis: <https://pub.dev/packages/very_good_analysis>

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (out of repo, but informs theme + spike)
- `/Users/fcavalcanti/dev/solvr/frontend/app/globals.css` — color tokens that the Flutter `ThemeData` mirrors verbatim (D-31 from Phase 23's APP-02). Light mode `:root` block is the canonical source.

### Existing Mobile Code
- **None.** Phase 24 is the cold-start of `mobile/`. `flutter create` baseline lands at the start of execution.

### Established Patterns (from sibling subprojects, mirrored where applicable)
- `api_server/Makefile` — target naming convention to mirror in `mobile/Makefile` (D-22).
- `api_server/.python-version` + `uv` pinning — same SDK-pinning discipline as FVM (D-05).
- `api_server/src/api_server/errors.py` `ErrorCode` enum — mirror in Dart (D-38).
- `api_server/src/api_server/middleware/idempotency.py` replay semantics — informs the typed client's idempotency-key UX (D-36).
- `frontend/components/playground-form.tsx` — TypeScript client patterns for `apiGet(...)` + `Authorization: Bearer` BYOK that the Dart client mirrors structurally (D-40).
- `tests/spikes/` (api_server side) — markdown spike artifact format the Flutter spike at `spikes/flutter-api-roundtrip.md` mirrors (D-54).

### Integration Points (where new code lands)

**New top-level directory:**
- `mobile/` — entire Flutter project (root for D-01).

**New files at repo root:**
- `spikes/flutter-api-roundtrip.md` — spike artifact (D-46/D-54).

**New files inside `mobile/`** (final structure decided by planner; suggested layout):
- `mobile/pubspec.yaml`, `mobile/pubspec.lock`
- `mobile/.fvmrc`
- `mobile/Makefile`
- `mobile/README.md` (D-22, D-44, D-49 docs)
- `mobile/analysis_options.yaml` (very_good_analysis include — D-23)
- `mobile/.env.example` (BASE_URL, SESSION_ID, OPENROUTER_KEY documented — D-44/D-49/D-51)
- `mobile/.gitignore` (D-08)
- `mobile/lib/main.dart` (entry; reads BASE_URL via `String.fromEnvironment` and validates per D-43; sets `SystemUiOverlayStyle.dark` per D-17)
- `mobile/lib/app.dart` (root `MaterialApp.router` with the Solvr Labs theme + go_router config)
- `mobile/lib/core/theme/solvr_theme.dart` (ThemeData mirroring solvr/frontend tokens per APP-02)
- `mobile/lib/core/api/api_client.dart` (or split per resource — D-31)
- `mobile/lib/core/api/auth_interceptor.dart` (D-35)
- `mobile/lib/core/api/result.dart` (sealed Result + ApiError + ErrorCode — D-32, D-38)
- `mobile/lib/core/api/api_endpoints.dart` (path constants)
- `mobile/lib/core/storage/secure_storage.dart` (flutter_secure_storage wrapper for session_id — D-35)
- `mobile/lib/core/router/app_router.dart` (go_router config — placeholder route only in P24)
- `mobile/lib/core/env/app_env.dart` (BASE_URL + boot validation — D-43, D-44)
- `mobile/lib/features/_placeholder/healthz_screen.dart` (the only screen — calls `/healthz`, renders "OK" via real ThemeData)
- `mobile/lib/features/{dashboard,new_agent,chat}/` (empty placeholder dirs per D-26)
- `mobile/integration_test/spike_api_roundtrip_test.dart` (D-45)
- `mobile/test/` (unit tests scaffold; minimal in P24)
- `mobile/ios/Runner/Info.plist` updates (URL scheme D-04, ATS exemption D-12, orientation D-14)
- `mobile/android/app/src/main/AndroidManifest.xml` updates (intent-filter D-04, orientation D-14)
- `mobile/android/app/src/debug/res/xml/network_security_config.xml` (cleartext exemption D-13)
- `.github/workflows/mobile.yml` (or extend root CI workflow — D-27)

**No backend files modified.** Phase 23 + 22c-oauth-google + 22c.3.1 ship everything mobile needs to consume.

</code_context>

<specifics>
## Specific Ideas

- **"The API is ready, just USE the API"** is the over-arching principle the user reinforced multiple times during this discussion. Every API-client decision is anchored in: there is no client architecture beyond "make HTTP calls with dio + parse the Stripe-shape response into typed Result." No abstraction layers, no DI ceremony, no codegen toolchains. The intelligence lives in the backend; the Flutter side is plumbing.
- **"The dev handles env, not the app"** is the second over-arching principle. No in-app debug menu, no env-banner, no runtime origin switcher. `--dart-define BASE_URL=...` at flutter-run time. The README documents per-target URLs (iOS Simulator localhost / Android Emulator 10.0.2.2 / device LAN IP / ngrok). Operator concerns (tunneling, IP discovery) stay external.
- **"Do the app as it was scoped — production-style"** rules out any debug-mode-only UI. Phase 24's placeholder screen renders through the real theme + real router + real client + real interceptor, with zero developer chrome. Debugging is `dart:developer log()` + IDE inspector. The placeholder IS the foundation; Phase 25 just adds screens to it.
- **The spike is the gate, not theater.** D-53 makes spike PASS a hard exit-gate requirement enforced by Phase 25's plan-checker. The 9-step round-trip (D-46) covers every load-bearing mechanism: cookie injection, Idempotency-Key replay, SSE delivery, Last-Event-ID resume, GET /messages parity. If any step fails, the foundation isn't ready — fix the foundation, not the spike.
- **The OAuth flow in Phase 24 is solved by NOT solving it.** D-49 routes around it: the spike obtains a session by pasting a cookie minted via the existing browser OAuth at the web playground. Phase 25 ships native `google_sign_in` + `flutter_appauth` calling Phase 23's mobile-credential endpoints. This unblocks Phase 24 without forcing OAuth UX work into the foundation.

</specifics>

<deferred>
## Deferred Ideas

- **Token-level streaming chat** — see `seeds/streaming-chat.md`. Triggered post-MVP if block-and-fast-ack + SSE feels janky in real demos.
- **Real Solvr Labs app icon + native splash** — Phase 24 ships placeholder icon. Real asset packaging belongs to a polish/release-readiness phase.
- **fastlane** — iOS/Android release automation. Premature; Phase 24 ships nothing to TestFlight or Play Store.
- **Code signing for release distribution** — App Store distribution cert, Play Store keystore, CI-side credential storage. Belongs to a release-readiness phase.
- **Apple Privacy Manifest (`PrivacyInfo.xcprivacy`)** — required only for App Store submission. Defer to release-readiness.
- **Push notifications, crash reporting (Sentry/Crashlytics), analytics** — explicitly out of MVP per `mobile-mvp-decisions.md`. Defer to a polish/release phase.
- **Localization (l10n) scaffolding** (`flutter_localizations` + `.arb` files) — MVP is en-US only.
- **Universal Links / App Links (HTTPS-verified deep linking)** — requires a verified HTTPS domain ownership we don't yet have. Future hardening once Hetzner deploy lands.
- **Build flavors (dev/staging/prod)** — premature without prod environments to flavor.
- **Dark mode** — `mobile-mvp-decisions.md` says "Light mode is canonical; dark mode optional later." Defer until a stakeholder asks for it.
- **In-app debug menu / env switcher / dev overlays** — explicitly rejected by user during Phase 24 discussion. If a future need arises, it's a deliberate add, not a default.
- **Background SSE / push-driven message delivery** — iOS suspends connections after ~30s background. D-13's reconnect-on-foreground covers MVP. True background push (APNS/FCM) is a future hardening.
- **API client codegen (retrofit / openapi-generator)** — re-litigate at 20+ endpoints. Hand-written wins at MVP scale.
- **Mobile spike in CI** — requires macOS runner + Docker + OpenRouter network + iOS Simulator. v0.4+ work.
- **Mobile-specific PR template** — re-evaluate if mobile review patterns diverge from the rest of the repo.
- **Keychain Sharing entitlement** — needed only when shipping app extensions or sharing data across bundle IDs. Add when first such feature lands.
- **fpdart / dartz Either** — re-evaluate if FP composition becomes a recurring pattern. Sealed Result wins at MVP scale.
- **freezed for immutable DTOs** — re-evaluate if DTO count crosses ~30 OR if sealed unions become common.
- **`cronet_http` dio adapter for Android HTTP/2** — performance optimization for v0.4+.
- **Web chat de-mock** (`frontend/app/dashboard/agents/[id]/page.tsx`) — Phase 23 deferred this. Belongs to a frontend phase, not mobile.

### Reviewed Todos (not folded)
None — `gsd-tools list-todos` returned 0 pending todos.

</deferred>

---

*Phase: 24-flutter-foundation*
*Context gathered: 2026-05-02*

# Phase 24: Flutter Foundation — Research

**Researched:** 2026-05-02
**Domain:** Flutter cold-start scaffold (mobile/) + hand-written typed dio client + theme + spike harness
**Confidence:** HIGH (load-bearing package APIs verified against pub.dev + official docs as of May 2026)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

The 56 D-decisions in `.planning/phases/24-flutter-foundation/24-CONTEXT.md` are LOCKED. Highlights the planner MUST honor verbatim:

- **D-01..D-04 (scaffold + bundle)** — `mobile/` root; bundle id `com.solvrlabs.agentplayground`; display name `Solvr Labs`; OAuth scheme `solvrlabs://`.
- **D-05 (FVM)** — Flutter SDK pinned via FVM; `.fvmrc` committed; `.fvm/flutter_sdk` symlink gitignored.
- **D-08 (.gitignore + lockfile)** — commit `pubspec.lock`.
- **D-09 (signing)** — debug only; no TestFlight / App Store work.
- **D-12 (iOS ATS)** — whitelist `localhost` + `NSAllowsLocalNetworking=true`.
- **D-13 (Android cleartext)** — `network_security_config.xml` scoped to debug; `localhost` + `10.0.2.2` + LAN ranges.
- **D-14 (orientation)** — portrait-only.
- **D-15 (deep link)** — custom URL scheme only, no Universal Links.
- **D-16 (no flavors)** — single debug+release; env via `--dart-define`.
- **D-17 (system UI)** — `SystemUiOverlayStyle.dark`.
- **D-18 (entitlements)** — default Keychain only; **no Keychain Sharing** entitlement. ⚠️ See `## Common Pitfalls #4` — known iOS-Simulator volatility risk for production secure_storage path; spike sidesteps via `--dart-define SESSION_ID` so risk does not block Phase 24, but flagged for Phase 25.
- **D-22 (Makefile)** — targets: `make doctor`, `make get`, `make ios`, `make android`, `make test`, `make spike`.
- **D-23 (lints)** — `very_good_analysis`.
- **D-25 (logging)** — `dart:developer log()` only; no third-party logger.
- **D-26 (folder layout)** — feature-based; `lib/core/` + `lib/shared/` + `lib/features/{dashboard,new_agent,chat}/` placeholder dirs.
- **D-31 (hand-written client)** — NO codegen for the API client (retrofit/openapi-generator banned).
- **D-32 (Result<T>)** — Dart 3 sealed class `sealed class Result<T> { Ok(T); Err(ApiError); }`.
- **D-33 (SSE)** — `flutter_client_sse` package (Phase 23 D-13 lock).
- **D-34 (JSON)** — manual `fromJson` / `toJson`; **no `build_runner` for JSON, no `*.g.dart` for DTOs**.
- **D-35 (cookie injection)** — dio Interceptor reads from `flutter_secure_storage`; on 401 clear stored session + emit auth-required event.
- **D-36 (Idempotency-Key)** — `Uuid().v4()` per Send; reuse on retry.
- **D-37 (timeouts)** — 10s connect / 30s receive; SSE has no receive timeout.
- **D-38 (ApiError)** — typed Dart enum mirroring `api_server/src/api_server/models/errors.py::ErrorCode`.
- **D-39 (no auto-retry)** — caller surfaces `Err`; idempotency-key + SSE-package-reconnect cover safe retries.
- **D-40 (BYOK header)** — `Authorization: Bearer <key>` only on `runs(...)` and `start(...)`; per-request override, not global.
- **D-41 (CancelToken)** — every dio call accepts a CancelToken; Riverpod auto-dispose maps to `cancelToken.cancel()`.
- **D-42 (pagination)** — `messagesHistory(limit: int = 200, max: 1000)`.
- **D-43 (env validation)** — fail loud at boot if `BASE_URL` empty/malformed; `Uri.tryParse`.
- **D-44 (env switch)** — `--dart-define BASE_URL=...`; **no in-app debug menu, no env banner, no runtime switcher**. ⚠️ This SUPERSEDES REQUIREMENTS.md APP-04's "in-app debug menu" wording — the planner MUST NOT regress to that.
- **D-45..D-56 (spike)** — integration_test at `mobile/integration_test/spike_api_roundtrip_test.dart`; markdown at `spikes/flutter-api-roundtrip.md`; 9-step round-trip; PASS is the **hard exit gate**; spike runs LOCAL ONLY (not CI).
- **Carry-forward from Phase 23 (D-13/14/15/17/22/26/28/34)** — chat reuses existing `POST /v1/agents/:id/messages` (no `/chat`); SSE on `GET /v1/agents/:id/messages/stream` with Last-Event-ID; OAuth via `google_sign_in` + `flutter_appauth`; Cookie transport for session; 2-call deploy (`/runs` then `/start`); 401 → OAuth route; `channel: 'inapp'`; cold-start uses `/v1/users/me`.

### Claude's Discretion

- Exact split of `lib/core/api/` (one file vs per-resource).
- Riverpod codegen vs hand-written providers (this RESEARCH **recommends codegen** — see Standard Stack and `## Common Pitfalls #1`).
- Exact `ThemeData` field-by-field setup (colors locked in APP-02; widget defaults at planner's discretion).
- Whether `mobile/.env.example` lives at `mobile/.env.example` or `mobile/dotenv.example` (cosmetic).
- Internal naming of spike helper functions.
- dio adapter choice (default `IOHttpClientAdapter` is fine).
- Whether to log every request/response in dev via the interceptor (planner picks; default: yes with redaction).
- Riverpod-managed singleton dio vs constructor-injected (planner picks; recommend Riverpod-managed).
- Exact `ErrorCode` enum values mirrored from `models/errors.py`.

### Deferred Ideas (OUT OF SCOPE)

- Token-level streaming (`seeds/streaming-chat.md`).
- Real Solvr Labs app icon + splash.
- fastlane / TestFlight / Play Store.
- Apple Privacy Manifest (`PrivacyInfo.xcprivacy`).
- Push notifications, Sentry/Crashlytics, analytics.
- Localization (`flutter_localizations` + `.arb`).
- Universal Links / App Links.
- Build flavors.
- Dark mode.
- **In-app debug menu / env switcher / dev overlays** (explicitly rejected).
- Background SSE / push delivery.
- API client codegen (re-litigate at 20+ endpoints).
- Mobile spike in CI (requires macOS runner + iOS Sim + Docker).
- Mobile-specific PR template.
- Keychain Sharing entitlement.
- `fpdart` / `dartz` `Either`.
- `freezed`.
- `cronet_http` adapter for Android HTTP/2.
- Web chat de-mock.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description (verbatim from REQUIREMENTS.md, with CONTEXT supersessions noted) | Research Support |
|----|-------------------------------------------------------------------------------|------------------|
| **APP-01** | A Flutter native project lives at `mobile/` with `flutter create` baseline + Riverpod (state) + go_router (nav) + dio (HTTP). | `## Standard Stack` pins exact versions of all 4 packages with `[VERIFIED: pub.dev]` confidence. CONTEXT D-01..D-08 honored. |
| **APP-02** | Flutter theme implements Solvr Labs design language: monochrome (`#1F1F1F` foreground / `#FAFAF7` background mirroring the OKLCH values from `solvr/frontend/app/globals.css`), corner radius `0`, `Inter` for sans-serif, `JetBrains Mono` for mono. Light mode is canonical. | `## Architecture Patterns` § Theme has the exact `ThemeData` skeleton + the OKLCH→sRGB conversion table for the 5 load-bearing tokens. Decision recommended on `## Common Pitfalls #6` for `google_fonts` runtime-fetch vs bundled. |
| **APP-03** | A typed API client covers every endpoint the screens consume: `POST /v1/agents/:id/start`, `POST /v1/agents/:id/messages` (CONTEXT D-14 supersedes the `/chat` URL in spec wording), `GET /v1/agents/:id/messages`, `GET /v1/agents`, `GET /v1/recipes`, `GET /v1/models`, plus carry-forward `POST /v1/runs`, `POST /v1/agents/:id/stop`, `GET /v1/users/me`, `GET /healthz`, `POST /v1/auth/{google,github}/mobile`, SSE `GET /v1/agents/:id/messages/stream`. Errors and timeouts surface as typed `Result`/`Either`. | `## Architecture Patterns` § API Client maps each endpoint to its Dart method; `## Architecture Patterns` § Error Envelope documents the exact `ErrorCode` enum mirror; `## Code Examples` shows a representative dio Interceptor + sealed Result + per-call CancelToken. |
| **APP-04** | An env-config switch lets the app target localhost / LAN IP / ngrok URL — runtime-configurable without recompile. | **CONTEXT D-44 SUPERSEDES** the "in-app debug menu" wording. The runtime-configuration mechanism is `--dart-define BASE_URL=...` at `flutter run` / `flutter build` time. The dev sets env externally per target. README documents iOS-Simulator (`localhost`) vs Android-Emulator (`10.0.2.2`) vs LAN/ngrok values. `## Common Pitfalls #5` covers the Pixel-system-image `10.0.3.2` edge case. |
| **APP-05** | A spike artifact at `spikes/flutter-api-roundtrip.md` proves end-to-end against a real local API server: deploy round-trip + chat round-trip + auth-shim header injection — captured BEFORE Phase 25's plan seals (Golden Rule #5). | The 9-step spike (CONTEXT D-46) is materially richer than the spec's 3-mechanism wording — it adds Idempotency-Key replay (D-46 step 7), Last-Event-ID resume (D-46 step 8), GET /messages parity (D-46 step 6), and clean stop (D-46 step 9). `## Architecture Patterns` § Spike Harness gives the canonical structure; `## Common Pitfalls #2` enumerates the SSE Last-Event-Id manual-injection requirement (load-bearing finding). |

</phase_requirements>

## Summary

This phase cold-starts a production-shaped Flutter app at `mobile/` whose only screen is a placeholder `/healthz` round-trip — but every load-bearing mechanism a Phase-25 chat UI will rely on is wired and proven by a 9-step integration_test spike against the live Phase 23 backend BEFORE Phase 25 plans seal. The 5 mechanisms whose package-level support determines whether the spike is even possible — (a) dio Interceptor lifecycle for cookie injection + 401 mapping, (b) `flutter_client_sse` Last-Event-ID manual injection, (c) Dart 3 sealed `Result<T>` exhaustive switch, (d) `google_fonts` Inter + JetBrains Mono delivery, (e) `--dart-define`-driven env validation at boot — were each verified against pub.dev / official docs in this research session. **Two findings in particular shape the planner's Wave-0 spike list:** (1) `flutter_client_sse` 2.0.3 has NO `lastEventId` parameter and NO auto-reconnect — the caller MUST track `event.id` and pass `Last-Event-Id` in the `header:` map on a manual reconnect; the spike step 8 must exercise this exact pattern, not assume the package "just resumes." (2) `flutter_secure_storage` on iOS Simulator can lose values across cold restarts; the spike sidesteps the issue via `--dart-define SESSION_ID=...` (D-49) but the production interceptor (D-35) needs Phase 25 to explicitly test secure-storage round-trip on a real device, NOT a Simulator — flagged for downstream.

Stack pins are concrete and verified as of May 2026: Flutter 3.41 (Dart 3.9), Riverpod 3.3.x, dio 5.9.x, go_router 17.x, flutter_client_sse 2.0.3, very_good_analysis 10.x, flutter_appauth 12.0.0, google_sign_in 7.2.0, flutter_secure_storage 10.0.0, google_fonts 8.1.0, uuid 4.5.x. The package compatibility matrix has zero red cells for these versions. The Riverpod codegen path (`riverpod_annotation` + `riverpod_generator` + `build_runner`) is the 2026 community default and is recommended here — but it does NOT conflict with D-34's "no build_runner for JSON" since the two runners (riverpod_generator vs json_serializable) are independent and only the JSON one is rejected.

**Primary recommendation:** Plan with Riverpod codegen for providers (`@riverpod` annotation), hand-written manual JSON for DTOs, hand-written sealed `Result<T>`, ONE shared dio instance behind a Riverpod provider with the cookie interceptor + log-redaction interceptor + a logging interceptor (dev-only, redacted Authorization+Cookie), `flutter_client_sse` wrapped in a thin `MessagesStream` class that **manually tracks `last_event_id` and re-passes it as a header on retry**, and a spike test that drives the 9 steps via a single integration_test `testWidgets` block with `IntegrationTestWidgetsFlutterBinding`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| HTTP request lifecycle | Mobile App | — | dio runs on-device; backend is just an HTTP server. |
| Auth cookie persistence | Mobile App (flutter_secure_storage) | — | Backend issues opaque session IDs; client persists them. Phase 24 spike injects cookie from `--dart-define`, sidestepping persistence (D-49). |
| BYOK key persistence | Mobile App (Phase 25) | — | Phase 24 only ships the per-request `Authorization: Bearer` plumbing (D-40); the actual key entry UX is Phase 25. |
| Idempotency-Key generation | Mobile App | — | Generated once per Send press (D-36); backend caches the response per IdempotencyMiddleware. |
| SSE Last-Event-Id tracking | Mobile App | — | `flutter_client_sse` does NOT auto-track. Caller maintains a `_lastSeq` field and re-injects on reconnect. Backend is dumb (replays from header). |
| Cookie / Authorization header transport | Mobile App | — | Backend session middleware (`ApSessionMiddleware`) reads the cookie either way; mobile sets header explicitly. |
| Recipe + model catalogs | Backend (`/v1/recipes`, `/v1/models`) | — | Golden Rule #2: NO Flutter-side hardcoded list. Phase 24 client surfaces the methods; Phase 25 UI consumes. |
| Chat history snapshot | Backend (`GET /v1/agents/:id/messages`) | — | Single source of truth: `inapp_messages` rows mapped to events server-side (Phase 23 D-03). Mobile renders. |
| Live chat reply delivery | Backend (SSE) | Mobile App (subscribe + display) | SSE is push-from-server; client opens the connection and consumes. |
| Container lifecycle | Backend (`/v1/runs` + `/v1/agents/:id/start` + `/stop`) | — | Mobile is a thin caller; container spawning lives entirely in api_server. |
| OAuth Google sign-in | iOS/Android Native (`google_sign_in`) | Backend (`POST /v1/auth/google/mobile`) | Native SDK collects credential; backend mints session. Phase 25 wires; Phase 24 spike uses cookie-paste shim (D-49). |
| OAuth GitHub sign-in | OS browser (`flutter_appauth`) | Backend (`POST /v1/auth/github/mobile`) | AppAuth pattern: system browser + PKCE. Phase 25 wires; Phase 24 only registers the deep-link scheme (D-04, D-15). |
| Theme + typography | Mobile App | — | `ThemeData` mirrors solvr/frontend OKLCH tokens. No backend involvement. |
| Env-config (BASE_URL) | Build-time (`--dart-define`) | — | D-44: external to the app. No runtime switcher. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **Flutter SDK** | **3.41.0** (Dart 3.9) `[CITED: docs.flutter.dev/release/release-notes]` | Mobile framework | Latest stable as of 2026-02-20 release; pinned via FVM per D-05. |
| **flutter_riverpod** | **3.3.1** `[CITED: pub.dev/packages/flutter_riverpod]` | State + DI + reactive caching | 1.76M downloads, 2.86k likes — community default. APP-01 mandates. |
| **riverpod_annotation** + `riverpod_generator` + `build_runner` | annotation **4.0.2** + matching gen `[CITED: pub.dev/packages/riverpod_annotation, riverpod.dev]` | Provider codegen | 2026 community-default authoring style for Riverpod; pairs with flutter_riverpod 3.x. **Independent from json_serializable** — using it does NOT contradict CONTEXT D-34. |
| **go_router** | **17.2.3** `[CITED: pub.dev/packages/go_router]` | Declarative routing | Maintained by Flutter team (`packages/go_router` in flutter/packages); APP-01 default. |
| **dio** | **5.9.2** `[CITED: pub.dev/packages/dio]` | HTTP client | Interceptors, CancelToken, per-request `Options(headers: {...})` merge — exactly the surface CONTEXT D-35/D-37/D-40/D-41 require. |
| **flutter_client_sse** | **2.0.3** `[VERIFIED: pub.dev + GitHub source — last release 2024-08-28]` | SSE consumer | LOCKED by Phase 23 D-13. Maintenance status: low (last release ~20 months ago) — flagged in `## State of the Art`. Caller-managed Last-Event-Id (see Pitfall #2). |
| **uuid** | **4.5.3** `[CITED: pub.dev/packages/uuid]` | UUIDv4 generation | `Uuid().v4()` for Idempotency-Key per D-36. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **flutter_secure_storage** | **10.0.0** `[CITED: pub.dev/packages/flutter_secure_storage]` | session_id persistence (Keychain / EncryptedSharedPreferences) | D-35 cookie injection. ⚠️ Pitfall #4 documents iOS-Simulator caveat. |
| **google_sign_in** | **7.2.0** `[CITED: pub.dev/packages/google_sign_in]` | Native Google sign-in (iOS + Android) | Phase 23 D-15. Phase 24 only adds the dependency + native config; sign-in flow is Phase 25. |
| **flutter_appauth** | **12.0.0** `[CITED: pub.dev/packages/flutter_appauth]` | AppAuth (system browser + PKCE) for GitHub | Phase 23 D-15. Phase 24 registers `solvrlabs://oauth/github` scheme; flow is Phase 25. |
| **google_fonts** | **8.1.0** `[CITED: pub.dev/packages/google_fonts]` | Inter + JetBrains Mono delivery | APP-02. Pitfall #6 covers runtime-fetch vs bundled-asset trade-off. |
| **very_good_analysis** | **10.0.0** `[CITED: pub.dev/packages/very_good_analysis]` | Strict lints | D-23. Stricter than `flutter_lints` (`public_member_api_docs`, `prefer_final_locals`, `sort_pub_dependencies`, `type_annotate_public_apis`, `unnecessary_await_in_return`). Does NOT conflict with manual JSON (no rule about codegen requirement). |
| **integration_test** | bundled (`flutter_test` SDK) | Spike + future widget E2E | D-45. `flutter test integration_test/foo_test.dart` is canonical (drive is web-only). |
| **fvm** (CLI) | latest (`fvm.app`) `[CITED: fvm.app/documentation/getting-started/configuration]` | Flutter SDK pinning | D-05. `.fvmrc` pins specific version; `.fvm/flutter_sdk` symlink. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `flutter_client_sse` (D-33 LOCKED) | `eventflux` 2.2.1 (auto-reconnect with backoff config) | EventFlux supports auto-reconnect via `ReconnectConfig`, BUT — like flutter_client_sse — it does NOT auto-track Last-Event-Id either. Custom-header injection is needed in BOTH packages. CONTEXT D-33 lock stands. |
| `flutter_client_sse` | `flutter_http_sse` (newer, has `retry: true` config) | Much smaller community; not a clear win over D-33's locked choice. |
| `flutter_client_sse` | hand-rolled chunked-decoder over `package:http` | More code to own; SSE parsing is non-trivial (id/event/data field accumulation, comment handling, `:ping\n\n` heartbeat handling). Stick with the package. |
| Riverpod codegen (`@riverpod`) | Hand-written `Provider`/`StateProvider`/`AsyncNotifierProvider` | Hand-written is 100% valid; codegen reduces boilerplate at the cost of one `build_runner` watch process during dev. **Independent from D-34** (D-34 forbids json codegen, not provider codegen). |
| Riverpod | Bloc, Provider, GetX, MobX | Riverpod is the APP-01 default; mobile-mvp-decisions.md re-confirms. No reason to deviate. |
| dio | `package:http` (stdlib-equivalent), Chopper | dio's interceptor surface + CancelToken + per-request Options merge are exactly what CONTEXT D-35/D-37/D-40/D-41 require. APP-01 default. |
| `very_good_analysis` | `flutter_lints`, `lints` | flutter_lints is permissive; very_good_analysis is the api_server-equivalent strict-from-day-1 choice. D-23 LOCKED. |
| FVM | asdf, mise (with `flutter` plugin), Docker-based Flutter | FVM is the project-specific defacto standard for Flutter; D-05 LOCKED. |
| Manual JSON | `freezed` + `json_serializable` codegen | Re-evaluate at 30+ DTOs (deferred). At ~10 DTOs the codegen tax exceeds the gain. D-34 LOCKED. |

**Installation:**

```bash
# pubspec.yaml  (planner writes the actual file)
dependencies:
  flutter:
    sdk: flutter
  flutter_riverpod: ^3.3.1
  riverpod_annotation: ^4.0.2
  go_router: ^17.2.3
  dio: ^5.9.2
  flutter_client_sse: ^2.0.3
  flutter_secure_storage: ^10.0.0
  google_sign_in: ^7.2.0
  flutter_appauth: ^12.0.0
  google_fonts: ^8.1.0
  uuid: ^4.5.3

dev_dependencies:
  flutter_test:
    sdk: flutter
  integration_test:
    sdk: flutter
  riverpod_generator: ^3.0.0       # planner verifies major matches annotation
  build_runner: ^2.4.0
  very_good_analysis: ^10.0.0
```

**Version verification:** Each version above was checked against pub.dev during this research session (2026-05-02). Re-verify with `flutter pub outdated` at scaffold time; if any of (flutter_client_sse, flutter_appauth, google_sign_in, flutter_secure_storage) has shipped a major bump in the intervening days, the planner reads the changelog before pinning.

## Architecture Patterns

### System Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│  Build host (--dart-define BASE_URL / SESSION_ID / OPENROUTER_KEY)   │
└────────────┬─────────────────────────────────────────────────────────┘
             │  baked at flutter run / flutter build
             ▼
┌──────────────────────────────────────────────────────────────────────┐
│  iOS Simulator   /   Android Emulator   /   Physical device          │
│ ┌──────────────────────────────────────────────────────────────────┐ │
│ │  main.dart                                                        │ │
│ │   1. Read BASE_URL via String.fromEnvironment + Uri.tryParse     │ │
│ │   2. Throw StateError on empty/malformed (D-43)                  │ │
│ │   3. SystemUiOverlayStyle.dark (D-17)                            │ │
│ │   4. runApp(ProviderScope(child: SolvrLabsApp()))                │ │
│ └─────────────────────────────┬────────────────────────────────────┘ │
│                               │                                      │
│ ┌─────────────────────────────▼────────────────────────────────────┐ │
│ │  app.dart  →  MaterialApp.router(theme: solvrTheme, ...)         │ │
│ │                                  │                                │ │
│ │            go_router (lib/core/router/app_router.dart)           │ │
│ │                  └─→ HealthzScreen (the only Phase-24 screen)    │ │
│ └──────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│ ┌──────────────────────────────────────────────────────────────────┐ │
│ │  ProviderScope tree (Riverpod 3.x)                                │ │
│ │    dioProvider → singleton Dio with:                              │ │
│ │       AuthInterceptor (cookie inject + 401 → clear+emit)         │ │
│ │       LogInterceptor (dev-only, Cookie+Authorization redacted)   │ │
│ │    apiClientProvider → wraps dioProvider, exposes typed methods   │ │
│ │    secureStorageProvider → flutter_secure_storage                 │ │
│ │    healthCheckProvider → Future<Result<HealthOk>>                 │ │
│ └──────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│      typed HTTP / SSE  ──────────────►  http://<BASE_URL>            │
└──────────────────────────────────────────────────────────────────────┘
                                              │
                                              │  (a) regular dio calls
                                              │      Cookie: ap_session=<uuid>
                                              │      Idempotency-Key: <uuid>
                                              │      Authorization: Bearer <byok>  (only on /runs, /start)
                                              │
                                              │  (b) flutter_client_sse
                                              │      Cookie: ap_session=<uuid>
                                              │      Last-Event-Id: <last seq>
                                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Phase-23 backend (api_server, FastAPI, port 8000 default)           │
│                                                                      │
│   POST /v1/runs              ▶ UPSERT-on-name → smoke → 200          │
│   POST /v1/agents/:id/start  ▶ spawn container, channel='inapp'      │
│   POST /v1/agents/:id/stop   ▶ stop container                        │
│   POST /v1/agents/:id/messages  ▶ 202 + message_id (Idem-Key REQ)    │
│   GET  /v1/agents/:id/messages  ▶ history (status IN done|failed)    │
│   GET  /v1/agents/:id/messages/stream  ▶ SSE id:<seq> event:<kind>   │
│   GET  /v1/agents               ▶ list user agents (status + last)   │
│   GET  /v1/recipes              ▶ recipes catalog                    │
│   GET  /v1/models               ▶ OpenRouter passthrough proxy       │
│   GET  /v1/users/me             ▶ cold-start auth check              │
│   POST /v1/auth/google/mobile   ▶ id_token → session  (Phase 25 use) │
│   POST /v1/auth/github/mobile   ▶ access_token → sess  (Phase 25 use)│
│   GET  /healthz                 ▶ {"ok": true}  (Phase 24 placeholder│
│                                    screen target)                    │
└──────────────────────────────────────────────────────────────────────┘
```

The Phase 24 placeholder screen drives data from `GET /healthz` (D-44 implicit; CONTEXT line 257 explicit) through the SAME real interceptor chain + theme + router that Phase 25's screens will use. The spike test exercises the same chain plus 8 more endpoints (D-46 steps 1-9).

### Recommended Project Structure

```
mobile/
├── .fvmrc                              # FVM SDK pin (D-05)
├── .gitignore                          # D-08 standard set
├── .env.example                        # BASE_URL, SESSION_ID, OPENROUTER_KEY documented
├── Makefile                            # D-22 targets
├── README.md                           # per-target BASE_URL docs (D-44, D-49)
├── analysis_options.yaml               # `include: package:very_good_analysis/analysis_options.yaml`
├── pubspec.yaml
├── pubspec.lock                        # D-08 — committed
├── lib/
│   ├── main.dart                       # entry; Uri.tryParse + StateError on bad BASE_URL (D-43)
│   ├── app.dart                        # MaterialApp.router + theme + router config
│   ├── core/
│   │   ├── env/
│   │   │   └── app_env.dart            # baseUrl getter; sessionIdFromEnv (spike-only)
│   │   ├── theme/
│   │   │   └── solvr_theme.dart        # ThemeData mirroring globals.css (APP-02)
│   │   ├── router/
│   │   │   └── app_router.dart         # go_router config; placeholder route only in P24
│   │   ├── api/
│   │   │   ├── api_client.dart         # typed methods (D-31)
│   │   │   ├── auth_interceptor.dart   # cookie inject + 401 (D-35)
│   │   │   ├── log_interceptor.dart    # dev-only, redacted (Claude's discretion)
│   │   │   ├── result.dart             # sealed Result<T> + ApiError + ErrorCode (D-32, D-38)
│   │   │   ├── api_endpoints.dart      # path constants
│   │   │   ├── messages_stream.dart    # flutter_client_sse wrapper w/ Last-Event-Id tracking
│   │   │   ├── dtos.dart               # manual fromJson/toJson DTOs (D-34)
│   │   │   └── providers.dart          # Riverpod codegen: @riverpod Dio dio(Ref ref) ...
│   │   ├── storage/
│   │   │   └── secure_storage.dart     # session_id read/write/clear (D-35)
│   │   └── auth/
│   │       └── auth_event_bus.dart     # Stream<AuthRequired> emitted on 401 (Phase 25 listens)
│   ├── shared/                         # reusable widgets / formatters (empty in P24)
│   └── features/
│       ├── _placeholder/
│       │   └── healthz_screen.dart     # the only Phase-24 screen
│       ├── dashboard/                  # placeholder dir (Phase 25)
│       ├── new_agent/                  # placeholder dir (Phase 25)
│       └── chat/                       # placeholder dir (Phase 25)
├── test/                               # unit tests (theme, Result, ApiError, env validation)
├── integration_test/
│   └── spike_api_roundtrip_test.dart   # D-45 — the gate
├── ios/
│   └── Runner/
│       └── Info.plist                  # ATS exemption + URL scheme + portrait orientation
├── android/
│   └── app/
│       ├── src/main/AndroidManifest.xml         # intent-filter + portrait orientation
│       └── src/debug/res/xml/network_security_config.xml  # cleartext debug-only
└── (spikes/ lives at repo root, not mobile/ — D-45)
```

### Pattern 1: Hand-Written Typed dio Client over Result<T>

**What:** A `lib/core/api/api_client.dart` exposing one Dart method per backend endpoint. Each method returns `Future<Result<T>>` where `T` is the success DTO.

**When to use:** Always for the typed surface (D-31). The spike + the placeholder screen + Phase 25's screens all consume this.

**Example:**
```dart
// Source: synthesized from CONTEXT D-31..D-43, dio docs (Context7 /cfug/dio),
//         Phase 23 contract docs (23-CONTEXT.md D-09..D-34)

class ApiClient {
  ApiClient(this._dio);
  final Dio _dio;

  Future<Result<HealthOk>> healthz({CancelToken? cancelToken}) async {
    try {
      final res = await _dio.get<Map<String, dynamic>>(
        '/healthz',
        cancelToken: cancelToken,
      );
      return Result.ok(HealthOk.fromJson(res.data!));
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }

  Future<Result<RunResponse>> runs({
    required RunRequest body,
    String? byokOpenRouterKey,
    CancelToken? cancelToken,
  }) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        '/v1/runs',
        data: body.toJson(),
        cancelToken: cancelToken,
        options: Options(
          headers: byokOpenRouterKey == null
              ? null
              : {'Authorization': 'Bearer $byokOpenRouterKey'},
        ),
      );
      return Result.ok(RunResponse.fromJson(res.data!));
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }

  Future<Result<MessagePostAck>> postMessage({
    required UuidValue agentId,
    required String content,
    required String idempotencyKey,
    CancelToken? cancelToken,
  }) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        '/v1/agents/$agentId/messages',
        data: {'content': content},
        options: Options(headers: {'Idempotency-Key': idempotencyKey}),
        cancelToken: cancelToken,
      );
      return Result.ok(MessagePostAck.fromJson(res.data!));
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }

  Future<Result<MessagesPage>> messagesHistory({
    required UuidValue agentId,
    int limit = 200,
    CancelToken? cancelToken,
  }) async {
    if (limit < 1 || limit > 1000) {
      return Result.err(ApiError.invalidArgument('limit', 'must be 1..1000'));
    }
    try {
      final res = await _dio.get<Map<String, dynamic>>(
        '/v1/agents/$agentId/messages',
        queryParameters: {'limit': limit},
        cancelToken: cancelToken,
      );
      return Result.ok(MessagesPage.fromJson(res.data!));
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }
  // ...stop, agentsList, recipes, models, usersMe, authGoogleMobile, authGithubMobile
}
```

### Pattern 2: dio Interceptor — Cookie Injection + 401 → Clear + Emit Auth Event

**What:** Single shared dio instance with one `Interceptor` subclass that:
- `onRequest`: read `session_id` from secure_storage (hot-cached), set `Cookie: ap_session=<id>` if present.
- `onError`: if `err.response?.statusCode == 401`, clear stored session + emit `AuthRequired` on a `core/auth/auth_event_bus.dart` stream. Phase 25 listens; Phase 24 only wires the stream + verifies it doesn't crash.

**When to use:** Wired in Phase 24 (D-35). Phase 25 attaches the listener. Spike (D-49) proves the inject-on-every-request path with a `--dart-define`-injected cookie.

**Example:**
```dart
// Source: synthesized from CONTEXT D-35, dio interceptor docs (Context7 /cfug/dio
//         "Implementing Dio Interceptors" + "QueuedInterceptor for Token Refresh")

class AuthInterceptor extends Interceptor {
  AuthInterceptor(this._storage, this._authEvents);
  final SecureStorage _storage;
  final StreamController<AuthRequired> _authEvents;

  @override
  void onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    final sessionId = await _storage.readSessionId();
    if (sessionId != null) {
      options.headers['Cookie'] = 'ap_session=$sessionId';
    }
    handler.next(options);
  }

  @override
  void onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    if (err.response?.statusCode == 401) {
      await _storage.clearSessionId();
      _authEvents.add(const AuthRequired());
    }
    handler.next(err);
  }
}
```

**Note on `QueuedInterceptor`:** dio's `QueuedInterceptor` exists for token-refresh patterns (Context7 dio docs). We do NOT use it (D-39 forbids retry/refresh logic). Plain `Interceptor` is correct.

### Pattern 3: Sealed `Result<T>` with Exhaustive Switch

**What:** Dart 3 sealed class. Subtypes MUST live in the same library (verified via Context7 /websites/pub_dev_dart3 + dart.dev/language/class-modifiers). Exhaustiveness is compile-time-checked — no `default:` needed.

**Example:**
```dart
// lib/core/api/result.dart
// Source: dart.dev/language/class-modifiers (verified)

sealed class Result<T> {
  const Result();
  const factory Result.ok(T value) = Ok<T>;
  const factory Result.err(ApiError error) = Err<T>;
}

final class Ok<T> extends Result<T> {
  const Ok(this.value);
  final T value;
}

final class Err<T> extends Result<T> {
  const Err(this.error);
  final ApiError error;
}

// Caller — exhaustive switch (no default branch):
final r = await api.healthz();
final widget = switch (r) {
  Ok(:final value) => Text('ok: ${value.ok}'),
  Err(:final error) => Text('error: ${error.message}'),
};
```

### Pattern 4: Typed `ApiError` Mirroring Backend Stripe Envelope

**What:** Mirror `api_server/src/api_server/models/errors.py::ErrorCode` enum. `DioException` → `ApiError` is a single static factory.

**Example:**
```dart
// lib/core/api/result.dart  (continued)

enum ErrorCode {
  invalidRequest,
  recipeNotFound,
  schemaNotFound,
  lintFail,
  payloadTooLarge,
  rateLimited,
  idempotencyBodyMismatch,
  unauthorized,
  internal,
  runnerTimeout,
  infraUnavailable,
  agentNotFound,
  agentNotRunning,
  agentAlreadyRunning,
  channelNotConfigured,
  channelInputsInvalid,
  concurrentPollLimit,
  eventStreamUnavailable,

  // Client-only (no backend-emitted equivalent)
  network,
  timeout,
  unknownServer,
}

class ApiError {
  ApiError({
    required this.code,
    required this.message,
    this.param,
    this.requestId,
    this.statusCode,
  });
  final ErrorCode code;
  final String message;
  final String? param;
  final String? requestId;
  final int? statusCode;

  static ApiError fromDioException(DioException e) {
    if (CancelToken.isCancel(e)) {
      return ApiError(code: ErrorCode.network, message: 'cancelled');
    }
    if (e.type == DioExceptionType.connectionTimeout
        || e.type == DioExceptionType.receiveTimeout
        || e.type == DioExceptionType.sendTimeout) {
      return ApiError(code: ErrorCode.timeout, message: e.message ?? 'timeout');
    }
    final response = e.response;
    if (response == null) {
      return ApiError(
        code: ErrorCode.network,
        message: e.message ?? 'network error',
      );
    }
    // Backend emits {"error": {"type", "code", "category", "message", "param", "request_id"}}
    final body = response.data;
    if (body is Map<String, dynamic> && body['error'] is Map<String, dynamic>) {
      final err = body['error'] as Map<String, dynamic>;
      return ApiError(
        code: _parseCode(err['code'] as String?),
        message: (err['message'] as String?) ?? 'unknown',
        param: err['param'] as String?,
        requestId: err['request_id'] as String?,
        statusCode: response.statusCode,
      );
    }
    return ApiError(
      code: ErrorCode.unknownServer,
      message: 'malformed error envelope',
      statusCode: response.statusCode,
    );
  }

  static ApiError invalidArgument(String param, String message) =>
      ApiError(code: ErrorCode.invalidRequest, message: message, param: param);

  static ErrorCode _parseCode(String? code) => switch (code) {
        'INVALID_REQUEST' => ErrorCode.invalidRequest,
        'RECIPE_NOT_FOUND' => ErrorCode.recipeNotFound,
        'SCHEMA_NOT_FOUND' => ErrorCode.schemaNotFound,
        'LINT_FAIL' => ErrorCode.lintFail,
        'PAYLOAD_TOO_LARGE' => ErrorCode.payloadTooLarge,
        'RATE_LIMITED' => ErrorCode.rateLimited,
        'IDEMPOTENCY_BODY_MISMATCH' => ErrorCode.idempotencyBodyMismatch,
        'UNAUTHORIZED' => ErrorCode.unauthorized,
        'INTERNAL' => ErrorCode.internal,
        'RUNNER_TIMEOUT' => ErrorCode.runnerTimeout,
        'INFRA_UNAVAILABLE' => ErrorCode.infraUnavailable,
        'AGENT_NOT_FOUND' => ErrorCode.agentNotFound,
        'AGENT_NOT_RUNNING' => ErrorCode.agentNotRunning,
        'AGENT_ALREADY_RUNNING' => ErrorCode.agentAlreadyRunning,
        'CHANNEL_NOT_CONFIGURED' => ErrorCode.channelNotConfigured,
        'CHANNEL_INPUTS_INVALID' => ErrorCode.channelInputsInvalid,
        'CONCURRENT_POLL_LIMIT' => ErrorCode.concurrentPollLimit,
        'EVENT_STREAM_UNAVAILABLE' => ErrorCode.eventStreamUnavailable,
        _ => ErrorCode.unknownServer,
      };
}
```

### Pattern 5: SSE Wrapper with Manual `Last-Event-Id` Tracking

**What:** A thin `MessagesStream` class that owns the `_lastSeq: String?` field and re-passes it on `connect(...)` calls. `flutter_client_sse` does NOT auto-track or auto-resume; the wrapper is the workaround.

**Example:**
```dart
// lib/core/api/messages_stream.dart
// Source: synthesized from flutter_client_sse 2.0.3 source
//         (github.com/pratikbaid3/flutter_client_sse) + Phase 23 D-13/D-25/D-26
//         + Phase 22c.3 D-09/D-34 (id:<seq> on every event).

class MessagesStream {
  MessagesStream({
    required Uri baseUrl,
    required this.agentId,
    required this.cookieProvider,
  }) : _baseUrl = baseUrl;
  final Uri _baseUrl;
  final UuidValue agentId;
  final Future<String?> Function() cookieProvider;
  String? _lastEventId;
  StreamSubscription<SSEModel>? _sub;
  final _events = StreamController<SseEvent>.broadcast();

  Stream<SseEvent> get events => _events.stream;
  String? get lastEventId => _lastEventId;

  Future<void> connect() async {
    final cookie = await cookieProvider();
    final headers = <String, String>{
      'Accept': 'text/event-stream',
      'Cache-Control': 'no-cache',
      if (cookie != null) 'Cookie': 'ap_session=$cookie',
      if (_lastEventId != null) 'Last-Event-Id': _lastEventId!,
    };
    final stream = SSEClient.subscribeToSSE(
      method: SSERequestType.GET,
      url: _baseUrl.resolve('/v1/agents/$agentId/messages/stream').toString(),
      header: headers,
    );
    _sub = stream.listen((SSEModel m) {
      // Backend emits id:<seq>, event:<kind>, data:<json>.
      if (m.id != null && m.id!.isNotEmpty) {
        _lastEventId = m.id;
      }
      _events.add(SseEvent(
        id: m.id,
        kind: m.event ?? 'unknown',
        data: m.data ?? '',
      ));
    }, onError: (Object e, StackTrace s) {
      _events.addError(e, s);
    });
  }

  /// Disconnect WITHOUT clearing `_lastEventId`. Caller invokes `connect()`
  /// again to resume from the same place.
  Future<void> disconnect() async {
    await _sub?.cancel();
    _sub = null;
  }

  /// Reset the cursor — used for "Load fresh" UX (out of Phase 24 scope).
  void resetCursor() {
    _lastEventId = null;
  }

  Future<void> dispose() async {
    await _sub?.cancel();
    await _events.close();
  }
}

class SseEvent {
  SseEvent({required this.id, required this.kind, required this.data});
  final String? id;
  final String kind;
  final String data;
}
```

### Pattern 6: Riverpod Codegen Provider Tree

**What:** `@riverpod` annotation on functions / classes generates the `*Provider` symbols + auto-dispose semantics. `riverpod_generator` runs via `build_runner`.

**Example:**
```dart
// lib/core/api/providers.dart
// Source: riverpod.dev/docs/concepts2/providers + Context7 /rrousselgit/riverpod
//         "Define a Basic Riverpod Generator Provider"

import 'package:riverpod_annotation/riverpod_annotation.dart';
part 'providers.g.dart';

@Riverpod(keepAlive: true)
Dio dio(Ref ref) {
  final baseUrl = ref.watch(appEnvProvider).baseUrl;
  final storage = ref.watch(secureStorageProvider);
  final authEvents = ref.watch(authEventBusProvider);

  final dio = Dio(BaseOptions(
    baseUrl: baseUrl.toString(),
    connectTimeout: const Duration(seconds: 10),  // D-37
    receiveTimeout: const Duration(seconds: 30),  // D-37
  ));
  dio.interceptors.addAll([
    AuthInterceptor(storage, authEvents),
    if (kDebugMode) RedactingLogInterceptor(),
  ]);
  ref.onDispose(dio.close);
  return dio;
}

@riverpod
ApiClient apiClient(Ref ref) => ApiClient(ref.watch(dioProvider));
```

The generated `dioProvider` and `apiClientProvider` are referenced as
`ref.watch(dioProvider)` etc. throughout the app. `ref.onDispose(...)` ties
the dio close call to provider disposal — when no consumer remains, the
HTTP client is shut down (D-41 cancel-on-dispose).

### Pattern 7: Spike Harness Skeleton

**What:** Single `testWidgets` block in `mobile/integration_test/spike_api_roundtrip_test.dart`. Uses `IntegrationTestWidgetsFlutterBinding`. Reads `BASE_URL`, `SESSION_ID`, `OPENROUTER_KEY` from `String.fromEnvironment(...)`. Drives the 9 steps directly through the same `ApiClient` + `MessagesStream` the production code uses.

**Example skeleton (planner fills in assertions):**
```dart
// integration_test/spike_api_roundtrip_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
// ...

const _baseUrl = String.fromEnvironment('BASE_URL', defaultValue: '');
const _sessionId = String.fromEnvironment('SESSION_ID', defaultValue: '');
const _byokKey = String.fromEnvironment('OPENROUTER_KEY', defaultValue: '');

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('9-step roundtrip — D-46', (tester) async {
    expect(_baseUrl, isNotEmpty, reason: '--dart-define BASE_URL=...');
    expect(_sessionId, isNotEmpty, reason: '--dart-define SESSION_ID=...');
    expect(_byokKey, isNotEmpty, reason: '--dart-define OPENROUTER_KEY=...');

    // Build Dio with cookie pre-injected (no secure_storage path on spike — D-49).
    final dio = Dio(BaseOptions(baseUrl: _baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 30),
    ));
    dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        options.headers['Cookie'] = 'ap_session=$_sessionId';
        handler.next(options);
      },
    ));
    final api = ApiClient(dio);

    // Step 1: POST /v1/runs
    final agentName =
      'spike-roundtrip-${DateTime.now().millisecondsSinceEpoch}-${_shortUuid()}';
    final runResult = await api.runs(
      body: RunRequest(name: agentName, recipeName: 'nullclaw',
                       model: 'anthropic/claude-haiku-4-5'),
      byokOpenRouterKey: _byokKey,
    );
    final agentId = _expectOk(runResult, step: 1).agentInstanceId;

    // Step 2: POST /v1/agents/:id/start
    final startRes = await api.start(agentId: agentId,
                       channel: 'inapp', channelInputs: const {});
    _expectOk(startRes, step: 2);

    // Step 3: connect SSE
    final stream = MessagesStream(baseUrl: Uri.parse(_baseUrl),
                                  agentId: agentId,
                                  cookieProvider: () async => _sessionId);
    final received = <SseEvent>[];
    stream.events.listen(received.add);
    await stream.connect();

    // Step 4: POST /v1/agents/:id/messages
    final idemKey = const Uuid().v4();
    final ack = await api.postMessage(agentId: agentId,
                         content: 'spike roundtrip',
                         idempotencyKey: idemKey);
    final messageId = _expectOk(ack, step: 4).messageId;

    // Step 5: wait for assistant reply via SSE
    final reply = await _waitForOutbound(received, timeout: const Duration(minutes: 10));
    expect(reply.data, isNotEmpty);

    // Step 6: GET /messages parity
    final hist = await api.messagesHistory(agentId: agentId, limit: 10);
    final histPayload = _expectOk(hist, step: 6);
    final assistantInHist = histPayload.messages.lastWhere((m) => m.role == 'assistant');
    expect(assistantInHist.content, _extractAssistantContent(reply.data));

    // Step 7: replay POST /messages with SAME idem key → same message_id
    final replay = await api.postMessage(agentId: agentId,
                         content: 'spike roundtrip',
                         idempotencyKey: idemKey);
    final replayAck = _expectOk(replay, step: 7);
    expect(replayAck.messageId, messageId);

    // Step 8: disconnect mid-stream + reconnect with Last-Event-Id
    final lastSeenId = stream.lastEventId;
    expect(lastSeenId, isNotNull);
    await stream.disconnect();
    final received2 = <SseEvent>[];
    stream.events.listen(received2.add);
    await stream.connect();
    // Send another message to provoke an event after the cursor.
    final idemKey2 = const Uuid().v4();
    await api.postMessage(agentId: agentId,
        content: 'after-resume', idempotencyKey: idemKey2);
    final reply2 = await _waitForOutbound(received2,
        timeout: const Duration(minutes: 10));
    // Assert no duplicate of `reply` in `received2` (Last-Event-Id worked).
    expect(received2.any((e) => e.id == lastSeenId), isFalse);

    // Step 9: POST /stop
    final stop = await api.stop(agentId: agentId);
    _expectOk(stop, step: 9);

    await stream.dispose();
  });
}
```

The wrapper functions (`_expectOk`, `_waitForOutbound`, `_shortUuid`,
`_extractAssistantContent`) live in the test file or a helper. Failure
captures (D-52) hook in via `addTearDown` — print step + status + body
+ redacted headers on any `expect` failure.

### Anti-Patterns to Avoid

- **Splitting `Ok` and `Err` into separate files.** Dart 3 sealed classes require subtypes in the same library. Putting them in different unrelated `.dart` files (without `part of`) BREAKS the compile-time exhaustiveness check.
- **Using `dio_cookie_manager` for our session cookie.** We control exactly one cookie (`ap_session`) — adding a CookieJar is overkill. Plain interceptor + `flutter_secure_storage` per D-35.
- **Passing `Last-Event-Id` only on the first connect.** It's the CALLER's job to track and re-pass on every reconnect. `flutter_client_sse` does NOT remember.
- **Hardcoding any catalog (recipes, models, agent types) in Dart.** Golden Rule #2. Always fetch from `/v1/recipes` + `/v1/models`. The CLIENT SURFACES THE METHOD; the SCREEN consumes it (Phase 25).
- **Wiring `package:auto_route` or `Navigator 1.0`.** APP-01 mandates `go_router`.
- **Making the spike a unit test** (`mobile/test/`). Unit tests run in a sandbox without a real network stack. Integration_test runs ON the simulator/emulator with full networking — see `## Common Pitfalls #3`.
- **Wrapping `_dio.get(...)` in a try/catch on generic `Exception`.** dio throws `DioException` only; broader catches hide real bugs.
- **Sending `Authorization: Bearer <byok>` on every request.** Only `/runs` and `/start` (D-40); session is via Cookie. Sending Authorization on `/messages` would be a silent no-op today but is misleading.
- **Calling `secureStorage.read(...)` on every dio request without caching.** `flutter_secure_storage` reads cross the platform channel; cache the value in memory and only re-read on logout/login.
- **Using `sealed class Result<T>` without `final` modifiers on `Ok`/`Err`.** Without `final` (or `base`/`interface`), the analyzer accepts third-party extensions and the exhaustiveness guarantee weakens.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP client + interceptor lifecycle | Custom `HttpClient` wrapper | `dio` 5.9 | dio's `Interceptor` + `CancelToken` + per-request `Options(headers:)` are exactly what CONTEXT D-35/D-37/D-40/D-41 need. Rolling your own loses HTTP/2, multipart, follow-redirects, and per-call timeouts. |
| SSE parsing (id/event/data fields, comment lines, heartbeat) | Custom `Stream<List<int>>` decoder over `package:http` chunked transfer | `flutter_client_sse` 2.0.3 | The SSE spec has corner cases (multi-line `data:`, `id:` reset on empty value, retry hint via `retry:`, comment-line `:` filtering). The package handles them. Wrap, don't replace. |
| OAuth 2.0 PKCE for GitHub | Custom WebView + redirect URI capture | `flutter_appauth` 12.0 | Google explicitly forbids embedded WebView OAuth (CONTEXT D-15 / Phase 23 D-15). AppAuth uses the system browser per RFC 8252. |
| Native Google sign-in | OAuth flow against Google's REST API directly | `google_sign_in` 7.2 | Apple/Google sign-in SDKs are required for App Store / Play Store policy compliance and produce the JWT id_token the backend's `/v1/auth/google/mobile` expects. |
| Secure session_id storage | Storing in `SharedPreferences` (plaintext on Android) | `flutter_secure_storage` 10.0 | `SharedPreferences` values are world-readable to root + adb on a debug build. Keychain / EncryptedSharedPreferences are the platform-correct slots. (Pitfall #4 covers iOS-Simulator volatility.) |
| UUID generation | `DateTime.now().millisecondsSinceEpoch.toString()` | `uuid` 4.5 + `Uuid().v4()` | RFC 4122 v4 has 122 random bits — a millis-based ID collides under retry-happy users with multi-tap. |
| Theme color tokens | Reverse-engineering OKLCH from reference images | Direct port of `solvr/frontend/app/globals.css` `:root` block | The values are literally locked in code (CONTEXT line 195). Phase 24 reads, converts to sRGB once, hard-codes in `solvr_theme.dart`. |
| Inter / JetBrains Mono font delivery | Manual asset bundling + `Font.fromAsset` boilerplate | `google_fonts` 8.1 | Built-in caching + production-ready bundle path; switching to bundled assets is one-line later. |
| Strict Dart lints | Hand-written `analysis_options.yaml` rule list | `very_good_analysis` 10.0 | api_server-equivalent strict-from-day-1; D-23 LOCKED. |
| Flutter SDK pinning | Manual checkouts of Flutter at specific git SHA | `fvm` `.fvmrc` | Per-project pinning + symlink + per-machine cache. D-05 LOCKED. |
| Idempotency-Key state on retries | Re-generating UUID per dio call | One UUID per **user Send press**, persisted on the in-flight message until ack | Backend's IdempotencyMiddleware caches the response per (key, body); reusing the key is the whole point. |

**Key insight:** Phase 24 is plumbing. The temptation is to build "minimal" replacements (e.g., a 30-line "fake SSE parser" or a stub-storage). Rule #1 + Golden Rule #5 combine to forbid that: the spike runs the SAME code paths Phase 25's screens will use, against REAL infra. If a package is good enough for production, it's the only acceptable choice for the spike.

## Runtime State Inventory

> **Skipped: greenfield phase.** Phase 24 is a cold-start of `mobile/`. There are no pre-existing renames, refactors, or migrations.
>
> Verified: `mobile/` does not exist in the repo (`ls /Users/fcavalcanti/dev/agent-playground/mobile/` returns no such file). No prior Flutter code, no prior asset bundles, no prior bundle-id registrations to migrate.

## Common Pitfalls

### Pitfall 1: Riverpod codegen vs CONTEXT D-34's "no build_runner for JSON" — DIFFERENT runners

**What goes wrong:** Planner sees D-34 ("no `build_runner` for JSON, no `*.g.dart` for DTOs") and reasonably extrapolates "no build_runner at all," then forces hand-written `Provider` declarations everywhere — losing auto-dispose and family-typing ergonomics.

**Why it happens:** Both `riverpod_generator` and `json_serializable` use `build_runner` as the runner, so they look like "the same thing."

**How to avoid:** D-34 explicitly says **"no `build_runner` for JSON"** — scoped to JSON serialization. `riverpod_generator` is an INDEPENDENT runner and the 2026 community-default authoring style. Use it. The `*.g.dart` files it produces are providers, not DTOs.

**Warning signs:** Planner writes 50+ lines of hand-rolled `Provider` and `StateNotifierProvider` boilerplate before the first feature ships. → Switch to `@riverpod` annotation.

### Pitfall 2: `flutter_client_sse` does NOT auto-track `Last-Event-Id` (LOAD-BEARING)

**What goes wrong:** Planner assumes "`flutter_client_sse` is the W3C-compliant client, it auto-resumes" — Spike step 8 (D-46) FAILS because the package re-connects from the start of the stream.

**Why it happens:** The W3C EventSource spec MANDATES that browser implementations track and re-send `Last-Event-Id` automatically. `flutter_client_sse` 2.0.3 does NOT — it has no `lastEventId` parameter, no `autoReconnect`, no `ReconnectConfig`. Verified against the source at `github.com/pratikbaid3/flutter_client_sse/blob/master/lib/flutter_client_sse.dart` and the public API docs at `pub.dev/documentation/flutter_client_sse/latest/flutter_client_sse/SSEClient/subscribeToSSE.html` — the function signature is:

```dart
static Stream<SSEModel> subscribeToSSE({
  required SSERequestType method,
  required String url,
  required Map<String, String> header,
  StreamController<SSEModel>? oldStreamController,
  Map<String, dynamic>? body,
})
```

No `lastEventId`. No `autoReconnect`.

**How to avoid:**
1. Build a `MessagesStream` wrapper class (Pattern 5 above) that owns `_lastEventId` state.
2. On every received `SSEModel`, persist `m.id` to `_lastEventId` (the package DOES parse `id:<seq>` from server lines into `SSEModel.id` — verified via source).
3. On `connect()`, inject `'Last-Event-Id': _lastEventId!` into the `header:` map if non-null.
4. Disconnect = cancel the listener subscription, NOT clear `_lastEventId`. Reconnect = call `connect()` again.

**Warning signs:**
- Spike step 8 receives the same first event after the manual reconnect that it received before the disconnect (= cursor not honored on the wire).
- Planner says "the package handles it." → Audit the package source. It doesn't.

**Sibling consideration:** `eventflux` 2.2.1 has auto-reconnect via `ReconnectConfig.reconnectHeader()` callback (which DOES let you supply `Last-Event-Id` per reconnect attempt) — but D-33 LOCKED `flutter_client_sse`. Honor the lock; build the wrapper.

### Pitfall 3: integration_test invocation differs from `flutter test` for unit tests

**What goes wrong:** Planner writes `flutter test integration_test/spike_api_roundtrip_test.dart` in `make spike` — but the Flutter docs sometimes show `flutter drive --target=...`. Confusion → broken make target.

**Why it happens:** `flutter drive` was the pre-2.0 command and lingers in old Stack Overflow answers.

**How to avoid:** As of Flutter 3.41 (CITED: docs.flutter.dev/testing/integration-tests), the canonical command IS `flutter test integration_test/<file>.dart` for native (iOS Sim, Android Emu, physical devices). `flutter drive` is now web-only.

```bash
# CORRECT — Phase 24 spike (D-50)
fvm flutter test integration_test/spike_api_roundtrip_test.dart \
  --dart-define=BASE_URL=$BASE_URL \
  --dart-define=SESSION_ID=$SESSION_ID \
  --dart-define=OPENROUTER_KEY=$OPENROUTER_KEY

# Add `-d <device-id>` if multiple devices are attached. Discover via `flutter devices`.
```

**Warning signs:** Planner writes `flutter drive` anywhere. → Replace with `flutter test integration_test/`.

### Pitfall 4: `flutter_secure_storage` on iOS Simulator can lose values cross-restart

**What goes wrong:** App stores `session_id`. User force-quits + relaunches the simulator (or hot-restarts). On read, `flutter_secure_storage` returns null. The app routes to OAuth login when it should resume.

**Why it happens:** iOS Simulator's keychain is volatile — values written without proper Keychain Sharing entitlement may not survive `Erase Content and Settings` AND in some Simulator builds may not survive across cold restarts. The flutter_secure_storage GitHub README explicitly notes: "If your app returns null when reading keys after a hot restart on a physical iOS device, this is typically caused by missing or incorrectly configured Keychain Sharing entitlements." A weaker version of this affects the Simulator (CITED: pub.dev + GitHub issues). [VERIFIED via WebSearch + flutter_secure_storage README.]

**How to avoid in Phase 24 specifically:** The spike (D-49) sidesteps this by injecting `SESSION_ID` via `--dart-define`, NOT through secure_storage. So the spike is unblocked.

**How to avoid in Phase 25 (flagged for downstream):** Phase 25 should test the OAuth-mint → secure_storage write → cold restart → read-back path on a **physical iOS device or Android Emulator**, NOT iOS Simulator. iOS Simulator may produce false negatives. Document this as a Phase-25 concern in the placeholder code or a `// TODO(phase-25): ...` comment near the secure_storage call.

**Warning signs (Phase 25):** Auth Required event fires after a clean cold start on iOS Simulator but NOT on a physical device. → Switch test target to physical device.

### Pitfall 5: Android Emulator host-alias `10.0.2.2` may not work on Pixel system images

**What goes wrong:** Spike runs on a fresh Android emulator created from "Pixel 7 Play Store" system image. Calls to `10.0.2.2:8000` time out — the host is unreachable.

**Why it happens:** Newer Google-Play-Store-enabled emulator images use a different virtual network configuration; the host alias may be `10.0.3.2` instead. (CITED via WebSearch — multiple flutter/flutter and dotnet/maui issue threads as of 2024-2026.)

**How to avoid:** Document in `mobile/README.md`:

> **Android Emulator network host alias.** The default is `10.0.2.2` for AOSP system images. **If `--dart-define BASE_URL=http://10.0.2.2:8000` times out**, your emulator is using a Pixel/Play-Store image that aliases the host as `10.0.3.2` instead. Recreate the AVD from a non-Play-Store image, or override `BASE_URL=http://10.0.3.2:8000`.

**Warning signs:** "Connection refused" or 30s timeout on every call from the Android emulator. → Try `10.0.3.2`.

### Pitfall 6: `google_fonts` runtime fetch on first launch — network dependency at boot

**What goes wrong:** Phase 24's spike runs on a freshly-installed app (no font cache). On first launch, `google_fonts` fetches Inter + JetBrains Mono from Google's CDN. If the device is offline (or has spotty wifi), the font load times out → the placeholder screen renders with the default system font, not the Solvr Labs theme.

**Why it happens:** `google_fonts` defaults to runtime HTTP fetch with disk caching. (CITED: pub.dev/packages/google_fonts.) The cache survives across launches — but the FIRST launch always hits the network unless assets are bundled.

**How to avoid:**
- **Recommended for Phase 24:** Bundle `Inter-Regular.ttf` + `JetBrainsMono-Regular.ttf` (and any used weights) under `mobile/assets/fonts/` and declare them in `pubspec.yaml`. `google_fonts` automatically prefers bundled assets over HTTP when present.
- Alternative: accept the runtime fetch + add a one-time `await GoogleFonts.pendingFonts(...)` warm-up at boot.
- Final alternative: drop `google_fonts` and use raw `Font` declarations against the bundled assets. (More boilerplate but simpler.)

**Recommendation:** Bundle the fonts. The spike runs offline-able and Phase 25's screens get deterministic typography from frame 0.

**Warning signs:** Spike intermittently fails because `expect(textStyle.fontFamily, 'Inter')` returns `null` or 'Roboto'. → Bundle the fonts.

### Pitfall 7: Dart 3 sealed-class subtypes MUST live in the same library

**What goes wrong:** Planner splits `Result<T>` into `result.dart` + `ok.dart` + `err.dart` for "tidiness." Compile fails with "subtype is not declared in the same library as the sealed class."

**Why it happens:** Dart's `sealed` modifier requires same-library declaration to give the compiler the exhaustive list. (CITED: dart.dev/language/class-modifiers.)

**How to avoid:** Keep `Result<T>`, `Ok<T>`, `Err<T>`, and `ApiError` + `ErrorCode` ALL in `lib/core/api/result.dart`. Use a `part 'result_apierror.dart'` / `part of 'result.dart'` split if size demands it — `part`/`part of` declarations count as the same library.

**Warning signs:** "The class 'Ok' must be declared in the same library as 'Result'."

### Pitfall 8: BYOK `Authorization: Bearer` overrides Cookie when both are set globally

**What goes wrong:** Planner sets `dio.options.headers['Authorization'] = 'Bearer ...'` once at boot. Every request now sends BYOK — including `/messages` (which doesn't need BYOK and should be cookie-only).

**Why it happens:** dio's global `options.headers` is merged into every request. Setting it globally instead of per-call breaks D-40's intent.

**How to avoid:** D-40 says BYOK is **per-request**, only on `runs(...)` and `start(...)`:

```dart
// CORRECT (per-request via Options.headers merge)
options: Options(
  headers: byokOpenRouterKey == null
      ? null
      : {'Authorization': 'Bearer $byokOpenRouterKey'},
),

// WRONG — global side effect
dio.options.headers['Authorization'] = 'Bearer $key';
```

The cookie interceptor sets the `Cookie:` header per-request via `onRequest` — that's fine because it's compatible. BYOK uses an entirely different header.

**Warning signs:** Backend logs show `Authorization: Bearer ...` on `/v1/agents/:id/messages` (which doesn't read it). → Move BYOK to per-call Options.

### Pitfall 9: very_good_analysis flags `print()` — use `dart:developer log()` per D-25

**What goes wrong:** Planner adds `print('debug: ...')` somewhere, CI fails on `avoid_print` lint.

**Why it happens:** very_good_analysis enables `avoid_print`. D-25 already mandates `dart:developer log()` instead.

**How to avoid:** `import 'dart:developer' as developer;` then `developer.log('msg', name: 'api_server')`. The IDE inspector renders these as a structured log feed. Keep `print` out of the codebase.

### Pitfall 10: Spike fails on a stale agent from a prior run

**What goes wrong:** Two consecutive spike runs use the same agent name (D-46 step 1) — the second `POST /v1/runs` with same `(user_id, name)` returns the existing agent_instance row instead of creating fresh state. SSE replays old events; assertions go red on confused content.

**Why it happens:** `POST /v1/runs` is UPSERT-on-name (D-22).

**How to avoid:** D-56 already mandates a unique-per-run name: `spike-roundtrip-<unix-ts>-<short-uuid>`. The planner MUST use this exact pattern in the spike code. NEVER hardcode a fixed name.

**Warning signs:** Step 1 returns 200 with an `agent_instance_id` that already had old `inapp_messages` rows. → Add timestamp/uuid to the name.

## Code Examples

Verified patterns from official sources:

### Dio Interceptor onRequest + onError (cookie + 401)
```dart
// Source: Context7 /cfug/dio "Implementing Dio Interceptors"
//         + https://github.com/cfug/dio/blob/main/dio/README.md

dio.interceptors.add(
  InterceptorsWrapper(
    onRequest: (RequestOptions options, RequestInterceptorHandler handler) {
      // CONTEXT D-35 cookie injection
      options.headers['Cookie'] = 'ap_session=<id-from-storage>';
      return handler.next(options);
    },
    onError: (DioException error, ErrorInterceptorHandler handler) {
      if (error.response?.statusCode == 401) {
        // CONTEXT D-35: clear session, emit event for router
        // (Phase 25 listens; Phase 24 just verifies it doesn't crash)
      }
      return handler.next(error);
    },
  ),
);
```

### Dio Per-Request Options Merge (BYOK header)
```dart
// Source: Context7 /cfug/dio "Execute Generic and Low-Level Requests with Dio"

await dio.post<Map<String, dynamic>>(
  '/v1/runs',
  data: body.toJson(),
  options: Options(
    headers: {'Authorization': 'Bearer $byokKey'},  // CONTEXT D-40
    sendTimeout: const Duration(seconds: 10),
    receiveTimeout: const Duration(seconds: 30),
  ),
  cancelToken: cancelToken,  // CONTEXT D-41
);
```

### Riverpod Codegen Provider with `ref.onDispose`
```dart
// Source: github.com/rrousselgit/riverpod README "Define a Basic Riverpod Generator Provider"
//         + Context7 /rrousselgit/riverpod "Notifier with code generation"

@Riverpod(keepAlive: true)
Dio dio(Ref ref) {
  final dio = Dio(BaseOptions(baseUrl: ref.watch(appEnvProvider).baseUrl.toString()));
  ref.onDispose(dio.close);
  return dio;
}
```

### Dart 3 Sealed Class Exhaustive Switch
```dart
// Source: dart.dev/language/class-modifiers (verified)

sealed class Result<T> { const Result(); }
final class Ok<T> extends Result<T> { const Ok(this.value); final T value; }
final class Err<T> extends Result<T> { const Err(this.error); final ApiError error; }

// Compiler verifies exhaustiveness — no default needed:
final widget = switch (await api.healthz()) {
  Ok(:final value) => Text('${value.ok}'),
  Err(:final error) => Text(error.message),
};
```

### iOS Info.plist NSAppTransportSecurity (localhost dev)
```xml
<!-- Source: developer.apple.com/documentation/bundleresources/.../nsapptransportsecurity
     CONTEXT D-12 -->

<key>NSAppTransportSecurity</key>
<dict>
    <key>NSAllowsLocalNetworking</key>
    <true/>
    <key>NSExceptionDomains</key>
    <dict>
        <key>localhost</key>
        <dict>
            <key>NSIncludesSubdomains</key>
            <false/>
            <key>NSExceptionAllowsInsecureHTTPLoads</key>
            <true/>
        </dict>
    </dict>
</dict>
```

### Android `network_security_config.xml` (debug-scoped cleartext)
```xml
<!-- Source: developer.android.com/privacy-and-security/security-config
     CONTEXT D-13. File path: mobile/android/app/src/debug/res/xml/network_security_config.xml -->

<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="false">
        <trust-anchors>
            <certificates src="system" />
        </trust-anchors>
    </base-config>
    <domain-config cleartextTrafficPermitted="true">
        <domain includeSubdomains="false">localhost</domain>
        <domain includeSubdomains="false">127.0.0.1</domain>
        <domain includeSubdomains="false">10.0.2.2</domain>
        <domain includeSubdomains="false">10.0.3.2</domain>
    </domain-config>
</network-security-config>
```

Reference from `mobile/android/app/src/debug/AndroidManifest.xml` (debug-only override):
```xml
<application
    android:networkSecurityConfig="@xml/network_security_config"
    ... />
```

### Android intent-filter for `solvrlabs://oauth/github` (flutter_appauth)
```xml
<!-- Source: pub.dev/packages/flutter_appauth README
     CONTEXT D-04. File path: mobile/android/app/src/main/AndroidManifest.xml -->

<activity
    android:name="net.openid.appauth.RedirectUriReceiverActivity"
    android:theme="@style/Theme.AppCompat.Translucent.NoTitleBar"
    android:exported="true"
    tools:node="replace">
    <intent-filter>
        <action android:name="android.intent.action.VIEW"/>
        <category android:name="android.intent.category.DEFAULT"/>
        <category android:name="android.intent.category.BROWSABLE"/>
        <data android:scheme="solvrlabs"
              android:host="oauth/github"/>
    </intent-filter>
</activity>
```

### iOS CFBundleURLTypes for `solvrlabs://`
```xml
<!-- Source: pub.dev/packages/flutter_appauth README
     CONTEXT D-04. File path: mobile/ios/Runner/Info.plist -->

<key>CFBundleURLTypes</key>
<array>
    <dict>
        <key>CFBundleTypeRole</key>
        <string>Editor</string>
        <key>CFBundleURLSchemes</key>
        <array>
            <string>solvrlabs</string>
        </array>
    </dict>
</array>
```

### `--dart-define` Env Validation at Boot (D-43)
```dart
// lib/core/env/app_env.dart
// Source: synthesized from CONTEXT D-43, dart.dev `String.fromEnvironment` docs

class AppEnv {
  AppEnv({required this.baseUrl});
  final Uri baseUrl;

  static AppEnv fromEnvironment() {
    const raw = String.fromEnvironment('BASE_URL', defaultValue: 'http://localhost:8000');
    if (raw.isEmpty) {
      throw StateError(
        'BASE_URL is empty. Pass --dart-define=BASE_URL=http://... at flutter run.'
      );
    }
    final uri = Uri.tryParse(raw);
    if (uri == null || !uri.hasScheme || (!uri.isScheme('http') && !uri.isScheme('https'))) {
      throw StateError(
        'BASE_URL is malformed: "$raw". Must be http(s)://host[:port].'
      );
    }
    return AppEnv(baseUrl: uri);
  }
}
```

### Solvr Labs Theme — OKLCH Token Conversion Table

The `:root` block of `solvr/frontend/app/globals.css` lines 6-39 ships OKLCH values; Flutter's `ThemeData` takes sRGB hex/RGBA. The mechanical conversion (planner cross-checks) for the Phase 24 load-bearing tokens:

| CSS token | OKLCH input | sRGB hex (calculated) | Flutter `Color` literal |
|-----------|-------------|----------------------|-------------------------|
| `--background` | `oklch(0.98 0.002 90)` | `#FAFAF7` (CONTEXT line 139 explicit) | `Color(0xFFFAFAF7)` |
| `--foreground` | `oklch(0.12 0 0)` | `#1F1F1F` (CONTEXT line 139 explicit) | `Color(0xFF1F1F1F)` |
| `--primary` | `oklch(0.12 0 0)` | `#1F1F1F` (same as `--foreground`) | `Color(0xFF1F1F1F)` |
| `--primary-foreground` | `oklch(0.98 0.002 90)` | `#FAFAF7` | `Color(0xFFFAFAF7)` |
| `--muted` / `--secondary` / `--accent` | `oklch(0.94 0.002 90)` | `#EFEFEC` (calculated) | `Color(0xFFEFEFEC)` |
| `--muted-foreground` | `oklch(0.45 0 0)` | `#6B6B6B` (calculated) | `Color(0xFF6B6B6B)` |
| `--border` / `--input` | `oklch(0.88 0.002 90)` | `#DEDEDA` (calculated) | `Color(0xFFDEDEDA)` |
| `--destructive` | `oklch(0.577 0.245 27.325)` | (calculated, ~`#D9333A`) | `Color(0xFFD9333A)` |
| `--radius` | `0rem` | — | `BorderRadius.zero` everywhere |

**Note:** CONTEXT line 139 hard-codes `#1F1F1F` and `#FAFAF7` — those values are AUTHORITATIVE. The other rows above are best-effort conversions; if a single source-of-truth Solvr Labs design token export becomes available, the planner replaces this table.

### Theme Skeleton

```dart
// lib/core/theme/solvr_theme.dart
// Source: synthesized from APP-02 + globals.css :root block + ThemeData docs

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class SolvrColors {
  static const background = Color(0xFFFAFAF7);
  static const foreground = Color(0xFF1F1F1F);
  static const muted = Color(0xFFEFEFEC);
  static const mutedForeground = Color(0xFF6B6B6B);
  static const border = Color(0xFFDEDEDA);
  static const destructive = Color(0xFFD9333A);
}

ThemeData solvrTheme() {
  final base = ThemeData.light(useMaterial3: true);
  return base.copyWith(
    scaffoldBackgroundColor: SolvrColors.background,
    colorScheme: const ColorScheme.light(
      surface: SolvrColors.background,
      onSurface: SolvrColors.foreground,
      primary: SolvrColors.foreground,
      onPrimary: SolvrColors.background,
      secondary: SolvrColors.muted,
      onSecondary: SolvrColors.foreground,
      error: SolvrColors.destructive,
      onError: SolvrColors.background,
      outline: SolvrColors.border,
    ),
    textTheme: GoogleFonts.interTextTheme(base.textTheme).apply(
      bodyColor: SolvrColors.foreground,
      displayColor: SolvrColors.foreground,
    ),
    // Mono only used in chrome (logo, status), not body text.
    // Pull JetBrainsMono via GoogleFonts.jetBrainsMonoTextTheme(...) when needed.
    cardTheme: const CardTheme(
      color: SolvrColors.background,
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.zero),
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: SolvrColors.background,
      foregroundColor: SolvrColors.foreground,
      elevation: 0,
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        shape: const RoundedRectangleBorder(borderRadius: BorderRadius.zero),
        backgroundColor: SolvrColors.foreground,
        foregroundColor: SolvrColors.background,
      ),
    ),
    inputDecorationTheme: const InputDecorationTheme(
      border: OutlineInputBorder(
        borderRadius: BorderRadius.zero,
        borderSide: BorderSide(color: SolvrColors.border),
      ),
    ),
  );
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Riverpod 2.x with hand-written `Provider`/`StateProvider` | Riverpod 3.x with `@riverpod` annotation + `riverpod_generator` | Riverpod 3.0 GA (~late 2024); `flutter_riverpod 3.3.1` is current | Less boilerplate; same runtime; codegen pairs with build_runner. Hand-written remains valid (D-23-friendly). |
| `flutter drive --target=integration_test/foo_test.dart` | `flutter test integration_test/foo_test.dart` | Flutter 2.0 (long ago); confirmed in Flutter 3.41 docs | `flutter drive` is now web-only. Use `flutter test` for native. |
| `xterm` package + manual ESC sequences | `@xterm/xterm` (web) — irrelevant to Phase 24 | — | No mobile equivalent; mobile chat UI uses native widgets. |
| `cookie_jar` + `dio_cookie_manager` for any HTTP cookie | Single dio Interceptor + flutter_secure_storage when there's exactly ONE cookie | Always for our shape | We control `ap_session` directly; no need for the jar. |
| Material 2 `ThemeData` defaults | Material 3 (`useMaterial3: true`) | Flutter 3.16+ | Phase 24 explicitly opts into Material 3; Phase 23 D-22 (carry-forward) implicitly assumed it. |
| Dart 2 union type via `freezed` `@freezed` `union case` | Dart 3 `sealed class` + pattern matching | Dart 3.0 (May 2023) | Native, no runner, compile-time exhaustiveness. D-32 LOCKED. |
| `flutter_lints` | `very_good_analysis` 10.0 (2026) | api_server policy mirror | D-23. |
| Manual `build_runner` daemon | `dart run build_runner watch -d` (built-in) | Flutter 3.x | One-line. Add to `make get` so codegen runs after `pub get` if needed. |

**Deprecated/outdated:**
- **`gotty`** (terminal — not relevant to Phase 24) — irrelevant; no shell.
- **WebView OAuth flows** — Google blocks new apps from using embedded WebView for sign-in. Use `google_sign_in` (native) or `flutter_appauth` (system browser). CONTEXT D-15 honors this.
- **`xterm.js` direct attach** — not a mobile concern.
- **Pre-Riverpod-2.0 `Provider` package** — old; superseded.
- **Hand-rolled OAuth 2.0 PKCE in Flutter** — `flutter_appauth` covers it; rolling our own is a backwards step.

## Assumptions Log

> All claims tagged `[ASSUMED]` in this research. The planner and discuss-phase use this section to identify decisions that need user confirmation before execution.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Riverpod 3.x is the 2026 community-default authoring style for new Flutter apps. | Standard Stack + Pitfall #1 | LOW — even if hand-written providers are equally valid, neither breaks the planner; the planner can pick either path. The risk is wasted refactor cost if codegen is later removed. CONTEXT D-26 says "likely codegen — community standard," confirming user intent. |
| A2 | `riverpod_annotation` major version 4.0.x is compatible with `flutter_riverpod` 3.3.x. | Standard Stack | LOW — pub.dev caps both at "current"; `flutter pub get` will surface incompatibility immediately. Planner verifies via `flutter pub outdated` at scaffold time. |
| A3 | `flutter_secure_storage` 10.0 works on iOS Simulator without Keychain Sharing entitlement for the SPIKE (since D-49 sidesteps via --dart-define). | Pitfall #4 | LOW — spike doesn't depend on it. Phase 25 path needs explicit physical-device verification (already flagged). |
| A4 | `flutter_client_sse` 2.0.3's `SSEModel.id` is populated from server's `id:` line. | Pattern 5 + Pitfall #2 | LOW — directly verified from package source: `case 'id': currentSSEModel.id = value;`. |
| A5 | The OKLCH→sRGB conversions for `--muted` (`#EFEFEC`), `--muted-foreground` (`#6B6B6B`), `--border` (`#DEDEDA`), `--destructive` (`#D9333A`) match Solvr Labs design intent. | Code Examples — Theme | MEDIUM — only `#1F1F1F` and `#FAFAF7` are EXPLICITLY locked in CONTEXT line 139. The rest are calculated approximations. Planner should regenerate via a real OKLCH→sRGB tool (Culori in JS, `chroma.js`, or pull a Tailwind v4 build artifact) and replace this table. The risk is wrong tints in muted UI elements; not a load-bearing failure but a polish miss. |
| A6 | Backend's `models/errors.py::ErrorCode` enum is the COMPLETE list mirrored in the Dart `ErrorCode` enum. | Pattern 4 | LOW — directly read from `api_server/src/api_server/models/errors.py`. As Phase 23+ adds new codes, the Dart mirror needs sync — flagged for ongoing maintenance. Planner adds a `// TODO: keep in sync with errors.py` comment. |
| A7 | `flutter test integration_test/` invocation works for both iOS Simulator and Android Emulator targets without further per-platform flags (assuming `flutter devices` shows the target as default). | Pitfall #3 + Pattern 7 | LOW — directly verified in docs.flutter.dev/testing/integration-tests. |
| A8 | OpenRouter still serves `https://openrouter.ai/api/v1/models` as a public endpoint that requires no Authorization header (Phase 23 D-19 assumed this). | Architectural Responsibility Map (mentioned but not directly Phase-24 work) | LOW — Phase 23 already verified and shipped this. Phase 24 just consumes. |
| A9 | The Phase 23 backend is locally runnable at `http://localhost:8000` via `make` targets without further Phase-24-side configuration. | Spike harness | LOW — Phase 23 SHIPPED; the harness is documented in `make e2e-inapp-docker`. Spike runs against a separately-started api_server (CONTEXT line 282 documents the operator concern as out-of-scope). |
| A10 | `Color(0xFF1F1F1F)` and `Color(0xFFFAFAF7)` (CONTEXT line 139 verbatim) are sRGB, not P3 / extended-color-space. | Theme | LOW — Flutter's `Color` defaults are sRGB; matching the web's hex codes. |

**Net assessment:** No blocking assumption. A5 and A6 are medium-priority maintenance / polish concerns the planner can absorb; the rest are routine.

## Open Questions

1. **Do the OKLCH non-explicit tokens convert to the right sRGB values?**
   - What we know: `#1F1F1F` and `#FAFAF7` are explicitly mirrored from CSS (CONTEXT line 139).
   - What's unclear: `--muted`, `--muted-foreground`, `--border`, `--destructive` rely on a programmatic OKLCH→sRGB conversion that this research approximated.
   - Recommendation: planner runs a proper OKLCH→sRGB conversion (using `culori` JS, the Tailwind v4 build output, or a Python `colormath` script) and replaces the approximations in `solvr_theme.dart`. Treat any disagreement with this RESEARCH's calculated values as authoritative.

2. **Is the Phase 23 `/v1/models` endpoint shape locked enough to manually-fromJson against?**
   - What we know: Phase 23 D-19/D-20 says passthrough byte-for-byte from OpenRouter.
   - What's unclear: OpenRouter's `/api/v1/models` schema can drift; does the Dart DTO need to be defensively `Map<String, dynamic>`-fielded (passing through unknown keys), or strongly-typed?
   - Recommendation: keep the Dart DTO field-permissive (use `Map<String, dynamic> raw` for unknown fields) — the typed projections only extract the 3-4 fields the UI consumes (id, name, context_length, pricing). This makes the client robust to OpenRouter additions.

3. **Should the spike use OpenRouter or Anthropic-direct via BYOK?**
   - What we know: D-47 picks `anthropic/claude-haiku-4-5` via OpenRouter (BYOK = `OPENROUTER_KEY`).
   - What's unclear: if Anthropic's billing endpoint flakes (Plan 22c.3-12 had a precedent — anthropic-direct credit-zero false-PASS), does the spike need a fallback model?
   - Recommendation: D-47 already picks via OpenRouter, which routes through OpenRouter's billing — different failure surface from Anthropic-direct. Stick with the lock. Document fallback model `anthropic/claude-3-5-sonnet-latest` as a manual override in `mobile/README.md`.

4. **Does `make spike` need a "warm-up" or "ensure backend running" check?**
   - What we know: D-50 wraps `flutter test ... --dart-define ...` and "fails loud with a usage banner if any env var missing."
   - What's unclear: should it also ping `${BASE_URL}/healthz` before invoking `flutter test`, to fail fast if the api_server isn't running?
   - Recommendation: yes, add a curl preflight to `make spike` (planner's discretion). Saves the spike a 60s timeout to discover the api_server is down.

5. **Is portrait-only orientation honored on iOS via Info.plist or programmatically?**
   - What we know: D-14 says "orientation locked to portrait."
   - What's unclear: the canonical iOS approach is Info.plist `UISupportedInterfaceOrientations` = `[Portrait]`; the Flutter approach is `SystemChrome.setPreferredOrientations(...)` in `main.dart`. Which is preferred?
   - Recommendation: BOTH (defense-in-depth). Set Info.plist + AndroidManifest.xml `screenOrientation="portrait"` AND call `SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp])` in `main.dart` before `runApp`.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `fvm` (Flutter Version Manager) CLI | D-05 | ✗ (per-machine setup) | — | Use bare `flutter` (untrusted SDK version) — flag in plan |
| Flutter SDK 3.41 | All | ✗ (per-machine setup, FVM-managed) | 3.41.0 (stable) | Older 3.x stable works but planner adjusts package pins |
| Xcode | iOS Simulator runs (D-22 `make ios`) | macOS-only | latest stable | Skip iOS spike on Linux dev machines |
| Android SDK + Android Emulator (`emulator` CLI + at least one AVD) | D-22 `make android` | Cross-platform | latest stable | Skip Android spike on machines without Android tools |
| `make` | D-22 | macOS/Linux | bundled | use `bash` scripts directly |
| `git` | scaffold | universal | — | — |
| `pnpm` / `npm` (NODE) | NOT needed for mobile/ | — | — | — |
| Local Phase-23 api_server running on `${BASE_URL}` | Spike (D-46) | requires `make` targets in `api_server/` | — | Spike fails fast; documented operator step |
| OpenRouter API key (`OPENROUTER_KEY`) | Spike step 1 (D-47, D-51) | dev's local `.env` | — | Spike fails fast with usage banner (D-50) |
| Valid `ap_session` cookie value (`SESSION_ID`) | Spike (D-49) | Manual: paste from browser DevTools after browser-OAuth | — | Spike fails fast |

**Missing dependencies with no fallback:**
- None at the framework level — all Flutter / FVM / Xcode / Android SDK installs are documented one-time per-machine setup steps that the user runs OUTSIDE the repo. Planner adds prerequisites to `mobile/README.md`.

**Missing dependencies with fallback:**
- iOS Simulator unavailable on Linux dev hosts → spike runs on Android Emulator only, OR on a physical iOS device via `flutter devices` lookup. Document in `mobile/README.md`.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `flutter_test` (unit/widget) + `integration_test` (spike + future widget E2E) — both Flutter SDK bundled |
| Config file | `mobile/analysis_options.yaml` (lint config); `mobile/pubspec.yaml` (test deps) |
| Quick run command | `fvm flutter test` (unit + widget tests in `mobile/test/`) |
| Full suite command | `fvm flutter test && fvm flutter test integration_test/spike_api_roundtrip_test.dart --dart-define=BASE_URL=$BASE_URL --dart-define=SESSION_ID=$SESSION_ID --dart-define=OPENROUTER_KEY=$OPENROUTER_KEY` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| APP-01 | Scaffold runs (`fvm flutter analyze` clean; `make doctor` green; placeholder screen builds for both targets) | smoke | `make doctor && fvm flutter analyze && fvm flutter test` | ❌ Wave 0 |
| APP-02 | Theme renders Inter + JetBrains Mono with #FAFAF7 background and #1F1F1F foreground; corner radius 0 | widget | `fvm flutter test test/theme/solvr_theme_test.dart` | ❌ Wave 0 |
| APP-02 | `ThemeData.colorScheme.surface` matches `Color(0xFFFAFAF7)` | widget | (same as above) | ❌ Wave 0 |
| APP-02 | `ElevatedButton` renders with `BorderRadius.zero` | widget | `fvm flutter test test/theme/button_radius_test.dart` | ❌ Wave 0 |
| APP-03 | `Result<T>` exhaustive switch compiles (sealed class + final subtypes) | unit | `fvm flutter test test/api/result_test.dart` | ❌ Wave 0 |
| APP-03 | `ApiError.fromDioException` parses Stripe envelope correctly across 8+ ErrorCode values | unit | `fvm flutter test test/api/api_error_test.dart` | ❌ Wave 0 |
| APP-03 | `ApiClient.healthz()` returns `Ok` against a httpbin-style mocked dio adapter | unit | `fvm flutter test test/api/api_client_test.dart` (use `MockAdapter` from `dio` test helpers) | ❌ Wave 0 |
| APP-03 | `AuthInterceptor` injects `Cookie: ap_session=<id>` from secure_storage; clears on 401 | unit | `fvm flutter test test/api/auth_interceptor_test.dart` | ❌ Wave 0 |
| APP-03 | Per-call BYOK: `Authorization: Bearer <key>` sent on `runs(byokOpenRouterKey: 'k')` but NOT on `messagesHistory(...)` | unit | (same file as above) | ❌ Wave 0 |
| APP-03 | `MessagesStream` re-injects `Last-Event-Id` from cached state on `connect()` after disconnect | unit | `fvm flutter test test/api/messages_stream_test.dart` | ❌ Wave 0 |
| APP-04 | `AppEnv.fromEnvironment()` throws `StateError` on empty BASE_URL | unit | `fvm flutter test test/env/app_env_test.dart` | ❌ Wave 0 |
| APP-04 | `AppEnv.fromEnvironment()` throws `StateError` on `BASE_URL=not-a-url` | unit | (same file) | ❌ Wave 0 |
| APP-04 | `AppEnv.fromEnvironment()` accepts `BASE_URL=http://localhost:8000` | unit | (same file) | ❌ Wave 0 |
| APP-05 | 9-step round-trip integration test passes against live api_server | integration | `make spike` | ❌ Wave 0 (D-45) |
| APP-05 | Markdown artifact at `spikes/flutter-api-roundtrip.md` recorded with verdict=PASS | manual capture | (post-test, dev writes per D-54) | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `fvm flutter analyze && fvm flutter test`
- **Per wave merge:** `fvm flutter analyze && fvm flutter test` (full unit suite)
- **Phase gate:** unit suite green AND `make spike` green AND `spikes/flutter-api-roundtrip.md` recorded with verdict=PASS

### Wave 0 Gaps

- [ ] `mobile/test/theme/solvr_theme_test.dart` — covers APP-02 (light theme + Inter + corner radius 0)
- [ ] `mobile/test/api/result_test.dart` — covers APP-03 sealed exhaustive
- [ ] `mobile/test/api/api_error_test.dart` — covers APP-03 ApiError.fromDioException across all `ErrorCode` enum values
- [ ] `mobile/test/api/api_client_test.dart` — covers APP-03 happy paths via `MockAdapter`
- [ ] `mobile/test/api/auth_interceptor_test.dart` — covers APP-03 cookie inject + 401 handling
- [ ] `mobile/test/api/messages_stream_test.dart` — covers APP-03 SSE wrapper Last-Event-Id tracking (use a local `HttpServer` or mock subscription)
- [ ] `mobile/test/env/app_env_test.dart` — covers APP-04 boot validation
- [ ] `mobile/integration_test/spike_api_roundtrip_test.dart` — covers APP-05 (D-45)
- [ ] Framework install: `fvm install <flutter-3.41.0>` once per machine + `fvm use 3.41.0` from `mobile/`
- [ ] CI workflow `.github/workflows/mobile.yml` — runs `fvm flutter analyze && fvm flutter test` on push to `mobile/**` (no integration_test in CI per D-27 / D-53)

### Out of CI (LOCAL ONLY per D-53)

- `make spike` — requires real api_server + real Docker daemon + OpenRouter network access + iOS Simulator OR Android Emulator. macOS runners on GitHub Actions can host iOS Simulator but the cost / config exceeds Phase 24's appetite (CONTEXT lines 297-298). Re-evaluate at v0.4.

## Security Domain

> **Skipped.** `.planning/config.json` does not set `security_enforcement` and CLAUDE.md does not mandate it for Phase 24. Phase 24 is a foundation/scaffolding phase with no new persisted data, no new auth surfaces (the spike's `--dart-define SESSION_ID` is dev-only and Phase 23's auth is reused 100%), and no PII collection.
>
> Notable security-adjacent points already in scope:
> - `flutter_secure_storage` (D-35) is the platform-correct slot for the future `session_id` value (Keychain on iOS, EncryptedSharedPreferences on Android).
> - The dio interceptor's `Cookie:` header is the same wire shape `ApSessionMiddleware` already validates.
> - `Authorization: Bearer <byok>` is per-request only (D-40), so BYOK keys never accidentally leak to non-BYOK endpoints.
> - Logs redact `Cookie:` and `Authorization:` headers in dev (Claude's discretion in interceptor design — recommended).
> - `--dart-define OPENROUTER_KEY=...` is bake-time. The key lives in dev's gitignored `.env`. Spike artifact (D-54) does NOT capture the raw key — only its presence as an env var.

## Sources

### Primary (HIGH confidence)
- Context7 `/cfug/dio` — Interceptor lifecycle, CancelToken, per-request Options merge, Token-refresh QueuedInterceptor pattern (NOT used here, but reference).
- Context7 `/rrousselgit/riverpod` — `@riverpod` annotation provider authoring; codegen as 2026 community-default.
- `pub.dev/packages/flutter_riverpod` — verified 3.3.1 latest as of 2026-04 (Riverpod 3.x stable).
- `pub.dev/packages/dio` — verified 5.9.2 latest.
- `pub.dev/packages/go_router` — verified 17.2.3 latest.
- `pub.dev/packages/flutter_client_sse` — verified 2.0.3 latest, last release 2024-08-28.
- `pub.dev/documentation/flutter_client_sse/latest/flutter_client_sse/SSEClient/subscribeToSSE.html` — `subscribeToSSE` exact function signature; NO `lastEventId` param. **Load-bearing for Pitfall #2.**
- `github.com/pratikbaid3/flutter_client_sse/blob/master/lib/flutter_client_sse.dart` — verified `id:` line parsing populates `SSEModel.id`.
- `pub.dev/packages/flutter_secure_storage` — verified 10.0.0 latest.
- `pub.dev/packages/google_sign_in` — verified 7.2.0 latest.
- `pub.dev/packages/flutter_appauth` — verified 12.0.0 latest; iOS `CFBundleURLTypes` + Android `intent-filter` setup verbatim.
- `pub.dev/packages/google_fonts` — verified 8.1.0 latest; runtime fetch + asset bundling behavior.
- `pub.dev/packages/uuid` — verified 4.5.3 latest; v3→v4 API-compatible.
- `pub.dev/packages/very_good_analysis` — verified 10.0.0 latest.
- `dart.dev/language/class-modifiers` — sealed-class same-library requirement + exhaustive switch behavior.
- `docs.flutter.dev/release/release-notes` — Flutter 3.41 (Dart 3.9) latest stable as of 2026-02-20.
- `docs.flutter.dev/testing/integration-tests` — `flutter test integration_test/foo_test.dart` is canonical; `flutter drive` is web-only.
- `docs.flutter.dev/release/release-notes/release-notes-3.41.0` — Dart 3.9 bundled in 3.41.
- `developer.android.com/privacy-and-security/security-config` — `network_security_config.xml` schema for cleartext-debug-only.
- `fvm.app/documentation/getting-started/configuration` — `.fvmrc` format pins specific version (not channel); `.fvm/flutter_sdk` symlink semantics.
- `riverpod.dev/docs/introduction/getting_started` — flutter_riverpod 3.3.1 + riverpod_annotation 4.0.2 current pins.

### Secondary (MEDIUM confidence)
- WebSearch: `flutter SSE package recommended 2025 2026 last-event-id reconnect` — surfaces `eventflux` as alternative; both `flutter_client_sse` and `eventflux` lack auto Last-Event-Id; both support custom-header injection. Confirms Pitfall #2 finding via independent corroboration.
- WebSearch: `flutter_secure_storage iOS Simulator default keychain` — multiple sources confirm Simulator volatility; "test on physical devices for production validation."
- WebSearch: `flutter integration_test localhost HTTP networking 10.0.2.2 android emulator` — confirms `10.0.2.2` works on most images; Pixel/Play-Store images may need `10.0.3.2` (Pitfall #5).
- `solvr/frontend/app/globals.css` lines 6-39 — :root OKLCH tokens (locally read; HIGH confidence on `#1F1F1F` / `#FAFAF7` per CONTEXT line 139, MEDIUM on derived hex for the other tokens pending re-conversion).
- `api_server/src/api_server/models/errors.py` — locally read; ErrorCode enum mirror.
- `api_server/src/api_server/routes/agent_messages.py` — locally read; SSE event shape (`id=<seq>`, `event=<kind>`).
- `api_server/src/api_server/routes/health.py` — locally read; `/healthz` returns `{"ok": true}` always.
- `api_server/src/api_server/middleware/session.py` — locally read; cookie-name `ap_session`.

### Tertiary (LOW confidence — flagged in Pitfalls or Open Questions)
- OKLCH→sRGB conversions for non-explicit Solvr tokens (`--muted`, `--border`, `--destructive`, etc.) — calculated in this research, not run through a verified converter. Open Question #1 + A5.
- `riverpod_generator` major-version compatibility with `riverpod_annotation` 4.0.x — confirmed via riverpod.dev docs as currently-paired but planner verifies at scaffold time. A2.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every package version verified against pub.dev publish dates; major-version compat checked.
- Architecture: HIGH — patterns are direct mirrors of Phase 23's documented contracts (cookie transport, idempotency, SSE shape) and dio's documented interceptor lifecycle.
- Pitfalls: HIGH — Pitfall #2 (`flutter_client_sse` no auto Last-Event-Id) verified via package source; Pitfalls #3-#9 each cite at least one official doc; Pitfall #10 derives directly from Phase 22c.3 / 23 store semantics.
- Theme tokens: MEDIUM — explicit `#1F1F1F` / `#FAFAF7` (CONTEXT-locked) HIGH; derived OKLCH→sRGB MEDIUM (Open Question #1).
- Spike harness: HIGH — pattern mirrors Phase 22c.3.1's `e2e-inapp-docker` make-target shape and Flutter integration_test docs; failure-mode capture (D-52) maps cleanly to `addTearDown`.

**Research date:** 2026-05-02
**Valid until:** 2026-06-02 (~30 days; package versions in this stack are stable, but `flutter_client_sse` 2.0.3 is approaching staleness — re-verify if a 3.x ships that adds Last-Event-Id support natively).

---

*Phase: 24-flutter-foundation*
*Researched: 2026-05-02*

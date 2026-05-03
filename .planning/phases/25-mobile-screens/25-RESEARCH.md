# Phase 25: Mobile Screens (end-to-end demo) — Research

**Researched:** 2026-05-03
**Domain:** Flutter mobile app — wiring four screens (Login + Dashboard + New Agent wizard + Chat) end-to-end against the local Phase 23 backend.
**Confidence:** HIGH for everything Phase 24 already proved (typed `ApiClient`, `MessagesStream` Last-Event-Id wrapper, `flutter_secure_storage`, dio + go_router + Riverpod). MEDIUM-HIGH for the three NEW pubspec deps (`flutter_markdown` / `url_launcher` / `golden_toolkit`) and for the two NEW cross-cutting Flutter mechanisms (`AppLifecycleState` SSE reconnect, scoped Riverpod across a `go_router` route group). LOW only on `google_sign_in` 7.x real-OAuth wiring + iOS native config — flagged for Wave 0/1 spike, but the test seam (D-66 + Phase 24 D-49) keeps the wave gates green even if the native path needs follow-up tuning.

---

<user_constraints>
## User Constraints (from 25-CONTEXT.md)

The CONTEXT document at `.planning/phases/25-mobile-screens/25-CONTEXT.md` is the
authoritative source for Phase 25. Do NOT re-litigate locked decisions. The
sections below are direct excerpts.

### Locked Decisions

68 D-numbered decisions across 11 sub-domains. Read CONTEXT.md fully; the
load-bearing ones for the planner are summarized in the **Implementation
Approach** section below mapped to waves and grep-checkable acceptance.

Highlights the planner MUST honor verbatim:

- **D-01..D-07**: native splash → `/v1/users/me` → `/dashboard` or `/login`; 401 anywhere → clear `flutter_secure_storage` session_id + route to `/login` + inline 401 banner; logout in Dashboard 3-dot overflow → `ConfirmDialog` → clear session_id (NOT BYOK keys per D-25).
- **D-08..D-20**: Dashboard rows; `StatusDot` 3-state colors; pull-to-refresh + foreground-resume re-fetch; no background polling; ASCII agent-name banner cycling on empty state.
- **D-21..D-34, D-54..D-60**: 3-step wizard; step 1 Clone (horizontal cards), step 2 Model picker (push route at `/new-agent/model/picker`) + BYOK, step 3 Name + Telegram + Deploy; pre-flight name-collision check; smoke-loading card with cancel; multi-channel deploy (1 × `/runs` + N × `/start`); telegram fields rendered DYNAMICALLY from `recipe.channels.telegram.required_user_input` (NEVER hardcoded).
- **D-35..D-53**: Chat bubbles (right/left + invert colors); Map dedup by `inappMessageId`; markdown via `flutter_markdown`; `url_launcher` https/http only; `Last-Event-ID` reconnect on `AppLifecycleState.resumed`; failed-bubble bottom sheet (Retry generates NEW Idempotency-Key).
- **D-61..D-66**: 9 shared widgets in `lib/shared/`; `golden_toolkit` snapshots at textScaleFactor 1.0 / 1.5 / 2.0; 5 waves; **Wave 5 spike** at `mobile/integration_test/screens_e2e_test.dart` + `spikes/flutter-screens-roundtrip.md` is the load-bearing exit gate; **`AuthService` interface** (D-66) — real impl (`google_sign_in` + `flutter_appauth`) + test impl (`SESSION_ID` via `--dart-define`).
- **D-67**: pubspec version bump `0.1.0+1 → 0.2.0+2` (Wave 1).
- **AMD-01**: REQUIREMENTS.md UI-02 must be rewritten in this phase's commit chain (Telegram is REAL, not stub).
- **AMD-02**: `23-CONTEXT.md` D-28 must be amended in this phase's commit chain ("inapp + optional telegram", not "inapp only").

### Claude's Discretion

(Verbatim from CONTEXT — planner picks defaults.)

- Riverpod provider granularity (one provider per screen vs per feature-slice).
- Exact `JetBrains Mono` font weight for the wordmark — UI-SPEC resolved to **w600**.
- ASCII banner cycling animation curve — UI-SPEC resolved to **`Curves.easeInOut` cross-fade 300ms**.
- Whether typing-dots animation uses `AnimatedBuilder` or `LottieFile` — UI-SPEC resolved to **`AnimatedBuilder`**, no extra dep.
- Whether wizard's step state is one provider or three — defer to planner; suggested **three with composition** in D-Discretion comment.
- Pull-to-refresh visual indicator (Material default `RefreshIndicator` unless designer pivots).
- Provider order on Login (Google first, GitHub second).
- Step validation predicate placement — defer to planner.
- Message length cap on send — none enforced client-side.
- Connectivity-offline app-wide banner — NONE.
- Naming the AuthService interface methods — defer to planner (`signInWithGoogle()` / `signInWithGithub()` / `signOut()` suggested).
- Exact `golden_toolkit` snapshot count + which screens — defer to planner; CONTEXT suggests Dashboard empty + Dashboard populated + Login + Chat with markdown reply.
- Whether `AsciiAgentBanner` pulls names from `GET /v1/recipes` itself or accepts an injected `Stream<List<String>>` — UI-SPEC resolved to **injected stream** (provider supplies; widget stays pure).

### Deferred Ideas (OUT OF SCOPE)

(Verbatim from CONTEXT — planner does NOT plan these.)

Telegram pairing flow (`dmPolicy:pairing`) | Backend `POST /v1/agents/deploy`
single-shot endpoint | Agent Stop / Restart from Dashboard rows | Agent Delete
endpoint + swipe-to-delete | Background SSE / push (APNS/FCM) | Token-level
streaming chat | Markdown image rendering | Custom URI scheme link tapping in
markdown | App-internal deep links | Connectivity-offline app-wide banner |
Bubble timestamps on every bubble | Cached recipes/models on device | Local
SQLite mirror | In-app Settings screen | Profile / Browse tabs functioning |
Universal Links / App Links | Real Solvr Labs app icon + native splash |
fastlane / TestFlight / Play Store | Apple Privacy Manifest | Push
notifications, crash reporting, analytics | Localization | Dark mode | In-app
debug menu / env switcher | Backend `/v1/agents/:id/restart-multi-channel`
endpoint | App version reaches `0.3.0`.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **UI-01** | Dashboard renders `GET /v1/agents`; row = name + model + status dot; empty state shows "+" CTA; tap row → Chat; tap "+" → New Agent. | `ApiClient.agentsList()` already shipped (Phase 24 Plan 04, signed off in spike step "extended response"). `AgentSummary` DTO already has `id/name/recipeName/model/status/createdAt/lastActivity` — only the rendering + `AppLifecycleState` foreground-refetch (D-12) is new. See **Mechanism §5** + **Pattern: Wave 2 Dashboard**. |
| **UI-02** *(amended via AMD-01)* | New Agent picks clone from `GET /v1/recipes` + model from `GET /v1/models` + name; tapping Deploy first POSTs `/v1/runs` (smoke), then `/v1/agents/:id/start` with `channel:'inapp'`, then (when toggled AND `channels_supported` includes telegram) a SECOND `/v1/agents/:id/start` with `channel:'telegram'` and dynamic `channel_inputs`. Telegram-only failure → Chat with sticky banner. | `ApiClient.runs()` + `start()` + `recipes()` + `models()` already shipped. Mirroring web `playground-form.tsx` lines 316-360 (deploy sequence) + 638-689 (dynamic channel-inputs) + 627-635 (BYOK label-swap). See **Mechanism §6** (multi-channel orchestration) + **Mechanism §7** (BYOK label dynamism) + **Mechanism §11** (model picker push-route) + **Mechanism §12** (pre-flight collision check). **Critical DTO gap: existing `Recipe` DTO is thin (only `name` + `channelsSupported`); planner MUST extend it.** |
| **UI-03** | Chat loads last-N messages via `GET /v1/agents/:id/messages`, renders bubbles, sends via `POST /v1/agents/:id/messages`; messages persist across kill+relaunch. | `ApiClient.messagesHistory()` + `postMessage()` + `MessagesStream` already shipped. Phase 23 history is **ASC oldest→newest** (verified in spike step 6 + 23-CONTEXT D-04). Persistence is automatic (DB is source of truth per D-63). See **Mechanism §4** (SSE reconnect on resume) + **Mechanism §9** (optimistic-insert + dedup). |
| **UI-04** | End-to-end demo on real device/simulator: open → Dashboard → "+" → wizard → Deploy → Chat → message → reply → kill → relaunch → history visible. | This IS the load-bearing requirement. **Wave 5 spike (D-65)** is the only test that proves it; widget tests + golden tests are supplemental. See **Validation Architecture** + **Mechanism §13** (Wave-5 harness extensions). |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

The five golden rules apply to every wave. Phase 25-specific implications:

1. **No mocks, no stubs.** Wave 5 spike runs against live local `api_server` + Postgres + Redis + a real container + real OpenRouter. Widget unit tests may use `http_mock_adapter` for the dio layer (Phase 24 already pulls it in dev_dependencies) — that's NOT a violation because the substrate IS the API client itself; the mock isolates the widget under test, not the API contract.
2. **Dumb client, intelligence in the API.** No Flutter-side hardcoded recipe/model/channel-input lists. Banner names from `GET /v1/recipes` (D-17). BYOK label from `recipe.channel_provider_compat` (D-32). Telegram fields from `recipe.channels.telegram.required_user_input` (D-54). Restart channel set from extended `GET /v1/agents` response (D-49 — flag the gap if extended endpoint isn't there).
3. **Ship when the stack works locally end-to-end.** Wave 5 spike artifact (`spikes/flutter-screens-roundtrip.md` with `verdict: PASS`) IS the ship signal. The plan-checker treats it as the exit gate.
4. **Root cause first.** Any test failure during execution gets investigated before "fix-to-pass". Same discipline as Phase 24 (which had 2 substrate fixes pulled out of the spike — `tools/run_recipe.py --network` + `Dockerfile.api` deps; both fixed at root, neither at the spike).
5. **Test everything. Probe gray areas BEFORE planning.** This research's **Mechanisms** section identifies 13 gray areas. Items flagged `[Wave-0 spike]` MUST be empirically validated before the consuming wave's PLAN is sealed. Items flagged `[in-substrate]` already have validated reference paths (Phase 24 spike or web playground-form).

## GSD Workflow Enforcement

Phase 25 is being executed under `/gsd-execute-phase 25` orchestration. All file
edits (including the AMD-01 / AMD-02 amendments to REQUIREMENTS.md and
23-CONTEXT.md) flow through the executor; no out-of-workflow direct edits.

---

## Summary

Phase 25 is the screen-plumbing phase of the Mobile MVP milestone. The
substrate is already in place: Phase 24 shipped a typed dio `ApiClient` exposing
**every endpoint** Phase 25 needs, a `MessagesStream` SSE wrapper that already
tracks `Last-Event-Id` correctly, a `flutter_secure_storage` wrapper, an
`AuthInterceptor` that injects `Cookie: ap_session` and emits `AuthRequired` on
401, the SolvrLabs theme, `go_router` config, env-config + boot validation, and
a 9-step round-trip integration_test that PASSED 2026-05-02 against a live
local backend. **`Recipe` and `RunRequest` DTOs are thin and need extension**
— Recipe currently exposes only `name + channelsSupported` (Phase 25 needs
`description`, `displayName`, `channelProviderCompat`); a new `RecipeDetail`
DTO is needed for `/v1/recipes/{name}` (D-54 source of truth for dynamic
Telegram inputs). The screen-plumbing scope is large but mechanically simple.

The plan-time research surface is dominated by **13 cross-cutting mechanisms**
that the planner must get right (each detailed in **Mechanism §1..§13** below):
five concern lifecycle / state / route plumbing (`AppLifecycleState`-driven SSE
reconnect, foreground-resume Dashboard re-fetch, scoped Riverpod across a
`go_router` route group, optimistic-insert + dedup on the chat list, the
push-pop model-picker route), four concern external integrations (real
`google_sign_in` 7.x + `flutter_appauth` OAuth on iOS+Android, `flutter_markdown`
+ `url_launcher` scheme allow-list, `golden_toolkit` font preload + textScale
sweep, the multi-channel deploy orchestration mirroring web playground-form),
two concern data shapes (BYOK label-swap from `recipe.channel_provider_compat`,
dynamic Telegram fields from `recipe.channels.telegram.required_user_input`),
and two concern Wave 5 (the screens-e2e spike harness extensions, and the
two REQUIREMENTS / 23-CONTEXT amendments which MUST land in this phase's
commit chain).

**Three new pubspec dependencies** are introduced in Wave 1: `flutter_markdown`,
`url_launcher`, `golden_toolkit` (dev). Two of these have material maintenance
signals the planner must handle: **`flutter_markdown` was discontinued by
Google in 2025** — the canonical successor is `flutter_markdown_plus`
(maintained by Foresight Mobile, 140k weekly downloads, drop-in API). CONTEXT
D-43 names `flutter_markdown` literally; the planner SHOULD substitute
`flutter_markdown_plus` and document the substitution as a Phase 25 amendment.
**`golden_toolkit` is in a similar state** (eBay archive; community fork is
`alchemist` from VeryGoodVentures) — but D-62 is locked, and `golden_toolkit`
still works against current Flutter; pin a version, document the maintenance
signal, defer the migration.

**`google_sign_in` 7.x** is a major API rewrite vs the 6.x pattern most Dart
training data documents. The new contract requires `GoogleSignIn.instance` +
`await initialize(...)` + `attemptLightweightAuthentication()` BEFORE any
sign-in call, and authentication + authorization are now separate steps. The
test seam (D-66 — `AuthService` interface + `--dart-define SESSION_ID`)
absorbs the risk: real OAuth path is verified by the manual smoke artifact
only; widget/integration tests use the test impl. **Wave 0 spike recommended**
to validate the real path before Wave 1 plans seal.

**Primary recommendation:** plan five waves per D-64. Wave 0 is a 2-task
diligence gate (real-OAuth spike + dependency-substitution decision for
`flutter_markdown_plus`). Wave 1 builds `lib/shared/` widgets + `lib/core/auth/`
+ Login + cold-start. Wave 2 ships Dashboard. Wave 3 ships the wizard +
multi-channel deploy. Wave 4 ships Chat. Wave 5 is the screens-e2e spike +
artifact + AMD-01 / AMD-02 amendments. Every wave's PLAN must include
grep-verifiable acceptance criteria that the executor can satisfy without
running on a simulator (for the unit/widget portion); the simulator-only path
is reserved for Wave 5.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Cold-start session probe (`/v1/users/me`) | Mobile App (boot path in `main.dart` + `app_router.dart`) | API (existing `routes/users.py`) | Native splash holds while the API call resolves; mobile decides `/dashboard` vs `/login` from the Result. No backend change. |
| OAuth real flow (Google + GitHub) | Mobile App (`AuthService` real impl: `google_sign_in` + `flutter_appauth`) | API (existing `POST /v1/auth/{google,github}/mobile`) | Native SDKs collect the credential; backend mints session. Phase 22c-oauth-google substrate is reused 100%. |
| Session storage | Mobile App (`flutter_secure_storage` via Phase 24 `SecureStorage` wrapper) | — | Keychain (iOS) / EncryptedSharedPreferences (Android). Already shipped. |
| BYOK key storage | Mobile App (`flutter_secure_storage`, per-provider entries) | — | NEW in Phase 25: extend the `SecureStorage` wrapper with `writeByokKey(provider, key)` / `readByokKey(provider)` + matching clear/exists. Logout does NOT clear (D-33). |
| Recipe / model catalog | API (`GET /v1/recipes`, `GET /v1/models`) | Mobile App (renders dynamically) | Dumb client. No client-side hardcoded lists; banner cycle uses live recipes (D-17). |
| Telegram channel-input form fields | API (`GET /v1/recipes/{name}` exposes `channels.telegram.required_user_input`) | Mobile App (renders one TextField per entry) | Server is source of truth; labels = `env` value verbatim; types from `secret`; hint + hint_url passed through. **NEVER hardcoded in Dart** (D-54 + Golden Rule #2). |
| Multi-channel deploy orchestration | Mobile App (sequential: 1 × `/runs` + N × `/start`) | API (existing endpoints accept channel-per-call) | Mirror of web playground-form lines 316-360. NO new backend endpoint. |
| SSE chat stream | Mobile App (`MessagesStream` + `AppLifecycleState` reconnect) | API (`GET /v1/agents/:id/messages/stream` with `Last-Event-ID` resume) | Phase 24 wrapper handles cursor; Phase 25 adds the `WidgetsBindingObserver` lifecycle hook + the Riverpod-scoped owning provider. |
| Optimistic message render | Mobile App (Map keyed by `inappMessageId`, dedup on SSE arrival) | API (POST `/messages` returns `message_id`; SSE delivers same id) | Race between POST response and SSE event is benign — same content per Phase 23 D-08. |
| Markdown rendering + link safety | Mobile App (`flutter_markdown` + `url_launcher` with `https/http` allow-list) | — | All security-relevant link filtering is client-side (D-46). Backend doesn't sanitize markdown (LLM output is what it is). |
| Status / lifecycle banners | Mobile App (`RestartBanner`, Telegram-failed banner) | API (`agent.status` from extended `GET /v1/agents` response) | Status is computed server-side from `agent_containers.container_status`; mobile only renders. Restart calls `POST /v1/agents/:id/start`; multi-channel restart needs the channel set — D-49 flags this as a planner-deferred TODO if extended `GET /v1/agents` doesn't already expose it. |
| Wave 5 e2e validation | Mobile App (integration_test driving WidgetTester) | API + Postgres + Redis + Container + OpenRouter (live) | Mirrors Phase 24 `make spike` shape. The harness IS the test of UI-04. |
| AMD-01 / AMD-02 amendments | Repo docs (`.planning/REQUIREMENTS.md`, `23-CONTEXT.md`) | — | Plan tasks (NOT docs-only commits) — verifier signals the wave gate. |

---

## Standard Stack

### Carry-Forward (Phase 24 — already in `mobile/pubspec.yaml`, locked, do not bump in this phase)

| Library | Version | Purpose | Source of truth |
|---------|---------|---------|-----------------|
| `flutter` SDK | `>= 3.41.0` (FVM-pinned) | Dart 3.9 + Flutter framework | Phase 24 D-22 + `mobile/pubspec.yaml` line 8 `[VERIFIED: pubspec.yaml]` |
| `flutter_riverpod` | `^3.3.1` | State management | `[VERIFIED: pubspec.yaml line 16]` |
| `riverpod_annotation` | `^4.0.2` | Codegen for Riverpod providers | `[VERIFIED: pubspec.yaml line 21]` |
| `riverpod_generator` (dev) | `^4.0.3` | build_runner for the above | `[VERIFIED: pubspec.yaml line 31]` |
| `go_router` | `^17.2.3` | Navigation | `[VERIFIED: pubspec.yaml line 18]` |
| `dio` | `^5.9.2` | HTTP client | `[VERIFIED: pubspec.yaml line 11]` |
| `flutter_client_sse` | `^2.0.3` | SSE consumer (Phase 24 wrapper handles Last-Event-Id) | `[VERIFIED: pubspec.yaml line 15]` — **maintenance status low; CONTEXT D-33 LOCKED.** Keep. |
| `flutter_secure_storage` | `^10.0.0` | Session_id + BYOK key persistence | `[VERIFIED: pubspec.yaml line 17]` — Phase 25 extends with per-provider BYOK methods |
| `google_sign_in` | `^7.2.0` | Native Google sign-in | `[VERIFIED: pubspec.yaml line 19]` — **major API rewrite vs 6.x; see Mechanism §3** |
| `flutter_appauth` | `^12.0.0` | GitHub OAuth (system browser + PKCE) | `[VERIFIED: pubspec.yaml line 14]` |
| `google_fonts` | `^8.1.0` | Inter + JetBrains Mono delivery | `[VERIFIED: pubspec.yaml line 20]` |
| `uuid` | `^4.5.3` | Idempotency-Key + local message id | `[VERIFIED: pubspec.yaml line 22]` |
| `very_good_analysis` (dev) | `^10.0.0` | Lints | `[VERIFIED: pubspec.yaml line 32]` |
| `http_mock_adapter` (dev) | `^0.6.1` | dio mocking for widget unit tests | `[VERIFIED: pubspec.yaml line 28]` |
| `build_runner` (dev) | `^2.4.0` | code generation | `[VERIFIED: pubspec.yaml line 25]` |
| `integration_test` (dev) | bundled with Flutter SDK | Wave 5 spike harness | `[VERIFIED: pubspec.yaml line 30]` |

### NEW in Phase 25 (Wave 1)

| Library | Recommended Version | Purpose | Notes |
|---------|---------------------|---------|-------|
| **`flutter_markdown_plus`** | `^1.0.6` (or current stable) | Chat-bubble markdown rendering (D-43 / D-46) | **CRITICAL**: CONTEXT D-43 names `flutter_markdown` literally, but Google **discontinued** that package in 2025 [CITED: github.com/flutter/flutter#162966]. The canonical successor is `flutter_markdown_plus` maintained by Foresight Mobile (140k weekly downloads, drop-in API; same `Markdown`/`MarkdownBody` widgets, same `onTapLink` callback) [CITED: foresightmobile.com/blog/flutter-markdown-plus-google-handover, pub.dev/packages/flutter_markdown_plus]. Planner should substitute and document the substitution as a Phase 25 amendment. The alternate fork `flutter_markdown_community` exists but Foresight Mobile's variant has higher adoption. Pin a major. Verify the latest with `flutter pub outdated` at scaffold time. |
| **`url_launcher`** | `^6.3.x` (verify at scaffold) | Open external browser for chat-bubble links (D-46) | First-party Flutter team plugin (`flutter.dev` verified publisher). Uses `launchUrl(Uri, mode: LaunchMode.externalApplication)` to force the OS browser instead of an in-app webview [CITED: pub.dev/packages/url_launcher]. iOS Info.plist must declare `LSApplicationQueriesSchemes` for any non-default scheme; `https`/`http` are default-allowed. See **Mechanism §2**. |
| **`golden_toolkit`** (dev) | `^0.15.x` | Snapshot tests at textScaleFactor 1.0/1.5/2.0 (D-62) | eBay archived; community fork is `alchemist` from VeryGoodVentures [CITED: github.com/Betterment/alchemist]. CONTEXT D-62 LOCKED to `golden_toolkit`. Pin a version, document the maintenance signal, do NOT switch in this phase — `golden_toolkit` still works against current Flutter SDK. The `loadAppFonts()` test-config pattern is the canonical one [CITED: pub.dev/documentation/golden_toolkit/latest/golden_toolkit/loadAppFonts.html]. See **Mechanism §10**. |

**Installation (Wave 1 Plan):**

```yaml
# mobile/pubspec.yaml — additions for Phase 25
dependencies:
  # ... existing
  flutter_markdown_plus: ^1.0.6   # NOTE: substitution for D-43's "flutter_markdown" — Google discontinued
  url_launcher: ^6.3.0
dev_dependencies:
  # ... existing
  golden_toolkit: ^0.15.0
```

```bash
cd mobile && fvm flutter pub get
```

**Version verification:** During Wave 1 execution, `fvm flutter pub outdated`
to confirm the latest stable for each. If any has shipped a major bump in
the days between this research and Wave 1, the planner reads the changelog
before pinning (Phase 24 RESEARCH established this discipline).

### Alternatives Considered (do NOT switch)

| Standard | Alternative | Why we picked the standard |
|----------|-------------|----------------------------|
| `flutter_markdown_plus` | `flutter_markdown_community` (also a fork) | Lower adoption; Foresight Mobile's variant has the verified-publisher Foresight Mobile + higher download count [CITED: pub.dev/packages/flutter_markdown_plus]. |
| `flutter_markdown_plus` | `flutter_smooth_markdown` | Different rendering approach (canvas-based); deviates further from the original API; CONTEXT D-43 named the original API. |
| `url_launcher` | `flutter_inappwebview` | Exact opposite of D-46's intent — D-46 wants the OS browser, not an in-app webview. WebView OAuth is also forbidden by Google in 2025+. |
| `golden_toolkit` | `alchemist` (Betterment/VeryGoodVentures) | CONTEXT D-62 LOCKED. Migration is a v2 chore. |
| `flutter_client_sse` | `eventflux` | CONTEXT D-33 LOCKED in Phase 24. Both lack auto-reconnect; both need manual `Last-Event-Id` injection — Phase 24's wrapper already solves this for `flutter_client_sse`. |

---

## Architecture Patterns

### System Architecture Diagram

```
                                  ┌──────────────────────────┐
                                  │ Native Splash            │
                                  │ (iOS LaunchScreen /      │
                                  │  Android launch_bg)      │
                                  └─────────────┬────────────┘
                                                │ holds until /v1/users/me resolves (D-01)
                                                ▼
                          ┌─────────────────────────────────────────┐
                          │ ApiClient.usersMe() (with Cookie inj.)  │
                          └──────────┬───────────────────┬──────────┘
                                     │ 200                │ 401 / no cookie
                                     ▼                    ▼
                        ┌──────────────────┐    ┌────────────────────┐
                        │ /dashboard       │    │ /login             │
                        │ Dashboard screen │    │ Login screen       │
                        └────────┬─────────┘    └─────────┬──────────┘
                                 │ tap row                │ tap "Continue with Google" / "Continue with GitHub"
                                 │ tap "+" / FAB          │
                                 ▼                        ▼
              ┌───────────────────────────┐    ┌─────────────────────────────┐
              │ /chat/:id (Chat)          │    │ AuthService.signInWith{G,GH}│
              │  ◀── SSE: messagesStream  │    │  ┌──── Real impl ────────┐  │
              │       (Last-Event-Id)     │    │  │ google_sign_in 7.x    │  │
              │  ───▶ POST /messages      │    │  │ flutter_appauth 12.x  │  │
              └───────────────────────────┘    │  └──── Test impl ──────┐│  │
                                               │  │ --dart-define SESS_ID││  │
                                               │  └────────────────────┘ │  │
                                               └────────────┬────────────┘
                                                            │ id_token / access_token
                                                            ▼
                                          ApiClient.authGoogleMobile() / authGithubMobile()
                                                            │ 200 + Set-Cookie ap_session=<uuid>
                                                            ▼
                                               (server returns SessionUser)
                                                            │
                                            secureStorage.writeSessionId(uuid)
                                                            │
                                                            ▼
                                                      go('/dashboard')

                          /new-agent flow (3 steps):
                          /new-agent/clone ─→ /new-agent/model ─→ /new-agent/name-deploy
                                              │
                                              └─→ /new-agent/model/picker (full-screen pop-with-result)

                          Wizard scope (Riverpod-scoped, cleared on close, D-21/D-31):
                              selectedRecipe, selectedModel, byokKey, agentName,
                              telegramEnabled, telegramInputs

                          Deploy tap on step 3 (D-56):
                              1. apiClient.runs(byok=...)
                              2. if verdict ≠ PASS → inline error (D-30)
                              3. apiClient.start(channel='inapp', byok=...)
                              4. if telegramEnabled:
                                   apiClient.start(channel='telegram', channelInputs=..., byok=...)
                              5. router.go('/chat/<new-agent-id>')   (REPLACE wizard)

                          Chat lifecycle (D-52):
                              onMount   — kick off GET /messages AND messagesStream.connect() in parallel
                              onResume  — stream.disconnect() + connect() (re-injects Last-Event-Id)
                              onPop     — stream.dispose()
```

### Recommended Project Structure (Phase 25 additions)

```
mobile/lib/
├── core/
│   ├── api/                        # Phase 24 — extend dtos.dart + add new providers
│   │   ├── dtos.dart               # EXTEND: enrich Recipe (description, displayName, channelProviderCompat); ADD RecipeDetail (full passthrough); ADD ModelInfo extras (contextLength, pricing); RunRequest add personality? (NO — out of MVP)
│   │   └── ...
│   ├── auth/                       # Phase 24 has auth_event_bus.dart only
│   │   ├── auth_service.dart       # NEW (D-66): interface
│   │   ├── auth_service_real.dart  # NEW: google_sign_in + flutter_appauth
│   │   ├── auth_service_test.dart  # NEW: --dart-define SESSION_ID seam
│   │   └── auth_event_bus.dart     # EXISTING (Phase 24)
│   ├── storage/
│   │   └── secure_storage.dart     # EXTEND: writeByokKey(provider) / readByokKey(provider) / clearByokKey(provider)
│   ├── lifecycle/                  # NEW
│   │   └── app_lifecycle_observer.dart  # WidgetsBindingObserver fan-out for AppLifecycleState (Mechanism §1)
│   ├── router/
│   │   └── app_router.dart         # FILL: /, /login, /dashboard, /new-agent/*, /chat/:id (D-21/D-26/D-60)
│   └── theme/                      # Phase 24 — add SolvrColors.success #22C55E (D-14)
├── shared/                         # NEW (D-61) — Wave 1 plan ships these BEFORE any screen
│   ├── status_dot.dart
│   ├── empty_state_scaffold.dart
│   ├── ascii_agent_banner.dart
│   ├── retry_banner.dart
│   ├── skeleton_row.dart
│   ├── typing_dots.dart
│   ├── failed_bubble.dart
│   ├── restart_banner.dart
│   └── confirm_dialog.dart
└── features/
    ├── login/                      # NEW Wave 1
    │   ├── login_screen.dart
    │   └── login_providers.dart    # Riverpod: pendingProvider, errorProvider
    ├── dashboard/                  # Wave 2 (currently empty dir)
    │   ├── dashboard_screen.dart
    │   ├── agent_row.dart
    │   └── dashboard_providers.dart
    ├── new_agent/                  # Wave 3 (currently empty dir)
    │   ├── wizard_shell.dart       # AppBar + stepper + body slot
    │   ├── clone_step.dart         # /new-agent/clone
    │   ├── model_step.dart         # /new-agent/model + BYOK
    │   ├── model_picker_screen.dart   # /new-agent/model/picker (push-pop)
    │   ├── name_deploy_step.dart   # /new-agent/name-deploy
    │   └── wizard_providers.dart   # wizardScopeProvider (D-21 scoped)
    └── chat/                       # Wave 4 (currently empty dir)
        ├── chat_screen.dart
        ├── bubble_widget.dart
        ├── input_bar.dart
        └── chat_providers.dart     # chatScopeProvider.family(agentId) (D-52)
```

### Pattern 1: AppLifecycleState observer (load-bearing for D-12 + D-52)

**What:** A single `WidgetsBindingObserver` registered at the `app.dart` /
`MaterialApp` level fans out lifecycle events into Riverpod providers; screens
listen via `ref.listen` instead of registering their own observers.

**When to use:** any provider whose state depends on app lifecycle
(Dashboard's `agentsListProvider` re-fetch on resume; Chat's SSE reconnect on
resume).

**Source:** Flutter docs `[CITED: api.flutter.dev/flutter/widgets/WidgetsBindingObserver-class.html]`. Pattern verified against community standard.

```dart
// lib/core/lifecycle/app_lifecycle_observer.dart  (NEW)
class AppLifecycleNotifier extends StateNotifier<AppLifecycleState>
    with WidgetsBindingObserver {
  AppLifecycleNotifier() : super(AppLifecycleState.resumed) {
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState s) => state = s;

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }
}

final appLifecycleProvider =
    StateNotifierProvider<AppLifecycleNotifier, AppLifecycleState>(
        (ref) => AppLifecycleNotifier());
```

Consumers:

```dart
// lib/features/dashboard/dashboard_providers.dart  (NEW)
@riverpod
class AgentsList extends _$AgentsList {
  @override
  Future<List<AgentSummary>> build() async {
    final api = ref.watch(apiClientProvider);
    // re-fetch when app resumes
    ref.listen(appLifecycleProvider, (prev, next) {
      if (prev != next && next == AppLifecycleState.resumed) {
        ref.invalidateSelf();
      }
    });
    final res = await api.agentsList();
    return res.match((ok) => ok, (err) => throw err);
  }
}
```

```dart
// lib/features/chat/chat_providers.dart  (NEW)
// MessagesStream is owned by the Riverpod chatScopeProvider; reconnect-on-resume:
ref.listen(appLifecycleProvider, (prev, next) async {
  if (prev != next && next == AppLifecycleState.resumed) {
    await stream.disconnect();
    await stream.connect();   // wrapper re-injects Last-Event-Id
  }
});
```

### Pattern 2: Multi-channel deploy orchestration (UI-02 / D-56)

**What:** Sequential `1 × /runs + N × /start` with explicit per-step error
shape. Mirrors web `playground-form.tsx` lines 316-360.

**When to use:** wizard's Deploy button only.

```dart
// lib/features/new_agent/name_deploy_step.dart  (NEW, illustrative)
Future<void> onDeploy(WidgetRef ref) async {
  final scope = ref.read(wizardScopeProvider);
  final api = ref.read(apiClientProvider);
  final cancel = CancelToken();
  ref.read(deployStateProvider.notifier).startSmoke(cancel);

  // Step 1 — pre-flight name collision (D-28)
  final agents = await api.agentsList();
  if (agents.match((list) => list.any((a) => a.name == scope.agentName), (_) => false)) {
    final choice = await ConfirmDialog.show(
      context, title: 'Name "${scope.agentName}" already used',
      body: 'Existing agent: ${existing.recipeName} + ${existing.model}. Re-deploy replaces it; rename keeps both.',
      cancelLabel: 'Cancel', confirmLabel: 'Re-deploy', destructive: true,
      thirdButtonLabel: 'Rename');
    if (choice == ConfirmDialogResult.cancel) return;
    if (choice == ConfirmDialogResult.third) { focusNameField(); return; }
    // confirm => proceed (UPSERT semantics handle replace)
  }

  // Step 2 — POST /v1/runs (smoke gate)
  final runRes = await api.runs(
    body: RunRequest(
      recipeName: scope.selectedRecipe.name,
      model: scope.selectedModel.id,
      agentName: scope.agentName,
    ),
    byokOpenRouterKey: scope.byokKey,
    cancelToken: cancel,
  );
  final runOk = runRes.match((r) => r, (e) => null);
  if (runOk == null) { ref.read(deployStateProvider.notifier).fail(...); return; }
  if (runOk.verdict != 'PASS') { ref.read(deployStateProvider.notifier).smokeFail(runOk); return; }

  final agentId = runOk.agentInstanceId;

  // Step 3 — POST /v1/agents/:id/start (channel='inapp')
  final inappRes = await api.start(agentId: agentId, byokOpenRouterKey: scope.byokKey);
  if (inappRes.isErr) { ref.read(deployStateProvider.notifier).inappFail(...); return; }   // D-57

  // Step 4 — optional Telegram
  String? telegramFailReason;
  if (scope.telegramEnabled) {
    final tgRes = await api.start(
      agentId: agentId,
      body: StartRequest(channel: 'telegram', channelInputs: scope.telegramInputs),
      byokOpenRouterKey: scope.byokKey,
    );
    if (tgRes.isErr) { telegramFailReason = tgRes.errOrNull?.message; }   // D-58 — non-fatal
  }

  // Step 5 — route to Chat (D-60: REPLACE wizard)
  ref.read(chatBannerProvider.notifier).setTelegramFail(telegramFailReason);
  router.go('/chat/$agentId');
}
```

### Pattern 3: Optimistic-insert + dedup-by-message-id Map (D-36 / D-41)

**What:** Maintain a `Map<String, ChatMessage>` keyed by `inappMessageId`. Both
the SSE-delivered event and the `GET /messages` history row share the same
`inapp_message_id` per Phase 23 D-08.

**When to use:** Chat screen's message list state.

```dart
// lib/features/chat/chat_providers.dart
class ChatState {
  final Map<String, ChatMessage> byId;
  final List<String> orderedIds;     // insertion order — preserved
  // ...
}

void onSseEvent(SseEvent ev) {
  final payload = jsonDecode(ev.data);
  final msg = ChatMessage.fromJson(payload);
  state = state.upsert(msg);     // map dedup is automatic
}

void onPostMessageOk(MessagePostAck ack, String localContent, String idemKey) {
  // Optimistic user bubble inserted with idemKey-as-temp-id; once /messages history
  // arrives or SSE delivers the user mirror, replace by inappMessageId.
}
```

### Anti-Patterns to Avoid

- **Storing the SSE connection at the widget level.** It must live in a
  Riverpod provider (`chatScopeProvider.family(agentId)`) so the
  `AppLifecycleState.resumed` listener can disconnect/reconnect without
  rebuilding the widget tree.
- **Hardcoding Telegram input labels** ("Bot Token", "User ID") — D-54
  + Golden Rule #2. Labels = `recipe.channels.telegram.required_user_input[i].env`
  verbatim.
- **Putting the BYOK label switch as a Dart `if recipe.name == 'hermes'`** —
  D-32. Switch reads `recipe.channelProviderCompat[selectedChannel].deferred.contains('openrouter')`.
- **Auto-retry on 401.** `AuthInterceptor` already clears + emits — Phase 25
  routes to `/login`. No retry-with-refresh in MVP.
- **Calling `_baseUrl` inside dio interceptors with a stale value.** Phase 24
  D-44 — env-config is `--dart-define BASE_URL=...`, NOT runtime-mutable.
- **Adding an in-app debug menu / env switcher.** Phase 24 D-44 + golden
  rule. CONTEXT explicitly forbids.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Markdown rendering with `JetBrains Mono` code blocks | A custom regex-based renderer | `flutter_markdown_plus` (`Markdown` widget with `styleSheet: MarkdownStyleSheet(code: TextStyle(fontFamily: GoogleFonts.jetBrainsMono().fontFamily))`) + `onTapLink` callback | Markdown has 12+ syntactic edge cases (inline code, bold-inside-italics, tables, lists, fenced blocks). Hand-rolling is a months-long project. |
| Chat link safety (only allow https/http) | A character-class regex over the URL string | `final scheme = uri.scheme.toLowerCase(); if (scheme != 'https' && scheme != 'http') return;` then `launchUrl(uri, mode: LaunchMode.externalApplication)` | Standard pattern. The `Uri.parse` API does the heavy lifting; the planner only writes the allow-list check. |
| iOS LaunchScreen + Android launch_background drawable | A Flutter-side "splash widget" that fades in | Native iOS `LaunchScreen.storyboard` + Android `<style name="LaunchTheme">` drawable, holding until `runApp()` returns first frame | D-01 explicitly. A Flutter splash widget produces a double-flash (LaunchScreen → blank → splash widget → real screen). Native splash is a single hold. |
| Foreground-resume re-fetch | Custom `Timer.periodic` polling | `WidgetsBindingObserver.didChangeAppLifecycleState` → `appLifecycleProvider` → `ref.invalidateSelf()` | D-12. Polling is battery-cost + UI flicker; lifecycle hook is the standard. |
| Last-Event-Id reconnect | Custom websocket-style reconnect loop | Phase 24's `MessagesStream` wrapper (`disconnect()` preserves `_lastEventId`; `connect()` re-injects it) | Already shipped. Phase 25 only wires the `AppLifecycleState.resumed` trigger. |
| Idempotency-Key on send | Random hex string with `Random()` | `package:uuid` v4 (Phase 24 dep). Retry generates a NEW key (D-45). | Phase 24 already uses `Uuid().v4()` in spike step 4 / 7 / 8. |
| Native OAuth (Google / GitHub) | Hand-rolled `webview_flutter` flow | `google_sign_in` 7.x (Google) + `flutter_appauth` 12.x (GitHub system browser + PKCE) | Google blocks WebView OAuth as of 2024+. The native SDKs are required for App Store / Play Store policy compliance. |
| Step indicator (`● ── ○ ── ○`) | A package | A pure custom `Widget` (~30 LOC) that takes `currentStep: int` and `labels: List<String>` and renders `Row` of filled/hollow circles + 1px hairlines. CONTEXT D-23 says "~30 LOC". | A package adds dep weight for one bespoke widget. |
| Step indicator with motion / progress | Hand-rolled `AnimationController` | Static (no animation) — wizard step transitions use go_router default page transitions; the indicator just re-renders. | Locked motion contract per UI-SPEC: no custom Hero, no Lottie, no Rive. |
| Pre-flight name-collision check | Backend endpoint that returns "exists?" | Reuse `GET /v1/agents`; client filters in-memory (D-28) | Reused; backend already returns the user's agents. |
| ASCII banner cycling animation | A `StreamBuilder` over the recipes list with manual frame timing | An `AnimatedSwitcher(duration: 300ms, switchInCurve: Curves.easeInOut)` driven by a `Timer.periodic(2s)` advancing the index | UI-SPEC resolved D-Discretion to this. ~40 LOC. |
| Multiline expanding TextField | Custom `IntrinsicHeight` measurement | `TextField(maxLines: null, minLines: 1, ...)` — Material handles the rest. Cap visible at ~5 with internal scroll once exceeded. | Standard. |

**Key insight:** the new substrate Phase 25 introduces is shallow — three
external packages that are well-trodden + two cross-cutting Flutter
mechanisms (`AppLifecycleState` + scoped Riverpod). Everything else is
composition over Phase 24's already-validated foundation.

---

## Runtime State Inventory

(This section is required for rename / refactor / migration phases. Phase 25
is **mostly greenfield** — the four feature dirs under `mobile/lib/features/`
are empty and Phase 25 fills them. The amendments to REQUIREMENTS.md UI-02
and 23-CONTEXT.md D-28 are doc-edits within the same commit chain.)

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — Phase 25 introduces NO new on-device storage beyond extending `flutter_secure_storage` with per-provider BYOK key entries (`byok_key_openrouter`, `byok_key_anthropic`). Existing `session_id` Keychain entry from Phase 24 remains. **No DB migrations.** No Postgres / Redis / ChromaDB changes. | Code-only: extend `SecureStorage` wrapper with new methods (D-33). |
| Live service config | None — Phase 25 makes no n8n / pm2 / Datadog / Tailscale / Cloudflare changes. | None. |
| OS-registered state | None for the app itself. **iOS `Info.plist`** gains `LSApplicationQueriesSchemes` entry for `https` (D-46) — that's a build-time config, not a runtime registration. Android `AndroidManifest.xml` already has the `solvrlabs://oauth/github` scheme registration from Phase 24 D-15. | Add `LSApplicationQueriesSchemes` to iOS Info.plist in Wave 4 (when `url_launcher` lands). |
| Secrets / env vars | **`SESSION_ID`** test-seam env var (D-66) is read by Wave 5 spike via `--dart-define`, mirroring Phase 24 D-49. **`OPENROUTER_KEY`** for the spike's BYOK (Phase 24 D-51 carry-forward). **No new prod secrets.** Per-deploy Telegram bot tokens are user-supplied at wizard time and held in `wizardScopeProvider` until wizard close (NOT persisted) per D-50. | Wave 5 Makefile target `make screens-e2e` passes `--dart-define SESSION_ID=$SESSION_ID --dart-define OPENROUTER_KEY=$OPENROUTER_KEY` (mirror `make spike`). |
| Build artifacts / installed packages | **`pubspec.lock`** rebuilds when `flutter_markdown_plus` / `url_launcher` / `golden_toolkit` are added. **iOS `Pods` directory** rebuilds; Phase 24's iOS scaffolding already ran `pod install` (Phase 24 plan 24-07 + spike). Android Gradle artifacts rebuild on first `flutter run` after pubspec change. **`mobile/build/`** is regenerated. | Wave 1 plan task 1: `cd mobile && fvm flutter pub get && cd ios && pod install`. Mirror Phase 24's pattern. |

**The canonical question (per template):** *After every file in the repo is
updated, what runtime systems still have the old string cached, stored, or
registered?* — **Nothing.** Phase 25 is feature work, not a rename.
REQUIREMENTS.md UI-02 + 23-CONTEXT.md D-28 amendments are doc-edits whose
content invariants are tested by the verifier (verifier reads the new wording),
not by runtime state.

---

## Common Pitfalls

### Pitfall 1: `flutter_markdown` is DISCONTINUED — substitute `flutter_markdown_plus`

**What goes wrong:** Wave 1 plan adds `flutter_markdown: ^0.7.x` to pubspec.
Pubspec resolves; build succeeds. Months later, a Flutter SDK bump breaks the
package and there is no maintainer to ship the fix.

**Why it happens:** Google handed over `flutter_markdown` to community
maintainers in February 2025; the original package is now archived.
[CITED: github.com/flutter/flutter/issues/162966]

**How to avoid:** Substitute `flutter_markdown_plus` (Foresight Mobile, the
canonical successor with verified-publisher status and 140k weekly downloads).
The API is drop-in: same `Markdown` / `MarkdownBody` widgets, same
`onTapLink: (text, href, title) {}` callback, same `styleSheet` prop. CONTEXT
D-43 names `flutter_markdown` literally — the planner should add an
amendment paragraph noting the substitution and rationale, in the same
commit chain that adds the dep. **[CITED: foresightmobile.com/blog/flutter-markdown-plus-google-handover]**

**Warning signs:** `pub outdated` flags `flutter_markdown` as discontinued;
documentation links return 404 or redirect to `flutter_markdown_plus`.

### Pitfall 2: `url_launcher` `launchUrl` opens an in-app SFSafariViewController by default — use `LaunchMode.externalApplication` for D-46

**What goes wrong:** Tapping a markdown link opens an in-app browser overlay
that the user has to dismiss to return to chat. Worse, on some iOS versions
the overlay traps the URL navigation in a way that makes `https://` redirect
behavior weird.

**Why it happens:** `url_launcher`'s default mode on iOS is
`LaunchMode.platformDefault` which uses `SFSafariViewController` (an in-app
browser). D-46 wants the OS Safari/Chrome.

**How to avoid:** Always pass `mode: LaunchMode.externalApplication` when
launching markdown links. **[CITED: pub.dev/packages/url_launcher]**

```dart
Future<void> _onTapLink(String text, String? href, String title) async {
  if (href == null) return;
  final uri = Uri.tryParse(href);
  if (uri == null) return;
  final scheme = uri.scheme.toLowerCase();
  if (scheme != 'https' && scheme != 'http') return;   // D-46 allow-list
  if (await canLaunchUrl(uri)) {
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }
}
```

**Warning signs:** Test on a real device — if the link opens an
embedded-looking overlay with a "Done" button, the mode is wrong.

### Pitfall 3: `google_sign_in` 7.x is a complete API rewrite — old patterns DO NOT compile

**What goes wrong:** Planner copies `GoogleSignIn().signIn()` from Stack
Overflow, AI training data, or Phase 23 design docs. Compile error: there is
no constructor; `signIn()` no longer exists.

**Why it happens:** v7.0 (released June 2025) introduced
`GoogleSignIn.instance` + mandatory `initialize(...)` + split
authentication/authorization steps. **Authentication and authorization are
separate calls now.** **[CITED: pub.dev/packages/google_sign_in/changelog,
isaacadariku.medium.com/google-sign-in-flutter-migration-guide]**

**How to avoid:** Real-impl skeleton (verified against the 7.x docs):

```dart
// lib/core/auth/auth_service_real.dart  (NEW — illustrative)
class GoogleSignInRealService implements AuthService {
  bool _initialized = false;

  Future<void> _ensureInit() async {
    if (_initialized) return;
    await GoogleSignIn.instance.initialize(
      clientId: '<ios-client-id>.apps.googleusercontent.com',
      // serverClientId is the WEB client id (used for backend id_token validation)
      serverClientId: '<web-client-id>.apps.googleusercontent.com',
    );
    _initialized = true;
  }

  @override
  Future<Result<SessionUser>> signInWithGoogle() async {
    await _ensureInit();
    final GoogleSignInAccount? account =
        await GoogleSignIn.instance.attemptLightweightAuthentication() ??
        await GoogleSignIn.instance.authenticate();
    if (account == null) return Result.err(ApiError.cancelled());
    final auth = account.authentication;
    final idToken = auth.idToken;
    if (idToken == null) return Result.err(ApiError.providerError('no id_token'));
    return _api.authGoogleMobile(idToken: idToken);
  }
}
```

**Warning signs:** "No such method 'signIn'", "GoogleSignIn is not a class".

**Mitigation in this phase:** D-66's `AuthService` interface + test impl
(`--dart-define SESSION_ID`) absorbs the risk for waves 1–4. Wave 5 (or a
Wave 0 spike before Wave 1 seals) verifies the real path on iOS Simulator +
Android Emulator. Native config (Info.plist `CFBundleURLTypes` for the
reverse-client-id, `GoogleService-Info.plist` for iOS, OAuth client setup in
Google Cloud Console) is a build-time concern; document the required external
setup in a `mobile/README.md` section.

### Pitfall 4: `flutter_appauth` requires Android intent-filter + iOS URL types — already shipped in Phase 24

**What goes wrong:** GitHub OAuth callback redirect lands in the OS browser
with a "Page can't be opened" because the redirect URI scheme `solvrlabs://`
isn't registered as a listener for the app.

**Why it happens:** AppAuth uses a custom URI scheme to receive the
authorization-code callback. Both iOS (`Info.plist` `CFBundleURLTypes`) and
Android (`AndroidManifest.xml` `intent-filter`) must register the scheme.

**Mitigation:** Phase 24 D-04 + D-15 already shipped the registration. The
24-RESEARCH file at lines 1144-1166 contains the verbatim Info.plist and
AndroidManifest entries. **Verify** at Wave 1 plan time that those entries
still exist — `git log` can confirm via the Phase 24 plan-07 commit.

### Pitfall 5: `flutter_secure_storage` on iOS Simulator can lose values cross-restart — flagged in Phase 24, materializes in Phase 25

**What goes wrong:** User signs in via OAuth real path; `session_id` is
written to Keychain. User force-quits the iOS Simulator app and relaunches.
On next read, `flutter_secure_storage` returns null. Cold-start probe gets a
401, app routes to `/login` again — looks like a session-persistence bug.

**Why it happens:** iOS Simulator's Keychain implementation is not as durable
across simulator restarts as the device's. **[CITED: Phase 24 RESEARCH Pitfall #4]**

**How to avoid in Phase 25:** Wave 5 spike runs against either a physical iOS
device or the Android Emulator (whose EncryptedSharedPreferences is
device-equivalent on the emulator). For iOS Simulator validation, document
the caveat in `spikes/flutter-screens-roundtrip.md` ("Tested on iOS Simulator
— Keychain persistence not verified across simulator force-quit; physical
device test required for production claim").

### Pitfall 6: `golden_toolkit` requires `flutter_test_config.dart` + `loadAppFonts()` to render the right fonts in snapshots

**What goes wrong:** `golden_toolkit` snapshot tests render with Flutter's
default test font (Ahem) instead of Inter / JetBrains Mono. The snapshot
visually diverges from the running app; reviewing the snapshot is useless.

**Why it happens:** `flutter test` defaults to Ahem for hermetic snapshot
output. `loadAppFonts()` from `golden_toolkit` swaps in the real fonts but
must be invoked from a test config file.

**How to avoid:** Add `mobile/test/flutter_test_config.dart`:

```dart
import 'dart:async';
import 'package:golden_toolkit/golden_toolkit.dart';

Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  await loadAppFonts();
  await testMain();
}
```

**[CITED: pub.dev/documentation/golden_toolkit/latest/golden_toolkit/loadAppFonts.html]**

`google_fonts` runtime-fetched fonts also need pre-registration. The Wave 1
plan should add a one-time `await GoogleFonts.pendingFonts([GoogleFonts.inter(), GoogleFonts.jetBrainsMono()])` in `loadAppFonts()` body OR bundle the .ttf files in `assets/` and declare them in `pubspec.yaml`'s `flutter.fonts` block. Bundling is more deterministic for CI.

**Warning signs:** Snapshot diff reviews show wide square boxes instead of
real glyphs.

### Pitfall 7: `WidgetTester.handleAppLifecycleStateChanged` is the integration_test API for kill-and-relaunch (D-65)

**What goes wrong:** Wave 5 spike tries to simulate "kill app, relaunch" via
some made-up call (`tester.restartApp()` doesn't exist; `tester.binding.reassembleApplication()` simulates hot-reload, not cold-start).

**Why it happens:** Flutter's integration_test doesn't have a literal "kill +
relaunch" primitive. The closest contract for "the app went to background,
came back, and re-fetched its state from the server" is to send
`AppLifecycleState.paused` then `AppLifecycleState.detached` then
`AppLifecycleState.resumed` and rebuild the widget tree.

**How to avoid:** Mirror the Phase 24 spike's `Step 8` lifecycle-disconnect
pattern. For UI-04's "kill + relaunch + history visible" assertion, the
acceptable proof is:

1. Tear down the chat widget (pop the route).
2. Send `await tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused)`
   then `.detached` then `.resumed`.
3. Re-pump the app with the SAME `secureStorage` so the stored
   `session_id` is still present.
4. Re-navigate to `/chat/<id>`.
5. Assert the messages from the prior session are visible (they came from
   `GET /messages`, not from any local cache — that's what proves persistence).

The Wave 5 spike artifact `spikes/flutter-screens-roundtrip.md` should
explicitly note: "kill-and-relaunch simulated via lifecycle-state pump +
widget-tree rebuild + secure-storage persistence; full process kill verified
manually by force-quitting the simulator/emulator app and relaunching." This
matches the Phase 24 spike's mix of programmatic + manual verification.

**[CITED: api.flutter.dev/flutter/flutter_test/WidgetTester/binding.html]**

### Pitfall 8: Pull-to-refresh + foreground-resume re-fetch can double-fire on warm resume

**What goes wrong:** User pulls to refresh; mid-fetch, they background the
app for a second and come back. The lifecycle observer fires
`AppLifecycleState.resumed` → invalidates the provider → triggers ANOTHER
fetch while the pull-to-refresh fetch is still inflight. Two concurrent
fetches; one wins arbitrarily; UI flickers.

**Why it happens:** Both gestures (pull) and lifecycle events trigger the
same provider invalidation.

**How to avoid:** Either (a) guard the lifecycle re-fetch with "only if last
fetch was > 30s ago", or (b) tag fetches with a `CancelToken` and have the
provider cancel any inflight request on re-invalidation. Option (b) matches
Phase 24 D-41 (every dio method accepts CancelToken) and is the safer pattern.

```dart
@riverpod
class AgentsList extends _$AgentsList {
  CancelToken? _cancel;
  @override
  Future<List<AgentSummary>> build() async {
    _cancel?.cancel();
    final cancel = _cancel = CancelToken();
    ref.onDispose(() => cancel.cancel());
    // ... rest as before
  }
}
```

**Warning signs:** UI flickers between two lists during quick foreground-flip.

### Pitfall 9: Message dedup by `inappMessageId` requires the SSE event payload to actually carry it — verify in Wave 4

**What goes wrong:** Phase 23 D-08 says the SSE-delivered content + the
`GET /messages` row are byte-identical. But the SSE event ALSO needs the
`inapp_message_id` field for dedup to work. The Phase 24 spike step 5
confirmed `payload.content` matches; it did NOT explicitly assert that
`payload.inapp_message_id` (or the equivalent envelope field) is present and
matches the history row.

**Why it happens:** Phase 22c.3-07 outbox publishes a JSON envelope `{seq,
kind, payload, correlation_id, ts}`. The `payload` for `kind=inapp_outbound`
contains content + source + captured_at — and per Plan 22c.3-04
`InappOutboundPayload`, NO `inapp_message_id` field is declared.

**How to avoid:** Wave 4 (Chat) plan task should empirically verify what the
SSE payload actually contains for `inapp_outbound` events. If the
`inapp_message_id` is absent, dedup must key on `seq` (always present per
D-34) cross-correlated to history rows — OR the planner adds a
**Wave 0 backend amendment** to extend `InappOutboundPayload` with
`inapp_message_id`. Either way, Wave 4 must NOT assume the field is there
without a grep against the actual envelope.

**Suggested validation step:** spike-style probe at Wave 4 plan-write time
— `curl -N http://localhost:8000/v1/agents/<id>/messages/stream` while a
test message is sent in another terminal; capture the actual envelope shape
into the plan's `<read_first>` block.

### Pitfall 10: Wizard "scoped Riverpod across go_router route group" needs explicit ProviderScope override OR a manually-cleared family provider

**What goes wrong:** D-21 wants `wizardScopeProvider` to live ONLY for the
duration of the wizard (steps 1, 2, 2.5, 3) and be cleared on close (D-31).
A naive `Provider` is app-wide; a naive `Provider.family` keyed by something
arbitrary leaks state.

**Why it happens:** Riverpod's "scope" concept is `ProviderScope` widget
boundaries. `go_router` does NOT automatically create ProviderScope per
route group.

**How to avoid:** Two viable patterns:

- **Pattern A (suggested):** A regular `StateNotifierProvider` for the
  wizard, manually `ref.invalidate(wizardScopeProvider)` in the wizard's
  `dispose()` AND when the user confirms the cancel ConfirmDialog (D-31).
  Single-instance; explicitly cleared. Works because there's only one
  wizard at a time (no parallel wizards).
- **Pattern B:** Wrap the wizard's `ShellRoute` in `go_router` with a
  `ProviderScope` widget that has `overrides: [wizardScopeProvider.overrideWith(...)]`,
  scoped to that branch. More elegant but requires understanding
  `ShellRoute` + `ProviderScope` overrides — pricier at planning time.

**[CITED: riverpod.dev/docs/concepts/scopes]**

The planner should default to **Pattern A**; document the chosen pattern in
the Wave 3 plan's `<read_first>` block.

---

## Code Examples

### `flutter_markdown_plus` with JetBrains Mono code blocks + safe link tap

```dart
// lib/features/chat/bubble_widget.dart  (NEW — illustrative)
// Source: pub.dev/packages/flutter_markdown_plus + url_launcher
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:url_launcher/url_launcher.dart';

class AssistantBubble extends StatelessWidget {
  final String content;
  const AssistantBubble({required this.content, super.key});

  Future<void> _onTapLink(String text, String? href, String title) async {
    if (href == null) return;
    final uri = Uri.tryParse(href);
    if (uri == null) return;
    final scheme = uri.scheme.toLowerCase();
    if (scheme != 'https' && scheme != 'http') return;   // D-46 allow-list
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }

  @override
  Widget build(BuildContext context) {
    final mono = GoogleFonts.jetBrainsMono(
      fontSize: 12, color: const Color(0xFF1F1F1F),
    );
    return MarkdownBody(
      data: content,
      onTapLink: _onTapLink,
      selectable: true,                                // D-48 native selection
      styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
        code: mono,                                    // inline code
        codeblockDecoration: BoxDecoration(            // fenced ``` blocks
          color: const Color(0xFFFFFFFF),
          border: Border.all(color: const Color(0xFFDEDEDA)),
        ),
        codeblockPadding: const EdgeInsets.all(8),
        // Markdown bold/italics inherit from theme. NO image rendering.
      ),
      imageBuilder: (uri, title, alt) => const SizedBox.shrink(),  // D-43: no images
    );
  }
}
```

### `WidgetsBindingObserver` + `appLifecycleProvider` (single source of resume events)

```dart
// lib/core/lifecycle/app_lifecycle_observer.dart  (NEW)
// Source: api.flutter.dev/flutter/widgets/WidgetsBindingObserver-class.html
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final appLifecycleProvider =
    StateNotifierProvider<AppLifecycleNotifier, AppLifecycleState>(
        (ref) => AppLifecycleNotifier());

class AppLifecycleNotifier extends StateNotifier<AppLifecycleState>
    with WidgetsBindingObserver {
  AppLifecycleNotifier() : super(AppLifecycleState.resumed) {
    WidgetsBinding.instance.addObserver(this);
  }
  @override
  void didChangeAppLifecycleState(AppLifecycleState s) => state = s;
  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }
}
```

Then in `app.dart`:

```dart
// Ensure the lifecycle notifier is created at app start so it observes from boot.
class _SolvrLabsAppState extends ConsumerState<SolvrLabsApp> {
  @override
  Widget build(BuildContext context) {
    ref.watch(appLifecycleProvider);   // primes the notifier
    // ... existing MaterialApp.router
  }
}
```

### Pre-flight name-collision dialog (D-28)

```dart
// lib/features/new_agent/name_deploy_step.dart  (NEW — illustrative)
// Mirrors web playground-form's behavior + D-28 wording
final agents = await api.agentsList();
final existing = agents.match(
  (list) => list.firstWhereOrNull((a) => a.name == scope.agentName),
  (_) => null,
);
if (existing != null) {
  final result = await ConfirmDialog.show(
    context,
    title: 'Name "${scope.agentName}" already used',
    body: 'Existing agent: ${existing.recipeName} + ${existing.model}. '
          'Re-deploy replaces it; rename keeps both.',
    cancelLabel: 'Cancel',
    confirmLabel: 'Re-deploy',
    destructive: true,
    thirdButtonLabel: 'Rename',
  );
  switch (result) {
    case ConfirmDialogResult.cancel: return;
    case ConfirmDialogResult.third:  nameFieldFocus.requestFocus(); return;
    case ConfirmDialogResult.confirm: break;   // proceed with UPSERT
  }
}
```

### Dynamic Telegram channel-input fields (D-54 — mirror of web playground-form lines 638-689)

```dart
// lib/features/new_agent/name_deploy_step.dart  (NEW — illustrative)
// recipeDetail comes from a NEW ApiClient.recipeDetail(name) call (Wave 3)
final inputs = recipeDetail.channels?['telegram']?['required_user_input'] ?? const [];
return Column(children: [
  for (final input in inputs)
    Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(input['env'] as String,
             style: Theme.of(context).textTheme.titleSmall),       // label = `env` verbatim
        const SizedBox(height: 4),
        TextField(
          obscureText: input['secret'] == true,
          autocorrect: false,
          enableSuggestions: false,
          decoration: InputDecoration(
            hintText: input['secret'] == true ? '••••••••' : '...',
          ),
          onChanged: (v) => ref.read(wizardScopeProvider.notifier)
                              .setTelegramInput(input['env'] as String, v),
        ),
        const SizedBox(height: 4),
        Wrap(children: [
          Text(input['hint'] as String? ?? ''),
          if (input['hint_url'] != null)
            TextButton(
              onPressed: () => _openExternal(input['hint_url'] as String),
              child: const Text('get one here'),
            ),
        ]),
      ]),
    ),
]);
```

### Wave 5 spike harness extension (mirror of `spike_api_roundtrip_test.dart` shape)

```dart
// mobile/integration_test/screens_e2e_test.dart  (NEW — Wave 5)
// Drives WidgetTester through Login → Dashboard → Wizard → Chat → kill+relaunch.
// Mirrors mobile/integration_test/spike_api_roundtrip_test.dart structure.
import 'package:agent_playground/app.dart';
import 'package:agent_playground/core/auth/auth_service.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'spike_helpers.dart';                                      // Phase 24 helpers

const _baseUrl = String.fromEnvironment('BASE_URL');
const _sessionId = String.fromEnvironment('SESSION_ID');
const _byokKey = String.fromEnvironment('OPENROUTER_KEY');

class TestAuthService implements AuthService {
  TestAuthService(this._sessionId);
  final String _sessionId;
  @override
  Future<Result<SessionUser>> signInWithGoogle() async {
    // Inject the pre-collected SESSION_ID via secureStorage and return a fake user.
    return Result.ok(SessionUser(id: '...', email: 'spike@test', /* ... */));
  }
  // ... github + signOut similar
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('UI-04 end-to-end: login → dashboard → wizard → chat → kill+relaunch',
      (tester) async {
    expect(_baseUrl, isNotEmpty);
    expect(_sessionId, isNotEmpty);
    expect(_byokKey, isNotEmpty);

    // Pre-seed secureStorage so cold-start /v1/users/me succeeds.
    await tester.runAsync(() async {
      // ... set ap_session via SecureStorage backend before runApp
    });

    // === Step 1: boot → /dashboard
    await tester.pumpWidget(ProviderScope(
      overrides: [authServiceProvider.overrideWithValue(TestAuthService(_sessionId))],
      child: const SolvrLabsApp(),
    ));
    await tester.pumpAndSettle(const Duration(seconds: 5));
    expect(find.text('No agents yet').or(find.byType(AgentRow)).hitTestable(), findsAtLeastNWidgets(1));

    // === Step 2: tap FAB → wizard
    await tester.tap(find.byIcon(Icons.add));
    await tester.pumpAndSettle();

    // === Step 3: pick recipe (first card)
    await tester.tap(find.byType(RecipeCard).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Next'));
    await tester.pumpAndSettle();

    // === Step 4: pick model (push picker, tap first row)
    await tester.tap(find.text('Pick a model'));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(ModelRow).first);
    await tester.pumpAndSettle();

    // === Step 5: enter BYOK key
    await tester.enterText(find.byKey(const Key('byok_key_input')), _byokKey);
    await tester.tap(find.text('Next'));
    await tester.pumpAndSettle();

    // === Step 6: enter agent name; toggle Telegram OFF; Deploy
    final agentName = 'screens-e2e-${DateTime.now().millisecondsSinceEpoch}';
    await tester.enterText(find.byKey(const Key('agent_name_input')), agentName);
    await tester.tap(find.text('Deploy'));
    await tester.pumpAndSettle(const Duration(minutes: 1));   // smoke + start can take ~30-45s

    // === Step 7: Chat opened; send "hi"
    await tester.enterText(find.byKey(const Key('chat_input')), 'hi');
    await tester.tap(find.byIcon(Icons.send));
    await waitForBubble(tester, role: 'assistant',
                         timeout: const Duration(minutes: 2));

    // === Step 8: simulate kill + relaunch
    await tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    await tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.detached);
    await tester.pumpWidget(const SizedBox.shrink());          // tear down
    await tester.pumpAndSettle();
    await tester.pumpWidget(ProviderScope(
      overrides: [authServiceProvider.overrideWithValue(TestAuthService(_sessionId))],
      child: const SolvrLabsApp(),
    ));
    await tester.pumpAndSettle(const Duration(seconds: 5));

    // === Step 9: navigate back to chat; assert history persists
    await tester.tap(find.text(agentName));   // dashboard row
    await tester.pumpAndSettle();
    expect(find.text('hi'), findsOneWidget);
    expect(find.byType(AssistantBubble), findsAtLeastNWidgets(1));
  }, timeout: const Timeout(Duration(minutes: 15)));
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `flutter_markdown` (Google) | `flutter_markdown_plus` (Foresight Mobile) | Feb 2025 | Discontinue + community handover. Drop-in API. |
| `google_sign_in` 6.x with `signIn()` | `google_sign_in` 7.x with `GoogleSignIn.instance.initialize()` + `attemptLightweightAuthentication()` | June 2025 | Major API rewrite; old patterns don't compile. |
| In-app `webview_flutter` for OAuth | `flutter_appauth` (system browser + PKCE) for GitHub; `google_sign_in` (native) for Google | Pre-2024 deprecated | Google blocks WebView OAuth as of 2024+ for new app registrations. |
| `golden_toolkit` (eBay) | `alchemist` (VeryGoodVentures / Betterment) | 2023+ | eBay archived their fork; community moved to Alchemist. CONTEXT D-62 keeps `golden_toolkit` (still works); planner notes the maintenance signal but doesn't switch in this phase. |
| Email/password mobile auth | OAuth-only (Google + GitHub) | Phase 22c-oauth-google | Aligned with PROJECT.md auth surface. |

**Deprecated / outdated:**
- `flutter_markdown` package (Google) — discontinued; substitute `flutter_markdown_plus`.
- `google_sign_in` 6.x patterns — replaced by 7.x; do not copy from older AI training data verbatim.
- `nhooyr.io/websocket` (server-side reference, not used here) — not relevant to mobile.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The SSE-delivered `inapp_outbound` event payload contains `inapp_message_id` (or an equivalent dedup key correlating to `GET /messages` history rows). | Mechanism §9 + Pitfall #9 | MEDIUM — if absent, Wave 4 must use `seq` as dedup key (still works since `seq` is monotonic per Phase 22c.3 D-09/D-34) OR the planner amends the backend `InappOutboundPayload` to include `inapp_message_id`. **[ASSUMED]** — verified against Phase 22c.3-04 model file: `InappOutboundPayload` has `content + source + captured_at` only. Mitigation suggested in Pitfall #9. |
| A2 | `flutter_markdown_plus` API is byte-drop-in vs `flutter_markdown`. | Pitfall #1 | LOW — Foresight Mobile's announcement explicitly states "drop-in replacement"; `MarkdownBody` widget signature is identical. **[CITED: foresightmobile.com/blog/flutter-markdown-plus-google-handover]** |
| A3 | iOS Simulator + Android Emulator can both run the Wave 5 spike. | Pitfall #5 + Pitfall #7 | LOW — Phase 24 spike already ran on iOS Simulator (iPhone 16e iOS 26.4.1). Android Emulator has the same `flutter test integration_test/` invocation contract. The Keychain caveat applies to iOS Simulator only. **[VERIFIED via Phase 24 spike artifact]** |
| A4 | The web playground-form's `recipe.channel_provider_compat[selectedChannel].deferred` is a list of provider names (lowercase strings). | Mechanism §7 | LOW — model verified in `api_server/src/api_server/models/recipes.py:67` `channel_provider_compat: dict[str, dict[str, list[str]]]` — exact shape `{channel_id: {supported: [...], deferred: [...]}}`. **[VERIFIED via api_server source]** |
| A5 | `flutter_appauth` 12.x + Phase 24's `solvrlabs://oauth/github` scheme registration still works against current iOS (26.x) and Android (14+). | Pitfall #4 | LOW — Phase 24 spike successfully shipped this; no Flutter SDK changes since the spike artifact (2026-05-02). **[VERIFIED via 24-RESEARCH lines 1144-1166]** |
| A6 | `WidgetTester.binding.handleAppLifecycleStateChanged` is the canonical API for Wave 5's "kill + relaunch" simulation. | Pitfall #7 | LOW — Flutter's integration_test docs document this method exactly. **[CITED: api.flutter.dev/flutter/flutter_test/WidgetTester]** |
| A7 | The new `flutter_markdown_plus` major version (1.0.x as of 2026-04) is compatible with Flutter 3.41.0 + Dart 3.9. | Standard Stack | LOW — pubspec compatibility floor is 3.22 / 3.4 per the changelog. **[CITED: pub.dev/packages/flutter_markdown_plus/versions/1.0.6/changelog]** |
| A8 | Restart from Chat (D-49) can default to `channel='inapp'` only if extended `GET /v1/agents` doesn't return per-agent channel set; this is acceptable as a planner-deferred TODO. | Mechanism §8 | LOW — D-49 explicitly captures this as a deferred TODO. The MVP demo flow doesn't require multi-channel restart. |

---

## Open Questions

1. **Does the SSE `inapp_outbound` envelope contain `inapp_message_id`?**
   - What we know: Phase 22c.3-04's `InappOutboundPayload` declares
     `content + source + captured_at`. Phase 23 D-08 says cross-channel
     content is byte-identical. The `seq` field is in the envelope (D-34).
   - What's unclear: whether `inapp_message_id` is in the payload or the
     envelope. If absent, Wave 4 dedup must key on `seq`.
   - Recommendation: Wave 4 plan task 1 includes a curl-spike against the
     live SSE endpoint to capture an actual envelope shape. Document the
     observed shape in the plan's `<read_first>` block. If
     `inapp_message_id` is absent, key dedup on `seq` and document the
     decision; do NOT amend the backend in Phase 25 (out of scope).

2. **Does the existing `GET /v1/agents` response include enough info for D-49's multi-channel Restart?**
   - What we know: 23-CONTEXT D-10 says `list_agents()` was extended with
     `status` + `last_activity` only. Per-agent channel set is NOT
     mentioned.
   - What's unclear: whether `agent_containers` rows enumerated in the
     extended response carry channel info, or whether mobile must guess.
   - Recommendation: Wave 2 plan task includes a curl spike of `GET /v1/agents`
     to capture actual response shape. If channel set is absent, D-49
     Restart defaults to `inapp` only; flag a Phase 25-or-later TODO for
     extending the endpoint.

3. **Does `recipe.channels.<id>.required_user_input` shape vary across the 5 recipes?**
   - What we know: openclaw + hermes both expose `required_user_input` as
     a list of `{env, secret, hint, hint_url?}` dicts. nullclaw + nanobot
     + zeroclaw don't have telegram channels (only inapp), so they don't
     trip this code path.
   - What's unclear: whether future recipes might use a different shape.
   - Recommendation: Wave 3 plan task uses a permissive parser (treat
     missing keys as null) and renders only what it has. Don't validate
     the shape strictly; surface unknowns as plain-text hints.

4. **Does `golden_toolkit`'s `loadAppFonts` correctly load `google_fonts` runtime-fetched fonts?**
   - What we know: `loadAppFonts` loads pubspec-declared fonts; `google_fonts` runtime-fetches.
   - What's unclear: whether the test harness will catch the right fonts at all.
   - Recommendation: Wave 1 plan task creating `flutter_test_config.dart`
     should include a smoke snapshot test asserting "rendered text is NOT
     in the Ahem fallback font" (a 1-line assertion that the pixel
     output of "S" is non-trivial). If snapshots show square boxes,
     bundle `Inter-Regular.ttf` + `JetBrainsMono-Regular.ttf` as
     `assets/fonts/` instead.

5. **Does CONTEXT's "REPLACE wizard" route for Deploy success (D-60) play nicely with go_router 17.x?**
   - What we know: D-60 says use `go_router.go('/chat/<id>')`. go_router's
     `go()` does a clean replace.
   - What's unclear: whether the wizard's nested route stack (`/new-agent/clone`
     → `/new-agent/model` → `/new-agent/name-deploy`) is fully torn down
     on `go()` to `/chat/...`, or whether the back stack accumulates.
   - Recommendation: Wave 3 plan task includes a Wave-3 widget test
     asserting "after Deploy success, `Navigator.canPop` is false" — i.e.,
     back from Chat goes to Dashboard, not back into the wizard.

---

## Environment Availability

(External dependencies for Wave 5; Wave 1–4 are pure Flutter unit/widget
tests with `http_mock_adapter`.)

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Flutter SDK | All waves | ✓ (Phase 24 pinned via FVM 3.41.0) | 3.41.0 | — |
| Xcode + iOS Simulator | Wave 5 spike (iOS path) | ✓ (Phase 24 spike ran on iPhone 16e iOS 26.4.1) | 26.4 | Skip iOS path; document as deferred |
| Android Studio + Emulator | Wave 5 spike (Android path) | ⚠ (planner-verify) | — | Skip Android path; document as deferred |
| Local `api_server` (Phase 23 backend) | Wave 5 spike | ✓ (Phase 24 spike used it) | post-22c.3-15 | Spike fails fast with curl pre-flight (mirrors `make spike`) |
| Postgres + Redis (via deploy compose) | Wave 5 spike (transitive) | ✓ (Phase 24 used `deploy/docker-compose.{prod,local}.yml`) | — | Spike fails fast |
| OpenRouter network access + valid `OPENROUTER_KEY` | Wave 5 spike (smoke gate) | ✓ (Phase 24 used it) | — | None — without a real LLM call, smoke can't pass |
| Real Google OAuth client (Web client + iOS client + Android client in Google Cloud Console) | Real-OAuth path verification (post-Wave 5 manual) | ⚠ (planner-verify with user) | — | Wave 5 uses test impl (`--dart-define SESSION_ID`); real-path validated manually only, documented in spike artifact |
| Real GitHub OAuth client | Real-OAuth path verification (post-Wave 5 manual) | ⚠ (planner-verify with user; Phase 22c-oauth-google had one) | — | Same as above |

**Missing dependencies with no fallback:**
- None blocking Phase 25's exit gate. The Wave 5 spike's test impl absorbs
  the unmockable native OAuth layer.

**Missing dependencies with fallback:**
- Real OAuth on iOS / Android: Wave 5 uses test impl; real path is a
  manual smoke after Wave 5, not a phase-exit blocker. Documented in
  `spikes/flutter-screens-roundtrip.md`.
- Android Emulator: if not booted at Wave 5 time, document iOS-only validation.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `flutter_test` (unit / widget) + `integration_test` (Wave 5 spike) — both bundled with Flutter SDK; carry-forward from Phase 24 |
| Config file | `mobile/analysis_options.yaml` (lints) + `mobile/pubspec.yaml` (test deps) + **NEW** `mobile/test/flutter_test_config.dart` (Wave 1 — `loadAppFonts()` for golden tests) |
| Quick run command | `cd mobile && fvm flutter analyze && fvm flutter test` |
| Full suite command | `cd mobile && fvm flutter analyze && fvm flutter test && make screens-e2e BASE_URL=... SESSION_ID=... OPENROUTER_KEY=...` |
| Estimated runtime | ~30s unit suite; ~3–5 min `make screens-e2e` against live local backend (mirrors Phase 24 spike) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| **UI-01** | Dashboard renders agents from `GET /v1/agents`; status dot reflects agent.status; pull-to-refresh re-fetches; empty state shows ASCII banner + Deploy button. | widget + integration | `fvm flutter test test/features/dashboard/` (mocks `ApiClient` via `http_mock_adapter`) + `make screens-e2e` (live) | ❌ Wave 0 |
| UI-01 (lifecycle) | Foreground-resume re-fetches agents (D-12). | widget | `fvm flutter test test/features/dashboard/dashboard_lifecycle_test.dart` (sends `AppLifecycleState.resumed` and asserts second fetch fired) | ❌ Wave 0 |
| **UI-02** *(amended via AMD-01)* | Wizard 3 steps; recipe + model + name validated; Deploy POSTs `/runs` then `/start` (inapp); Telegram toggle adds N×`/start`; failure paths render correctly. | widget + integration | `fvm flutter test test/features/new_agent/` + `make screens-e2e` (covers happy path with Telegram OFF) | ❌ Wave 0 |
| UI-02 (D-32 BYOK label-swap) | BYOK label flips to "Anthropic API Key" when `recipe.channel_provider_compat[selectedChannel].deferred` includes `'openrouter'`. | widget | `fvm flutter test test/features/new_agent/byok_label_test.dart` (uses two mock recipes — one with deferred, one without) | ❌ Wave 0 |
| UI-02 (D-54 dynamic Telegram fields) | Telegram fields render with labels = `env` value verbatim, types from `secret`, hints from `hint`+`hint_url`. NEVER hardcoded. | widget + grep | `fvm flutter test test/features/new_agent/telegram_inputs_test.dart` + `! grep -rn '"TELEGRAM_BOT_TOKEN"' lib/` (proves no hardcoded labels) | ❌ Wave 0 |
| UI-02 (D-28 collision dialog) | Pre-flight `GET /v1/agents`; on collision, show 3-button dialog. | widget | `fvm flutter test test/features/new_agent/collision_dialog_test.dart` | ❌ Wave 0 |
| UI-02 (D-56 multi-channel) | Sequential `runs` + `start(inapp)` + optional `start(telegram)`. | widget | `fvm flutter test test/features/new_agent/multi_channel_deploy_test.dart` (mocks 3 dio responses, asserts call sequence + bodies) | ❌ Wave 0 |
| UI-02 (D-30 smoke fail) | verdict ≠ PASS → inline red-bordered card with `verdict.detail` + Retry/Edit buttons. | widget | covered in `multi_channel_deploy_test.dart` | ❌ Wave 0 |
| **UI-03** | Chat history loads ASC oldest→newest; bubbles render markdown; Send POSTs with Idempotency-Key; SSE delivers; failed bubbles render red border + Retry sheet. | widget + integration | `fvm flutter test test/features/chat/` + `make screens-e2e` | ❌ Wave 0 |
| UI-03 (D-36 dedup) | Map keyed by `inappMessageId`; SSE event + history row dedupe. | widget | `fvm flutter test test/features/chat/dedup_test.dart` (in-memory simulation) | ❌ Wave 0 |
| UI-03 (D-41 optimistic) | User bubble inserted with idemKey local-id; flips to failed on POST error. | widget | `fvm flutter test test/features/chat/optimistic_send_test.dart` (mocks dio failure) | ❌ Wave 0 |
| UI-03 (D-43 markdown) | Code fences render in JetBrains Mono; images stripped (D-43); links go through `url_launcher` only on https/http (D-46). | widget + golden | `fvm flutter test test/features/chat/markdown_render_test.dart` (verifies code-fence font family + image-stripped) | ❌ Wave 0 |
| UI-03 (D-45 retry-fresh-key) | Tap Retry on failed bubble → NEW UUID; existing failed bubble preserved. | widget | `fvm flutter test test/features/chat/retry_test.dart` | ❌ Wave 0 |
| UI-03 (D-46 link safety) | Markdown links: only https + http reach `url_launcher`. | widget | `fvm flutter test test/features/chat/link_safety_test.dart` (asserts `javascript:` / `data:` / `mailto:` taps result in NO call to `launchUrl`) | ❌ Wave 0 |
| UI-03 (D-52 SSE reconnect-on-resume) | `AppLifecycleState.resumed` triggers `MessagesStream.disconnect()` + `connect()` (preserves Last-Event-Id). | widget | `fvm flutter test test/features/chat/resume_reconnect_test.dart` | ❌ Wave 0 |
| **UI-04** | End-to-end demo flow on real device/simulator. | **integration (Wave 5 spike — load-bearing)** | `cd mobile && make screens-e2e BASE_URL=$BASE_URL SESSION_ID=$SESSION_ID OPENROUTER_KEY=$OPENROUTER_KEY` | ❌ Wave 0 (Wave 5 ships the file) |
| UI-04 (D-65 kill-and-relaunch) | History persists across simulated kill+relaunch via `WidgetTester.handleAppLifecycleStateChanged` + widget tear-down + re-pump. | integration | covered in `screens_e2e_test.dart` step 8 | ❌ Wave 0 |
| Cross-cutting (D-62 a11y) | Snapshots at textScaleFactor 1.0 / 1.5 / 2.0 for: Login, Dashboard empty, Dashboard populated, Chat with markdown reply. | golden | `fvm flutter test test/golden/` | ❌ Wave 0 |
| Cross-cutting (auth) | 401 anywhere clears session + routes to /login + shows banner. | widget | `fvm flutter test test/core/auth/auth_event_bus_test.dart` (extends Phase 24's auth bus) | ❌ Wave 0 |
| Cross-cutting (cold-start) | `/v1/users/me` 200 → `/dashboard`; 401 → `/login`; 5xx/timeout → retry screen. | widget | `fvm flutter test test/main_boot_test.dart` (mocks 3 ApiClient responses) | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `cd mobile && fvm flutter analyze && fvm flutter test`
  (~30s; covers all unit/widget/golden tests via `flutter_test_config.dart`).
- **Per wave merge:** `cd mobile && fvm flutter analyze && fvm flutter test`
  (full unit + widget + golden suite). Wave 5 additionally runs `make screens-e2e`.
- **Phase gate:** All unit suite green AND `make screens-e2e` green AND
  `spikes/flutter-screens-roundtrip.md` recorded with `verdict: PASS` AND
  AMD-01 + AMD-02 amendments landed in commit chain (verifier matches the
  new wording verbatim).

### Wave 0 Gaps

Wave 0 in Phase 25 is a planning-time diligence gate, not a code wave per se.
It owns:

- [ ] **Real-OAuth spike (suggested)**: 30-min spike on iOS Simulator + Android Emulator
  validating `google_sign_in` 7.x `instance.initialize()` →
  `attemptLightweightAuthentication()` flow returns a real `id_token` AND
  `flutter_appauth` GitHub flow round-trips through Safari/Chrome to the
  `solvrlabs://oauth/github` callback. Output: `spikes/phase-25-oauth-real.md`
  with PASS/FAIL marker. **[Mitigation:** D-66 test-seam absorbs the risk for
  Wave 1–4; this spike de-risks Wave 5 manual smoke.**]**
- [ ] **`flutter_markdown_plus` substitution decision**: confirmed at
  Wave 1 plan-write time. Document substitution as Phase 25 amendment AMD-03
  (planner adds) in CONTEXT.md.
- [ ] **`mobile/test/flutter_test_config.dart`** — `loadAppFonts()` for
  golden_toolkit (Wave 1 owns the file creation + the smoke assertion).
- [ ] **Test infrastructure** — Wave 1 plan adds:
  - `mobile/test/features/{login,dashboard,new_agent,chat}/` directories
  - `mobile/test/golden/` directory
  - `mobile/test/shared/` for shared widget unit tests (D-61)
  - `mobile/integration_test/screens_e2e_test.dart` (Wave 5 owns the body; Wave 1 stubs the file with a `skip: true` placeholder)
- [ ] **`mobile/Makefile` `screens-e2e` target** — Wave 1 stubs (mirroring `make spike` shape); Wave 5 wires the actual test file.

If no gaps: not applicable — Phase 25 introduces 4 new screens + 9 new
shared widgets, all of which need test files.

---

## Security Domain

(Per project config: `security_enforcement` is not explicitly disabled —
the `.planning/config.json` has no `security_enforcement` key; treating as
enabled. Phase 25 is mobile UI work; the security surface is small but
non-zero.)

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | YES | OAuth via `google_sign_in` 7.x + `flutter_appauth` 12.x — native SDKs, no hand-rolled flows. Backend mints session (Phase 22c-oauth-google substrate). |
| V3 Session Management | YES | `ap_session` cookie via `Cookie` header (Phase 23 D-17); `flutter_secure_storage` for `session_id` persistence; 401 clears storage + routes to /login (D-03). |
| V4 Access Control | YES (transitive) | Mobile relies on `require_user` middleware server-side. Mobile-side surface = "401 → clear + /login" pattern. |
| V5 Input Validation | YES | Agent name regex `^[a-z0-9][a-z0-9_-]*$` + length cap mirrored client-side from `runs.py:_validate_name` (D-27). BYOK key length not validated client-side (server returns 401 if invalid; D-Discretion). |
| V6 Cryptography | YES (transitive) | `flutter_secure_storage` uses iOS Keychain (`kSecAttrAccessibleAfterFirstUnlock`) + Android EncryptedSharedPreferences. Phase 24 D-18 confirmed Keychain-only entitlements (no Keychain Sharing). |
| V7 Error Handling | YES | Errors surface via Phase 24's `ApiError` (Stripe-shape envelope). No raw exception strings in UI. |
| V8 Data Protection | YES | BYOK keys: D-33 stores per-provider in Keychain/EncryptedSharedPreferences; logout does NOT clear (deliberate — user keys are theirs). Per-deploy Telegram tokens are NOT persisted (D-50 — held in `wizardScopeProvider` until wizard close). |
| V14 Configuration | YES | `--dart-define BASE_URL` is the only env-config (Phase 24 D-44); no in-app debug menu. |

### Known Threat Patterns for Flutter Mobile

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Markdown XSS via `javascript:` / `data:` URI in LLM reply | Tampering | D-46 allow-list (`https`/`http` only) + `Uri.scheme` check before `launchUrl` (Pitfall #2 + Mechanism §2). |
| Markdown image rendering pulling remote URL → SSRF / tracking pixel | Information Disclosure | D-43 explicitly disables image rendering (`imageBuilder: (_,__,___) => SizedBox.shrink()` in MarkdownStyleSheet). |
| BYOK key leakage via logs | Information Disclosure | Phase 24's `RedactingLogInterceptor` (D-52) redacts `Authorization` to last 8 chars in dev logs. Wave 5 spike uses the same interceptor. |
| Session token leakage via `flutter_secure_storage` on iOS Simulator | Information Disclosure | iOS Simulator Keychain is a known-leaky test surface (Pitfall #5); production claims need physical-device verification. Documented in spike artifact. |
| OAuth state mixup via WebView intercept | Spoofing | We DON'T use WebView OAuth (Pitfall #4) — `google_sign_in` is native; `flutter_appauth` uses system browser with PKCE. Backend's CSRF state is the second control (Phase 22c-oauth-google D-22c-OAUTH-01). |
| Markdown HTML injection (`<script>` tags) | Tampering | `flutter_markdown_plus` parses Markdown only; HTML in markdown is rendered as plaintext by default. Verify in Wave 4 widget test. |
| Custom URI schemes registered by other apps intercepting `solvrlabs://` callback | Spoofing | iOS App Universal Links + Android App Links are the long-term mitigation (Phase 24 D-15 deferred). Custom URI scheme is the MVP path; document the residual risk in `spikes/flutter-screens-roundtrip.md`. |
| Telegram bot-token leakage via wizard state retention after deploy | Information Disclosure | D-50 — bot tokens NOT persisted to `flutter_secure_storage`; held in `wizardScopeProvider` until wizard close. Wave 3 plan task asserts this via grep (`! grep 'TELEGRAM_BOT_TOKEN' lib/core/storage/`). |

---

## Implementation Approach

The 5-wave structure (D-64) maps cleanly to the substrate dependency graph.
Each wave's plans should follow the Phase 24 atomic-task pattern (one task =
one commit; verify after each).

### Wave 0 — Diligence Gate (~half day, 2 tasks; planning-time only)

| Task | Output | D-# refs |
|------|--------|----------|
| Wave 0 task A: Real-OAuth spike (suggested but not strictly required) | `spikes/phase-25-oauth-real.md` with PASS/FAIL marker — verifies `google_sign_in` 7.x `instance.initialize()` → `attemptLightweightAuthentication()` returns id_token AND `flutter_appauth` GitHub flow round-trips through system browser to `solvrlabs://oauth/github` callback. | D-66, Pitfall #3 |
| Wave 0 task B: Substitution decision for `flutter_markdown_plus` | Append AMD-03 to CONTEXT.md noting the substitution + rationale. Update Wave 1 plan to use `flutter_markdown_plus` as the dep name. | Pitfall #1 |

### Wave 1 — Foundation (D-01..D-07 + D-61 + D-62 + D-66 + D-67 + dep adds)

Task structure (single plan, ~10 atomic tasks):

| Task | What | Verify |
|------|------|--------|
| 1 | Bump `pubspec.yaml` version `0.1.0+1 → 0.2.0+2` (D-67); add `flutter_markdown_plus`, `url_launcher`, `golden_toolkit` deps; `pub get` + `pod install` | Grep version + 3 deps in pubspec.lock |
| 2 | Add `mobile/test/flutter_test_config.dart` with `loadAppFonts()` + smoke font-presence test | `flutter test test/golden/font_smoke_test.dart` |
| 3 | iOS `Info.plist` `LSApplicationQueriesSchemes`: add `https` (Pitfall #2) | Grep entry; `flutter build ios --debug --no-codesign` smoke |
| 4 | `lib/core/lifecycle/app_lifecycle_observer.dart` (Mechanism §1) | Unit test asserting `appLifecycleProvider` reflects state changes |
| 5 | `lib/core/storage/secure_storage.dart`: add `writeByokKey(provider) / readByokKey(provider) / clearByokKey(provider)`; logout-does-NOT-clear-BYOK invariant test | Unit test |
| 6 | `lib/core/auth/auth_service.dart` interface + `auth_service_real.dart` (Google + GitHub real impls) + `auth_service_test.dart` (`--dart-define SESSION_ID` test impl) | Unit test on test impl; real impl validated by Wave 0 spike |
| 7 | `lib/shared/` — 9 widgets per D-61 + UI-SPEC contracts. One file per widget. Per-widget unit test asserting visual contract (where testable). | `flutter test test/shared/` |
| 8 | `lib/features/login/login_screen.dart` + `login_providers.dart` (D-04..D-06) | Widget test asserts wordmark + 2 buttons + pending/error states |
| 9 | `lib/main.dart` + `lib/app.dart` cold-start: replace HealthzScreen with `/v1/users/me` probe → `/login` or `/dashboard` (D-01..D-03); native splash already shipped by Phase 24 D-30 (deferred to polish — verify the LaunchScreen.storyboard / launch_background drawable exist; if not, document as deferred to a v0.3 polish phase) | Widget test mocks 3 ApiClient responses |
| 10 | `lib/core/router/app_router.dart`: fill in `/login`, `/dashboard` (placeholder), `/new-agent/*` (placeholder), `/chat/:id` (placeholder); delete `_placeholder/healthz_screen.dart` | Widget test on initial route resolution |

### Wave 2 — Dashboard (D-08..D-20)

Task structure (~6-8 atomic tasks):

| Task | What | Verify |
|------|------|--------|
| 1 | Extend `dtos.dart` `Recipe` DTO with `description` + `displayName` + `channelProviderCompat` (Wave 3 needs them but Wave 2 starts using `description` for the AsciiAgentBanner stream's optional rich rendering); extend `AgentSummary` if needed (already complete — no extension needed) | Unit test on DTO parsing |
| 2 | `dashboard_providers.dart`: `recipesProvider` (cached `AsyncValue`, refetched per wizard open) + `agentsListProvider` (refetched on resume + pull-to-refresh + mount; uses CancelToken-based concurrency guard per Pitfall #8) | Unit test |
| 3 | `agent_row.dart`: row layout (status dot + name + model + last_activity); 1px divider; ellipsis | Widget test |
| 4 | `dashboard_screen.dart`: AppBar (wordmark + 3-dot overflow with Sign out → ConfirmDialog → clear session + go('/login')), bottom nav with disabled Browse/Profile, FAB → `/new-agent/clone`, RefreshIndicator wraps the list, empty state → `EmptyStateScaffold` + `AsciiAgentBanner` | Widget test (each scenario: empty, loading-skeleton, populated, fetch-error retry banner) |
| 5 | Lifecycle test: `AppLifecycleState.resumed` triggers a second fetch | Widget test |
| 6 | Golden: Dashboard empty (with cycling banner — capture one frame) + Dashboard populated (3 mock rows incl. failed status) | `flutter test test/golden/dashboard_*.dart` |

### Wave 3 — New Agent Wizard (D-21..D-34, D-54..D-60)

Task structure (~10 atomic tasks):

| Task | What | Verify |
|------|------|--------|
| 1 | `dtos.dart`: add `RecipeDetail` (full passthrough Map<String, dynamic>) + extend `OpenRouterModel` with `contextLength` + `pricing` extras (for picker richness D-26) | Unit test |
| 2 | `api_client.dart`: add `recipeDetail(name)` method calling `GET /v1/recipes/{name}` | Unit test |
| 3 | `wizard_shell.dart`: AppBar (back arrow OR X icon — D-31), stepper bar (D-23), body slot (~30 LOC for the stepper itself per D-23) | Widget test on stepper rendering |
| 4 | `wizard_providers.dart`: `wizardScopeProvider` (Pattern A from Pitfall #10 — single `StateNotifierProvider`, manually invalidated on close) | Unit test |
| 5 | `clone_step.dart` (D-25): horizontal scrolling cards from `recipesProvider`; selection ↔ wizardScope; Next disabled until selected | Widget test |
| 6 | `model_picker_screen.dart` (D-26): full-screen scaffold with search TextField + virtualized ListView of 300+ models; tap pops with selection. Uses `Navigator.push` rather than `go_router.go` so it pops naturally back to step 2. | Widget test on virtualization + search |
| 7 | `model_step.dart` (D-26 + D-32 + D-34): "Pick a model" button → push picker; selected card; BYOK TextField (dynamic label per D-32 reading `recipe.channelProviderCompat[channel].deferred`); auto-fill from `secureStorage.readByokKey(provider)`; obscureText + eye-toggle | Widget test (label-swap test + BYOK auto-fill test) |
| 8 | `name_deploy_step.dart` (D-27..D-30, D-54..D-58): name TextField with regex validation (mirror `routes/runs.py:60-66` `^[a-z0-9][a-z0-9_-]*$` + 64 cap); Telegram toggle (visible only when `recipe.channelsSupported` includes `'telegram'` per D-55); dynamic Telegram fields from `recipeDetail.channels.telegram.required_user_input` (D-54); Deploy button with collision check (D-28) → multi-channel deploy (Pattern 2) → smoke loading card → success/fail UX | Widget tests for: regex validation, collision dialog, smoke fail rendering, multi-channel orchestration with mocked dio responses |
| 9 | Wizard cancel UX (D-31): X icon → ConfirmDialog if dirty → invalidate wizardScope + pop | Widget test |
| 10 | Telegram-failed banner state (D-50 / D-58): on Telegram-only failure, store `telegramFailReason` in a Riverpod provider scoped to the new agent; consumed by Chat screen's banner. | Unit test |

### Wave 4 — Chat (D-35..D-53)

Task structure (~10 atomic tasks):

| Task | What | Verify |
|------|------|--------|
| 1 | Wave 4 plan task 1: curl-spike against live `/v1/agents/<id>/messages/stream` to capture actual SSE envelope shape; document in plan's `<read_first>` block (closes Open Question #1) | spike output committed |
| 2 | `chat_providers.dart`: `chatScopeProvider.family(agentId)` — owns `MessagesStream`, message Map, scroll controller, lifecycle observer subscription | Unit test |
| 3 | Resume reconnect: subscribe to `appLifecycleProvider`; on `resumed`, `disconnect()` + `connect()` (preserves Last-Event-Id) | Widget test (mocks lifecycle event, asserts second connect call) |
| 4 | `bubble_widget.dart` user variant + assistant variant (D-35); failed bubble via shared `FailedBubble` (D-44 / D-61); markdown via `flutter_markdown_plus` with JetBrains Mono code blocks (Mechanism §2) + image-stripping + `onTapLink` allow-list (D-46) | Widget tests + golden snapshot (markdown reply) |
| 5 | `input_bar.dart`: multiline expanding TextField (D-40); Send icon button with disabled / spinner / cancel-on-tap states (D-51); cancel via dio CancelToken | Widget test |
| 6 | Optimistic insert (D-41): user bubble at full opacity with idemKey local id; assistant `TypingDots` placeholder; SSE arrival replaces placeholder | Widget test |
| 7 | Map dedup (D-36): on `GET /messages` history landing AND SSE `inapp_outbound`, dedupe by `inappMessageId` (or `seq` if Pitfall #9 confirms) | Widget test |
| 8 | Auto-scroll suppression (D-42): scroll position > 50px from bottom suppresses auto-scroll; "New message ↓" chip appears | Widget test |
| 9 | Failed-bubble Retry (D-44 / D-45): tap → bottom sheet → Retry generates NEW UUID v4 + POST /messages | Widget test (asserts NEW idemKey != cached idemKey) |
| 10 | Restart banner (D-49) + Telegram-failed banner (D-50): pinned banners reading agent.status / `telegramFailReason` provider | Widget tests |

### Wave 5 — Exit Gate (D-65 + AMD-01 + AMD-02)

Task structure (~5 atomic tasks):

| Task | What | Verify |
|------|------|--------|
| 1 | `mobile/integration_test/screens_e2e_test.dart` — body fleshed out per **Code Examples §Wave 5 spike harness extension**; reuses Phase 24's `spike_helpers.dart`. | `flutter analyze` clean; offline `flutter test integration_test/screens_e2e_test.dart -d <device>` parses (no execution yet) |
| 2 | `mobile/Makefile` `screens-e2e` target wired with same fail-fast preflight as `make spike` (BASE_URL/SESSION_ID/OPENROUTER_KEY required + curl pre-check) | Grep target |
| 3 | **AMD-01**: rewrite `.planning/REQUIREMENTS.md` UI-02 per CONTEXT amendments block | Verifier matches new wording verbatim |
| 4 | **AMD-02**: append amendment paragraph to `.planning/phases/23-backend-mobile-api-chat-proxy-persistence-auth-shim/23-CONTEXT.md` D-28 | Verifier matches new wording verbatim |
| 5 | Live `make screens-e2e` run + capture `spikes/flutter-screens-roundtrip.md` (mirror Phase 24's artifact frontmatter — `verdict: PASS`, target = "iOS Simulator (iPhone 16e iOS 26.4.x)" + Android Emulator if available, reproducibility tuple) | `verdict: PASS` literal string match |

---

## Risks & Open Questions

(See **Open Questions** section above for the 5 substrate questions. The
risks below are higher-level.)

### Risk 1: `flutter_markdown` discontinuation surfaces during Wave 4

- **Likelihood:** HIGH if planner uses literal D-43 wording; LOW if planner adopts AMD-03 substitution at Wave 0.
- **Impact:** Medium (rewrite Wave 4 task 4 to use `flutter_markdown_plus` API; no semantic change).
- **Mitigation:** Wave 0 task B explicitly adopts `flutter_markdown_plus`. Document as AMD-03.

### Risk 2: `google_sign_in` 7.x native config (Info.plist `CFBundleURLTypes`, `GoogleService-Info.plist`, Android `OAUTH_CLIENT_ID`) blocks real-OAuth path

- **Likelihood:** MEDIUM if Phase 22c-oauth-google didn't already produce the OAuth client IDs; LOW otherwise (Phase 22c-oauth-google has them).
- **Impact:** HIGH if blocking — real-OAuth manual smoke fails after Wave 5; MVP demo uses test impl only (which is acceptable for the local-only milestone but weak as a "shippable" claim).
- **Mitigation:** Wave 0 spike + early planner check with user that Google Cloud Console / GitHub Apps have the iOS + Android client IDs configured.

### Risk 3: `golden_toolkit` snapshot tests are flaky on different host OS / CI

- **Likelihood:** MEDIUM (golden tests are infamously OS-sensitive).
- **Impact:** LOW for Phase 25 — D-62 says "PR-checklist + golden_toolkit", not "CI gate"; locally-run snapshots are fine as a regression catcher.
- **Mitigation:** Run snapshots on a single dev machine; commit `.png` files. CI runs `flutter test --update-goldens` only by manual trigger. Deferred from Phase 25's automated gate.

### Risk 4: Wave 5 spike runtime exceeds the 15-minute test timeout

- **Likelihood:** LOW (Phase 24's 9-step spike completed in ~13s in-test; Phase 25's spike adds ~10 more steps but each step is widget-driven, not network-driven for most).
- **Impact:** HIGH if blocking (red exit gate).
- **Mitigation:** Set `timeout: const Timeout(Duration(minutes: 15))` (matches Phase 24); split into multiple `testWidgets` blocks if any one step risks > 5min on its own.

### Risk 5: D-49 multi-channel Restart can't access per-agent channel set

- **Likelihood:** MEDIUM (Open Question #2).
- **Impact:** LOW — D-49 already documents the planner-deferred TODO.
- **Mitigation:** Wave 4 task 10 plan-checks the `GET /v1/agents` response shape; if channel set absent, default to `inapp` only with a TODO comment + a Phase 25 follow-up entry in the planner's deferred list.

### Risk 6: Real OAuth client IDs not configured in dev environment

- **Likelihood:** HIGH if Phase 22c-oauth-google's deploy.env shape is different from mobile-platform-native config.
- **Impact:** MEDIUM (Wave 0 spike fails; Wave 5 manual smoke documented as deferred).
- **Mitigation:** Wave 0 task A accepts FAIL — D-66 test seam is the load-bearing path. Document the gap in `spikes/phase-25-oauth-real.md`.

---

## Source of Truth References

(Paths the planner should cite in `read_first` blocks of plan files.)

### Project-level
- `CLAUDE.md` — five golden rules; in particular Rules 1, 2, 5 dominate Phase 25's discipline.
- `.planning/REQUIREMENTS.md` — UI-01..UI-04 (UI-02 to be amended via AMD-01).
- `.planning/phases/25-mobile-screens/25-CONTEXT.md` — 68 D-decisions + 2 amendments. **Authoritative for Phase 25.**
- `.planning/phases/25-mobile-screens/25-UI-SPEC.md` — visual + interaction contract; resolves D-Discretion items.
- `.planning/phases/25-mobile-screens/25-DISCUSSION-LOG.md` — rationale trail for the 68 decisions.
- `.planning/notes/mobile-mvp-decisions.md` — historical decisions (note: contains stale "Telegram disabled" wording superseded by AMD-01).
- `memory/feedback_solvr_matrix_aesthetic.md` — drove D-17 (cycling banner) + D-61 (`AsciiAgentBanner`).
- `memory/feedback_dumb_client_no_mocks.md` — drove D-32 / D-54 / D-55 / D-56 (no client-side hardcoded catalogs).
- `memory/feedback_telegram_is_live_channel_not_stub.md` — drove AMD-01 + AMD-02 (Telegram is real, not stub).

### Prior phase contracts
- `.planning/phases/24-flutter-foundation/24-CONTEXT.md` — D-01..D-56 (theme, ApiClient, MessagesStream, etc.). Phase 25 builds directly on top.
- `.planning/phases/24-flutter-foundation/24-RESEARCH.md` — covers Phase 24's pitfalls (especially Pitfall #2 = `flutter_client_sse` no-auto-Last-Event-Id, Pitfall #4 = iOS Simulator Keychain volatility, Pitfall #6 = `google_fonts` runtime-fetch). All carry-forward to Phase 25.
- `.planning/phases/24-flutter-foundation/24-09-SUMMARY.md` — what the spike actually verified.
- `spikes/flutter-api-roundtrip.md` — Phase 24 PASS artifact; Phase 25 Wave 5 produces a sibling.
- `.planning/phases/23-backend-mobile-api-chat-proxy-persistence-auth-shim/23-CONTEXT.md` — D-28 (to be amended via AMD-02), D-04/D-08/D-09/D-13/D-17/D-22/D-27.
- `.planning/phases/22c-oauth-google/22c-CONTEXT.md` — OAuth contracts (`require_user`, `ApSessionMiddleware`, `upsert_user`, `mint_session`).

### Backend endpoints + models the screens consume
- `api_server/src/api_server/routes/runs.py` — `POST /v1/runs`. **Read `_validate_name` regex pattern** at `models/runs.py:66` — D-27 mirrors verbatim. Note: regex is on `models/runs.py:60-67` (recipe_name) and `:77-82` (agent_name `^[a-zA-Z0-9][a-zA-Z0-9 _-]*$` allows uppercase + space) — D-27's `^[a-z0-9][a-z0-9_-]*$` matches the strict recipe-name regex; the planner should clarify in the Wave 3 plan which to mirror.
- `api_server/src/api_server/routes/agent_lifecycle.py` — `POST /v1/agents/:id/start` (per-channel container spawn; called twice for inapp+telegram).
- `api_server/src/api_server/routes/agent_messages.py` — `POST /v1/agents/:id/messages` (Idempotency-Key REQUIRED), `GET /v1/agents/:id/messages?limit=N` (ASC oldest→newest), SSE `GET /v1/agents/:id/messages/stream` (Last-Event-ID).
- `api_server/src/api_server/routes/agents.py` — `GET /v1/agents` extended with `status` + `last_activity`.
- `api_server/src/api_server/routes/recipes.py` — `GET /v1/recipes` + `GET /v1/recipes/{name}`.
- `api_server/src/api_server/routes/models.py` — `GET /v1/models`.
- `api_server/src/api_server/routes/users.py` — `GET /v1/users/me` (cold-start probe per D-01).
- `api_server/src/api_server/routes/auth.py` — `POST /v1/auth/google/mobile` + `POST /v1/auth/github/mobile`.
- `api_server/src/api_server/models/recipes.py` — **`RecipeSummary.channels_supported` + `channel_provider_compat` exact shapes** (drives D-32 / D-55).
- `api_server/src/api_server/middleware/session.py` — `ApSessionMiddleware` (cookie-header transport).
- `api_server/src/api_server/middleware/idempotency.py` — replay semantics (informs D-45).

### Existing mobile code (Phase 24 — REUSE)
- `mobile/lib/core/api/api_client.dart` — every endpoint method already exists.
- `mobile/lib/core/api/messages_stream.dart` — SSE wrapper with Last-Event-Id (Phase 24 Plan 05).
- `mobile/lib/core/api/auth_interceptor.dart` — Cookie injection + 401 handler.
- `mobile/lib/core/api/dtos.dart` — DTOs (extend `Recipe`; add `RecipeDetail`).
- `mobile/lib/core/api/result.dart` — sealed `Result<T>` + `ApiError`.
- `mobile/lib/core/storage/secure_storage.dart` — extend with BYOK methods.
- `mobile/lib/core/auth/auth_event_bus.dart` — auth event bus.
- `mobile/lib/core/router/app_router.dart` — fill in routes.
- `mobile/lib/main.dart` + `mobile/lib/app.dart` — wire AuthService + cold-start.
- `mobile/integration_test/spike_api_roundtrip_test.dart` + `spike_helpers.dart` — Wave 5 extends.
- `mobile/Makefile` — add `make screens-e2e`.

### Web frontend (mirror dumb-client patterns)
- `frontend/components/playground-form.tsx` lines **316-360** — deploy call sequence (mobile mirrors verbatim per D-56).
- `frontend/components/playground-form.tsx` lines **638-689** — dynamic channel-inputs rendering (mobile mirrors per D-54 in Dart).
- `frontend/components/playground-form.tsx` lines **627-635** — BYOK label-swap logic (mobile mirrors per D-32).

### Recipe sources (DO NOT hardcode in Dart; READ at planning time only)
- `recipes/openclaw.yaml` lines **440-453** — `channels.telegram.required_user_input`: TELEGRAM_BOT_TOKEN + TELEGRAM_ALLOWED_USER (with `prefix_required: "tg:"` + `hint_url: https://t.me/userinfobot`).
- `recipes/hermes.yaml` lines **263-281** — `channels.telegram.required_user_input`: TELEGRAM_BOT_TOKEN + TELEGRAM_ALLOWED_USERS (CSV) + 2 optional inputs.

### External / package documentation (NEW deps)
- `flutter_markdown_plus` — https://pub.dev/packages/flutter_markdown_plus (substitute for D-43's `flutter_markdown`)
- `flutter_markdown_plus` handover backstory — https://foresightmobile.com/blog/flutter-markdown-plus-google-handover
- `flutter_markdown` discontinuation — https://github.com/flutter/flutter/issues/162966
- `url_launcher` — https://pub.dev/packages/url_launcher (D-46)
- `golden_toolkit` — https://pub.dev/packages/golden_toolkit (D-62)
- `golden_toolkit` `loadAppFonts` API — https://pub.dev/documentation/golden_toolkit/latest/golden_toolkit/loadAppFonts.html

### External / package documentation (already in pubspec from Phase 24)
- `google_sign_in` 7.x migration — https://isaacadariku.medium.com/google-sign-in-flutter-migration-guide-pre-7-0-versions-to-v7-version-cdc9efd7f182
- `google_sign_in` 7.x changelog — https://pub.dev/packages/google_sign_in/changelog
- `flutter_appauth` — https://pub.dev/packages/flutter_appauth
- `flutter_secure_storage` — https://pub.dev/packages/flutter_secure_storage
- `flutter_riverpod` scopes — https://riverpod.dev/docs/concepts/scopes
- `WidgetsBindingObserver` — https://api.flutter.dev/flutter/widgets/WidgetsBindingObserver-class.html
- `WidgetTester.handleAppLifecycleStateChanged` — https://api.flutter.dev/flutter/flutter_test/WidgetTester
- `flutter_client_sse` — https://pub.dev/packages/flutter_client_sse (D-33 LOCKED)

---

## Sources

### Primary (HIGH confidence)
- `.planning/phases/25-mobile-screens/25-CONTEXT.md` — read in full; 68 decisions + 2 amendments are the source of truth.
- `.planning/phases/25-mobile-screens/25-UI-SPEC.md` — read in full; visual + interaction contract.
- `.planning/phases/24-flutter-foundation/24-CONTEXT.md` + `24-RESEARCH.md` + `24-09-SUMMARY.md` — Phase 24 substrate verified end-to-end via spike.
- `mobile/lib/core/api/api_client.dart` (305 LOC) — every endpoint Phase 25 needs already methodized.
- `mobile/lib/core/api/messages_stream.dart` (129 LOC) — SSE wrapper with Last-Event-Id tracking.
- `mobile/lib/core/api/dtos.dart` (242 LOC) — DTOs (Recipe is thin; needs extension).
- `mobile/integration_test/spike_api_roundtrip_test.dart` (262 LOC) — Wave 5 harness reference.
- `mobile/integration_test/spike_helpers.dart` (72 LOC) — reusable for Wave 5.
- `mobile/Makefile` — `make spike` shape; Wave 5 mirrors as `make screens-e2e`.
- `mobile/pubspec.yaml` — current dep set; Phase 25 adds 3.
- `frontend/components/playground-form.tsx` lines 316-360, 627-635, 638-689 — deploy + BYOK + dynamic channel-inputs reference (the canonical web client behavior to mirror).
- `api_server/src/api_server/routes/runs.py` + `models/runs.py:60-82` — name regex source.
- `api_server/src/api_server/models/recipes.py` — `RecipeSummary` schema.
- `recipes/openclaw.yaml:440-453` + `recipes/hermes.yaml:263-281` — Telegram channel inputs verbatim.
- `spikes/flutter-api-roundtrip.md` — Phase 24 PASS artifact reproducibility.

### Secondary (MEDIUM-HIGH confidence)
- pub.dev pages for `flutter_markdown_plus`, `url_launcher`, `golden_toolkit`, `google_sign_in 7.x` (verified via WebSearch).
- `flutter_markdown` discontinuation thread on GitHub flutter/flutter#162966.
- Foresight Mobile blog post on `flutter_markdown_plus` handover.
- `google_sign_in` 7.x migration guides (Medium / pub.dev changelog).

### Tertiary (LOW — flagged for Wave-time validation)
- Riverpod `ProviderScope` scope documentation (linked but not deeply tested for `go_router` ShellRoute integration; **Pitfall #10** flags Pattern A vs B).
- `WidgetTester.handleAppLifecycleStateChanged` exact behavior across iOS Simulator + Android Emulator (Pitfall #7 — likely fine but Wave 5 task 5 is the ground-truth).

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Phase 24 already pinned and verified everything except the 3 new deps; the 3 new ones are pub.dev-verified-publisher and well-trodden.
- Architecture: HIGH — patterns mirror Phase 24's own + the web playground-form's known-good behavior.
- Pitfalls: HIGH for the 10 pitfalls documented (5 are direct carry-forward from Phase 24 RESEARCH; 5 are new but verified via pub.dev / docs).
- Dependency substitution (`flutter_markdown` → `flutter_markdown_plus`): HIGH (multiple sources confirm discontinuation + drop-in successor).
- `google_sign_in` 7.x real-OAuth path: MEDIUM-HIGH — API docs are clear, but the native config (Info.plist URL types + Google Cloud Console client IDs) hasn't been spike-verified for this project's specific OAuth setup. Wave 0 task A closes this.
- D-49 multi-channel Restart shape: LOW — Open Question #2; mitigation = TODO comment + planner-deferred entry.
- SSE envelope `inapp_message_id` presence: LOW — Open Question #1; mitigation = Wave 4 plan task 1 spike.

**Research date:** 2026-05-03
**Valid until:** 2026-06-03 (30 days for stable Flutter ecosystem) — but
re-verify all 3 new pubspec deps with `flutter pub outdated` at Wave 1
plan-write time.

---

## RESEARCH COMPLETE

**Phase:** 25 — mobile-screens
**Confidence:** HIGH overall; 2 LOW open questions flagged with concrete
mitigations; 1 HIGH-impact dependency substitution (`flutter_markdown` →
`flutter_markdown_plus`) recommended as AMD-03.

### Key Findings

- **Substrate is largely shipped.** Phase 24 already provides every endpoint
  method, SSE wrapper, secure storage, theme, router, and a 9-step spike
  PASSING against live infra. Phase 25 is screen plumbing on top.
- **`flutter_markdown` was discontinued by Google in 2025.** CONTEXT D-43
  names it literally; planner should substitute `flutter_markdown_plus`
  (Foresight Mobile, drop-in API) and document as AMD-03.
- **`google_sign_in` 7.x is a major API rewrite vs 6.x.** Use
  `instance.initialize()` + `attemptLightweightAuthentication()` patterns;
  D-66's test seam absorbs the risk for waves 1-4; Wave 0 spike validates
  the real path.
- **Multi-channel deploy mirrors web `playground-form.tsx`** — 1×`/runs` +
  N×`/start` sequential calls; NO new backend endpoint; AMD-01 + AMD-02
  encode this in REQUIREMENTS.md and 23-CONTEXT.md.
- **Existing `Recipe` DTO is too thin** (only `name + channelsSupported`);
  Wave 2 task 1 must extend with `description`, `displayName`,
  `channelProviderCompat`. A NEW `RecipeDetail` DTO is needed for
  `/v1/recipes/{name}` to drive D-54 dynamic Telegram fields.
- **2 LOW-confidence open questions** flagged with concrete plan-time
  mitigations: (1) does the SSE `inapp_outbound` envelope contain
  `inapp_message_id` (Wave 4 task 1 spike); (2) does extended `GET /v1/agents`
  return per-agent channel set (Wave 4 task 10 plan-check; default to inapp
  only if absent per D-49).

### File Created
`/Users/fcavalcanti/dev/agent-playground/.planning/phases/25-mobile-screens/25-RESEARCH.md`

### Confidence Assessment

| Area | Level | Reason |
|------|-------|--------|
| Standard stack | HIGH | Phase 24 + 3 new deps all pub.dev-verified; substitution `flutter_markdown_plus` confirmed via multiple sources. |
| Architecture | HIGH | Mirrors Phase 24's own + web playground-form's known-good patterns. |
| Pitfalls | HIGH | 10 documented (5 carry-forward from 24-RESEARCH, 5 new but doc-cited). |
| Validation | HIGH | Test map covers UI-01..UI-04; Wave 5 spike is the load-bearing exit gate. |
| Open questions | LOW (acceptable) | Both have concrete plan-time mitigations; neither blocks wave-1 from starting. |

### Open Questions (planner consumes)

5 substrate questions documented in **Open Questions** section with concrete
recommendations for resolution at Wave 4 / Wave 2 plan-write time. None
block Wave 1 or Wave 0.

### Ready for Planning

Research complete. Planner can now create PLAN.md files for waves 0
(diligence gate, optional/recommended), 1 (foundation), 2 (Dashboard), 3
(New Agent wizard), 4 (Chat), and 5 (exit gate + AMD amendments).

The Phase 25 plan-checker should treat the existence of
`spikes/flutter-screens-roundtrip.md` with `verdict: PASS` AND the AMD-01 /
AMD-02 amendments landed in the commit chain as the load-bearing exit gate
signals.

---

Sources:
- [pub.dev/packages/flutter_markdown_plus](https://pub.dev/packages/flutter_markdown_plus)
- [github.com/flutter/flutter#162966 — flutter_markdown discontinuation](https://github.com/flutter/flutter/issues/162966)
- [foresightmobile.com — flutter_markdown_plus handover](https://foresightmobile.com/blog/flutter-markdown-plus-google-handover)
- [pub.dev/packages/url_launcher](https://pub.dev/packages/url_launcher)
- [pub.dev/packages/golden_toolkit](https://pub.dev/packages/golden_toolkit)
- [pub.dev/documentation/golden_toolkit/latest/golden_toolkit/loadAppFonts.html](https://pub.dev/documentation/golden_toolkit/latest/golden_toolkit/loadAppFonts.html)
- [pub.dev/packages/google_sign_in/changelog](https://pub.dev/packages/google_sign_in/changelog)
- [Google Sign-In Flutter Migration Guide pre-7.0 → v7](https://isaacadariku.medium.com/google-sign-in-flutter-migration-guide-pre-7-0-versions-to-v7-version-cdc9efd7f182)
- [pub.dev/packages/flutter_appauth](https://pub.dev/packages/flutter_appauth)
- [pub.dev/packages/flutter_client_sse](https://pub.dev/packages/flutter_client_sse)
- [pub.dev/packages/flutter_secure_storage](https://pub.dev/packages/flutter_secure_storage)
- [api.flutter.dev/flutter/widgets/WidgetsBindingObserver-class.html](https://api.flutter.dev/flutter/widgets/WidgetsBindingObserver-class.html)
- [api.flutter.dev/flutter/flutter_test/WidgetTester](https://api.flutter.dev/flutter/flutter_test/WidgetTester)
- [github.com/Betterment/alchemist — alchemist alternative](https://github.com/Betterment/alchemist)
- [pub.dev/packages/flutter_markdown_plus/versions/1.0.6/changelog](https://pub.dev/packages/flutter_markdown_plus/versions/1.0.6/changelog)

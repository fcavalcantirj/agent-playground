# Phase 24: Flutter Foundation — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `24-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-05-02
**Phase:** 24-flutter-foundation
**Areas discussed:** Repo layout & identity, API client architecture, Env-config switch UX, Spike scope & how to get a session

---

## Repo layout & identity

### Project root location
| Option | Description | Selected |
|--------|-------------|----------|
| `mobile/` sibling | Top-level next to api_server/, frontend/, recipes/ | ✓ |
| `app/` | Top-level app/ — overloaded term in this repo | |
| Separate repo | Brand new git repo, doubles cognitive overhead | |

### Bundle/applicationId
| Option | Description | Selected |
|--------|-------------|----------|
| `com.solvrlabs.agentplayground` | Brand-aligned, codename-preserving, future rebrand-safe | ✓ |
| `com.solvrlabs.solvr` | Brand-only; risky given brand decision deferred | |
| Pick during scaffold | Risk of inconsistent ad-hoc choice | |

### OAuth deep-link custom URL scheme
| Option | Description | Selected |
|--------|-------------|----------|
| `solvrlabs://` | Brand-aligned, full word reduces collision risk | ✓ |
| `solvr://` | Shorter, higher collision risk | |
| `com.solvrlabs.agentplayground://` | Reverse-DNS, max safe but ugly | |

### Flutter SDK pinning
| Option | Description | Selected |
|--------|-------------|----------|
| FVM with .fvmrc + .fvm/ committed | In-repo SDK pin, mirrors uv | ✓ |
| No FVM — PATH | Faster scaffold, drift risk later | |

### Native dirs (ios/android)
| Option | Description | Selected |
|--------|-------------|----------|
| Commit both | Standard Flutter monorepo practice; required for OAuth deep-links | ✓ |
| Commit android, ignore ios | Loses iOS reviewability | |
| Generate on demand | Loses native config | |

### .gitignore strategy
| Option | Description | Selected |
|--------|-------------|----------|
| Standard Flutter .gitignore | Battle-tested set | ✓ |
| Plus pubspec.lock ignored | Anti-pattern given FVM pinning | |

### Min platform API levels
| Option | Description | Selected |
|--------|-------------|----------|
| iOS 13.0 + Android API 23 | Flutter defaults; ~99.5% device coverage | ✓ |
| iOS 15+ / Android API 26+ | Premature for MVP | |
| Decide during scaffold | Worth knowing the floor | |

### mobile/Makefile
| Option | Description | Selected |
|--------|-------------|----------|
| Yes — mobile/Makefile | Mirrors api_server/Makefile, single dev-loop discovery point | ✓ |
| No — raw flutter/fvm commands | Less ceremony, weaker for second contributor | |

### Lints
| Option | Description | Selected |
|--------|-------------|----------|
| very_good_analysis | Stricter; matches ruff philosophy | ✓ |
| flutter_lints (default) | Lighter, less safety net | |
| lints/recommended (pure Dart) | Wrong fit for Flutter | |

### Code signing in Phase 24
| Option | Description | Selected |
|--------|-------------|----------|
| Personal team / debug only | No App Store submission in P24 | ✓ |
| Set up release signing now | Premature; produces nothing demoable | |

### Flutter SDK version pin
| Option | Description | Selected |
|--------|-------------|----------|
| Latest stable (3.x stable channel) | Re-pin as a chore later | ✓ |
| Specific tested version | Adds maintenance burden | |
| Latest beta | Skip — beta is not for foundations | |

### fastlane
| Option | Description | Selected |
|--------|-------------|----------|
| Defer entirely | No demoable value during MVP | ✓ |
| Set up now | Premature | |

### README scope
| Option | Description | Selected |
|--------|-------------|----------|
| Minimal: setup + run + spike | ~50-80 lines, enough for second contributor | ✓ |
| Full: + architecture + state mgmt + theming | Costs hours, rots fast | |
| Skip README | Hostile to onboarding | |

### CI for mobile/
| Option | Description | Selected |
|--------|-------------|----------|
| Minimal mobile CI workflow now | analyze + test on push, ~30 LOC | ✓ |
| Defer entirely until Phase 25 | Loses early lint signal | |
| Defer + manually run before each commit | Honor system, brittle | |

### PR template
| Option | Description | Selected |
|--------|-------------|----------|
| Reuse existing PR template | GSD artifacts already structure context | ✓ |
| Mobile-specific template | Premature | |

### App version scheme
| Option | Description | Selected |
|--------|-------------|----------|
| 0.1.0+1, increment per phase | Aligns with milestone-based versioning | ✓ |
| 0.0.1+1 strict semver | Translation overhead | |
| Pick during scaffold | Misleading if left at flutter create's 1.0.0+1 | |

### App icon + splash
| Option | Description | Selected |
|--------|-------------|----------|
| Placeholder only — defer real assets | Adds nothing to spike's truth-claim | ✓ |
| Ship Solvr Labs icon + splash now | Hours of asset work | |

### Localization (l10n)
| Option | Description | Selected |
|--------|-------------|----------|
| Defer | MVP is en-US only | ✓ |
| Set up flutter_localizations now | Premature | |

### Pre-commit hooks
| Option | Description | Selected |
|--------|-------------|----------|
| Reuse repo's existing strategy | Keep ceremony low | ✓ |
| Add lefthook for Flutter-specific hooks | Overkill for solo | |

### App display name
| Option | Description | Selected |
|--------|-------------|----------|
| Solvr Labs | User-facing brand per mobile-mvp-decisions.md | ✓ |
| Agent Playground | May truncate on tight Android launchers | |
| Solvr | Less unique on home screen | |

### iOS App Transport Security
| Option | Description | Selected |
|--------|-------------|----------|
| Whitelist localhost + LAN ranges in Info.plist | Production HTTPS still enforced for non-exempted | ✓ |
| NSAllowsArbitraryLoads = true (debug only) | Apple-rejects on submission | |
| Use only HTTPS via ngrok for dev | Heavy ergonomics hit | |

### Android cleartext HTTP
| Option | Description | Selected |
|--------|-------------|----------|
| networkSecurityConfig.xml debug-build only | Granular, mirrors iOS approach | ✓ |
| android:usesCleartextTraffic=true (debug only) | Less granular | |
| ngrok always | Heavy | |

### Orientation
| Option | Description | Selected |
|--------|-------------|----------|
| Portrait only | Removes rotation-bug class | ✓ |
| Both portrait and landscape | No mockup design exists for landscape | |

### Deep linking mode
| Option | Description | Selected |
|--------|-------------|----------|
| Custom URL scheme only — solvrlabs:// | No HTTPS domain required | ✓ |
| Universal Links / App Links (HTTPS verified) | Need verified domain we don't have | |
| Both | No extra value during MVP | |

### Android build flavors
| Option | Description | Selected |
|--------|-------------|----------|
| No flavors yet — single debug+release | Don't yet have prod env to flavor | ✓ |
| Set up dev/prod flavors now | Cargo-cult | |

### Status bar styling
| Option | Description | Selected |
|--------|-------------|----------|
| Light background — dark icons | Matches monochrome theme | ✓ |
| Defer to Phase 25 | Inconsistent first-launch screenshot risk | |

### iOS entitlements (Keychain)
| Option | Description | Selected |
|--------|-------------|----------|
| Default Keychain only — no sharing group | flutter_secure_storage works without it | ✓ |
| Add Keychain Sharing now | Premature | |

### Apple Privacy Manifest
| Option | Description | Selected |
|--------|-------------|----------|
| Defer to release-readiness phase | Required only for App Store submission | ✓ |
| Ship minimal manifest now | Pre-empts but no immediate value | |

### Telemetry (push, crash, analytics)
| Option | Description | Selected |
|--------|-------------|----------|
| Defer all three | Out of MVP per mobile-mvp-decisions.md | ✓ |
| Add Sentry or Crashlytics now | Setup hours + 3rd-party SDK before need | |

### Accessibility floor
| Option | Description | Selected |
|--------|-------------|----------|
| Capture conventions in CONTEXT, enforce in Phase 25 | Phase 24 has no real screens to audit | ✓ |
| Skip — add in polish phase | Retrofit is harder | |
| Block Phase 24 ship on a11y audit now | Nothing to audit yet | |

### dart format line length
| Option | Description | Selected |
|--------|-------------|----------|
| Default 80 | very_good_analysis + community default | ✓ |
| 100 | Personal taste | |
| 120 | Works against multi-pane review | |

### Logging convention
| Option | Description | Selected |
|--------|-------------|----------|
| dart:developer log() | Stdlib, IDE-aware | ✓ |
| logger package | Overkill for MVP | |
| print() | Linter flags it | |

### lib/ folder structure
| Option | Description | Selected |
|--------|-------------|----------|
| Feature-based: lib/features/, lib/core/, lib/shared/ | Riverpod community convention | ✓ |
| Layer-based: data/domain/presentation | Clean Architecture, heavier | |
| Flat lib/ — organize when patterns emerge | Loses upfront reasoning | |

---

## API client architecture

### Typed API client style
**Asked twice** — first round prompted user to ask for an explanation; second round asked again with concrete code samples. After the second round, user pushed back: *"you knoe api is defined right? just USE the api, I/m NOt even understanding the logic of this question. wtf man"* — accepted the simplest path: **hand-written dio wrappers, no codegen debate.**

| Option | Description | Selected |
|--------|-------------|----------|
| Hand-written over dio | 150-300 LOC, SSE+Result+Cookie all natural | ✓ |
| retrofit codegen | build_runner overhead, doesn't model SSE | |
| openapi-generator from FastAPI /openapi.json | Verbose, no SSE, throws-on-error | |

### Result/Either type
| Option | Description | Selected |
|--------|-------------|----------|
| Hand-rolled sealed class — Result<T> | Dart 3 sealed + zero deps | ✓ |
| fpdart Either<L, R> | Adds ~150KB + learning curve | |
| dartz Either | Less actively maintained | |

### SSE library
| Option | Description | Selected |
|--------|-------------|----------|
| flutter_client_sse | Locked by Phase 23 D-13 | ✓ |
| eventsource_plus | Re-litigates Phase 23 decision | |
| Hand-roll on dio streams | ~80 LOC of fiddly framing | |

### JSON serialization
| Option | Description | Selected |
|--------|-------------|----------|
| Manual fromJson/toJson | ~10-15 DTOs, trivial | ✓ |
| json_serializable + build_runner | Pays off at 30+ DTOs | |
| freezed | Heavy for plain DTOs | |

### Auth cookie injection
| Option | Description | Selected |
|--------|-------------|----------|
| dio Interceptor reads from flutter_secure_storage per request | ~20 LOC, no jar needed | ✓ |
| cookie_jar + dio_cookie_manager | Overkill for one cookie | |

### Idempotency-Key generation
| Option | Description | Selected |
|--------|-------------|----------|
| uuid v4 per Send press, stored on in-flight message | Reuses on retry | ✓ |
| Hash (agent_id, content, timestamp_to_minute) | Wrong semantics | |
| Ulid | No advantage here | |

### Timeout policy
| Option | Description | Selected |
|--------|-------------|----------|
| 10s connect / 30s receive; SSE no receive timeout | Covers slow container spawn | ✓ |
| Default dio timeouts (no limits) | Hangs forever | |
| Tighter — 5s/15s | False-positive timeouts | |

### Error envelope decoding
**User note:** *"dude, api is ready. use it."* — confirmed: mirror the existing Stripe-shape envelope verbatim, don't invent a new shape.

| Option | Description | Selected |
|--------|-------------|----------|
| Parse Stripe envelope into typed ApiError | Exhaustive switch on ErrorCode | ✓ |
| Keep error as Map<String, dynamic> | Boilerplate every screen | |

### Retry policy
| Option | Description | Selected |
|--------|-------------|----------|
| No auto-retry; surface Err to caller | Idempotency-Key for safe user-driven retry | ✓ |
| dio_smart_retry on 5xx + network | Hides real failures during demo | |

### OpenRouter BYOK key in client
| Option | Description | Selected |
|--------|-------------|----------|
| Wire shape in client; entry UX deferred to Phase 25 | Spike uses --dart-define key | ✓ |
| Defer BYOK entirely | Spike couldn't exercise /runs | |
| Ship full BYOK settings screen | Scope creep into Phase 25 | |

### CancelToken support
| Option | Description | Selected |
|--------|-------------|----------|
| Yes — every dio call accepts CancelToken; Riverpod auto-cancels on dispose | Without this, SSE leaks | ✓ |
| Skip cancel tokens | SSE leak per visit | |

---

## Env-config switch UX

**User pushback verbatim:** *"MAH MAN. wtf. API IS READY FUCKING USE API, DOES APP KNOWS ABOUT IP, NGROX, ANYTHING>???? JUST USE THE INTERNET, LET THE DEV TO THE REST DUDE"*

Result: collapsed all three sub-questions into a single decision — no in-app switcher, no debug menu, no persistence. **`--dart-define BASE_URL=...` only.** The user's Q2 ("shared_preferences") and Q3 ("debug menu only") answers are moot under this — they were clicked through during pushback. The locked decision is **D-44**: dev sets URL externally; app reads `String.fromEnvironment('BASE_URL', defaultValue: 'http://localhost:8000')` at boot.

**Plus:** *"yeah, do the app as is was scoped, THE APP, dash, screens, no debug. use logs."* — reinforced: production-style UI shell, no debug overlays. (The word "chrome" caused a misunderstanding mid-discussion — clarified: app-UI jargon for surrounding framing, unrelated to Google Chrome the browser.)

| Option | Description | Selected |
|--------|-------------|----------|
| `--dart-define BASE_URL=...` only, dev sets per target | Honors "dev handles env, not the app" | ✓ |
| In-app debug menu (5-tap / shake gesture) | Rejected — adds dev-mode UI to a production app | |
| Compile-time --dart-define + in-app debug menu override | Rejected — overcomplicates for no gain | |

---

## Spike scope & how to get a session

### Spike scope
| Option | Description | Selected |
|--------|-------------|----------|
| Full round-trip: deploy + send + SSE reply + auth header | Covers all load-bearing mechanisms | ✓ |
| Minimal: just /healthz + auth header | Skips the genuinely risky parts | |
| Deploy round-trip only | Skips SSE + cookie injection | |

### Session source
| Option | Description | Selected |
|--------|-------------|----------|
| Manually mint via existing browser OAuth + paste cookie | Real session, real middleware, real isolation | ✓ |
| Spike directly hits POST /v1/auth/google/mobile | Chicken-and-egg with Phase 25 OAuth UI | |
| Add a dev-only test endpoint that mints a session | Backwards — D-15 forbids dev-mode shim | |

### Spike code location
| Option | Description | Selected |
|--------|-------------|----------|
| mobile/integration_test/ + spikes/flutter-api-roundtrip.md | Stays as regression test post-spike | ✓ |
| Throwaway script in spikes/ only | Loses regression value | |
| Tucked into mobile/test/ with mocked Dio | Violates Golden Rule #1 | |

### Spike size / time-box
| Option | Description | Selected |
|--------|-------------|----------|
| Half-day max — past that, foundation isn't ready | Spike is the gate | ✓ |
| Whatever it takes — no time-box | Risks scope creep | |

### Recipe + model for spike
**User chose freeform:** *"to test everything together? null claw + haiku"* — accepted: nullclaw + Claude Haiku 4.5. Real combo, exercises agent container path + real LLM round-trip.

| Option | Description | Selected |
|--------|-------------|----------|
| hermes + cheapest free OpenRouter model | Simplest validated recipe | |
| picoclaw + Sonnet 4.6 | Costs real money per spike run | |
| Pick at spike time | Inconsistent re-run risk | |
| nullclaw + Claude Haiku 4.5 (user's choice) | Real combo, real LLM | ✓ |

### Cleanup after spike
| Option | Description | Selected |
|--------|-------------|----------|
| POST /v1/agents/:id/stop + leave agent_instance row | Frees container, keeps row for inspection | ✓ |
| Full teardown (delete agent_instance + messages) | No /delete endpoint exists | |
| No cleanup | Stops accumulating containers | |

### Pass criteria
| Option | Description | Selected |
|--------|-------------|----------|
| Hard checks on each step (9 steps) | Fails loud with response body | ✓ |
| Soft checks — "saw something on each step" | Risks passing while a mechanism is broken | |

### BYOK key source
| Option | Description | Selected |
|--------|-------------|----------|
| --dart-define OPENROUTER_KEY=<key> from local .env | Never committed | ✓ |
| Read from a JSON file at known path | Risk of accidental commit | |
| Hardcode a free-tier key | Don't share keys | |

### Backend prereq check
**User pushback:** *"spike, backend pre req/???? dude, explain. we have api, you can test outside the app. we want to use inside app. whats the biggie here dude?????"*

Result: dropped the prereq check entirely. The spike's purpose is to validate the Flutter side; the backend is already validated by Phase 23's 49/49. Connection-refused is the prereq signal.

| Option | Description | Selected |
|--------|-------------|----------|
| GET /readyz first — abort with hint | Over-engineered | |
| Just hit /healthz | Partial-failure risk | |
| No prereq check — let it fail naturally | Connection-refused IS the signal | ✓ |

### Last-Event-ID resume coverage
| Option | Description | Selected |
|--------|-------------|----------|
| Yes — mid-stream cancel + reconnect with Last-Event-ID + assert no missed events | D-13 reconnect contract is the trickiest part | ✓ |
| No — just assert SSE delivers "a" reply | Skips the trickiest mechanism | |

### Cross-channel parity check
| Option | Description | Selected |
|--------|-------------|----------|
| Yes — fetch GET /messages and assert byte-equal to SSE | D-08 byte-identical guarantee verified | ✓ |
| Skip — SSE arrival is enough | Silent dispatcher bug risk | |

### Failure-mode capture format
| Option | Description | Selected |
|--------|-------------|----------|
| Print step + status + body + redacted headers | Mirrors api_server log redaction | ✓ |
| Print step + status code only | Forces re-runs to debug | |

### Platform-host alias handling
| Option | Description | Selected |
|--------|-------------|----------|
| Document in README — dev sets BASE_URL per target | Honors "dev handles env" rule | ✓ |
| App auto-rewrites localhost → 10.0.2.2 on Android | Hidden magic | |
| Use a .env.simulator / .env.emulator per platform | File-shuffling overhead | |

### Spike invocation
| Option | Description | Selected |
|--------|-------------|----------|
| make spike | One command, reproducible | ✓ |
| Document raw flutter command in markdown | Hostile to re-typing | |

### Phase 24 exit gate
| Option | Description | Selected |
|--------|-------------|----------|
| Hard gate — spike PASS required for APP-05 | Golden Rule #5 | ✓ |
| Soft gate — informational only | Defeats Golden Rule #5 | |

### Spike CI policy
| Option | Description | Selected |
|--------|-------------|----------|
| Local only — documented in README | macOS+iOS+Docker+OpenRouter not trivially in CI | ✓ |
| Add GitHub Actions job | Premature; v0.4+ work | |

### Spike artifact capture mode
| Option | Description | Selected |
|--------|-------------|----------|
| Manual capture after green run | Matches existing spikes/ convention | ✓ |
| Auto-emit — test runner writes markdown on PASS | Rigid output format | |

### Spike reproducibility metadata
| Option | Description | Selected |
|--------|-------------|----------|
| Yes — date, git SHA, Flutter version, recipe, model, BASE_URL, target | Enables future reproduction | ✓ |
| Just date + PASS verdict | Loses reproducibility | |

### Concurrent spike runs
| Option | Description | Selected |
|--------|-------------|----------|
| Each spike uses unique agent name | Two devs can run simultaneously | ✓ |
| Document "one spike at a time" in README | Honor system | |

### FVM symlink tracking
| Option | Description | Selected |
|--------|-------------|----------|
| Commit .fvmrc only; gitignore .fvm/flutter_sdk symlink | Standard FVM convention | ✓ |
| Commit both | Symlink is host-specific | |

### Environment validation at boot
| Option | Description | Selected |
|--------|-------------|----------|
| Fail loud on empty/malformed BASE_URL with fix-pointer | No silent fallback masking config errors | ✓ |
| Silent fallback to http://localhost:8000 | Wastes debug time | |

### Pagination on messages history client method
| Option | Description | Selected |
|--------|-------------|----------|
| Optional limit param (default 200, max 1000); no offset/cursor | Mirrors backend D-04 | ✓ |
| Add cursor param now for forward-compat | Backend doesn't support it | |

---

## Claude's Discretion

- Exact split of `lib/core/api/` files (one vs per-resource).
- Whether to use `riverpod_annotation` codegen or hand-write providers.
- Exact `ThemeData` field-by-field setup beyond the locked color tokens.
- Internal naming of the spike's helper functions.
- dio adapter choice (default `IOHttpClientAdapter`; `cronet_http` deferred).
- Whether to log every request/response in dev mode via the interceptor.
- Riverpod-managed singleton dio vs constructor-injected.
- Exact `ErrorCode` enum values mirrored from backend.

## Deferred Ideas

See `24-CONTEXT.md` `<deferred>` section.

---

## Notes on this discussion

The user pushed back hard at three points:
1. **Asked for an explanation of "typed API client style"** — first pass was too dense. Second pass with code samples got "wtf man, just USE the API" — accepted that hand-written is the obvious answer.
2. **Rejected in-app env-switcher entirely** — "API IS READY FUCKING USE API, DOES APP KNOWS ABOUT IP" — collapsed three sub-questions into `--dart-define` only.
3. **Rejected backend prereq check in the spike** — "we have api, you can test outside the app" — dropped the prereq probe.

Also clarified mid-discussion that "chrome" means UI framing, not the browser. Updated phrasing thereafter to "production-style UI shell" / "no developer overlays."

Re-asked "any gray areas?" multiple times per the `feedback_re_ask_gray_areas.md` memory — surfaced ATS, cleartext config, platform-host alias, env-validation, FVM symlink tracking, and a few others on later passes that the first pass missed.

---
phase: 25
slug: mobile-screens
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-03
---

# Phase 25 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> See `25-RESEARCH.md ## Validation Architecture` for the rubric this fills in.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | flutter_test (widget + unit) + integration_test (driver) + golden_toolkit (snapshots) |
| **Config file** | `mobile/test/flutter_test_config.dart` (Wave 1 task — loads fonts via `loadAppFonts()` for goldens) |
| **Quick run command** | `cd mobile && flutter test test/features/<feature>/` (per-screen widget tests) |
| **Full suite command** | `cd mobile && flutter test && flutter test --update-goldens=false` (unit + widget + golden, NOT integration) |
| **Integration command** | `cd mobile && make screens-e2e` (Wave 5 — drives a live local `api_server` per D-65) |
| **Estimated runtime** | ~5–15s widget+golden suite; ~60–120s integration spike |

---

## Sampling Rate

- **After every task commit:** `flutter test test/features/<feature>/` (per-feature subset; <5s)
- **After every wave:** `cd mobile && flutter test` (full unit+widget+golden; <30s)
- **Before phase verification:** `make screens-e2e` (Wave 5 integration spike) green AND `spikes/flutter-screens-roundtrip.md verdict: PASS` committed
- **Max feedback latency:** ~30s for wave-end sampling; ~120s for the exit-gate spike

---

## Per-Task Verification Map

> Task IDs follow the planner's wave-numbering. Threat refs are N/A — Phase 25 has no `<threat_model>` items beyond carry-forward (auth/Cookie/BYOK/url_launcher scheme allow-list, all already mitigated by Phase 23 + Phase 24 + D-46).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 25-01-* | 01 | 1 | UI-01,UI-02,UI-03 (substrate) | — | Login + cold-start + AuthService seam (D-66) + shared widgets render | widget | `cd mobile && flutter test test/features/login/ test/shared/` | ❌ W0 | ⬜ pending |
| 25-02-* | 02 | 2 | UI-01 | — | Dashboard renders empty / populated / error / loading states from `GET /v1/agents`; FAB + cycling banner; pull-to-refresh + lifecycle resume re-fetch | widget + golden | `cd mobile && flutter test test/features/dashboard/ test/golden/dashboard_*` | ❌ W0 | ⬜ pending |
| 25-03-* | 03 | 3 | UI-02 (amended) | — | 3-step wizard renders + scoped state preserved across back/forward; recipe cards + model picker push-route + dynamic Telegram fields per recipe metadata; pre-flight name-collision check; multi-channel deploy 1×/runs + N×/start | widget + integration | `cd mobile && flutter test test/features/new_agent/` | ❌ W0 | ⬜ pending |
| 25-04-* | 04 | 4 | UI-03 | — | Chat history loads via `GET /messages?limit=200` then SSE merges by message_id (or `seq` per Open Question #1); optimistic insert + dedup; failed-bubble retry generates NEW Idempotency-Key; markdown rendering; url_launcher https-only allow-list; restart + Telegram-failed banners | widget + integration | `cd mobile && flutter test test/features/chat/` | ❌ W0 | ⬜ pending |
| 25-05-* | 05 | 5 | UI-04 (full demo) + AMD-01 + AMD-02 | — | End-to-end: Login → Dashboard → wizard → Deploy → Chat → reply → kill → relaunch → history visible. AMD-01 lands REQUIREMENTS.md UI-02 rewrite. AMD-02 lands 23-CONTEXT.md D-28 amendment paragraph. | integration | `cd mobile && make screens-e2e` + `cat spikes/flutter-screens-roundtrip.md \| grep '^verdict: PASS'` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*"❌ W0" = file does not exist yet; created during Wave 1 (test config) or per-feature wave.*

---

## Wave 0 Requirements

> Wave 0 here means "files that must exist BEFORE Wave 1 task implementations can verify themselves." 25-RESEARCH.md ## Implementation Approach also flags 2 dedicated Wave-0 spikes (real OAuth on a device + SSE envelope shape) — those land via dedicated plans before Wave 1 seals.

- [ ] `mobile/test/flutter_test_config.dart` — global font loading via `golden_toolkit.loadAppFonts()` so goldens are deterministic
- [ ] `mobile/test/golden/` — directory for screenshot snapshots
- [ ] `mobile/test/shared/`, `mobile/test/features/login/`, `mobile/test/features/dashboard/`, `mobile/test/features/new_agent/`, `mobile/test/features/chat/` — per-feature test dirs (created as each wave's first task)
- [ ] `mobile/integration_test/screens_e2e_test.dart` — Wave 5 exit-gate driver (extends `spike_api_roundtrip_test.dart` harness shape)
- [ ] `mobile/Makefile` — `make screens-e2e` target mirroring `make spike` (BASE_URL + SESSION_ID `--dart-define`)
- [ ] `pubspec.yaml` deps: `flutter_markdown_plus` (per AMD-03), `url_launcher`, `golden_toolkit` (Wave 1)
- [ ] `mobile/ios/Runner/Info.plist` — `LSApplicationQueriesSchemes` entries for https/http (per Pitfall #5 in 25-RESEARCH)
- [ ] **Wave-0 spike A** (suggested): real-OAuth diligence — boot `LoginScreen` against a Google Cloud Console iOS+Android client; capture PASS in `spikes/flutter-google-signin-7x.md`
- [ ] **Wave-0 spike B** (open question #1): live SSE envelope inspection on `/v1/agents/:id/messages/stream` to confirm dedup key (`inapp_message_id` vs `seq`)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Native OAuth sheet (Google + GitHub) on real device | UI-01 substrate / D-66 real impl | The native sheet cannot be driven by `WidgetTester`; the AuthService test seam (D-66) injects a `SESSION_ID` for automated runs. Real path is verified by Wave 5 manual smoke. | (a) Run `cd mobile && flutter run --release` on a real iOS device + Android emulator. (b) Tap Continue with Google → sheet appears → complete sign-in → land on Dashboard. (c) Repeat with GitHub. (d) Capture screenshot evidence in `spikes/flutter-screens-roundtrip.md`. |
| Visual fidelity vs `25-UI-SPEC.md` mockups (Solvr theme + JetBrains Mono / Inter + corner radius 0) | All UI-* | Pixel-perfect + perceptual review is not automatable; goldens catch regressions but not first-time correctness against design intent. | Side-by-side compare each screen with the relevant `25-UI-SPEC.md` section; record deviations as PR notes. |
| Telegram pairing live round-trip (toggle ON, deploy, message bot from real Telegram client, see reply) | UI-02 (amended via AMD-01) | End-to-end Telegram requires a live bot token + a real Telegram user opening a chat. The /start API path is automatable (returns container ID); the chat-from-Telegram side is manual. | (a) Toggle Telegram ON in wizard. (b) Provide live `TELEGRAM_BOT_TOKEN` + your numeric Telegram user ID. (c) Deploy. (d) Open the bot in Telegram, send "hi", verify a reply lands. (e) Capture in spike artifact. |
| iOS Simulator + Android Emulator parity for full demo | UI-04 | One-time per-platform smoke is the only way to prove env-config switching works on both targets. | Run the full demo flow on each target with `BASE_URL` set appropriately. Capture PASS rows in `spikes/flutter-screens-roundtrip.md` matrix. |

---

## Validation Sign-Off

- [ ] All tasks have either an automated verify command OR a Wave-0 listed dependency the planner ties them to
- [ ] Sampling continuity: per-wave full-suite run after every wave; no 3 consecutive tasks without automated feedback (each task has at least a per-feature `flutter test` invocation in `<acceptance_criteria>`)
- [ ] Wave 0 (file scaffolding + 2 suggested spikes) closes BEFORE Wave 1 implementation tasks begin
- [ ] No watch-mode flags (CI-shape `flutter test` only; integration uses `flutter drive` / `flutter test integration_test/`)
- [ ] Feedback latency < 30s for wave-end full suite; < 120s for Wave 5 exit gate
- [ ] `nyquist_compliant: true` set in frontmatter once planner confirms every requirement (UI-01..UI-04) maps to ≥1 plan with ≥1 grep-verifiable acceptance criterion

**Approval:** pending

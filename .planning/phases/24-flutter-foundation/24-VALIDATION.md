---
phase: 24
slug: flutter-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-02
---

# Phase 24 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `flutter_test` (unit/widget) + `integration_test` (spike) — both Flutter SDK bundled |
| **Config file** | `mobile/analysis_options.yaml` (lint config); `mobile/pubspec.yaml` (test deps) |
| **Quick run command** | `cd mobile && fvm flutter analyze && fvm flutter test` |
| **Full suite command** | `cd mobile && fvm flutter analyze && fvm flutter test && make spike` (spike requires live api_server + simulator/emulator + BASE_URL/SESSION_ID/OPENROUTER_KEY) |
| **Estimated runtime** | ~30s unit suite; ~2–4 min `make spike` end-to-end |

---

## Sampling Rate

- **After every task commit:** Run `cd mobile && fvm flutter analyze && fvm flutter test`
- **After every plan wave:** Run `cd mobile && fvm flutter analyze && fvm flutter test` (full unit suite)
- **Before `/gsd-verify-work`:** Unit suite green AND `make spike` green AND `spikes/flutter-api-roundtrip.md` recorded with `verdict: PASS`
- **Max feedback latency:** 30s (unit), 4 min (spike — local-only per D-53)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 24-01-* | 01 (FVM scaffold) | 1 | APP-01 | — | N/A | smoke | `cd mobile && fvm flutter analyze && fvm flutter test` | ❌ W0 | ⬜ pending |
| 24-02-* | 02 (theme + placeholder) | 2 | APP-02 | — | N/A | widget | `fvm flutter test test/theme/solvr_theme_test.dart` | ❌ W0 | ⬜ pending |
| 24-03-* | 03 (Result + ApiError) | 2 | APP-03 | — | N/A | unit | `fvm flutter test test/api/result_test.dart test/api/api_error_test.dart` | ❌ W0 | ⬜ pending |
| 24-04-* | 04 (api_client + interceptor + BYOK) | 3 | APP-03 | — | Cookie/Authorization redaction in dev logs | unit | `fvm flutter test test/api/api_client_test.dart test/api/auth_interceptor_test.dart` | ❌ W0 | ⬜ pending |
| 24-05-* | 05 (MessagesStream Last-Event-ID wrapper) | 3 | APP-03 | — | N/A | unit | `fvm flutter test test/api/messages_stream_test.dart` | ❌ W0 | ⬜ pending |
| 24-06-* | 06 (env + boot validation) | 3 | APP-04 | — | Fail loud on empty BASE_URL — no silent fallback | unit | `fvm flutter test test/env/app_env_test.dart` | ❌ W0 | ⬜ pending |
| 24-07-* | 07 (native platform setup: ATS / cleartext / URL scheme / orientation) | 1 | APP-01, APP-04 | — | iOS ATS exempts only localhost+local networks; Android cleartext debug-only | smoke | `cd mobile && fvm flutter build ios --debug --no-codesign && fvm flutter build apk --debug` | ❌ W0 | ⬜ pending |
| 24-08-* | 08 (CI workflow + Makefile + lints) | 4 | APP-01 | — | N/A | smoke | `make doctor && make get && make test` | ❌ W0 | ⬜ pending |
| 24-09-* | 09 (spike integration test) | 4 | APP-05 | — | Spike redacts Cookie + Authorization to last 8 chars per D-52 | integration | `make spike BASE_URL=$BASE_URL SESSION_ID=$SESSION_ID OPENROUTER_KEY=$OPENROUTER_KEY` | ❌ W0 | ⬜ pending |
| 24-10-* | 10 (spike artifact capture) | 5 | APP-05 | — | Artifact does not record raw OPENROUTER_KEY (only its presence) | manual | dev writes `spikes/flutter-api-roundtrip.md` after green run | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `mobile/test/theme/solvr_theme_test.dart` — covers APP-02 (light theme + Inter + JetBrains Mono + corner radius 0)
- [ ] `mobile/test/api/result_test.dart` — covers APP-03 sealed-class exhaustive-switch
- [ ] `mobile/test/api/api_error_test.dart` — covers APP-03 `ApiError.fromDioException` across all `ErrorCode` enum values mirrored from `api_server/src/api_server/errors.py`
- [ ] `mobile/test/api/api_client_test.dart` — covers APP-03 typed-endpoint happy paths via dio `MockAdapter`
- [ ] `mobile/test/api/auth_interceptor_test.dart` — covers APP-03 cookie injection from `flutter_secure_storage` + 401-clear behavior + per-request BYOK injection (D-35, D-40)
- [ ] `mobile/test/api/messages_stream_test.dart` — covers APP-03 SSE wrapper Last-Event-Id tracking + manual reconnect (Pitfall #2 mitigation per RESEARCH §Pattern 5)
- [ ] `mobile/test/env/app_env_test.dart` — covers APP-04 fail-loud boot validation (D-43)
- [ ] `mobile/integration_test/spike_api_roundtrip_test.dart` — covers APP-05 9-step round-trip (D-45/D-46)
- [ ] Framework install: `fvm install 3.41.0 && fvm use 3.41.0` once per machine inside `mobile/`
- [ ] CI workflow `.github/workflows/mobile.yml` — runs `fvm flutter analyze && fvm flutter test` on push to `mobile/**` (no integration_test in CI per D-27 / D-53)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| App boots on iOS Simulator and lands on `/healthz` placeholder | APP-01 | Requires macOS + Xcode + booted Simulator; not feasible in CI for v0.3 | `cd mobile && fvm flutter run -d <simulator-id> --dart-define BASE_URL=http://localhost:8000` |
| App boots on Android Emulator and lands on `/healthz` placeholder | APP-01 | Requires booted Android Emulator | `cd mobile && fvm flutter run -d <emulator-id> --dart-define BASE_URL=http://10.0.2.2:8000` |
| Theme visually matches Solvr Labs light-mode tokens (sample widget renders Inter + JetBrains Mono + flat corners) | APP-02 | Pixel-level visual sign-off requires running app | Compare placeholder screen to `/Users/fcavalcanti/dev/solvr/frontend/` reference |
| `make spike` green against running api_server + Docker + OpenRouter | APP-05 | Local-only per D-53 (no macOS+Docker+Network in CI) | `make spike BASE_URL=... SESSION_ID=... OPENROUTER_KEY=...` after `cd api_server && make dev` |
| Spike artifact `spikes/flutter-api-roundtrip.md` captured with `verdict: PASS` + reproducibility metadata | APP-05 | Manual capture after green run per D-54 | Dev writes markdown after green spike, commits |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s (unit) / < 4 min (spike, local-only)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

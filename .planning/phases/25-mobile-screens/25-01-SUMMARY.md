---
plan: 01
phase: 25-mobile-screens
type: execute
wave: 0
status: complete
date: 2026-05-03
---

# Phase 25 Plan 01 — Wave 0 OAuth + SSE Diligence Spikes — SUMMARY

Wave 0 closes the only LOW-confidence open questions in 25-RESEARCH.md
before Wave 1 seals AuthService and Wave 4 seals chat dedup.

## Verdicts

| Spike | File | Verdict | Decision |
|-------|------|---------|----------|
| A — Real OAuth (google_sign_in 7.x + flutter_appauth 12.x) | `spikes/flutter-google-signin-7x.md` | **PASS** | iOS Simulator confirmed: Google id_token non-null, GitHub callback round-trips. Android deferred to v0.3 per D-32. |
| B — SSE envelope inspection (dedup key) | `spikes/flutter-sse-envelope-inspect.md` | **PASS** with `dedup_key: seq` | SSE envelope lacks `inapp_message_id`; chat dedup must key on `seq`. RESEARCH.md amended. |

## Tasks committed

| Task | Commit | Notes |
|------|--------|-------|
| Task 2 (Spike B) | `09553d1` | Captured live SSE envelope + history-row sample; amended 25-RESEARCH.md with one-line decision note. |
| Task 1 (Spike A) | `0c9b92e` | Captured iOS Simulator PASS for both Google + GitHub; kept Info.plist Google reversed-client-id URL scheme; deleted temp `lib/spike_oauth.dart` scaffolding. |

## Hand-off notes for Wave 1

### Plan 25-02 (Foundation + AuthService)

- **AuthService real-impl proceeds with `google_sign_in` 7.x verbatim**
  per 25-RESEARCH §3. The v6→v7 API rewrite shipped as expected
  (`GoogleSignIn.instance.initialize()` + `attemptLightweightAuthentication()`
  + `authenticate()` + `account.authentication.idToken` non-null).
- D-66 test seam still ships (`auth_service_test_seam.dart`) for
  unit-test parallelization, but the production iOS path no longer
  depends on it.
- `AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS` env is populated with the iOS
  client ID `303159181051-bb29s5i9cgbii8dlkirlnupgdi1jh8r7.apps.googleusercontent.com`.
- Info.plist Google reversed-client-id URL scheme is registered.

### Plan 25-07 (Chat dedup)

- **AMENDMENT to D-36**: chat dedup Map keys on `seq` (int), NOT
  `inappMessageId` (String). The SSE inapp_outbound envelope on the
  wire is `{seq, kind, payload:{source, content, captured_at}, correlation_id, ts}`
  with NO `inapp_message_id` field.
- History rows from `GET /v1/agents/{id}/messages` DO carry
  `inapp_message_id`, but those IDs identify user-assistant interaction
  PAIRS (both user message and assistant reply share one ID), not
  individual messages — do not use `inapp_message_id` as a per-row
  dedup key.
- Recommended Wave 4 chat row key: `(role, seq)` for SSE arrivals,
  `(role, created_at)` for history rows, with cross-correlation by
  content-equality OR a small replay-window dedup heuristic.

### Plan 25-08 (Wave 5 e2e)

- Add `--dart-define GOOGLE_WEB_CLIENT_ID=…` to the run script when
  the Web Client ID is provisioned in `.env`. The backend audience
  verify accepts the iOS client ID alone, but the Web Client ID
  provides defense-in-depth and matches Phase 22c-oauth-google
  contract.
- Real OAuth flow now works end-to-end on iOS Simulator → backend
  audience verify → session cookie. Wave 5 can drop the Phase 24
  `D-49` browser-cookie spike helper if the env has all three OAuth
  IDs populated.

## Wave 0 cleanup

- `mobile/lib/main.dart` — UNCHANGED (Wave 0 scaffolding lived in a
  separate `lib/spike_oauth.dart` entry point that was deleted).
- `mobile/ios/Runner/Info.plist` — added one extra `<dict>` to
  `CFBundleURLTypes` for the Google reversed-client-id scheme; kept
  because Wave 1 plan 25-02 needs it.
- No production code under `mobile/lib/core/` or `mobile/lib/features/`
  was touched.

## Acceptance criteria

- [x] `spikes/flutter-google-signin-7x.md` exists with `verdict: PASS`
- [x] `spikes/flutter-sse-envelope-inspect.md` exists with `dedup_key: seq`
- [x] `25-RESEARCH.md` has the one-line `Wave 0 Spike B verdict` note prepended (because dedup_key=seq)
- [x] No new files under `mobile/lib/core/` or `mobile/lib/features/`
- [x] Both artifacts mirror `spikes/flutter-api-roundtrip.md` frontmatter shape
- [x] User explicitly confirmed Spike A PASS via the resume-signal channel

## Self-Check: PASSED

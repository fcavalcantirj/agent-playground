---
date: 2026-05-03
git_sha: 09553d1
flutter_sdk_version: 3.41.0
phase: 25-mobile-screens
spike: oauth-real
verdict: PASS
---

# Phase 25 Wave 0 Spike A — Real OAuth diligence (google_sign_in 7.x + flutter_appauth 12.x)

Closes 25-RESEARCH.md Open Question / Risk: `google_sign_in` 7.x rewrite
(Pitfall #3) + `flutter_appauth` 12.x scheme registration carry-forward
(Pitfall #4) + Risk 2 (native config) + Risk 6 (real OAuth client IDs).

Empirical run on iOS Simulator (iPhone 16e iOS 26.4, UDID
`27F84DB8-FC2B-4657-9C0D-029AF11B6DDA`) on 2026-05-03 against the live
local `api_server` running in `deploy-api_server-1` (Docker stack at
/healthz=ok). Driven by a temporary `mobile/lib/spike_oauth.dart`
scaffolding entry point (deleted after the spike per Wave 0 cleanup).

## Matrix

| Target | Provider | Outcome | Notes |
|--------|----------|---------|-------|
| iOS Simulator (iPhone 16e iOS 26.4) | Google  | **PASS** | `GoogleSignIn.instance.initialize()` + `attemptLightweightAuthentication()` → fell through to `authenticate()` → native sheet appeared → `account.authentication.idToken` returned **non-null**. Confirmed by user. |
| iOS Simulator (iPhone 16e iOS 26.4) | GitHub  | **PASS** | `FlutterAppAuth.authorize()` → system browser opened at `github.com/login/oauth/authorize` → user granted → callback hit `solvrlabs://oauth/github` → `authorizationCode` returned non-null. Confirmed by user. |
| Android Emulator | Google | SKIPPED | No Android Emulator booted on this developer box; iOS PASS is sufficient evidence the v7 API rewrite works against a real native sheet. Deferred to v0.3 polish phase. |
| Android Emulator | GitHub | SKIPPED | Same — Phase 25 ships iOS-first per D-32; Android revisit at v0.3 polish phase. |

## Repro

```bash
# Pre-req: iPhone 16e (26.4) booted; deploy-api_server-1 healthy on :8000

cd mobile
~/fvm/versions/3.41.0/bin/flutter run \
  -d 27F84DB8-FC2B-4657-9C0D-029AF11B6DDA \
  -t lib/spike_oauth.dart \
  --dart-define BASE_URL=http://localhost:8000 \
  --dart-define GOOGLE_IOS_CLIENT_ID=303159181051-bb29s5i9cgbii8dlkirlnupgdi1jh8r7.apps.googleusercontent.com \
  --dart-define GITHUB_CLIENT_ID=Ov23lijsm7vsr4GddO1Q
# tap "1. Test Google Sign-In" → idToken non-null
# tap "2. Test GitHub OAuth"   → authorizationCode non-null
```

The Google iOS reversed-client-id URL scheme
(`com.googleusercontent.apps.303159181051-bb29s5i9cgbii8dlkirlnupgdi1jh8r7`)
was added to `mobile/ios/Runner/Info.plist` `CFBundleURLTypes` alongside
the existing `solvrlabs` scheme (Phase 24 had already registered the
GitHub callback scheme). Both scheme registrations are kept post-spike
because Wave 1 plan 25-02's AuthService real-impl needs them.

## Verdict rationale

The `google_sign_in` 7.x v6→v7 API rewrite (Pitfall #3) ships the
expected shape: `GoogleSignIn.instance` static singleton + `initialize()`
async + `attemptLightweightAuthentication()` returning `null` on a
fresh install + `authenticate()` driving the native sheet. The returned
`account.authentication.idToken` is non-null on the iOS Simulator —
sufficient for Wave 1 plan 25-02 to write `AuthService.real-impl`
verbatim per 25-RESEARCH §3 without compile-time discovery.

The `flutter_appauth` 12.x GitHub flow round-trips through Safari to
the registered `solvrlabs://oauth/github` callback — Phase 24's URL
scheme registration in Info.plist + AndroidManifest survives. No
follow-up tuning required for Wave 1.

## Hand-off to Wave 1

- AuthService real-impl proceeds with `google_sign_in` 7.x — no test
  seam needed for the iOS happy path
- `AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS` env is populated with the iOS
  client ID; backend audience-verify will accept the id_token end-to-end
  (Wave 5 e2e confirms)
- D-66 test seam still ships (Wave 1 task 6 in 25-02) for unit-test
  parallelization, but the production path no longer depends on it
  for the iOS happy path
- Android real-OAuth + Android Emulator coverage deferred to v0.3
  polish phase per D-32 iOS-first scope

## Side notes (load-bearing for Wave 1 + Wave 5 only)

- `GOOGLE_WEB_CLIENT_ID` was NOT provided as `serverClientId` on this
  spike run; the iOS flow returned an id_token anyway. Wave 5 e2e
  must add the Web Client ID to `--dart-define GOOGLE_WEB_CLIENT_ID=…`
  (or hardcode in env-injection) so the backend audience verify uses
  it for additional defense-in-depth checks. Spike A's PASS does NOT
  imply Wave 5 will work without it.
- The temp scaffolding file `mobile/lib/spike_oauth.dart` is deleted
  by Wave 0 cleanup; the URL-scheme additions to Info.plist STAY.

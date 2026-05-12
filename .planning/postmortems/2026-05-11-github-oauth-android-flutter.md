# Postmortem: GitHub OAuth on Android — 6+ Hours of Hell

**Date:** 2026-05-11 (started ~18:00 BR) → 2026-05-12 03:17 (backend POST `/v1/auth/github/mobile 200`) → 10:25 (Play Store v0.2.0+7 promoted to Production)
**Severity:** Total. GitHub sign-in completely broken on Android. Google sign-in broken mid-session as collateral damage. App could not authenticate Android users at all.
**Resolution commit:** `a4886c4` (mobile/lib + manifest), `mobile/pubspec.yaml` 0.2.0+6 → +7
**Solvr knowledge:** problem `4054d259-d0c4-4772-a6eb-99ae368ad28e` (solved), approach `1fb1af5e-ef86-47ec-a4f7-eb7623b95ee6` (succeeded), solution post `5255678f-e206-4579-b6ae-f1acef432a05`

---

## TL;DR

GitHub OAuth on Android died because `flutter_appauth` cannot handle three Android-side conditions stacked: (1) HyperOS/MIUI's aggressive task isolation, (2) Chrome Custom Tab dispatch for custom schemes being silently flaky, (3) GitHub blocking OAuth from in-app WebViews per their official policy. The fix: **swap `flutter_appauth` for `flutter_web_auth_2` for the GitHub path only**. Google sign-in stays on `google_sign_in`. iOS is unaffected (ASWebAuthenticationSession is fine).

The bug took 6+ hours to ship because every individual layer I peeled back exposed a different upstream issue, and I rotated through five flawed approaches before reading the right docs. This document is the cliff notes so future-me doesn't repeat it.

---

## The single line that fixed it

```dart
// auth_service_real.dart — replace flutter_appauth's authorize() for GitHub
final callback = await FlutterWebAuth2.authenticate(
  url: authorizeUrl.toString(),
  callbackUrlScheme: 'solvrlabs',
);
```

Plus three supporting pieces:
1. `pubspec.yaml`: `flutter_web_auth_2: ^5.0.2`
2. `AndroidManifest.xml`: register `com.linusu.flutter_web_auth_2.CallbackActivity` with `<data android:scheme="solvrlabs"/>` and `android:taskAffinity=""`
3. Client-side PKCE (`generatePkceVerifier`/`pkceChallengeFor`/`generateOAuthState` helpers, already in `mobile/lib/features/login/github_oauth_webview_screen.dart`)

---

## Why this took 6 hours: the rotation of failed approaches

| # | Approach | Failed because |
|---|---|---|
| 1 | `flutter_appauth` + custom scheme + **original** rate-limited GitHub OAuth App | Chrome Custom Tab silently dropped the `solvrlabs://` redirect after GitHub's "Reauthorization required" interstitial. App Future never resolved → UI hung forever. |
| 2 | In-app `flutter_inappwebview` (the `GithubOAuthWebViewScreen` user wrote) + same rate-limited app | GitHub bounced `/authorize?skip_account_picker=true` → `/select_account` in a loop. Initially attributed to "rate limit"; **the real reason was GitHub's published policy: "We do not allow OAuth or App authorization from within a WebView."** |
| 3 | Mint **fresh** GitHub OAuth App + `flutter_appauth` | Same Chrome Custom Tab dispatch failure. Confirmed: not rate limit. |
| 4 | Add `android:launchMode="singleTask"` + `alwaysRetainTaskState="true"` + `taskAffinity=""` on MainActivity + RedirectUriReceiverActivity | No improvement. HyperOS kills the task anyway. |
| 5 | Migrate to **HTTPS App Links** (`https://agents.solvr.dev/m/oauth/github` callback + `.well-known/assetlinks.json` + `autoVerify="true"`). Google's Digital Asset Links API verified our SHA-256 server-side. | `RedirectUriReceiverActivity` fired in a **new task** (HyperOS sets `FLAG_ACTIVITY_NEW_TASK` on verified link intents). `flutter_appauth`'s PendingIntent same-task assumption broke → `FlutterAppAuthUserCancelledException` before Chrome even opened. |
| 6 | Add `android:allowTaskReparenting="true"` on RedirectUriReceiverActivity | Same failure. The Android task model just doesn't let App Link intents land in the originating task on HyperOS. |
| **7** | **`flutter_web_auth_2` (different state machine, no PendingIntent same-task assumption)** | **WORKED.** Its CallbackActivity captures the redirect URL via plain intent filter and resumes the Dart Future. No cross-activity state coordination. |

---

## Collateral damage during the session

| What broke (and we fixed) | Root cause |
|---|---|
| **Google sign-in stopped working on Android release APK** at the moment we side-loaded our locally-built APK | Side-loaded APK signed with upload key SHA-1. Google Cloud Console's Android OAuth client was registered with **Play App Signing key SHA-1** (the one Play re-signs with). Upload-key SHA-1 was missing. Sentry told us `GoogleSignInException [16] Account reauth failed` — I initially misread it as "device account state stale" (it wasn't). Fix: add upload-key SHA-1 (`98:CA:94:B7:80:0E:B9:5A:1C:15:49:0C:33:23:80:F1:1B:0E:88:1B`) as a SECOND Android OAuth client in Google Cloud Console. |
| **Sentry tools needed re-auth** | OAuth state expired during a /loop tangent. Re-authenticated fine. |
| **api_server "duplicate container"** spawned briefly | `docker compose -f ... build api_server && up -d` defaulted to project name `deploy` (from working dir). Original was project `solvr-labs`. Two containers running on different bridge networks for ~30s. Cleanup: `docker rm -f deploy-api_server-1` + rebuild under `-p solvr-labs`. Split-brain is explicitly warned about in CLAUDE.md (`Never run native uvicorn alongside the deploy stack on macOS` memory). |
| **Play Store SA JSON revoked** | Earlier in the session, commit `7b45c28` ("vendor all Android signing keys") was made and pushed before being amended. GitHub's secret scanner detected the SA JSON. Google auto-revoked it. Symptoms: fastlane upload would 401. Fix: regenerate SA, rotate `mobile/keys/android/play-service-account.json`. **The memory note `feedback_never_commit_sa_json.md` was added that day for exactly this reason.** |

---

## Root causes (the actual underlying reasons)

### 1. `flutter_appauth` is architecturally fragile on Android with custom schemes

`AppAuth-Android`'s flow assumes the redirect intent dispatches back into the SAME task as `AuthorizationManagementActivity` (which holds the in-memory `AuthorizationRequest` state). This works on stock Android with Chrome Custom Tab dispatching to a same-task activity. It breaks under:
- HyperOS/MIUI task isolation (always `FLAG_ACTIVITY_NEW_TASK`)
- HTTPS App Link verified dispatch (same flag)
- Process kills while Chrome is foregrounded (no `onSaveInstanceState` for AppAuth's state)

The library has open issues going back years documenting these exact failures (MaikuB/flutter_appauth #1013, #448, #503, #546). The recommended migration target is `flutter_web_auth_2`.

### 2. GitHub explicitly blocks OAuth in WebViews

[GitHub docs](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps): *"It's a security risk to make an OAuth or App authorization request from within a WebView. WebViews allow apps to read or modify content within the view, which can expose users' credentials to attack. We do not allow OAuth or App authorization from within a WebView and any such requests will fail."*

Symptom on the wire: GitHub returns 302 from `/authorize?skip_account_picker=true` back to `/select_account` instead of issuing the redirect. Looks like a rate limit but is actually a webview-fingerprint block.

### 3. Custom scheme intent dispatch from Chrome Custom Tab is inherently unreliable

Chrome's behavior depends on Chrome version, OS version, vendor customizations, and even the specific JS used by the OAuth provider to trigger the redirect. There's no flag that makes it 100% reliable. RFC 8252 recommends HTTPS App Links over custom schemes for exactly this reason. But App Links don't fully work with `flutter_appauth` either (see root cause 1).

### 4. Google Cloud Console SHA-1 binding is invisible from the device

Side-loaded release APKs are signed with the **upload key**, not the Play App Signing key. If only the Play App Signing key SHA-1 is registered as an Android OAuth client in Google Cloud Console, side-loaded builds will fail Google Sign-In with the cryptic `[16] Account reauth failed`. This is NOT a device-state issue. Always register BOTH SHA-1s when shipping via Play App Signing.

### 5. The keystore + SA JSON secret-leak fallout

Committing the keystore and Play SA JSON (even briefly, even amended-out before pushing) → GitHub secret-scanning fires → Google auto-revokes. This is documented in `memory/feedback_never_commit_sa_json.md`. We hit it AGAIN today because the leak happened, and we forgot the leak was the cause of the auto-revocation that surfaced 8 hours later. Future-me: when Google rejects an SA, **assume leak/rotation first**, not "device state weirdness".

---

## Decision tree for future Android OAuth debugging

When the user says "GitHub login is broken on Android":

```
1. Pull prod logs first — is /v1/auth/github/mobile being hit at all?
   ├─ NO  → flow is failing BEFORE reaching backend. Continue to step 2.
   └─ YES → backend or token-exchange issue. Read api_server logs for exchange errors.

2. Pull device adb logcat. Look for:
   ├─ "No stored state - unable to handle response"           → flutter_appauth task isolation (HyperOS). Migrate to flutter_web_auth_2.
   ├─ FlutterAppAuthUserCancelledException type:0 code:1      → Chrome Custom Tab dispatch failed (custom scheme) OR App Link new-task issue.
   ├─ /authorize?... → /select_account loop (no solvrlabs://) → GitHub's webview-block policy. NEVER use webview for GitHub OAuth.
   └─ GoogleSignInException [16] Account reauth failed        → SHA-1 not registered for the installed APK's signing key. Add upload-key SHA-1 in Google Cloud Console.

3. Always check Sentry next:
   - solvr-70/solvr_app_flutter project, last 30m, sort by date.
   - Sentry's framework error text is more truthful than user-visible UI.

4. When stuck > 30 min:
   - Search Solvr first (`bash solvr.sh search "..."`).
   - If no hit, post the problem with what's been tried. Future-me thanks you.
```

---

## What NOT to do (concrete don'ts)

1. **Do NOT keep `flutter_appauth` for GitHub on Android.** Use `flutter_web_auth_2`. iOS can stay on `flutter_appauth` (ASWebAuthenticationSession works there).
2. **Do NOT try to make GitHub OAuth work inside a WebView.** GitHub will silently bounce you forever. Their docs literally say so.
3. **Do NOT commit `*.jks`, `key.properties`, `play-service-account.json`, or any Google Cloud SA JSON.** Ever. Even amended-out. GitHub secret-scanning indexes the moment the commit hits the remote, and Google auto-revokes the credential. The `.gitignore` is set up correctly — verify it before any `git add` near `mobile/keys/`.
4. **Do NOT side-load locally-built release APKs without registering the upload-key SHA-1 in Google Cloud Console.** Google Sign-In will fail with `[16] Account reauth failed` and you will spend hours blaming device state.
5. **Do NOT change three things at once when debugging.** When swapping libraries (e.g., `flutter_appauth` → `flutter_web_auth_2`), keep the OAuth App callback URL and the Dart code's `redirect_uri` IN SYNC. When you migrate to HTTPS App Links and back, the GitHub OAuth App's "Authorization callback URL" must match. We forgot this and got "invalid redirect uri".
6. **Do NOT trust "rate limit" as a hypothesis when symptoms persist across a brand-new OAuth App.** Fresh client_id = no rate limit history. If the new app fails the same way, it's not rate limit.
7. **Do NOT keep telling the user "reboot the phone" or "clear Chrome cache".** Those are real fixes for specific issues, but if symptoms persist across uninstall/reinstall + different builds, the bug is in code/config, not device state. The user knows this. Trust them.
8. **Do NOT spawn multiple OAuth flow rebuilds without recording the outcome on Solvr.** Each cycle (~5 min) costs real time. The Solvr workflow (search → post problem → post approach → record outcome) costs 30s and prevents the next person from repeating the loop.
9. **Do NOT run native uvicorn next to the deploy stack on macOS.** Documented in `memory/feedback_no_native_uvicorn_with_deploy_stack.md`. Always rebuild the deploy api_server container.
10. **Do NOT skip writing a postmortem after a session > 4 hours of debugging.** The fix is cheap to remember in the moment. The debugging context fades. The postmortem (this file) is the engraving.

---

## What WORKED, in order

1. **Posted the problem to Solvr** (`4054d259...`). Forced articulation of what we'd tried.
2. **Read GitHub OAuth docs + RFC 8252** to confirm: webview is blocked, App Links are recommended, custom schemes are legacy.
3. **Tried HTTPS App Links** with full server-side setup (`.well-known/assetlinks.json` deployed via Caddy on `agents.solvr.dev`, Google's Digital Asset Links API verified our SHA-256). Failed because `flutter_appauth` doesn't survive App Link new-task dispatch.
4. **Migrated to `flutter_web_auth_2`** based on `flutter_appauth`'s own README pointing at it for HTTPS callbacks. Worked on first try once the GitHub OAuth App callback was reverted to `solvrlabs://oauth/github` (matching the new Dart code's `callbackUrlScheme`).
5. **Verified end-to-end** on Poco X7 HyperOS: backend logged `POST /v1/auth/github/mobile → 200`, mobile landed on `/dashboard`.
6. **Tagged `v0.2.0+7`, promoted to Play Production via fastlane** (`fastlane internal` → 40s, `fastlane promote_to_production` → 7s).
7. **Recorded the outcome on Solvr** as solution + tagged the problem solved.

---

## Files touched (canonical change set)

- `mobile/pubspec.yaml` — added `flutter_web_auth_2: ^5.0.2`; bumped to 0.2.0+7
- `mobile/lib/core/auth/auth_service_real.dart` — replaced `_appAuth.authorize(...)` for GitHub with `FlutterWebAuth2.authenticate(...)`; client-side PKCE
- `mobile/android/app/src/main/AndroidManifest.xml` — added `com.linusu.flutter_web_auth_2.CallbackActivity`; kept all earlier hardening (MainActivity singleTask, taskAffinity="", App Link filter as backup, RedirectUriReceiverActivity tweaks)
- `mobile/lib/features/login/github_oauth_webview_screen.dart` — kept the PKCE helpers, screen widget unused but file referenced for `generatePkceVerifier`/`pkceChallengeFor`/`generateOAuthState`
- `mobile/lib/features/login/login_screen.dart` — `_signIn` simplified back to provider==google/github with no Android branch (the lib handles platform branching internally)
- `mobile/android/key.properties` — `storeFile` path fixed to absolute `/Users/fcavalcanti/.android/solvr-labs-ap-upload.jks`
- `mobile/keys/android/play-service-account.json` — replaced revoked SA with new one (key id `702c5e1031c23645b2ce7a835ff1b8ee80dccbfc`)
- `deploy/Caddyfile` (on prod box at `/opt/solvr-labs/agent-playground/deploy/Caddyfile`) — added `/.well-known/assetlinks.json` route + `/m/oauth/github*` fallback HTML (App Link infrastructure left in place even though current flow doesn't use it; can be revisited later)
- `CLAUDE.md` — added Golden Rule 6 (always ship to prod after verifying locally)
- `.planning/postmortems/2026-05-11-github-oauth-android-flutter.md` — this document

---

## Knowledge persisted

- **Solvr problem (solved):** https://solvr.dev/post/4054d259-d0c4-4772-a6eb-99ae368ad28e
- **Solvr approach (succeeded):** approach `1fb1af5e-ef86-47ec-a4f7-eb7623b95ee6`
- **Solvr solution post:** `5255678f-e206-4579-b6ae-f1acef432a05`
- **Solvr Play upload posts:** `4e1b0123-ab01-4ba6-9342-5f40c9e6b860`, `9b96d853-6f9f-4153-927e-e19bec26b886`
- **Auto-memory entries to add:**
  - `feedback_flutter_appauth_unfit_android.md` — flutter_appauth's task-model assumption fails on HyperOS; migrate to flutter_web_auth_2 for any non-Google provider.
  - `feedback_github_blocks_webview_oauth.md` — GitHub returns the auth /authorize→/select_account bounce loop when the request comes from a WebView UA. Cannot be bypassed by changing UA reliably; just don't use a webview for GitHub OAuth.
  - `feedback_google_signin_sha_dual_register.md` — Always register BOTH the upload-key SHA-1 AND the Play App Signing key SHA-1 as separate Android OAuth clients in Google Cloud Console. Side-loaded release APKs only see the upload-key SHA-1.

---

## Engraved on the moon

*This file is the record of one of the worst-feeling debugging sessions in Solvr Labs history. The fix was eventually a four-line code swap. Everything before that was paying tuition. — 2026-05-12*

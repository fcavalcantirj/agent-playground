---
phase: 24-flutter-foundation
plan: 07
subsystem: mobile
tags: [ios, android, manifest, ats, cleartext, deep-link, portrait, bundle-id]
requires:
  - 24-01 (Flutter scaffold provided mobile/ios/Runner/Info.plist + mobile/android/app + build.gradle.kts)
provides:
  - "iOS ATS exemption: NSAllowsLocalNetworking=true + localhost exception domain"
  - "iOS portrait-only orientation lock"
  - "iOS solvrlabs:// custom URL scheme registration (CFBundleURLTypes)"
  - "iOS display name 'Solvr Labs' (CFBundleDisplayName)"
  - "iOS PRODUCT_BUNDLE_IDENTIFIER=com.solvrlabs.agentplayground (Debug/Release/Profile + RunnerTests)"
  - "Android applicationId=com.solvrlabs.agentplayground"
  - "Android app label 'Solvr Labs'"
  - "Android portrait-only orientation lock on MainActivity"
  - "Android solvrlabs://oauth intent-filter via net.openid.appauth.RedirectUriReceiverActivity"
  - "Android cleartext HTTP scoped to debug builds via src/debug/AndroidManifest.xml + network_security_config.xml (localhost / 127.0.0.1 / 10.0.2.2 / 10.0.3.2)"
  - "Android release builds retain default cleartextTrafficPermitted=false (production manifest does NOT reference network_security_config)"
affects:
  - mobile/ios/Runner/Info.plist
  - mobile/ios/Runner.xcodeproj/project.pbxproj
  - mobile/android/app/build.gradle.kts
  - mobile/android/app/src/main/AndroidManifest.xml
  - mobile/android/app/src/debug/AndroidManifest.xml
  - mobile/android/app/src/debug/res/xml/network_security_config.xml
tech-stack:
  added: []
  patterns:
    - "Info.plist: NSAppTransportSecurity dict with NSAllowsLocalNetworking + NSExceptionDomains.localhost"
    - "Info.plist: CFBundleURLTypes array of dicts with CFBundleTypeRole=Editor + CFBundleURLSchemes"
    - "AndroidManifest debug-only override using src/debug/AndroidManifest.xml + tools:replace"
    - "network_security_config base-config (deny) + domain-config (per-host allow)"
    - "appauth RedirectUriReceiverActivity with tools:node=replace"
key-files:
  created:
    - mobile/android/app/src/debug/res/xml/network_security_config.xml
  modified:
    - mobile/ios/Runner/Info.plist
    - mobile/ios/Runner.xcodeproj/project.pbxproj
    - mobile/android/app/build.gradle.kts
    - mobile/android/app/src/main/AndroidManifest.xml
    - mobile/android/app/src/debug/AndroidManifest.xml
decisions:
  - "Bundle/applicationId locked at com.solvrlabs.agentplayground (lowercase, no underscore) per D-02"
  - "iOS scaffold default was com.solvrlabs.agentPlayground (camelCase) — replaced across all 6 PRODUCT_BUNDLE_IDENTIFIER lines (Runner Debug/Release/Profile + RunnerTests Debug/Release/Profile)"
  - "Android namespace=com.solvrlabs.agent_playground (with underscore, in build.gradle.kts) was left UNCHANGED — the plan only mandated applicationId; namespace governs the Java/Kotlin package path (MainActivity.kt lives under com/solvrlabs/agent_playground/) and is separate from the user-visible package identity. aapt dump confirms package='com.solvrlabs.agentplayground' (correct, applicationId-derived) — only launchable-activity carries the underscore-namespace path, which is allowed by Android"
  - "Cleartext config scoped to src/debug/ via AndroidManifest variant override + tools:replace; release builds inherit cleartextTrafficPermitted=false default"
  - "iOS UISupportedInterfaceOrientations and UISupportedInterfaceOrientations~ipad both reduced to portrait-only (dropped landscape + upside-down per D-14)"
metrics:
  duration: ~10m
  completed: 2026-05-02
---

# Phase 24 Plan 07: iOS + Android Native Manifests Summary

Wired iOS Info.plist + Android manifests + Gradle so Flutter dio calls to a local
api_server actually succeed at runtime: ATS exemption for localhost on iOS,
debug-scoped cleartext config for localhost / 10.0.2.2 / 127.0.0.1 / 10.0.3.2 on
Android, portrait orientation lock on both platforms, the `solvrlabs://` custom
URL scheme registered for the future flutter_appauth GitHub OAuth callback, and
bundle id / applicationId / display name uniformly set to
`com.solvrlabs.agentplayground` / `Solvr Labs`.

## What Was Built

### Task 1 — iOS (`3cb352a`)

**`mobile/ios/Runner/Info.plist`:**
- `CFBundleDisplayName` set to `Solvr Labs` (D-03).
- New `NSAppTransportSecurity` dict (D-12):
  - `NSAllowsLocalNetworking=true` (covers RFC1918 ranges).
  - `NSExceptionDomains.localhost` with `NSExceptionAllowsInsecureHTTPLoads=true`
    and `NSIncludesSubdomains=false`.
- New `CFBundleURLTypes` array (D-04, D-15):
  - One entry: `CFBundleTypeRole=Editor`, `CFBundleURLSchemes=[solvrlabs]`.
- `UISupportedInterfaceOrientations` and `UISupportedInterfaceOrientations~ipad`
  both narrowed to `[UIInterfaceOrientationPortrait]` (D-14). Dropped
  landscape-left, landscape-right, and the iPad portrait-upside-down variant.

**`mobile/ios/Runner.xcodeproj/project.pbxproj`:**
- All `PRODUCT_BUNDLE_IDENTIFIER = com.solvrlabs.agentPlayground;` →
  `com.solvrlabs.agentplayground;` (lowercase, no underscore) (D-02).
- All `com.solvrlabs.agentPlayground.RunnerTests;` →
  `com.solvrlabs.agentplayground.RunnerTests;` (RunnerTests retains the
  `.RunnerTests` suffix, just normalizes the parent identifier).
- Replacements applied across Runner Debug/Release/Profile and RunnerTests
  Debug/Release/Profile (6 lines total).

### Task 2 — Android (`71d657b`)

**`mobile/android/app/build.gradle.kts`:**
- `applicationId = "com.solvrlabs.agentplayground"` (D-02 — replaced the
  scaffold's underscore variant `com.solvrlabs.agent_playground`).
- `minSdk` left at `flutter.minSdkVersion` (Flutter 3.41 default = API 24,
  which satisfies D-06's API 23 floor — no change needed).
- Android `namespace` left at `com.solvrlabs.agent_playground` (governs
  Java/Kotlin package path for MainActivity.kt; separate from applicationId
  per Android Gradle Plugin contract).

**`mobile/android/app/src/main/AndroidManifest.xml` (production manifest):**
- `android:label="Solvr Labs"` on `<application>` (D-03).
- `android:screenOrientation="portrait"` on the `.MainActivity` `<activity>` (D-14).
- Added `xmlns:tools` namespace.
- New `<activity>` declaration for
  `net.openid.appauth.RedirectUriReceiverActivity` with `tools:node="replace"`
  and an intent-filter for `solvrlabs://oauth/*` (D-04, D-15) — both
  `solvrlabs://oauth/github` (used by flutter_appauth in Phase 25) and
  `solvrlabs://oauth/google` (currently unused — google_sign_in is native)
  resolve to this single activity via the bare `android:host="oauth"` data
  matcher.
- Production manifest does NOT reference `network_security_config`, so
  release builds inherit `cleartextTrafficPermitted=false` by default.

**`mobile/android/app/src/debug/AndroidManifest.xml` (debug-only override):**
- Preserved the existing `<uses-permission android:name="android.permission.INTERNET"/>`
  declaration (required for hot reload).
- Added `<application>` element with `android:usesCleartextTraffic="true"` +
  `android:networkSecurityConfig="@xml/network_security_config"` +
  `tools:replace="android:networkSecurityConfig"` (D-13). This file is merged
  ONLY into the debug build variant; release retains the default secure config.

**`mobile/android/app/src/debug/res/xml/network_security_config.xml` (new):**
- `<base-config cleartextTrafficPermitted="false">` denies cleartext for
  unlisted domains.
- `<domain-config cleartextTrafficPermitted="true">` permits cleartext for:
  - `localhost` (real-device-on-same-host edge case)
  - `127.0.0.1` (loopback)
  - `10.0.2.2` (Android Emulator host loopback — the canonical dev URL)
  - `10.0.3.2` (Genymotion / some Pixel-system-image variants)

## Verification

### Grep gates (both tasks PASS)

iOS Info.plist:
- `NSAllowsLocalNetworking` present
- `<string>solvrlabs</string>` present
- `UIInterfaceOrientationPortrait` present (only portrait orientations remain)
- `<string>Solvr Labs</string>` present

iOS pbxproj:
- `com.solvrlabs.agentplayground` present
- `com.solvrlabs.agent_playground` (underscore) absent
- `com.solvrlabs.agentPlayground` (camelCase) absent

Android:
- `applicationId = "com.solvrlabs.agentplayground"` in build.gradle.kts
- `android:label="Solvr Labs"` in main manifest
- `android:screenOrientation="portrait"` in main manifest
- `android:scheme="solvrlabs"` in main manifest
- `mobile/android/app/src/debug/AndroidManifest.xml` exists with
  `usesCleartextTraffic="true"`
- `mobile/android/app/src/debug/res/xml/network_security_config.xml` exists with
  `10.0.2.2` and `127.0.0.1`
- Production manifest does NOT contain `10.0.2.2` (cleartext domain is
  debug-only)

### Build verification

**Android:** `cd mobile && fvm flutter build apk --debug` → `✓ Built
build/app/outputs/flutter-apk/app-debug.apk` (157 MB, ~227s gradle).

`aapt dump badging app-debug.apk` confirmed:
- `package: name='com.solvrlabs.agentplayground'`
- `application-label:'Solvr Labs'`
- `sdkVersion:'24'` (≥ D-06 floor of 23)
- `targetSdkVersion:'36'`

`aapt dump xmltree` of merged AndroidManifest.xml in the APK confirmed:
- `android:usesCleartextTraffic=0xffffffff` (true) ← debug-only merge worked
- `android:networkSecurityConfig=@0x7f110001` ← resource reference present
- `android:screenOrientation=0x1` (portrait)
- `RedirectUriReceiverActivity` with intent-filter
  `scheme="solvrlabs"` + `host="oauth"` ← deep-link wiring verified end-to-end

**iOS:** `fvm flutter build ios --debug --no-codesign --simulator` was
attempted but failed BEFORE reaching our Info.plist/pbxproj changes due to a
host-side Xcode environment fault — `xcodebuild -list` (the very first
sub-command Flutter runs to discover the project layout) crashed with:

```
Failed to load code for plug-in com.apple.dt.IDESimulatorFoundation
... Symbol not found:
_$s12DVTDownloads21DownloadableAssetTypeO22developerDocumentationy...
xcodebuild failed to load a required plug-in. Ensure your system frameworks
are up-to-date by running 'xcodebuild -runFirstLaunch'.
```

This is a Swift symbol-name mismatch between Xcode 26.4.1 and the macOS
26.3.1 host's `/Library/Developer/PrivateFrameworks/DVTDownloads.framework`
— an environmental drift unrelated to anything in this plan. Logged as
out-of-scope per executor scope-boundary rule. The plan's environment notes
explicitly authorized the fallback: *"Verification: this is mostly XML/Gradle
config — no flutter test asserting it. Verify by running `fvm flutter build
ios --debug --no-codesign` and `fvm flutter build apk --debug` if feasible;
otherwise document config edits + grep-based assertions in SUMMARY."* All
grep-based assertions PASS, and the Info.plist + pbxproj edits are pure XML
property/text changes that cannot fail to load — they don't compile, they
parse.

Build log: `/tmp/24-07-ios-build.log` (preserved for handoff).

## Threat Disposition Verification

All four T-24-07-* threat-register dispositions are mitigated:

- **T-24-07-01** (iOS ATS exemption): mitigated — `NSExceptionDomains.localhost`
  is the only allowlisted domain; `NSAllowsLocalNetworking=true` covers RFC1918.
  Production HTTPS still enforced for everything else.
- **T-24-07-02** (Android cleartext config): mitigated — cleartext config is at
  `src/debug/res/xml/`; production AndroidManifest does NOT reference it
  (verified by grep gate `! grep -q "10.0.2.2" mobile/android/app/src/main/AndroidManifest.xml`).
  Release builds inherit `cleartextTrafficPermitted=false` default.
- **T-24-07-03** (Custom URL scheme squat): accepted per D-15 — Universal
  Links / App Links deferred until a verified HTTPS domain exists. PKCE in
  flutter_appauth (Phase 25) is the runtime defense.
- **T-24-07-04** (applicationId mismatch): mitigated — single canonical value
  `com.solvrlabs.agentplayground` enforced by grep gate; no underscore or
  camelCase variants remain in pbxproj or build.gradle.kts. Verified by aapt
  dump showing `package: name='com.solvrlabs.agentplayground'`.

## Deviations from Plan

**[Rule 1 - Bug] Plan referenced wrong iOS bundle id starting state.**

- **Found during:** Task 1 reading.
- **Issue:** The plan instructed to "find every line matching
  `PRODUCT_BUNDLE_IDENTIFIER = com.solvrlabs.agent_playground;`" (with
  underscore). The actual scaffolded `project.pbxproj` already had
  `com.solvrlabs.agentPlayground;` (camelCase, capital P) — Flutter's
  `flutter create` PascalCase-conversion of the project name. The plan's
  grep gate `! grep -q "com.solvrlabs.agent_playground"` would pass
  regardless, but the camelCase variant would silently survive.
- **Fix:** Replaced both `com.solvrlabs.agentPlayground.RunnerTests;` and
  `com.solvrlabs.agentPlayground;` with `com.solvrlabs.agentplayground.RunnerTests;`
  and `com.solvrlabs.agentplayground;` respectively. Verified the camelCase
  variant is now absent (extra grep gate added beyond the plan's verify
  block).
- **Files modified:** `mobile/ios/Runner.xcodeproj/project.pbxproj`
- **Commit:** `3cb352a`

**[Rule 2 - Robustness] Preserved INTERNET permission in debug AndroidManifest.**

- **Found during:** Task 2 step 3.
- **Issue:** The plan's debug-AndroidManifest snippet had only an
  `<application>` element, no `<uses-permission>`. The existing
  `mobile/android/app/src/debug/AndroidManifest.xml` (from `flutter create`)
  declares `<uses-permission android:name="android.permission.INTERNET"/>` —
  required for Flutter hot reload + DDS over the network. Overwriting
  blindly would silently break hot reload.
- **Fix:** Merged the cleartext `<application>` block INTO the existing
  manifest, keeping the `<uses-permission>` line intact and adding the
  `xmlns:tools` namespace at the manifest level.
- **Files modified:** `mobile/android/app/src/debug/AndroidManifest.xml`
- **Commit:** `71d657b`

## Out-of-scope items deferred (not fixed)

- **Xcode 26.4.1 ↔ macOS 26.3.1 IDESimulatorFoundation plug-in symbol-mismatch:**
  Host-level environment drift (Swift symbol not found in DVTDownloads
  framework). Affects ALL `flutter build ios` invocations on this host until
  the operator runs `xcodebuild -runFirstLaunch` or reinstalls Xcode/CLT.
  Logged for visibility; out-of-scope for this plan (does not affect Plan 06
  HealthzScreen runtime once the host is repaired, since the iOS edits are
  pure declarative XML).

## Known Stubs

None — Plan 07 is config-only (XML + Gradle). No code stubs introduced.

## Self-Check: PASSED

- File `mobile/ios/Runner/Info.plist` — FOUND (modified)
- File `mobile/ios/Runner.xcodeproj/project.pbxproj` — FOUND (modified)
- File `mobile/android/app/build.gradle.kts` — FOUND (modified)
- File `mobile/android/app/src/main/AndroidManifest.xml` — FOUND (modified)
- File `mobile/android/app/src/debug/AndroidManifest.xml` — FOUND (modified)
- File `mobile/android/app/src/debug/res/xml/network_security_config.xml` — FOUND (created)
- Commit `3cb352a` — FOUND (Task 1 iOS)
- Commit `71d657b` — FOUND (Task 2 Android)
- Build artifact `mobile/build/app/outputs/flutter-apk/app-debug.apk` — FOUND
  (157 MB, debug APK with merged manifest verified by aapt)

#!/usr/bin/env bash
# release.sh — single source of truth for Flutter release builds.
#
# 2026-05-18 PATCH (third-strike-fix): OAuth IDs are sourced ONLY from prod
# `.env.prod` via `ssh msv-prod cat /opt/solvr-labs/agent-playground/deploy/.env.prod`.
# The wrapper REFUSES to fall back to local `.env` for any release target.
# Three consecutive Android releases (+7, +8, +9) shipped to Play Production
# with the WRONG GitHub OAuth client ID because the previous wrapper read
# local `.env` (legacy IDs from a different Google Cloud project and a
# different GitHub OAuth App). See:
#  * memory/feedback_release_oauth_ids_come_from_prod_envprod_only.md
#  * memory/feedback_never_ship_play_prod_without_device_apk_verify.md
#  * CLAUDE.md top-of-file STOP banner
#
# Also runs `flutter clean` before release builds (sim-targeted framework
# slices contaminated the +9 IPA on first TestFlight upload — App Store
# Connect rejected with "Simulator platforms aren't permitted").
#
# Targets:
#   apk-local         — release APK built with PROD OAuth IDs, for `adb install -r`
#                       device verification BEFORE any Play Store upload.
#   verified          — touch a flag file marking the most recent apk-local as
#                       verified by the user on a real device. REQUIRED before
#                       android-internal / android-prod / ios-testflight.
#   android-internal  — build AAB with PROD IDs + fastlane internal. Requires
#                       a `verified` flag from the same shell session.
#   android-prod      — fastlane promote_to_production. Requires `verified`.
#   ios-testflight    — build IPA with PROD IDs + fastlane beta. Requires `verified`.
#
# The `verified` gate is structural: there is no way to ship a release
# artifact through this wrapper without explicit user device verification.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOBILE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$MOBILE_DIR/.." && pwd)"
FASTLANE_BIN="/Users/fcavalcanti/.local/share/gem/ruby/3.4.0/gems/fastlane-2.234.0/bin/fastlane"

PROD_SSH_HOST="msv-prod"
PROD_ENV_PATH="/opt/solvr-labs/agent-playground/deploy/.env.prod"
VERIFIED_FLAG="$MOBILE_DIR/.last-build-verified"

usage() {
  cat <<USAGE
release.sh — Flutter release wrapper (third-strike-fix 2026-05-18)

Usage: $0 <target>

Targets:
  apk-local         Build release APK with PROD OAuth IDs; install on device for sign-in test
  verified          Mark the most recent apk-local as verified after on-device sign-in
                    succeeded for Google AND GitHub. Touches $VERIFIED_FLAG.
  android-internal  Build AAB + fastlane internal (Play internal track). Requires verified.
  android-prod      fastlane promote_to_production. Requires verified.
  ios-testflight    Build IPA + fastlane beta (TestFlight). Requires verified.

OAuth IDs come from PROD ONLY (ssh $PROD_SSH_HOST cat $PROD_ENV_PATH). Local
.env is IGNORED for release targets. This is structural — the wrapper
refuses to build if ssh fails or .env.prod is unreachable.

Verification gate: a release target REFUSES to run unless the user has
explicitly run \`release.sh verified\` within the last 4 hours, AFTER
having installed the apk-local APK and signed in via Google AND GitHub
on a real Android device.
USAGE
}

if [[ $# -ne 1 ]]; then usage; exit 1; fi
TARGET="$1"

# ── Pull OAuth IDs from PROD only, never from local .env ───────────────
fetch_prod_oauth() {
  echo "▶ pulling OAuth IDs from prod (ssh $PROD_SSH_HOST $PROD_ENV_PATH)..."
  local raw
  if ! raw=$(ssh -o BatchMode=yes "$PROD_SSH_HOST" "cat $PROD_ENV_PATH" 2>&1); then
    echo "ERROR: ssh $PROD_SSH_HOST $PROD_ENV_PATH failed:" >&2
    echo "$raw" >&2
    echo "" >&2
    echo "OAuth IDs for release builds come ONLY from prod .env.prod." >&2
    echo "If ssh is broken, the build refuses to proceed (we will NOT" >&2
    echo "fall back to local .env — that path has broken auth 3 times)." >&2
    exit 4
  fi
  # Public IDs only (these go in --dart-define and end up in the APK/IPA).
  # We do NOT export secrets (CLIENT_SECRET / STATE_SECRET) — those stay
  # on the server and are not part of any client artifact.
  export PROD_GOOGLE_SERVER_CLIENT_ID="$(echo "$raw" | grep ^AP_OAUTH_GOOGLE_CLIENT_ID= | cut -d= -f2-)"
  export PROD_GITHUB_CLIENT_ID="$(echo "$raw" | grep ^AP_OAUTH_GITHUB_MOBILE_CLIENT_ID= | cut -d= -f2-)"
  # SENTRY_DSN_MOBILE may or may not be in prod env; fallback to local if absent.
  PROD_SENTRY_DSN_MOBILE="$(echo "$raw" | grep ^SENTRY_DSN_MOBILE= | cut -d= -f2- || true)"
  if [[ -z "$PROD_SENTRY_DSN_MOBILE" && -f "$REPO_ROOT/.env" ]]; then
    PROD_SENTRY_DSN_MOBILE="$(grep ^SENTRY_DSN_MOBILE= "$REPO_ROOT/.env" | cut -d= -f2- || true)"
  fi
  export PROD_SENTRY_DSN_MOBILE
  # GOOGLE_IOS_CLIENT_ID is per-platform (only used by mobile, not the api_server),
  # so it lives in Info.plist's reversed URL scheme. We derive it from the first
  # entry in AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS that ends with a non-web suffix,
  # matching the iOS-typed client. For 62651278829 the iOS client is
  # 62651278829-jec9uveaakbgbth17sq289r3rtr6j70v.apps.googleusercontent.com.
  # Until upstream prod env explicitly carries GOOGLE_IOS_CLIENT_ID, we read
  # the FIRST entry of the comma-list and use that as the iOS-typed client
  # (verified via `mobile/ios/Runner/Info.plist:59` cross-check 2026-05-18).
  PROD_GOOGLE_IOS_CLIENT_ID="$(echo "$raw" | grep ^AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS= | cut -d= -f2- | tr ',' '\n' | head -1)"
  export PROD_GOOGLE_IOS_CLIENT_ID

  # RevenueCat public SDK keys (one per platform, used at runtime by the
  # purchases_flutter SDK). These are SAFE to bake into the AAB / IPA —
  # they're "public" in RC's threat model (the secret webhook key stays
  # server-side). When unset in prod, the IAP path no-ops gracefully and
  # the UI shows "billing unavailable" instead of crashing.
  PROD_REVENUECAT_API_KEY_IOS="$(echo "$raw" | grep ^AP_REVENUECAT_API_KEY_IOS= | cut -d= -f2- || true)"
  PROD_REVENUECAT_API_KEY_ANDROID="$(echo "$raw" | grep ^AP_REVENUECAT_API_KEY_ANDROID= | cut -d= -f2- || true)"
  export PROD_REVENUECAT_API_KEY_IOS PROD_REVENUECAT_API_KEY_ANDROID

  for v in PROD_GOOGLE_SERVER_CLIENT_ID PROD_GITHUB_CLIENT_ID PROD_GOOGLE_IOS_CLIENT_ID; do
    if [[ -z "${!v}" ]]; then
      echo "ERROR: $v is empty after ssh fetch — prod .env.prod is missing a required key." >&2
      exit 5
    fi
  done

  # Loud print so future-you can spot drift BEFORE fastlane uploads.
  echo "▶ prod-sourced OAuth IDs being baked into the build:"
  echo "    GOOGLE_SERVER_CLIENT_ID project = $(echo "$PROD_GOOGLE_SERVER_CLIENT_ID" | cut -d- -f1)"
  echo "    GOOGLE_IOS_CLIENT_ID    project = $(echo "$PROD_GOOGLE_IOS_CLIENT_ID" | cut -d- -f1)"
  echo "    GITHUB_CLIENT_ID        prefix  = $(echo "$PROD_GITHUB_CLIENT_ID" | head -c 12)…"
  if [[ -n "$PROD_REVENUECAT_API_KEY_IOS" || -n "$PROD_REVENUECAT_API_KEY_ANDROID" ]]; then
    echo "    REVENUECAT_API_KEY_IOS  prefix  = $(echo "$PROD_REVENUECAT_API_KEY_IOS" | head -c 8)…"
    echo "    REVENUECAT_API_KEY_AND  prefix  = $(echo "$PROD_REVENUECAT_API_KEY_ANDROID" | head -c 8)…"
  else
    echo "    REVENUECAT_API_KEY_*    UNSET — IAP will no-op (web-only billing)"
  fi
  echo
}

# ── Verification gate ──────────────────────────────────────────────────
require_verified() {
  if [[ ! -f "$VERIFIED_FLAG" ]]; then
    echo "ERROR: no verified flag at $VERIFIED_FLAG" >&2
    echo "" >&2
    echo "You must run 'release.sh apk-local', install the APK on your" >&2
    echo "Android device (adb install -r), sign in via Google AND GitHub" >&2
    echo "and reach the dashboard for BOTH providers, THEN run:" >&2
    echo "    $0 verified" >&2
    echo "" >&2
    echo "to confirm the on-device sign-in works. Only after that will" >&2
    echo "this wrapper let you ship to Play / TestFlight." >&2
    exit 6
  fi
  # Reject stale verification (> 4 hours old).
  local age_s
  age_s=$(( $(date +%s) - $(stat -f %m "$VERIFIED_FLAG" 2>/dev/null || stat -c %Y "$VERIFIED_FLAG") ))
  if (( age_s > 14400 )); then
    echo "ERROR: verified flag is older than 4 hours ($((age_s/60)) min). Re-verify on device." >&2
    rm -f "$VERIFIED_FLAG"
    exit 7
  fi
  echo "▶ verified flag present (age: $((age_s/60)) min) — release path unlocked"
}

GIT_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
SENTRY_ENV="prod"

build_common_defines=(
  --dart-define "BASE_URL=https://agents.solvr.dev"
  --dart-define "SENTRY_RELEASE=$GIT_SHA"
  --dart-define "SENTRY_ENVIRONMENT=$SENTRY_ENV"
)

do_clean() {
  echo "▶ flutter clean (prevent sim-slice contamination in release builds)"
  cd "$MOBILE_DIR"
  fvm flutter clean >/dev/null
}

# Read the expected versionCode (the +N part of pubspec `version: X.Y.Z+N`)
expected_version_code() {
  grep ^version: "$MOBILE_DIR/pubspec.yaml" | sed -E 's/version: *[^+]+\+([0-9]+).*/\1/'
}

# After a fastlane Play upload, query the track and HARD-FAIL if the track
# doesn't list the expected versionCode. Catches the "silent stale-AAB
# upload" bug from 2026-05-18 where fastlane reported success but
# `[versionCodes]` on the track was unchanged.
verify_play_track_version() {
  local track="$1" expected="$2"
  echo "▶ verifying Play '$track' track now lists versionCode $expected..."
  local result
  result=$("$FASTLANE_BIN" run google_play_track_version_codes track:"$track" 2>&1 | grep -E "^.*Result:" | tail -1)
  echo "    $result"
  if ! echo "$result" | grep -qE "\[$expected(,|\])"; then
    echo "ERROR: Play '$track' track does NOT list versionCode $expected after upload." >&2
    echo "       fastlane reported success but the track wasn't actually updated." >&2
    echo "       (This is the 2026-05-18 false-success bug. See CLAUDE.md banner.)" >&2
    echo "       Investigate manually before promoting further." >&2
    exit 8
  fi
  echo "    ✓ confirmed: track lists $expected"
}

case "$TARGET" in
  apk-local)
    fetch_prod_oauth
    do_clean
    cd "$MOBILE_DIR"
    fvm flutter build apk --release \
      "${build_common_defines[@]}" \
      --dart-define "GOOGLE_SERVER_CLIENT_ID=$PROD_GOOGLE_SERVER_CLIENT_ID" \
      --dart-define "GITHUB_CLIENT_ID=$PROD_GITHUB_CLIENT_ID" \
      --dart-define "SENTRY_DSN_MOBILE=$PROD_SENTRY_DSN_MOBILE" \
      --dart-define "REVENUECAT_API_KEY_IOS=$PROD_REVENUECAT_API_KEY_IOS" \
      --dart-define "REVENUECAT_API_KEY_ANDROID=$PROD_REVENUECAT_API_KEY_ANDROID"
    APK="$MOBILE_DIR/build/app/outputs/flutter-apk/app-release.apk"
    # Invalidate any stale verification — this is a new build, must re-verify.
    rm -f "$VERIFIED_FLAG"
    echo
    echo "▶ APK built: $APK"
    echo
    echo "▶ NEXT STEP — verify on your real Android device:"
    echo "    1. Plug your Android device + enable USB debugging"
    echo "    2. adb install -r '$APK'"
    echo "       (if it errors with INSTALL_FAILED_UPDATE_INCOMPATIBLE:"
    echo "        adb uninstall dev.solvrlabs.agentplayground && adb install '$APK')"
    echo "    3. Open the app, sign in via Google → reach dashboard"
    echo "    4. Sign out, sign in via GitHub → reach dashboard"
    echo "    5. If BOTH worked, run: $0 verified"
    echo
    echo "▶ Only AFTER step 5 will android-internal / android-prod /"
    echo "▶ ios-testflight be unlocked."
    ;;

  verified)
    touch "$VERIFIED_FLAG"
    echo "▶ verified flag touched at $VERIFIED_FLAG"
    echo "▶ release path UNLOCKED for the next 4 hours. You may now run:"
    echo "    $0 android-internal"
    echo "    $0 android-prod      (after android-internal + re-verify via Play Store)"
    echo "    $0 ios-testflight"
    ;;

  android-internal)
    require_verified
    fetch_prod_oauth
    do_clean
    cd "$MOBILE_DIR"
    EXPECTED_VC=$(expected_version_code)
    if [[ -z "$EXPECTED_VC" ]]; then
      echo "ERROR: could not parse versionCode from pubspec.yaml" >&2; exit 9
    fi
    echo "▶ pubspec expects versionCode $EXPECTED_VC"
    fvm flutter build appbundle --release \
      "${build_common_defines[@]}" \
      --dart-define "GOOGLE_SERVER_CLIENT_ID=$PROD_GOOGLE_SERVER_CLIENT_ID" \
      --dart-define "GITHUB_CLIENT_ID=$PROD_GITHUB_CLIENT_ID" \
      --dart-define "SENTRY_DSN_MOBILE=$PROD_SENTRY_DSN_MOBILE" \
      --dart-define "REVENUECAT_API_KEY_IOS=$PROD_REVENUECAT_API_KEY_IOS" \
      --dart-define "REVENUECAT_API_KEY_ANDROID=$PROD_REVENUECAT_API_KEY_ANDROID"
    AAB="$MOBILE_DIR/build/app/outputs/bundle/release/app-release.aab"
    if [[ ! -f "$AAB" ]]; then
      echo "ERROR: AAB not produced at $AAB. Build silently failed?" >&2; exit 10
    fi
    echo "▶ AAB built ($(stat -f %z "$AAB" 2>/dev/null || stat -c %s "$AAB") bytes), uploading..."
    (cd "$MOBILE_DIR/android" && "$FASTLANE_BIN" internal)
    # POST-UPLOAD VERIFICATION — catches the 2026-05-18 silent-stale-upload
    # bug where fastlane "succeeded" but the track was never updated.
    (cd "$MOBILE_DIR/android" && verify_play_track_version internal "$EXPECTED_VC")
    # Invalidate the flag so the user MUST re-verify after the Play Store
    # internal-track update before we let them promote to production.
    rm -f "$VERIFIED_FLAG"
    echo "▶ uploaded to Play internal track + Play API confirmed versionCode $EXPECTED_VC."
    echo "▶ Re-install from Play Store internal-testing track on your device,"
    echo "▶ re-verify Google + GitHub,"
    echo "▶ then run '$0 verified' again before '$0 android-prod'."
    ;;

  android-prod)
    require_verified
    EXPECTED_VC=$(expected_version_code)
    echo "▶ pubspec expects versionCode $EXPECTED_VC on production track"
    # Sanity: internal track MUST already have the expected versionCode before
    # we promote. Otherwise we'd be promoting whatever's stale in internal —
    # exactly the 2026-05-18 false-success failure mode.
    (cd "$MOBILE_DIR/android" && verify_play_track_version internal "$EXPECTED_VC")
    (cd "$MOBILE_DIR/android" && "$FASTLANE_BIN" promote_to_production)
    (cd "$MOBILE_DIR/android" && verify_play_track_version production "$EXPECTED_VC")
    rm -f "$VERIFIED_FLAG"
    echo "▶ Promoted internal → production AND Play API confirmed versionCode $EXPECTED_VC. 100% rollout."
    ;;

  ios-testflight)
    require_verified
    fetch_prod_oauth
    do_clean
    cd "$MOBILE_DIR"
    fvm flutter build ipa --release \
      "${build_common_defines[@]}" \
      --dart-define "GOOGLE_SERVER_CLIENT_ID=$PROD_GOOGLE_SERVER_CLIENT_ID" \
      --dart-define "GITHUB_CLIENT_ID=$PROD_GITHUB_CLIENT_ID" \
      --dart-define "GOOGLE_IOS_CLIENT_ID=$PROD_GOOGLE_IOS_CLIENT_ID" \
      --dart-define "SENTRY_DSN_MOBILE=$PROD_SENTRY_DSN_MOBILE" \
      --dart-define "REVENUECAT_API_KEY_IOS=$PROD_REVENUECAT_API_KEY_IOS" \
      --dart-define "REVENUECAT_API_KEY_ANDROID=$PROD_REVENUECAT_API_KEY_ANDROID"
    (cd "$MOBILE_DIR/ios" && "$FASTLANE_BIN" beta)
    rm -f "$VERIFIED_FLAG"
    echo "▶ Uploaded to TestFlight. Processing in App Store Connect"
    echo "▶ ~5-10 min before testers see it."
    ;;

  *)
    usage; exit 1 ;;
esac

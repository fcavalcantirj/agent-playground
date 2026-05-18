#!/usr/bin/env bash
# release.sh — single source of truth for Flutter release builds.
#
# Sources mobile/../.env, validates the required OAuth + Sentry env vars,
# runs `flutter clean` (so sim-contaminated frameworks don't ride into a
# release IPA — we hit this on 2026-05-18 +9 first iOS TestFlight push),
# builds with ALL required --dart-define values, then optionally chains
# fastlane.
#
# Usage:
#   mobile/scripts/release.sh <target>
#
# Targets:
#   apk-local            — build release APK at build/app/outputs/flutter-apk/app-release.apk
#                          (for `adb install` on your plugged-in Android device)
#   android-internal     — build AAB → fastlane internal (Play Store internal track)
#   android-prod         — fastlane promote_to_production (assumes internal already up)
#   ios-testflight       — build IPA → fastlane beta (TestFlight)
#
# Env vars required (sourced from .env):
#   BASE_URL                            (we hard-default to https://agents.solvr.dev)
#   GOOGLE_IOS_CLIENT_ID                (iOS only)
#   AP_OAUTH_GOOGLE_CLIENT_ID           (used as GOOGLE_SERVER_CLIENT_ID dart-define)
#   AP_OAUTH_GITHUB_MOBILE_CLIENT_ID    (used as GITHUB_CLIENT_ID dart-define)
#   SENTRY_DSN_MOBILE
#
# The validate step refuses to proceed if any of these are missing,
# preventing the silent "client_id=\"\" -3 user cancelled" failure
# mode documented in CLAUDE.md golden rule #6.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOBILE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$MOBILE_DIR/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"
FASTLANE_BIN="/Users/fcavalcanti/.local/share/gem/ruby/3.4.0/gems/fastlane-2.234.0/bin/fastlane"

usage() {
  cat <<USAGE
release.sh — Flutter release wrapper

Usage: $0 <target>

Targets:
  apk-local            Build release APK for adb install (on-device test BEFORE Play upload)
  android-internal     Build AAB + fastlane internal (Play internal track)
  android-prod         Promote internal → production via fastlane (no rebuild)
  ios-testflight       Build IPA + fastlane beta (TestFlight)

Env vars read from $ENV_FILE:
  BASE_URL, GOOGLE_IOS_CLIENT_ID, AP_OAUTH_GOOGLE_CLIENT_ID,
  AP_OAUTH_GITHUB_MOBILE_CLIENT_ID, SENTRY_DSN_MOBILE

The script refuses to build if any required value is missing or empty —
prevents the silent "client_id="" -> sign-in fails with no obvious cause"
trap documented in CLAUDE.md.
USAGE
}

if [[ $# -ne 1 ]]; then usage; exit 1; fi
TARGET="$1"

# ── load + validate env ─────────────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found" >&2; exit 2
fi
set -a; source "$ENV_FILE"; set +a

: "${BASE_URL:=https://agents.solvr.dev}"

require() {
  local name="$1" hint="$2"
  if [[ -z "${!name:-}" ]]; then
    echo "ERROR: $name is unset/empty. Hint: $hint" >&2
    exit 3
  fi
}

# always-required (Android + iOS share)
require AP_OAUTH_GOOGLE_CLIENT_ID         "GCP OAuth web client ID — Google Console > Credentials"
require AP_OAUTH_GITHUB_MOBILE_CLIENT_ID  "GitHub mobile OAuth App > Client ID"
require SENTRY_DSN_MOBILE                 "Sentry mobile project DSN"

# iOS-only
if [[ "$TARGET" == "ios-testflight" ]]; then
  require GOOGLE_IOS_CLIENT_ID            "iOS-typed OAuth client in Google Console (separate from server client)"
fi

cd "$MOBILE_DIR"
GIT_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
SENTRY_ENV="${SENTRY_ENVIRONMENT:-prod}"

COMMON_DEFINES=(
  --dart-define "BASE_URL=$BASE_URL"
  --dart-define "GOOGLE_SERVER_CLIENT_ID=$AP_OAUTH_GOOGLE_CLIENT_ID"
  --dart-define "GITHUB_CLIENT_ID=$AP_OAUTH_GITHUB_MOBILE_CLIENT_ID"
  --dart-define "SENTRY_DSN_MOBILE=$SENTRY_DSN_MOBILE"
  --dart-define "SENTRY_RELEASE=$GIT_SHA"
  --dart-define "SENTRY_ENVIRONMENT=$SENTRY_ENV"
)

echo "▶ target=$TARGET  base_url=$BASE_URL  release_sha=${GIT_SHA:0:12}"

# ── helpers ─────────────────────────────────────────────────────────────
do_clean() {
  echo "▶ flutter clean (avoid sim-slice contamination in release builds)"
  fvm flutter clean >/dev/null
}

case "$TARGET" in
  apk-local)
    do_clean
    fvm flutter build apk --release "${COMMON_DEFINES[@]}"
    APK="$MOBILE_DIR/build/app/outputs/flutter-apk/app-release.apk"
    echo
    echo "▶ APK built: $APK"
    echo "▶ Install on plugged-in Android device:"
    echo "    adb install -r '$APK'"
    echo "▶ If install fails with INSTALL_FAILED_UPDATE_INCOMPATIBLE, uninstall first:"
    echo "    adb uninstall dev.solvrlabs.agentplayground && adb install '$APK'"
    ;;

  android-internal)
    do_clean
    fvm flutter build appbundle --release "${COMMON_DEFINES[@]}"
    (cd "$MOBILE_DIR/android" && "$FASTLANE_BIN" internal)
    echo "▶ Uploaded to Play Internal track. Verify on device via Play Store internal-testing track,"
    echo "▶ THEN run: mobile/scripts/release.sh android-prod"
    ;;

  android-prod)
    (cd "$MOBILE_DIR/android" && "$FASTLANE_BIN" promote_to_production)
    echo "▶ Promoted internal → production. 100% rollout."
    ;;

  ios-testflight)
    # iOS adds GOOGLE_IOS_CLIENT_ID on top of common defines.
    do_clean
    fvm flutter build ipa --release \
      "${COMMON_DEFINES[@]}" \
      --dart-define "GOOGLE_IOS_CLIENT_ID=$GOOGLE_IOS_CLIENT_ID"
    (cd "$MOBILE_DIR/ios" && "$FASTLANE_BIN" beta)
    echo "▶ Uploaded to TestFlight. Processing in App Store Connect ~5-10 min before testers see it."
    ;;

  *)
    usage; exit 1 ;;
esac

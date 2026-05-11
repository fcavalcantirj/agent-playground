# Android signing & publishing keys

**Only the public X.509 cert (`play_app_signing.der`) is committed.** Everything else is `.gitignore`d and lives on each contributor's local disk.

This used to be a "vendor all keys, it's a private repo" folder. On 2026-05-11 we
got bit: GitHub's secret-scanning push-protection blocked the SA JSON, we
unblocked it, pushed, and minutes later Google Cloud auto-disabled the key for
abuse-policy violation. Even on private repos. Lesson: secret-scanners crawl
GitHub regardless of repo visibility. Don't commit JSON service-account keys.

## What lives here

| File | Tracked? | What it is |
|---|---|---|
| `play_app_signing.der` | ✅ yes — public cert | Google's Play App Signing public cert. Use its SHA-1 to register the Android OAuth client. |
| `solvr-labs-ap-upload.jks` | 🚫 gitignored | Upload keystore. `flutter build appbundle --release` uses this. Losing it = request reset from Google. |
| `play-service-account.json` | 🚫 gitignored | Fastlane → Play Developer API credentials. Rotate if exposed (Google will auto-disable a leaked one). |
| `../../android/key.properties` | 🚫 gitignored | Plaintext keystore passwords (used by `app/build.gradle.kts`). Points at `../../keys/android/solvr-labs-ap-upload.jks` via relative path. |

## Bootstrap a fresh clone

A fresh clone WILL NOT build a release AAB until you populate the three
gitignored files. Sources:

- **Upload keystore (`solvr-labs-ap-upload.jks`):** ask Felipe for the encrypted
  backup, or — if lost — request upload-key reset in Play Console.
- **`mobile/android/key.properties`:** matching passwords from the keystore.
  Template:
  ```
  storeFile=../../keys/android/solvr-labs-ap-upload.jks
  storePassword=<from password manager>
  keyAlias=upload
  keyPassword=<from password manager>
  ```
- **Service account JSON:** mint a new one — Cloud Console → IAM → Service
  Accounts → `play-publisher@solvrlabs.iam.gserviceaccount.com` → Keys → Add
  Key → JSON → save here as `play-service-account.json`.

Debug builds work without any of this.

## Fingerprints — `play_app_signing.der`

| Algo | Fingerprint |
|---|---|
| **SHA-1** | `6B:38:01:2B:8D:A8:60:9B:92:52:A6:3A:82:75:F7:E7:CF:49:6B:65` |
| **SHA-256** | `72:6C:DC:17:35:FE:C3:2F:76:E3:8C:D0:AA:C2:E7:5E:66:C6:8E:7E:D9:31:5B:7E:7F:A5:CF:85:E8:99:5D:51` |
| **MD5** | `35:7D:7C:AF:0B:E2:B8:FC:E9:A3:F3:27:45:38:EC:DE` |

Verify locally:
```bash
keytool -printcert -file play_app_signing.der | grep -E "SHA1|SHA256|MD5"
```

## Upload-key vs App-signing-key (don't confuse)

- **Upload key** (`solvr-labs-ap-upload.jks`) — what we sign AABs with before upload. Private.
- **App-signing key** (`play_app_signing.der`) — Google's key that re-signs the APK delivered to devices. Public cert only here.

This **app-signing** SHA-1 is what Android SDKs (google_sign_in, Firebase) check at runtime — so it's the one to register in Google Cloud Console as the Android OAuth client fingerprint.

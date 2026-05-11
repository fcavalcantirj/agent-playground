# Android signing certificates

## `play_app_signing.der`

**Public X.509 certificate** for the Google Play App Signing key that re-signs every release of `com.solvrlabs.agentplayground` server-side after upload.

Non-secret — Play Console publishes the same fingerprints under your app's *App integrity* page. Vendored here so any team member registering a third-party SDK (Firebase, Facebook, sign-in providers, attestation services) can grab the SHA-1 / SHA-256 without logging into Play Console.

### Fingerprints

| Algo | Fingerprint |
|---|---|
| **SHA-1** | `6B:38:01:2B:8D:A8:60:9B:92:52:A6:3A:82:75:F7:E7:CF:49:6B:65` |
| **SHA-256** | `72:6C:DC:17:35:FE:C3:2F:76:E3:8C:D0:AA:C2:E7:5E:66:C6:8E:7E:D9:31:5B:7E:7F:A5:CF:85:E8:99:5D:51` |
| **MD5** | `35:7D:7C:AF:0B:E2:B8:FC:E9:A3:F3:27:45:38:EC:DE` |

### Verify locally

```bash
keytool -printcert -file play_app_signing.der | grep -E "SHA1|SHA256|MD5"
```

Should match the table above.

### How it gets used

When the app is installed from Play Store, Android Package Manager records THIS certificate as the app's signing identity. Native SDKs (e.g. `google_sign_in`) read that cert at runtime and forward its SHA-1 to Google servers, which then look up the matching Android OAuth client ID in Google Cloud Console. So this is the SHA-1 you put into:

- Google Cloud Console → Android OAuth client → SHA-1 fingerprint field
- Firebase project → Android app → SHA-1
- Any other "register your Android app's signing cert" workflow

### Where to re-obtain

Play Console → Test and release → Setup → **App integrity** → App signing key certificate → "Download certificate".

### NOT in this folder

The **upload key** (`~/.android/solvr-labs-ap-upload.jks`) — that's the private signing key you USE to sign AABs before upload. It stays out of git permanently. Losing it = request reset from Google. Backed up encrypted to:
- (TODO: document where the .jks live encrypted backups)

Don't confuse the two:
- *Upload key* → signs the AAB you push to Play (private, never commit)
- *App signing key* (this file) → Google's key that signs the APK delivered to user devices (public cert, safe to commit)

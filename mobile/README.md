# Solvr Labs (mobile/)

Phase 24 — Flutter foundation.  This is the **mobile MVP scaffold** for the
Agent Playground.  Phase 25 ships the Dashboard / New Agent / Chat screens;
Phase 24 ships the production-shaped foundation — typed dio client, theme,
interceptors, env-config — and proves the full deploy + chat + SSE
round-trip via a checked-in spike against the live local `api_server`.

## Quick Start

```bash
# one-time per machine
fvm install 3.41.0
fvm use 3.41.0
cd mobile && fvm flutter pub get

# sanity check
cd mobile && make doctor

# boot on iOS Simulator (default URL points at localhost:8000)
cd mobile && make ios BASE_URL=http://localhost:8000

# boot on Android Emulator
cd mobile && make android BASE_URL=http://10.0.2.2:8000
```

## Per-Target `BASE_URL` (D-44)

| Target                        | `BASE_URL`                                       | Why |
|-------------------------------|--------------------------------------------------|-----|
| iOS Simulator                 | `http://localhost:8000`                          | Simulator's `localhost` maps to the host (your Mac). |
| Android Emulator              | `http://10.0.2.2:8000`                           | `localhost` inside the emulator means the EMULATOR itself.  `10.0.2.2` is Android's gateway-to-host alias. |
| Genymotion / Pixel emulator   | `http://10.0.3.2:8000`                           | Different host-gateway alias on some Android emulator builds. |
| Real device on same WiFi      | `http://192.168.X.Y:8000`                        | Use the host Mac's LAN IP (`ifconfig en0` or System Settings > Network).  Phone + Mac MUST be on the same network. |
| ngrok tunnel (out-of-network) | `https://abc.ngrok-free.app`                     | `ngrok http 8000` tunnel; rotates per session.  HTTPS so iOS ATS allows it without exemption. |

There is **no in-app env switcher / debug menu / env banner**.  Per-target
switching happens at `flutter run` time via `--dart-define BASE_URL=...`
(D-44 + project memory rule on env-config).

## Tests

```bash
cd mobile && make test          # unit + widget tests (~30s)
cd mobile && make spike \       # full 9-step round-trip against live api_server (~2-4 min)
  BASE_URL=http://localhost:8000 \
  SESSION_ID=<paste from browser DevTools> \
  OPENROUTER_KEY=$(grep OPENROUTER_KEY ../.env | cut -d= -f2)
```

The spike (`make spike`) runs on a real iOS Simulator OR Android Emulator
OR physical device.  It does **not** run in CI (D-53 — requires real
api_server + real Docker + OpenRouter network).  CI only runs `flutter
analyze` + unit tests via `.github/workflows/mobile.yml`.

### Spike Prerequisites

1. **Live `api_server`** running locally:  `cd api_server && make dev`
   (boots Postgres + Redis + the FastAPI server in docker compose).
2. **A valid ap_session cookie** (the `ap_session` cookie set by the web
   playground after OAuth):  sign in to the web playground at
   `http://localhost:3000/login` via Google OAuth (Phase 22c-oauth-google
   ships this), open browser DevTools → Application → Cookies →
   `http://localhost:8000` → copy the value of the `ap_session` cookie
   (a UUID).  Phase 25 replaces this manual paste with native
   `google_sign_in` calling `POST /v1/auth/google/mobile`.
3. **An OpenRouter BYOK key**:  put `OPENROUTER_KEY=sk-or-...` in a
   gitignored `.env` at the repo root.  The spike injects it as
   `Authorization: Bearer <key>` only on `POST /v1/runs` and
   `POST /v1/agents/:id/start` (D-40).
4. **A booted simulator OR emulator OR connected device.**

The spike on success appends evidence to `spikes/flutter-api-roundtrip.md`
with reproducibility metadata (D-54).

### Spike Concurrency (D-56)

Each spike run uses a unique agent name (`spike-roundtrip-<unix-ts>-<uuid>`),
so two simultaneous spike runs (e.g. two devs) get distinct
`agent_instances`.  The hard concurrency limit is the dev box's container
concurrency cap (configured in api_server) — exceeding it surfaces as a
`CONCURRENT_POLL_LIMIT` error from `POST /v1/agents/:id/start`.

## First-Run Network

On the FIRST run on a fresh simulator / emulator / device, the
`google_fonts` package fetches `Inter` + `JetBrainsMono` from Google's
CDN (~200 KB total).  If the device has no network on first launch the
theme falls back to the platform default (SF / Roboto) — placeholder
screen still renders.  This is acceptable for the MVP per RESEARCH
Pitfall #6; bundled-asset migration is a polish-phase concern.

## Folder Layout (D-26)

```
lib/
├── main.dart                  # entry — AppEnv.fromEnvironment + ProviderScope + runApp
├── app.dart                   # MaterialApp.router with solvrTheme
├── core/
│   ├── env/app_env.dart       # BASE_URL boot validation (D-43)
│   ├── theme/solvr_theme.dart # ThemeData mirroring solvr/frontend (APP-02)
│   ├── router/app_router.dart # go_router; placeholder route in P24
│   ├── api/                   # typed client + interceptors + Result + DTOs (D-31..D-42)
│   ├── storage/               # flutter_secure_storage wrapper for session_id (D-35)
│   └── auth/                  # auth-required event bus (Phase 25 listens)
├── shared/                    # reusable widgets (Phase 25)
└── features/                  # feature-based; P24 has only _placeholder/
```

## CI

`.github/workflows/mobile.yml` runs `fvm flutter analyze && fvm flutter
test` on every push to `mobile/**`.  No simulator runs (those need
macOS runners + booted simulators).  The spike runs locally only.

## Phase Index

- 24-CONTEXT.md  — locked decisions (56 D-decisions)
- 24-RESEARCH.md — package-version research + patterns + pitfalls
- 24-PATTERNS.md — file-by-file analog mapping
- 24-VALIDATION.md — per-task verification map
- 24-NN-PLAN.md  — execution plans (this directory)
- spikes/flutter-api-roundtrip.md — exit-gate evidence (Plan 10)

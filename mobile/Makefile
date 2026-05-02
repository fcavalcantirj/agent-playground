.PHONY: doctor get test ios android spike clean

doctor:  ## Phase 24 D-22 — fvm flutter doctor; one-time per-machine sanity check.
	fvm flutter doctor

get:  ## Phase 24 D-22 — fvm flutter pub get; resolve deps + write pubspec.lock.
	fvm flutter pub get

test:  ## Phase 24 D-22 — unit + widget tests (NOT the spike).
	fvm flutter analyze
	fvm flutter test

ios:  ## Phase 24 D-22 — run on iOS Simulator.  e.g. make ios DEVICE=<id> BASE_URL=http://localhost:8000
	fvm flutter run \
	  $(if $(DEVICE),-d $(DEVICE),) \
	  --dart-define BASE_URL=$(BASE_URL)

android:  ## Phase 24 D-22 — run on Android Emulator.  e.g. make android BASE_URL=http://10.0.2.2:8000
	fvm flutter run \
	  $(if $(DEVICE),-d $(DEVICE),) \
	  --dart-define BASE_URL=$(BASE_URL)

spike:  ## Phase 24 D-50 — 9-step roundtrip integration_test. Requires BASE_URL, SESSION_ID, OPENROUTER_KEY (D-49/D-51).
	@test -n "$$BASE_URL" || (echo "ERROR: BASE_URL not set. Per-target values: iOS Sim=http://localhost:8000  Android Emu=http://10.0.2.2:8000  device=http://<lan-ip>:8000  ngrok=https://<id>.ngrok-free.app" && exit 1)
	@test -n "$$SESSION_ID" || (echo "ERROR: SESSION_ID not set. Sign in to the web playground (Phase 22c-oauth-google) and copy ap_session cookie from browser DevTools." && exit 1)
	@test -n "$$OPENROUTER_KEY" || (echo "ERROR: OPENROUTER_KEY not set. Paste your OpenRouter BYOK key from local .env (e.g. \`make spike OPENROUTER_KEY=\$$(grep OPENROUTER_KEY ../.env | cut -d= -f2)\`)." && exit 1)
	@curl -fsS --max-time 5 "$$BASE_URL/healthz" >/dev/null || (echo "ERROR: api_server not healthy at $$BASE_URL/healthz. Start it with: cd ../api_server && make dev. RESEARCH Q4: this preflight saves the spike a 60s timeout when the backend is down." && exit 1)
	fvm flutter test integration_test/spike_api_roundtrip_test.dart \
	  --dart-define BASE_URL=$$BASE_URL \
	  --dart-define SESSION_ID=$$SESSION_ID \
	  --dart-define OPENROUTER_KEY=$$OPENROUTER_KEY

clean:  ## Phase 24 — wipe build artifacts.
	fvm flutter clean

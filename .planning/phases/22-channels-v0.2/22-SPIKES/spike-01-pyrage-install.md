# Spike 01 — pyrage install in api_server image

**Date:** 2026-04-18
**Plan affected:** 22-02 (age crypto)
**Verdict:** PASS (implicit via spike 02) with deploy delta

## Finding

Pure Python wheel, installs cleanly inside `deploy-api_server-1` via `pip install pyrage`. API surface inspected (see spike-02 for actual calls).

Current image (`tools/Dockerfile.api` baked with uv) does NOT include pyrage nor `cryptography`. `pip install` inside the running container works for probe but won't survive `docker compose up --build`.

## Plan delta

Plan 22-02 must also:

1. Add `pyrage` to `api_server/pyproject.toml` dependencies.
2. Add `cryptography` to `api_server/pyproject.toml` dependencies (HKDF for per-user KEK).
3. Rebuild image via `docker compose -f docker-compose.prod.yml -f docker-compose.local.yml build api_server`.
4. New env var `AP_CHANNEL_MASTER_KEY` (32 bytes base64) for the HKDF root. Must land in `deploy/.env.prod` secrets (gitignored; deploy.sh template ships a placeholder).

Zero structural surprise — just two dep additions and one env var. Minor.

## Verdict: PASS

pyrage works; cryptography works; HKDF → passphrase round-trip proven (spike 02).

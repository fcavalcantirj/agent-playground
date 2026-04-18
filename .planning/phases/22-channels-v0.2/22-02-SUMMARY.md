---
phase: 22-channels-v0.2
plan: 02
subsystem: database
tags: [postgres, alembic, asyncpg, age, pyrage, cryptography, hkdf, byok, channels]

# Dependency graph
requires:
  - phase: 19-api-foundation
    provides: alembic baseline (001), agent_instances table, ANONYMOUS_USER_ID seed, asyncpg repo pattern in run_store.py
  - phase: 22-channels-v0.2
    provides: 22-SPIKES/spike-01-pyrage-install.md + spike-02-age-hkdf.md (pyrage surface + cross-user KEK isolation proven)
provides:
  - alembic migration 003_agent_containers with BYTEA channel_config_enc + partial unique index on (agent_instance_id) WHERE status='running'
  - api_server.crypto.age_cipher module with encrypt_channel_config / decrypt_channel_config, per-user KEK via HKDF-SHA256 over AP_CHANNEL_MASTER_KEY
  - 5 new CRUD functions in run_store.py for persistent container lifecycle (insert_pending, write_running, mark_stopped, fetch, fetch_running_for_agent)
  - AP_CHANNEL_MASTER_KEY env var wired through docker-compose + .env.prod (template)
affects: [22-03-runner-persistent, 22-05-api-endpoints, 23-persistent-volumes]

# Tech tracking
tech-stack:
  added:
    - pyrage>=1.2 (Rust-backed age bindings, passphrase mode)
    - cryptography>=42 (HKDF-SHA256 for per-user KEK derivation)
  patterns:
    - Two-phase insert pattern reused for agent_containers (insert_pending_* -> write_*_running / mark_*_stopped), mirrors insert_pending_run / write_verdict
    - Partial unique index for MVP "one-active-per-agent" concurrency enforcement (raised via asyncpg.UniqueViolationError, route maps to 409)
    - AP_ENV=prod fail-loud gate on secrets (no silent dev-fallback in production)

key-files:
  created:
    - api_server/alembic/versions/003_agent_containers.py
    - api_server/src/api_server/crypto/__init__.py
    - api_server/src/api_server/crypto/age_cipher.py
    - deploy/.env.prod.example
  modified:
    - api_server/pyproject.toml (pyrage + cryptography deps)
    - tools/Dockerfile.api (mirror deps in baked pip install)
    - deploy/docker-compose.prod.yml (AP_CHANNEL_MASTER_KEY env passthrough)
    - api_server/src/api_server/services/run_store.py (5 new CRUD fns + imports + __all__)
    - .gitignore (gitignore deploy/.env.prod — holds live POSTGRES_PASSWORD + master key)

key-decisions:
  - Separate agent_containers table (not additive columns on agent_instances) — lets a single agent have a history of containers across start/stop cycles, useful for Phase 23 persistent volumes
  - Partial unique index (WHERE status='running') over a full unique constraint — stopped history doesn't block new starts; concurrent /start serializes on the UPDATE-to-running step
  - Aligned crypto helper to read AP_ENV (not AGENT_PLAYGROUND_ENV as plan originally wrote) — matches the deploy's actual convention in config.py and docker-compose.prod.yml; without this, prod fail-loud would never fire (deviation — see below)
  - age passphrase mode (not x25519 identities) — KEK rotation is simpler and covers the threat model (DB exfil, not key custody), per CLAUDE.md "libsodium / age" guidance

patterns-established:
  - "age-based at-rest encryption: per-user KEK = HKDF(master, info='ap-ch-'+uid.bytes), passphrase = b64(KEK), pyrage.passphrase.{encrypt,decrypt}"
  - "BYTEA-only channel cred storage: no plaintext sibling column exists at any lifecycle stage"
  - "Gitignored deploy/.env.prod + checked-in .env.prod.example — live secrets never land in git, template documents the shape"

requirements-completed: [SC-02, SC-04, SC-05]

# Metrics
duration: 28min
completed: 2026-04-18
---

# Phase 22 Plan 02: agent_containers audit table + age channel-cred encryption Summary

**Alembic 003 adds an agent_containers table with BYTEA age-encrypted channel_config + partial-unique-index "one running container per agent", plus a pyrage/HKDF per-user KEK crypto helper and 5 asyncpg CRUD functions — the data-plane foundation for Plan 22-05's /start, /stop, /status endpoints.**

## Performance

- **Duration:** ~28 min
- **Started:** 2026-04-18T17:10:00Z (approx)
- **Completed:** 2026-04-18T17:37:32Z
- **Tasks:** 4 (Task 0, 1, 2, 3 — all auto, no checkpoints)
- **Files modified:** 9 (4 created, 5 modified)

## Accomplishments

- Migration 003_agent_containers applied forward + downgrade round-trip clean against live dev Postgres (deploy-postgres-1 @ version 17-alpine)
- Partial unique index `ix_agent_containers_agent_instance_running` WHERE container_status='running' proven to fire on concurrent double-start (asyncpg.UniqueViolationError raised as expected)
- age + HKDF per-user KEK helper verified inside the rebuilt api_server container: round-trip within user OK, cross-user decrypt raises pyrage.DecryptError, ciphertext non-deterministic (random nonce), prod fails loud without master key, wrong-length master key fails loud
- 5 CRUD functions (insert_pending_agent_container, write_agent_container_running, mark_agent_container_stopped, fetch_agent_container, fetch_running_container_for_agent) all parameterized ($1, $2 …), no f-string interpolation, BYTEA round-trips, UUID→text cast in SELECT, NUMERIC→float conversion on boot_wall_s
- AP_CHANNEL_MASTER_KEY plumbed through compose without baking the live secret into git (.env.prod gitignored, .env.prod.example template committed)
- api_server image rebuilt with pyrage + cryptography baked in (not relying on the spike pip-install hack) and healthy post-recreate

## Task Commits

Each task was committed atomically (no TDD per plan — type: execute):

1. **Task 0: pyrage + cryptography deps, AP_CHANNEL_MASTER_KEY env, image rebuild** — `ba686cc` (chore)
2. **Task 1: Alembic migration 003 — agent_containers table** — `a8b09ee` (feat)
3. **Task 2: age-based per-user KEK crypto helper** — `de1dbd4` (feat)
4. **Task 3: 5 agent_containers CRUD functions in run_store.py** — `d82169a` (feat)

**Plan metadata (this SUMMARY + state):** will be committed by the orchestrator after the wave completes.

## Files Created/Modified

Created:
- `api_server/alembic/versions/003_agent_containers.py` — migration adding agent_containers table (14 columns, 2 CHECK constraints, 2 indexes — one partial unique)
- `api_server/src/api_server/crypto/__init__.py` — package marker, re-exports encrypt/decrypt
- `api_server/src/api_server/crypto/age_cipher.py` — encrypt_channel_config / decrypt_channel_config with HKDF-SHA256 per-user KEK + pyrage.passphrase
- `deploy/.env.prod.example` — checked-in template documenting POSTGRES_PASSWORD + AP_CHANNEL_MASTER_KEY (.env.prod itself is gitignored)

Modified:
- `api_server/pyproject.toml` — added `pyrage>=1.2`, `cryptography>=42`
- `tools/Dockerfile.api` — mirrored the deps in the baked pip install line so rebuilds pick them up
- `deploy/docker-compose.prod.yml` — added `AP_CHANNEL_MASTER_KEY: ${AP_CHANNEL_MASTER_KEY}` to api_server's environment block (value sourced from .env.prod at compose time via `--env-file`)
- `api_server/src/api_server/services/run_store.py` — added `datetime` import, 5 new async CRUD functions, updated `__all__`
- `.gitignore` — added `deploy/.env.prod` so live secrets stay out of git

## Decisions Made

- **Separate table over additive columns on agent_instances** — history of containers across start/stop cycles is a requirement (per PATTERNS.md §Artifact 6 rationale) and adding it later would be a destructive migration. Cost now is ~1 FK + 1 table; benefit later is Phase 23 volumes have a clean join target.
- **Partial unique index on (agent_instance_id) WHERE status='running'** over a full unique constraint — the MVP semantic is "one running container per agent", not "one container ever". A full constraint would require DELETE-on-stop (loses audit trail) or updating rows back (breaks referential history). Partial index gives the constraint without the semantic cost.
- **age passphrase mode, not x25519 identities** — the threat model is DB exfil, not key custody. Passphrase mode means rotation is just re-encrypt with a new KEK derivation; x25519 would require per-user keypair storage + migration tooling. CLAUDE.md says "libsodium / age" — age passphrase is the age-native path.
- **AP_ENV alignment** — plan originally had the helper read `AGENT_PLAYGROUND_ENV="production"` but the deployed convention is `AP_ENV="prod"` (see `api_server/src/api_server/config.py` line 39 + `docker-compose.prod.yml` line 40). Left uncorrected, the fail-loud check never fires. Documented as Rule 1 deviation below.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan's crypto helper read wrong env-var name — fail-loud gate would never fire**
- **Found during:** Task 2 (Verified by reading `api_server/src/api_server/config.py` and `deploy/docker-compose.prod.yml` during implementation)
- **Issue:** Plan's Task 2 code used `os.environ.get("AGENT_PLAYGROUND_ENV", "dev")` with comparison against `"production"`, but the deployed env uses `AP_ENV=prod` (per config.py's `Settings.env` field with `validation_alias="AP_ENV"` and compose sets `AP_ENV: prod`). As-written, `_master_key()` would always hit the dev fallback branch in production because neither the var name nor the value would match — silently shipping the 32-zero-byte key.
- **Fix:** Aligned the helper to read `os.environ.get("AP_ENV", "dev")` with comparison against `"prod"`. Matches the existing convention.
- **Files modified:** `api_server/src/api_server/crypto/age_cipher.py`
- **Verification:** `docker exec -e AP_ENV=prod -e AP_CHANNEL_MASTER_KEY= deploy-api_server-1 python3 ...` → `RuntimeError: AP_CHANNEL_MASTER_KEY required when AP_ENV=prod` (fail-loud confirmed)
- **Committed in:** `de1dbd4` (Task 2 commit)

**2. [Rule 2 - Missing Critical] Plan didn't gitignore deploy/.env.prod — live POSTGRES_PASSWORD would have landed in git**
- **Found during:** Task 0 (Pre-commit `git status` showed `deploy/.env.prod` as untracked and not gitignored; the existing file in the main repo contains the real Postgres password)
- **Issue:** Plan Task 0 step 2 said "add AP_CHANNEL_MASTER_KEY= to deploy/.env.prod" and treated the file as a "template comment only", but the file in practice holds the live POSTGRES_PASSWORD. Committing it would leak the secret; committing only an empty shell doesn't match reality.
- **Fix:** Added `deploy/.env.prod` to `.gitignore`; created `deploy/.env.prod.example` as the checked-in template documenting both secrets' shape (with blank values + generation commands). Compose is invoked with `--env-file deploy/.env.prod` so the ignored file still supplies the runtime values.
- **Files modified:** `.gitignore`, `deploy/.env.prod.example` (new), — and `deploy/.env.prod` itself was written on disk but left untracked
- **Verification:** `git status --short` does not list `deploy/.env.prod`; `docker inspect deploy-api_server-1` shows `DATABASE_URL` with the real password resolved from the ignored file via `--env-file`; api_server health endpoint returns 200
- **Committed in:** `ba686cc` (Task 0 commit)

**3. [Rule 3 - Blocking] Dockerfile.api didn't install pyrage/cryptography — rebuild would drop the spike's pip-install hack**
- **Found during:** Task 0 (Reading `tools/Dockerfile.api` — it pins every dep via an explicit pip install list, not `pip install .`)
- **Issue:** Plan Task 0 only added deps to `pyproject.toml`, but the image's pip install line is hardcoded in the Dockerfile. A rebuild without mirroring the deps would produce an image without pyrage/cryptography, and all subsequent tasks' verifications would fail on import.
- **Fix:** Added `'pyrage>=1.2' 'cryptography>=42'` to the hardcoded `RUN pip install ...` line in `tools/Dockerfile.api` so the image contract matches `pyproject.toml`.
- **Files modified:** `tools/Dockerfile.api`
- **Verification:** `docker compose build api_server` succeeded; post-rebuild container imports pyrage.passphrase + cryptography cleanly without the spike's inline pip install
- **Committed in:** `ba686cc` (Task 0 commit)

**4. [Rule 3 - Blocking] Compose `${VAR}` substitution needed `--env-file` flag — container recreated without password, asyncpg auth failed**
- **Found during:** Task 0 (First `docker compose up -d` after rebuild — api_server logs showed `InvalidPasswordError: password authentication failed for user "ap"`)
- **Issue:** Compose substitutes `${POSTGRES_PASSWORD}` and `${AP_CHANNEL_MASTER_KEY}` at YAML parse time from the SHELL env, not from the container-side `env_file:` block. Without the shell vars set, compose substitutes empty strings and the resolved `DATABASE_URL` in the container is `postgresql+asyncpg://ap:@postgres:5432/...`.
- **Fix:** Re-ran compose with `--env-file deploy/.env.prod` (which loads the file into compose's substitution context BEFORE the YAML is parsed). `DATABASE_URL` resolved correctly and api_server healthcheck returned 200.
- **Files modified:** none (documented the correct invocation for future operators)
- **Verification:** `docker inspect deploy-api_server-1` shows full `DATABASE_URL` with password; `/healthz` returns 200 within 5s
- **Documented in:** `deploy/.env.prod.example` header comments (guiding future operators to the `--env-file` flag)

---

**Total deviations:** 4 auto-fixed (1 Rule 1 bug, 1 Rule 2 missing critical, 2 Rule 3 blocking)
**Impact on plan:** All four were correctness-essential. Without #1 prod would silently use the 32-zero-byte dev fallback key; without #2 a secret would ship to git; without #3 the image rebuild produces a broken container; without #4 the rebuilt container can't authenticate to Postgres. No scope creep — each is in-plan infrastructure that the plan didn't fully specify.

## Issues Encountered

- **pyrage API surface drift** — plan referenced `pyrage.passphrase.Recipient.from_str(...)` and `pyrage.passphrase.Identity.from_str(...)` in earlier drafts; spike-02 absorbed the correction ("actual API: just `encrypt(data, passphrase_str)` and `decrypt(data, passphrase_str)`"). Plan's final Task 2 already had the correction; no additional action needed.
- **Compose `--env-file` vs `env_file:`** — two different mechanisms. `env_file:` in the YAML injects variables INTO the container; `--env-file` passed to compose CLI supplies variables for YAML `${VAR}` substitution. The plan assumed both happen automatically; actual operators must pass `--env-file` explicitly. Documented in `.env.prod.example` for Plan 22-03+ operators.

## User Setup Required

None — Plan 22-02 is pure data-plane. No external service configuration; operators only need to rotate `AP_CHANNEL_MASTER_KEY` in `deploy/.env.prod` from the empty template value to `$(openssl rand -base64 32)` before any production deploy that uses persistent channels.

## Next Phase Readiness

Ready for **Plan 22-05** (API endpoints `/start` / `/stop` / `/status`):
- `insert_pending_agent_container` + `write_agent_container_running` implement the two-phase "Pitfall 4" DB pool release pattern documented in PATTERNS.md §4
- `fetch_running_container_for_agent` gives /stop + /status their deterministic path from `agent_instance_id` → `container_id`
- Partial unique index provides the concurrency guarantee `/start` needs (UniqueViolation → 409 AGENT_ALREADY_RUNNING)
- `channel_config_enc` BYTEA + `crypto/age_cipher.py` give /start its at-rest persistence path for bot tokens (SC-05 satisfied at the schema layer; /start route is responsible for calling `encrypt_channel_config` with the user-supplied creds then discarding the plaintext)

Ready for **Plan 22-03** (runner `--mode persistent`):
- No direct coupling from 22-02 → 22-03; the runner interacts with containers, not DB. 22-03 is unblocked.

No blockers. No concerns.

## Self-Check: PASSED

All claimed artifacts exist and all claimed commits land on the branch:

- FOUND: `api_server/alembic/versions/003_agent_containers.py`
- FOUND: `api_server/src/api_server/crypto/__init__.py`
- FOUND: `api_server/src/api_server/crypto/age_cipher.py`
- FOUND: `deploy/.env.prod.example`
- FOUND: commit `ba686cc` (Task 0 — pyrage + cryptography deps)
- FOUND: commit `a8b09ee` (Task 1 — alembic 003)
- FOUND: commit `de1dbd4` (Task 2 — age cipher)
- FOUND: commit `d82169a` (Task 3 — run_store CRUD)

---
*Phase: 22-channels-v0.2*
*Plan: 02*
*Completed: 2026-04-18*

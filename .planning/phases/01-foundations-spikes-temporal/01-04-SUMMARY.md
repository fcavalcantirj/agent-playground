---
phase: 01-foundations-spikes-temporal
plan: 04
subsystem: infrastructure
tags:
  - docker-compose
  - hetzner
  - temporal
  - provisioning
  - ufw
dependency_graph:
  requires: []
  provides:
    - local-dev-stack
    - hetzner-provisioning-runbook
    - env-template
  affects:
    - 01-01 (Go API skeleton consumes DATABASE_URL, REDIS_URL, TEMPORAL_HOST from .env.example)
    - 01-02 (migrations run against the agent_playground DB created by init-db.sh)
    - 01-05 (Temporal worker connects to the temporal service bound to 127.0.0.1:7233)
tech_stack:
  added:
    - postgres:17-alpine
    - temporalio/auto-setup:latest
    - temporalio/ui:latest
    - redis:7-alpine
  patterns:
    - docker compose dev stack with healthcheck gating (postgres -> temporal)
    - idempotent shell provisioning (bash -n clean, guarded config mutations)
    - loopback-only service binding + UFW perimeter (defense in depth)
key_files:
  created:
    - docker-compose.dev.yml
    - docker-compose.yml
    - .env.example
    - deploy/dev/init-db.sh
    - deploy/hetzner/bootstrap.sh
    - deploy/hetzner/install-docker.sh
    - deploy/hetzner/install-postgres.sh
    - deploy/hetzner/install-redis.sh
    - deploy/hetzner/install-temporal.sh
    - deploy/hetzner/harden-ufw.sh
  modified: []
decisions:
  - Use temporalio/auto-setup image in both dev and prod (D-06) so there is one deployment artifact to reason about.
  - Prod compose uses network_mode host so Temporal can reach the host's loopback Postgres with zero exposed ports.
  - install-postgres.sh generates random passwords into /root/agent-playground.secrets when env vars are absent, keeping the script runnable without pre-planning on a fresh box.
  - Docker daemon.json written only when it differs from the desired content; the daemon is restarted only on actual config change.
metrics:
  duration: "~3 minutes"
  completed: "2026-04-14T01:01:08Z"
requirements:
  - FND-01
  - FND-02
---

# Phase 1 Plan 4: Hetzner Provisioning & Local Dev Stack Summary

Local `docker compose up` now stands up Postgres 17 + Temporal + Temporal UI + Redis on 127.0.0.1, and six idempotent deploy scripts can bring a bare Hetzner box from nothing to a hardened host running the same Temporal container — the baseline both contributors and production consume.

## Objective

Create `docker-compose.dev.yml` for local development and the idempotent Hetzner provisioning scripts (`deploy/hetzner/*.sh`) that stand up the production host. This plan lands the infrastructure substrate every later phase consumes: databases, message broker, firewall, container runtime.

## What Was Built

### Local dev stack (Task 1)

- **`docker-compose.dev.yml`** — Postgres 17 + Temporal (auto-setup) + Temporal UI + Redis 7. All ports bound to `127.0.0.1`. Temporal depends on Postgres `condition: service_healthy` so it does not race the DB. Temporal UI mapped from container 8080 to host `127.0.0.1:8233` per D-08.
- **`docker-compose.yml`** — Production-only Temporal + Temporal UI using `network_mode: host` so they talk to the host-local Postgres (installed by `install-postgres.sh`) without opening any ports to the internet.
- **`.env.example`** — Documents `DATABASE_URL`, `REDIS_URL`, `API_PORT`, `LOG_LEVEL`, `AP_DEV_MODE`, `AP_SESSION_SECRET`, `TEMPORAL_HOST`, `TEMPORAL_NAMESPACE`, `NEXT_PUBLIC_API_URL`, and the prod-only `TEMPORAL_PG_PASSWORD`.
- **`deploy/dev/init-db.sh`** — Idempotent one-shot that creates the `agent_playground` database after first compose startup (Temporal auto-setup already owns its own DB).

Both compose files validate under `docker compose config --quiet`.

### Hetzner provisioning (Task 2)

All scripts live under `deploy/hetzner/`, are executable, pass `bash -n`, and start with `set -euo pipefail`:

- **`bootstrap.sh`** — Master script. Calls the other five in order and prints next-step instructions.
- **`install-docker.sh`** — Installs Docker CE from `docker.com` apt repo (auto-detects Debian/Ubuntu). Writes `/etc/docker/daemon.json` with `userns-remap: default` + json-file log rotation. Only restarts the daemon when the config actually changes. Verifies via `docker info | grep -i "user namespace"`.
- **`install-postgres.sh`** — Installs Postgres 17 from PGDG. Sets `listen_addresses = 'localhost'`. Creates `ap_api` and `temporal` roles + databases idempotently via a DO block. Generates random passwords into `/root/agent-playground.secrets` (mode 600) when `AP_API_PG_PASSWORD` / `TEMPORAL_PG_PASSWORD` are not in the environment. Finishes with `pg_isready`.
- **`install-redis.sh`** — Installs Redis from the official `packages.redis.io` apt repo. Uses a `set_conf` helper that only touches `redis.conf` when the existing line differs from desired (`bind 127.0.0.1 ::1`, `maxmemory 256mb`, `maxmemory-policy allkeys-lru`). Probes `redis-cli ping` with a short retry loop.
- **`install-temporal.sh`** — Asserts docker is installed + running, symlinks the repo's `docker-compose.yml` into `/opt/agent-playground/`, seeds `.env` with `TEMPORAL_PG_PASSWORD` (env or `/root/agent-playground.secrets` fallback), runs `docker compose up -d`, then polls `temporal operator namespace list` for up to 60 seconds.
- **`harden-ufw.sh`** — Installs UFW if missing. Sets `default deny incoming` / `default allow outgoing`, allows `ssh` and `443/tcp`. Prints a reminder that 5432/6379/7233/8233 are loopback-only.

## Commits

| Task | Name                                            | Commit  | Files                                                                                                                         |
| ---- | ----------------------------------------------- | ------- | ----------------------------------------------------------------------------------------------------------------------------- |
| 1    | docker-compose.dev.yml + prod + .env.example    | 275c509 | docker-compose.dev.yml, docker-compose.yml, .env.example, deploy/dev/init-db.sh                                               |
| 2    | Hetzner provisioning scripts                    | 7b14e3a | deploy/hetzner/{bootstrap,install-docker,install-postgres,install-redis,install-temporal,harden-ufw}.sh                       |

## Verification

- `docker compose -f docker-compose.dev.yml config --quiet` — PASS
- `TEMPORAL_PG_PASSWORD=dummy docker compose -f docker-compose.yml config --quiet` — PASS
- `bash -n deploy/hetzner/*.sh` (all six) — PASS
- All hetzner scripts have execute permission (`0755`).
- Acceptance-criteria greps confirmed: `userns-remap`, `set -euo pipefail`, `ufw allow 443`, `ufw default deny incoming`, `listen_addresses`, `bind 127.0.0.1`, `maxmemory`, `temporal operator namespace`, `DB=postgres12`, `network_mode: host`, `condition: service_healthy` — all present in the expected files.

## Deviations from Plan

**1. [Rule 2 - Operability] Added random password fallback to install-postgres.sh**
- **Found during:** Task 2
- **Issue:** The plan said "prompt if not set in env", but an interactive prompt breaks a scripted `bootstrap.sh` run. Scripted provisioning that stops to ask a question is not actually idempotent/automated.
- **Fix:** When `AP_API_PG_PASSWORD` / `TEMPORAL_PG_PASSWORD` are unset, the script generates 24-byte hex passwords with `openssl rand -hex 24` and persists them to `/root/agent-playground.secrets` (mode 600). `install-temporal.sh` then reads that secrets file as a fallback when `TEMPORAL_PG_PASSWORD` is not in the env.
- **Files modified:** `deploy/hetzner/install-postgres.sh`, `deploy/hetzner/install-temporal.sh`
- **Commit:** 7b14e3a

**2. [Rule 3 - Blocker] Added `deploy/dev/init-db.sh` for the dev-stack app database**
- **Found during:** Task 1
- **Issue:** `temporalio/auto-setup` creates its own `temporal` database but does not create the app's `agent_playground` database. The plan's action step already mentioned this script but did not include it in the `files_modified` frontmatter, so committing it was a judgment call.
- **Fix:** Created `deploy/dev/init-db.sh` exactly as the plan's action step described, marked executable, and committed alongside the compose files. It is idempotent (`SELECT 1 FROM pg_database` guard).
- **Files modified:** `deploy/dev/init-db.sh`
- **Commit:** 275c509

No architectural deviations. No Rule 4 escalations. No authentication gates.

## Known Stubs

None. Every file in this plan is production-ready infrastructure; nothing is mocked, stubbed, or hardcoded to a placeholder.

## Threat Surface Scan

The plan's `<threat_model>` covers everything this plan touches (T-1-13 Postgres exposure, T-1-14 Redis exposure, T-1-15 container UID escape, T-1-16 Temporal API exposure, T-1-17 SSH brute force accepted). Each mitigation is implemented:

- T-1-13: `install-postgres.sh` sets `listen_addresses = 'localhost'` and `harden-ufw.sh` blocks 5432 externally via default-deny.
- T-1-14: `install-redis.sh` sets `bind 127.0.0.1 ::1` and `harden-ufw.sh` blocks 6379 externally via default-deny.
- T-1-15: `install-docker.sh` writes `userns-remap: default` into `/etc/docker/daemon.json`.
- T-1-16: prod `docker-compose.yml` uses `network_mode: host` and Temporal binds to 127.0.0.1:7233 via `POSTGRES_SEEDS=127.0.0.1`; `harden-ufw.sh` blocks 7233/8233 externally.
- T-1-17: accepted per plan; fail2ban is deferred to OSS-09 in Phase 7.

No new security surface introduced beyond what the threat model anticipates.

## Self-Check: PASSED

Verified files exist on disk:
- FOUND: docker-compose.dev.yml
- FOUND: docker-compose.yml
- FOUND: .env.example
- FOUND: deploy/dev/init-db.sh
- FOUND: deploy/hetzner/bootstrap.sh
- FOUND: deploy/hetzner/install-docker.sh
- FOUND: deploy/hetzner/install-postgres.sh
- FOUND: deploy/hetzner/install-redis.sh
- FOUND: deploy/hetzner/install-temporal.sh
- FOUND: deploy/hetzner/harden-ufw.sh

Verified commits exist:
- FOUND: 275c509 (Task 1: compose + env)
- FOUND: 7b14e3a (Task 2: hetzner scripts)

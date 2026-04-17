# Agent Playground API — Hetzner Deployment

Phase 19 deploys the FastAPI `api_server/` service to a single Hetzner host behind
Caddy-managed TLS. Single-tenant, single-box — multi-tenant isolation is phase 22+.

## Prerequisites

1. Hetzner dedicated box with Docker Engine 27+ installed (see `deploy/hetzner/install-docker.sh`).
2. DNS A record: `api.agentplayground.dev` → Hetzner box IPv4.
3. Ports 80 + 443 open to the internet (`deploy/hetzner/harden-ufw.sh` already does this — 443 allowed; add 80 if not present for ACME HTTP-01 challenge fallback).
4. Git checkout of this repo on the box at a stable path (e.g. `/srv/agent-playground`).

## First Deploy

```bash
ssh ap@your-hetzner-host
cd /srv/agent-playground/deploy
bash deploy.sh
# First run auto-generates secrets/pg_password (kept out of git via .gitignore).
# Caddy requests Let's Encrypt cert on first boot — watch logs:
docker compose -f docker-compose.prod.yml logs -f caddy
```

Verify live:

```bash
curl -fsS https://api.agentplayground.dev/healthz
curl -fsS https://api.agentplayground.dev/readyz | jq
bash ../test/smoke-api.sh --live
```

## Subsequent Deploys

```bash
cd /srv/agent-playground/deploy
bash deploy.sh
```

The script is idempotent. It: pulls git, ensures secret exists, builds api_server with
the correct DOCKER_GID (Pitfall 5), ensures postgres is up + healthy, runs
`alembic upgrade head` **[BLOCKING]** before rolling api_server, then rolls + probes.

## Trust Boundary: Docker Socket

**Accepted risk per CONTEXT.md D-08.**

The `api_server` container mounts `/var/run/docker.sock` because the runner
(`tools/run_recipe.py`) shells out to `docker build` and `docker run` to execute
recipe containers. This is a **container-escape surface**: anyone who achieves code
execution inside the api_server container can control Docker on the host and,
therefore, the host.

**Why accepted for Phase 19:**
- Single-tenant box (no other untrusted workloads colocated).
- No authenticated users yet; BYOK is the only surface, and keys never persist.
- Runner has been hardened in Phases 9–18 (lint gate, timeouts, output bounds,
  provenance, isolation defaults per recipe).

**Mitigations in place:**
- UFW blocks all inbound except 22 (SSH) + 80 + 443.
- api_server container runs as non-root (`apiuser`, UID 1001) inside the container.
- Log redaction middleware (Plan 19-06) prevents BYOK leak into log sinks.
- Rate limit + idempotency middleware (Plan 19-05) bound abuse from a single key.
- `AP_ENV=prod` gates `/docs` and `/redoc` closed (D-10).
- No Postgres port exposed to the host network — compose-internal only.

**Phase 22+ plan:** switch to Sysbox runtime (user-namespaced Docker-in-Docker
without host socket mount) OR introduce a broker service that executes recipes on a
firecracker microVM pool.

## Rollback

```bash
cd /srv/agent-playground
git checkout <known-good-sha>
cd deploy
bash deploy.sh
```

Or rollback just the image:

```bash
cd /srv/agent-playground/deploy
docker compose -f docker-compose.prod.yml down api_server
docker image tag api_server:previous api_server:latest
docker compose -f docker-compose.prod.yml up -d api_server
```

## Adding New Env Vars

Env vars for the api_server container are sourced from two places:

1. **Non-secret, declarative knobs** — add to `docker-compose.prod.yml` under the
   `api_server.environment:` block. Also add to `.env.example` at the repo root so
   dev setups match.
2. **Secrets (DB password, API keys, etc.)** — write to `deploy/secrets/<name>`
   (`.gitignore` in that directory blocks accidental commits) and reference via
   the `secrets:` block in compose, or interpolate into `.env.prod` from
   `deploy/deploy.sh` at deploy time.

After adding a new var, re-run `bash deploy.sh` — it will rebuild + roll the service.

## Backups

Postgres state lives in the `pgdata` named volume on the host. Phase 19 does NOT
automate backups. A manual snapshot recipe:

```bash
cd /srv/agent-playground/deploy
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U ap agent_playground_api > backup-$(date +%F).sql
```

Future phase: snapshot to Hetzner Storage Box via `restic` (matches Phase 7 PER-04
pattern for volumes).

## Note on CLAUDE.md Banner

CLAUDE.md banner (dated 2026-04-15) says do NOT touch `deploy/`. That banner referred
to the abandoned Go-era `deploy/` artifacts (`deploy/ap-base/`, `deploy/ap-runtime-*/`,
`deploy/hetzner/`, `deploy/dev/`). Phase 19 re-uses the `deploy/` directory per
CONTEXT.md §D-08 (locked decision) for Python+FastAPI production artifacts added
**alongside** — not replacing — the existing content. See
`.planning/phases/19-api-foundation/19-CONTEXT.md` §D-08.

## Troubleshooting

- **TLS cert reissue fails:** check `docker compose logs caddy` — ACME rate limit
  is 5 failures + 5 duplicates per hour per domain. Fix: ensure `caddy_data` named
  volume is NOT accidentally pruned (persistence was the Pitfall 7 issue).
- **`/readyz` says `docker_daemon: false`:** container can't see Docker socket.
  Check `DOCKER_GID` matches host: `stat -c %g /var/run/docker.sock` on host, compare
  against build-time arg. Re-run `deploy.sh` — it recomputes and rebuilds.
- **`alembic upgrade head` fails:** check `DATABASE_URL` resolves postgres:5432 from
  inside the compose network; confirm postgres healthy via
  `docker compose -f docker-compose.prod.yml exec postgres pg_isready -U ap`.
- **`curl https://api.agentplayground.dev` times out:** confirm Hetzner Cloud
  Firewall (if used) and `ufw status` both allow 80/443 inbound, and that DNS
  actually resolves to the box (`dig +short api.agentplayground.dev`).

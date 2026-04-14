#!/bin/bash
# Install / start the Temporal server on the Hetzner host via docker compose.
#
# Assumes install-docker.sh and install-postgres.sh have already run — Docker
# must be present, and Postgres must accept connections on 127.0.0.1:5432
# with a `temporal` role whose password lives in $TEMPORAL_PG_PASSWORD.
#
# Idempotent: `docker compose up -d` reconciles running state; the script
# only creates /opt/agent-playground/.env if it doesn't already exist.
set -euo pipefail

APP_DIR="/opt/agent-playground"
ENV_FILE="${APP_DIR}/.env"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

echo "[install-temporal] starting"

if ! command -v docker >/dev/null 2>&1; then
  echo "[install-temporal] ERROR: docker not installed — run install-docker.sh first" >&2
  exit 1
fi

if ! systemctl is-active --quiet docker; then
  echo "[install-temporal] starting docker daemon"
  systemctl start docker
fi

mkdir -p "$APP_DIR"

# Symlink the compose file from the checked-out repo so an upgrade is just
# `git pull && docker compose up -d` from $APP_DIR.
if [ ! -e "${APP_DIR}/docker-compose.yml" ]; then
  ln -sf "${REPO_ROOT}/docker-compose.yml" "${APP_DIR}/docker-compose.yml"
  echo "[install-temporal] symlinked docker-compose.yml -> ${REPO_ROOT}/docker-compose.yml"
fi

# Seed the .env file with the Temporal Postgres password, either from the
# environment or, as a last resort, from /root/agent-playground.secrets
# (written by install-postgres.sh when no password was provided).
if [ ! -f "$ENV_FILE" ]; then
  TEMPORAL_PG_PASSWORD="${TEMPORAL_PG_PASSWORD:-}"
  if [ -z "$TEMPORAL_PG_PASSWORD" ] && [ -f /root/agent-playground.secrets ]; then
    TEMPORAL_PG_PASSWORD="$(grep -E '^TEMPORAL_PG_PASSWORD=' /root/agent-playground.secrets | tail -n1 | cut -d= -f2-)"
  fi
  if [ -z "$TEMPORAL_PG_PASSWORD" ]; then
    echo "[install-temporal] ERROR: TEMPORAL_PG_PASSWORD is not set and no secrets file found" >&2
    exit 1
  fi
  umask 077
  echo "TEMPORAL_PG_PASSWORD=${TEMPORAL_PG_PASSWORD}" > "$ENV_FILE"
  echo "[install-temporal] wrote $ENV_FILE"
fi

# Bring Temporal up (compose handles idempotency — already-running containers
# are left alone, missing ones are created).
(cd "$APP_DIR" && docker compose up -d)

# Poll until Temporal answers. Uses `temporal` CLI inside the server container
# so we don't have to install it on the host.
echo "[install-temporal] waiting for temporal to become ready"
attempts=0
max_attempts=30
until docker compose -f "${APP_DIR}/docker-compose.yml" exec -T temporal temporal operator namespace list >/dev/null 2>&1; do
  attempts=$((attempts + 1))
  if [ "$attempts" -ge "$max_attempts" ]; then
    echo "[install-temporal] ERROR: temporal did not become ready after ${max_attempts} attempts" >&2
    exit 1
  fi
  sleep 2
done

echo "[install-temporal] temporal operator namespace list succeeded"
echo "[install-temporal] done"

#!/usr/bin/env bash
# Idempotent CREATE DATABASE agent_playground_api (Phase 19).
# Mirrors deploy/dev/init-db.sh shape. Safe to re-run.
set -euo pipefail

cd "$(dirname "$0")"
# --env-file so compose can interpolate ${POSTGRES_PASSWORD} from .env.prod at
# parse time. Without this, `exec` against the postgres service works because
# postgres already has the password baked in via env_file, but other compose
# invocations from this project silently substitute empty strings.
COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env.prod"
DB=agent_playground_api

# -d postgres: always connect to the default maintenance DB (which always
# exists) rather than letting psql default to -d $PGUSER, which on first boot
# is `ap` and does not exist yet.
if $COMPOSE exec -T postgres \
      psql -U ap -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DB'" 2>/dev/null \
      | grep -q 1; then
  echo "[init-api-db] database $DB already exists"
else
  $COMPOSE exec -T postgres \
    psql -U ap -d postgres -c "CREATE DATABASE $DB OWNER ap"
  echo "[init-api-db] database $DB created"
fi

echo "[init-api-db] db: ready"

#!/usr/bin/env bash
# Idempotent CREATE DATABASE agent_playground_api (Phase 19).
# Mirrors deploy/dev/init-db.sh shape. Safe to re-run.
set -euo pipefail

cd "$(dirname "$0")"
COMPOSE="docker compose -f docker-compose.prod.yml"
DB=agent_playground_api

if $COMPOSE exec -T postgres \
      psql -U ap -tAc "SELECT 1 FROM pg_database WHERE datname='$DB'" 2>/dev/null \
      | grep -q 1; then
  echo "[init-api-db] database $DB already exists"
else
  $COMPOSE exec -T postgres \
    psql -U ap -c "CREATE DATABASE $DB OWNER ap"
  echo "[init-api-db] database $DB created"
fi

echo "[init-api-db] db: ready"

#!/bin/bash
# Create the agent_playground database used by the Go API.
#
# Temporal's own database is created automatically by the `temporalio/auto-setup`
# image on first start, so it's not our concern here. This script is idempotent:
# it checks for the database before attempting to create it.
set -euo pipefail

COMPOSE_FILE="docker-compose.dev.yml"

if docker compose -f "$COMPOSE_FILE" exec -T postgresql \
    psql -U temporal -tAc "SELECT 1 FROM pg_database WHERE datname = 'agent_playground'" | grep -q 1; then
  echo "Database agent_playground already exists"
else
  docker compose -f "$COMPOSE_FILE" exec -T postgresql \
    psql -U temporal -c "CREATE DATABASE agent_playground OWNER temporal"
  echo "Database agent_playground created"
fi

echo "Database agent_playground ready"

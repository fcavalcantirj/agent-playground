#!/bin/bash
# Install PostgreSQL 17 on a Debian/Ubuntu Hetzner host from the PGDG apt
# repository and create the app + Temporal databases.
#
# Idempotent: skips installation if Postgres 17 is already present, uses
# `CREATE ... IF NOT EXISTS`-style guards for users and databases, and
# only rewrites postgresql.conf when `listen_addresses` is not already
# bound to localhost.
#
# Security (T-1-13): listen_addresses = 'localhost'. The host's UFW
# (harden-ufw.sh) additionally blocks 5432 from the internet.
set -euo pipefail

PG_MAJOR=17
PG_CONF="/etc/postgresql/${PG_MAJOR}/main/postgresql.conf"

echo "[install-postgres] starting"

if command -v pg_lsclusters >/dev/null 2>&1 && pg_lsclusters | awk '{print $1}' | grep -qx "${PG_MAJOR}"; then
  echo "[install-postgres] postgres ${PG_MAJOR} already installed"
else
  echo "[install-postgres] installing postgres ${PG_MAJOR} from PGDG"
  apt-get update
  apt-get install -y curl ca-certificates gnupg lsb-release

  install -d /etc/apt/keyrings
  if [ ! -f /etc/apt/keyrings/pgdg.gpg ]; then
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      | gpg --dearmor -o /etc/apt/keyrings/pgdg.gpg
  fi

  codename="$(. /etc/os-release && echo "${VERSION_CODENAME}")"
  echo "deb [signed-by=/etc/apt/keyrings/pgdg.gpg] https://apt.postgresql.org/pub/repos/apt ${codename}-pgdg main" \
    > /etc/apt/sources.list.d/pgdg.list

  apt-get update
  apt-get install -y "postgresql-${PG_MAJOR}"
fi

# Ensure listen_addresses = 'localhost' (bind only to loopback).
if [ -f "$PG_CONF" ]; then
  if grep -Eq "^\s*listen_addresses\s*=\s*'localhost'" "$PG_CONF"; then
    echo "[install-postgres] listen_addresses already set to 'localhost'"
  else
    echo "[install-postgres] configuring listen_addresses = 'localhost' in $PG_CONF"
    # Remove any existing listen_addresses line, then append ours
    sed -i "/^\s*listen_addresses\s*=/d" "$PG_CONF"
    echo "listen_addresses = 'localhost'" >> "$PG_CONF"
    systemctl restart "postgresql@${PG_MAJOR}-main" || systemctl restart postgresql
  fi
fi

systemctl enable --now postgresql

# Read passwords from environment (caller is expected to export these).
# Fall back to generating a random password and writing it to /root/ if unset,
# so a first-time operator can still run the script without pre-planning.
AP_API_PG_PASSWORD="${AP_API_PG_PASSWORD:-}"
TEMPORAL_PG_PASSWORD="${TEMPORAL_PG_PASSWORD:-}"

if [ -z "$AP_API_PG_PASSWORD" ]; then
  AP_API_PG_PASSWORD="$(openssl rand -hex 24)"
  echo "AP_API_PG_PASSWORD=$AP_API_PG_PASSWORD" >> /root/agent-playground.secrets
  chmod 600 /root/agent-playground.secrets
  echo "[install-postgres] generated AP_API_PG_PASSWORD (saved to /root/agent-playground.secrets)"
fi

if [ -z "$TEMPORAL_PG_PASSWORD" ]; then
  TEMPORAL_PG_PASSWORD="$(openssl rand -hex 24)"
  echo "TEMPORAL_PG_PASSWORD=$TEMPORAL_PG_PASSWORD" >> /root/agent-playground.secrets
  chmod 600 /root/agent-playground.secrets
  echo "[install-postgres] generated TEMPORAL_PG_PASSWORD (saved to /root/agent-playground.secrets)"
fi

# Create roles + databases idempotently via `psql` as the postgres superuser.
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ap_api') THEN
    CREATE ROLE ap_api LOGIN PASSWORD '${AP_API_PG_PASSWORD}';
  ELSE
    ALTER ROLE ap_api WITH PASSWORD '${AP_API_PG_PASSWORD}';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'temporal') THEN
    CREATE ROLE temporal LOGIN PASSWORD '${TEMPORAL_PG_PASSWORD}';
  ELSE
    ALTER ROLE temporal WITH PASSWORD '${TEMPORAL_PG_PASSWORD}';
  END IF;
END
\$\$;
SQL

for db in agent_playground temporal; do
  if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname = '${db}'" | grep -q 1; then
    echo "[install-postgres] database ${db} already exists"
  else
    owner="ap_api"
    if [ "$db" = "temporal" ]; then
      owner="temporal"
    fi
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE ${db} OWNER ${owner}"
    echo "[install-postgres] created database ${db} owned by ${owner}"
  fi
done

pg_isready -h 127.0.0.1
echo "[install-postgres] done"

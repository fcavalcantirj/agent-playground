#!/bin/bash
# Configure UFW as the perimeter firewall: deny all incoming except SSH
# and HTTPS. Everything else (Postgres, Redis, Temporal, Docker-internal
# ports) is reachable only via the loopback interface.
#
# Idempotent: `ufw allow` silently no-ops on existing rules, and
# `ufw --force enable` leaves an already-enabled firewall alone.
set -euo pipefail

echo "[harden-ufw] starting"

if ! command -v ufw >/dev/null 2>&1; then
  echo "[harden-ufw] installing ufw"
  apt-get update
  apt-get install -y ufw
fi

ufw default deny incoming
ufw default allow outgoing

ufw allow ssh
ufw allow 443/tcp

# Enable — --force skips the interactive prompt; safe to call on an
# already-enabled firewall.
ufw --force enable

echo "[harden-ufw] current status:"
ufw status verbose

echo "[harden-ufw] Postgres (5432), Redis (6379), Temporal (7233, 8233) are NOT exposed — loopback only"
echo "[harden-ufw] done"

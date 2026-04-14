#!/bin/bash
# Agent Playground — Hetzner host bootstrap.
#
# Master provisioning script. Calls every install-*.sh + harden-ufw.sh in
# the correct order. Each sub-script is independently idempotent, so this
# script is safe to re-run.
#
# Run as root on a fresh Debian/Ubuntu Hetzner dedicated box.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Agent Playground Host Bootstrap ==="
echo "Date: $(date -u)"
echo "Script dir: $SCRIPT_DIR"
echo ""

"$SCRIPT_DIR/install-docker.sh"
"$SCRIPT_DIR/install-postgres.sh"
"$SCRIPT_DIR/install-redis.sh"
"$SCRIPT_DIR/install-temporal.sh"
"$SCRIPT_DIR/harden-ufw.sh"

echo ""
echo "=== Bootstrap complete ==="
echo "Next steps:"
echo "  1. Copy .env to /opt/agent-playground/.env"
echo "  2. Start Temporal: cd /opt/agent-playground && docker compose up -d"
echo "  3. Start API: systemctl start agent-playground-api"

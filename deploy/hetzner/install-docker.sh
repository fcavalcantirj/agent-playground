#!/bin/bash
# Install Docker Engine 27.x on a Debian/Ubuntu Hetzner host and configure
# the daemon with userns-remap for per-container UID isolation (T-1-15
# mitigation).
#
# Idempotent: skips installation if Docker is already present, and only
# rewrites /etc/docker/daemon.json (and bounces the daemon) when the config
# differs from what we want.
set -euo pipefail

DAEMON_JSON="/etc/docker/daemon.json"
DAEMON_JSON_DESIRED='{
  "userns-remap": "default",
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}'

echo "[install-docker] starting"

if command -v docker >/dev/null 2>&1; then
  echo "[install-docker] docker already installed: $(docker --version)"
else
  echo "[install-docker] installing Docker CE from docker.com apt repo"

  apt-get update
  apt-get install -y ca-certificates curl gnupg lsb-release

  install -m 0755 -d /etc/apt/keyrings
  if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
    # Detect Debian vs Ubuntu
    distro="$(. /etc/os-release && echo "$ID")"
    curl -fsSL "https://download.docker.com/linux/${distro}/gpg" \
      | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
  fi

  distro="$(. /etc/os-release && echo "$ID")"
  codename="$(. /etc/os-release && echo "${VERSION_CODENAME}")"
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/${distro} ${codename} stable" \
    > /etc/apt/sources.list.d/docker.list

  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

# Configure daemon.json (idempotent — only rewrite if different)
mkdir -p /etc/docker
needs_restart=0
if [ ! -f "$DAEMON_JSON" ] || ! diff -q <(echo "$DAEMON_JSON_DESIRED") "$DAEMON_JSON" >/dev/null 2>&1; then
  echo "[install-docker] writing $DAEMON_JSON with userns-remap"
  echo "$DAEMON_JSON_DESIRED" > "$DAEMON_JSON"
  needs_restart=1
else
  echo "[install-docker] $DAEMON_JSON already up to date"
fi

if [ "$needs_restart" = "1" ]; then
  echo "[install-docker] restarting docker daemon to apply config"
  systemctl restart docker
fi

systemctl enable --now docker

echo "[install-docker] version: $(docker --version)"
if docker info 2>/dev/null | grep -qi "user namespace"; then
  echo "[install-docker] user namespace remapping active"
else
  echo "[install-docker] WARNING: user namespace remapping not detected in 'docker info'"
fi

echo "[install-docker] done"

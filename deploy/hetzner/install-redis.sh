#!/bin/bash
# Install Redis 7 on a Debian/Ubuntu Hetzner host and bind it to the
# loopback interface with a conservative memory cap.
#
# Security (T-1-14): bind 127.0.0.1 ::1 + UFW blocks 6379 from outside.
# Idempotent: skips installation if redis-server is already present,
# rewrites redis.conf lines only when they differ from desired.
set -euo pipefail

REDIS_CONF="/etc/redis/redis.conf"

echo "[install-redis] starting"

if command -v redis-server >/dev/null 2>&1; then
  echo "[install-redis] redis already installed: $(redis-server --version | head -n1)"
else
  echo "[install-redis] installing redis from redis.io apt repo"
  apt-get update
  apt-get install -y curl ca-certificates gnupg lsb-release

  install -d /etc/apt/keyrings
  if [ ! -f /etc/apt/keyrings/redis.gpg ]; then
    curl -fsSL https://packages.redis.io/gpg \
      | gpg --dearmor -o /etc/apt/keyrings/redis.gpg
    chmod a+r /etc/apt/keyrings/redis.gpg
  fi

  codename="$(. /etc/os-release && echo "${VERSION_CODENAME}")"
  echo "deb [signed-by=/etc/apt/keyrings/redis.gpg] https://packages.redis.io/deb ${codename} main" \
    > /etc/apt/sources.list.d/redis.list

  apt-get update
  apt-get install -y redis
fi

# Idempotent config mutations. Each helper only touches redis.conf
# when the existing line doesn't match desired state.
set_conf() {
  local key="$1"
  local value="$2"
  local line="${key} ${value}"
  if grep -Eq "^\s*${key}\s+" "$REDIS_CONF"; then
    if ! grep -Eq "^\s*${key}\s+${value}\s*$" "$REDIS_CONF"; then
      sed -i "s|^\s*${key}\s.*|${line}|" "$REDIS_CONF"
      echo "[install-redis] updated $key"
    else
      echo "[install-redis] $key already $value"
    fi
  else
    echo "$line" >> "$REDIS_CONF"
    echo "[install-redis] appended $key $value"
  fi
}

if [ -f "$REDIS_CONF" ]; then
  set_conf "bind" "127.0.0.1 ::1"
  set_conf "maxmemory" "256mb"
  set_conf "maxmemory-policy" "allkeys-lru"
fi

systemctl enable --now redis-server || systemctl enable --now redis

# Give the server a moment to bind, then probe.
for i in 1 2 3 4 5; do
  if redis-cli -h 127.0.0.1 ping 2>/dev/null | grep -q PONG; then
    echo "[install-redis] redis responded to PING"
    break
  fi
  sleep 1
done

echo "[install-redis] done"

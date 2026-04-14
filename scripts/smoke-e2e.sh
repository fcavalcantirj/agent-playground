#!/usr/bin/env bash
# scripts/smoke-e2e.sh — Phase 2 hypothesis-proof smoke test.
#
# Exercises the API-driven agent start path end-to-end:
#   1. Verify dev compose stack is up (postgres + redis)
#   2. Verify ap-base + recipe images are present (build if missing)
#   3. Start the Go API in the background
#   4. Obtain a dev session cookie via /api/dev/login
#   5. POST /api/sessions with the requested recipe → assert 201 + capture id
#   6. POST /api/sessions/<id>/message with a real prompt → assert 200 + non-empty text
#   7. DELETE /api/sessions/<id> → assert 200
#   8. Assert ZERO dangling playground-* containers
#   9. Assert ZERO leaked /tmp/ap/secrets/<session_id> dirs
#  10. Tear down API
#
# CONTEXT D-32, D-33, D-34. The curl output is the demo.
#
# Usage:
#   AP_DEV_BYOK_KEY=sk-ant-... ./scripts/smoke-e2e.sh picoclaw
#   AP_DEV_BYOK_KEY=sk-ant-... ./scripts/smoke-e2e.sh hermes
#
# Without AP_DEV_BYOK_KEY set, the script exits 0 with a SKIPPED message so
# CI stays green in the no-key path.

set -euo pipefail

AGENT="${1:-}"
if [[ -z "$AGENT" ]]; then
    echo "usage: $0 <picoclaw|hermes>" >&2
    exit 2
fi
if [[ "$AGENT" != "picoclaw" && "$AGENT" != "hermes" ]]; then
    echo "error: unknown agent '$AGENT' (expected picoclaw or hermes)" >&2
    exit 2
fi

if [[ -z "${AP_DEV_BYOK_KEY:-}" ]]; then
    echo "SKIPPED: AP_DEV_BYOK_KEY not set (export a real Anthropic API key to run the live smoke test)"
    exit 0
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

API_PORT="${API_PORT:-8080}"
API_BASE="http://localhost:${API_PORT}"
MODEL_ID="${AP_SMOKE_MODEL:-claude-sonnet-4-5}"
COOKIE_JAR="$(mktemp -t ap-smoke-cookie.XXXXXX)"
API_LOG="$(mktemp -t ap-smoke-api.XXXXXX.log)"
API_PID=""
SESSION_ID=""

log()  { echo "[smoke:$AGENT] $*"; }
fail() { echo "[smoke:$AGENT] FAIL: $*" >&2; exit 1; }

# --- Always clean up, on success or failure ---
cleanup() {
    local rc=$?
    set +e

    # Best-effort DELETE for an in-flight session so we exercise the
    # teardown path even on mid-test failure.
    if [[ -n "$SESSION_ID" && -n "$API_PID" ]]; then
        curl -fsS -b "$COOKIE_JAR" -X DELETE \
            "${API_BASE}/api/sessions/${SESSION_ID}" >/dev/null 2>&1 || true
    fi

    if [[ -n "$API_PID" ]]; then
        kill "$API_PID" 2>/dev/null || true
        wait "$API_PID" 2>/dev/null || true
    fi

    # Belt-and-suspenders: force-remove any leaked playground-* containers.
    local leaked
    leaked="$(docker ps -a --filter name=playground- --format '{{.ID}}' 2>/dev/null || true)"
    if [[ -n "$leaked" ]]; then
        echo "$leaked" | xargs -r docker rm -f >/dev/null 2>&1 || true
    fi

    rm -f "$COOKIE_JAR" 2>/dev/null || true

    if [[ $rc -ne 0 && -f "$API_LOG" ]]; then
        echo
        echo "=== API log tail (last 100 lines) ==="
        tail -100 "$API_LOG" || true
        echo "=== end API log ==="
    fi
    rm -f "$API_LOG" 2>/dev/null || true

    exit $rc
}
trap cleanup EXIT INT TERM

# --- Step 1: dev compose stack ---
log "verifying dev compose stack (postgres + redis)"
if ! docker compose -f docker-compose.dev.yml ps --services --filter status=running 2>/dev/null | grep -q '^postgresql$'; then
    log "starting docker-compose dev stack"
    docker compose -f docker-compose.dev.yml up -d postgresql redis
    sleep 3
fi

# --- Step 2: images present (build if missing) ---
log "verifying ap-base + ap-${AGENT} images"
if ! docker image inspect ap-base:v0.1.0 >/dev/null 2>&1; then
    log "building ap-base:v0.1.0"
    make build-ap-base
fi
if ! docker images "ap-${AGENT}" --format '{{.Repository}}' | grep -q "^ap-${AGENT}$"; then
    log "building ap-${AGENT}"
    make "build-${AGENT}"
fi

# --- Step 3: kill any stale process on the port, then start API ---
log "clearing stale process on :${API_PORT} (if any)"
lsof -ti tcp:"${API_PORT}" 2>/dev/null | xargs -r kill -9 2>/dev/null || true

log "starting Go API (log: ${API_LOG})"
(
    cd api && \
    AP_DEV_MODE=true \
    AP_SESSION_SECRET=test-secret-that-is-at-least-32-characters-long \
    DATABASE_URL="postgres://temporal:temporal@localhost:5432/agent_playground?sslmode=disable" \
    REDIS_URL=redis://localhost:6379 \
    TEMPORAL_HOST= \
    API_PORT="${API_PORT}" \
    AP_DEV_BYOK_KEY="${AP_DEV_BYOK_KEY}" \
    go run ./cmd/server/ > "$API_LOG" 2>&1
) &
API_PID=$!

# Wait for /healthz
for i in $(seq 1 60); do
    if curl -fsS "${API_BASE}/healthz" >/dev/null 2>&1; then
        log "API healthy after ${i}s"
        break
    fi
    # Detect early death.
    if ! kill -0 "$API_PID" 2>/dev/null; then
        fail "API process exited before becoming healthy (see log tail)"
    fi
    sleep 1
done
if ! curl -fsS "${API_BASE}/healthz" >/dev/null; then
    fail "API never became healthy on ${API_BASE}/healthz"
fi

# --- Step 4: dev login → cookie ---
log "obtaining dev session cookie"
curl -fsS -c "$COOKIE_JAR" -X POST \
    -H 'Content-Type: application/json' \
    -d '{"email":"smoke@example.com"}' \
    "${API_BASE}/api/dev/login" > /dev/null \
    || fail "dev login failed"
grep -q ap_session "$COOKIE_JAR" || fail "no ap_session cookie set on login"

# --- Step 5: POST /api/sessions ---
log "creating session (recipe=${AGENT} model=${MODEL_ID})"
CREATE_RESP="$(curl -fsS -b "$COOKIE_JAR" -X POST \
    -H 'Content-Type: application/json' \
    -d "{\"recipe\":\"${AGENT}\",\"model_provider\":\"anthropic\",\"model_id\":\"${MODEL_ID}\"}" \
    "${API_BASE}/api/sessions")" \
    || fail "POST /api/sessions failed"

echo "  → ${CREATE_RESP}"
SESSION_ID="$(printf '%s' "$CREATE_RESP" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')"
[[ -n "$SESSION_ID" ]] || fail "no session id in create response: ${CREATE_RESP}"
printf '%s' "$CREATE_RESP" | grep -q '"status":"running"' \
    || fail "session not in running state after create: ${CREATE_RESP}"

# --- Step 6: POST /api/sessions/<id>/message — the hypothesis proof ---
log "sending real prompt to ${AGENT} (this is the demo)"
MESSAGE_RESP="$(curl -fsS -b "$COOKIE_JAR" -X POST \
    -H 'Content-Type: application/json' \
    -d '{"text":"In exactly five words, say hello."}' \
    "${API_BASE}/api/sessions/${SESSION_ID}/message")" \
    || fail "POST /api/sessions/:id/message failed (see API log tail)"

echo
echo "================ AGENT RESPONSE ================"
echo "$MESSAGE_RESP"
echo "================================================"
echo

RESPONSE_TEXT="$(printf '%s' "$MESSAGE_RESP" | sed -n 's/.*"text":"\([^"]*\)".*/\1/p')"
[[ -n "$RESPONSE_TEXT" ]] || fail "empty text in message response: ${MESSAGE_RESP}"
if printf '%s' "$RESPONSE_TEXT" | grep -qiE 'error|exception|traceback'; then
    fail "response text looks like an error: ${RESPONSE_TEXT}"
fi
log "got non-empty response (${#RESPONSE_TEXT} chars)"

# --- Step 7: DELETE /api/sessions/<id> ---
log "deleting session ${SESSION_ID}"
DELETE_RESP="$(curl -fsS -b "$COOKIE_JAR" -X DELETE \
    "${API_BASE}/api/sessions/${SESSION_ID}")" \
    || fail "DELETE /api/sessions/:id failed"
printf '%s' "$DELETE_RESP" | grep -q '"status":"stopped"' \
    || fail "delete did not return stopped status: ${DELETE_RESP}"

# Clear SESSION_ID so trap cleanup doesn't re-issue DELETE.
DELETED_SESSION_ID="$SESSION_ID"
SESSION_ID=""

# --- Step 8: ZERO dangling containers ---
sleep 2
DANGLING="$(docker ps -a --filter name=playground- --format '{{.Names}}')"
if [[ -n "$DANGLING" ]]; then
    fail "dangling playground containers after delete: ${DANGLING}"
fi
log "zero dangling playground-* containers — clean teardown verified"

# --- Step 9: ZERO leaked secret dirs ---
if [[ -d "/tmp/ap/secrets/${DELETED_SESSION_ID}" ]]; then
    fail "secret dir not cleaned: /tmp/ap/secrets/${DELETED_SESSION_ID}"
fi
log "secret dir cleanup verified"

log "PASS: ${AGENT} hypothesis proof"

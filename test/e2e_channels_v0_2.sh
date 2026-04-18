#!/usr/bin/env bash
# Phase 22a SC-03 gate — end-to-end Telegram round-trip for all 5 v0.2-channel recipes.
#
# Requirements:
#   - Local API server running (default http://localhost:8000)
#   - Postgres + docker daemon healthy
#   - deploy/.env.local (gitignored) OR .env.local with:
#       TELEGRAM_BOT_TOKEN=...
#       TELEGRAM_ALLOWED_USER=152099202
#       TELEGRAM_CHAT_ID=152099202
#       OPENROUTER_API_KEY=...
#       ANTHROPIC_API_KEY=...
#
# Usage:
#   bash test/e2e_channels_v0_2.sh
#   bash test/e2e_channels_v0_2.sh --recipe hermes        # single recipe
#   bash test/e2e_channels_v0_2.sh --rounds 1             # fewer rounds for smoke
#   API_BASE=http://localhost:8000 bash test/e2e_channels_v0_2.sh
#
# Exit codes:
#   0  all round-trips PASS (5 recipes x ROUNDS, or just --recipe x ROUNDS)
#   1  any round-trip failed
#   2  missing env / infra
#
# Design notes:
#   - Each round creates a FRESH agent_instance (unique name suffix by
#     timestamp + round index) so partial-index 409s can't happen.
#   - Stop + cleanup runs in a trap so Ctrl-C or assertion failure still
#     tears down the spawned container.
#   - A JSON report lands at .planning/phases/22-channels-v0.2/22-e2e-report.json
#     for retrospectives.

set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000}"
ROUNDS="${ROUNDS:-3}"
RECIPE_FILTER=""
REPORT_PATH="${REPORT_PATH:-.planning/phases/22-channels-v0.2/22-e2e-report.json}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --recipe)   RECIPE_FILTER="$2"; shift 2;;
    --rounds)   ROUNDS="$2"; shift 2;;
    --api-base) API_BASE="$2"; shift 2;;
    -h|--help)
      sed -n '2,32p' "$0"
      exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

# --- env bootstrap ---
if [[ -f deploy/.env.local ]]; then
  set -a; source deploy/.env.local; set +a
elif [[ -f .env.local ]]; then
  set -a; source .env.local; set +a
fi

for var in TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID OPENROUTER_API_KEY ANTHROPIC_API_KEY; do
  if [[ -z "${!var:-}" ]]; then
    echo "missing $var (put in deploy/.env.local or .env.local)" >&2
    exit 2
  fi
done

# TELEGRAM_ALLOWED_USER falls back to TELEGRAM_CHAT_ID (user's own DM).
TELEGRAM_ALLOWED_USER="${TELEGRAM_ALLOWED_USER:-$TELEGRAM_CHAT_ID}"

# --- recipe matrix ---
# Each row: recipe_name|llm_provider|llm_key_env|llm_model|requires_pairing
declare -a MATRIX=(
  "hermes|openrouter|OPENROUTER_API_KEY|anthropic/claude-haiku-4.5|false"
  "picoclaw|openrouter|OPENROUTER_API_KEY|anthropic/claude-haiku-4.5|false"
  "nullclaw|openrouter|OPENROUTER_API_KEY|anthropic/claude-haiku-4.5|false"
  "nanobot|openrouter|OPENROUTER_API_KEY|anthropic/claude-haiku-4.5|false"
  "openclaw|anthropic|ANTHROPIC_API_KEY|anthropic/claude-haiku-4-5|true"
)

# --- helpers ---
_pass() { printf "  \033[32mPASS\033[0m %s\n" "$1"; }
_fail() { printf "  \033[31mFAIL\033[0m %s\n" "$1"; }
_info() { printf "  \033[36mINFO\033[0m %s\n" "$1"; }

TOTAL=0
PASSED=0
declare -a REPORT_LINES=()
ACTIVE_AGENT_ID=""
ACTIVE_CONTAINER_ID=""
ACTIVE_BEARER=""

cleanup() {
  if [[ -n "$ACTIVE_AGENT_ID" && -n "$ACTIVE_BEARER" ]]; then
    _info "teardown: stopping agent $ACTIVE_AGENT_ID"
    curl -fsS -X POST "$API_BASE/v1/agents/$ACTIVE_AGENT_ID/stop" \
      -H "Authorization: Bearer $ACTIVE_BEARER" >/dev/null 2>&1 || true
  fi
  ACTIVE_AGENT_ID=""
  ACTIVE_CONTAINER_ID=""
}
trap cleanup EXIT INT TERM

# Drain Telegram backlog once so getUpdates doesn't see pre-existing messages.
python3 test/lib/telegram_harness.py drain --token "$TELEGRAM_BOT_TOKEN" >/dev/null || {
  echo "warning: initial Telegram drain failed — proceeding anyway" >&2
}

echo "e2e: API_BASE=$API_BASE ROUNDS=$ROUNDS RECIPE_FILTER=${RECIPE_FILTER:-all}"

for entry in "${MATRIX[@]}"; do
  IFS='|' read -r RECIPE PROVIDER KEY_ENV MODEL REQ_PAIR <<<"$entry"
  if [[ -n "$RECIPE_FILTER" && "$RECIPE_FILTER" != "$RECIPE" ]]; then continue; fi

  BEARER="${!KEY_ENV}"

  echo ""
  echo "=== $RECIPE (provider=$PROVIDER model=$MODEL pair=$REQ_PAIR) ==="

  for R in $(seq 1 "$ROUNDS"); do
    TOTAL=$((TOTAL + 1))
    STAMP=$(date +%s)
    AGENT_NAME="e2e-$RECIPE-$STAMP-$R"
    _info "round $R/$ROUNDS  agent_name=$AGENT_NAME"

    # 1. Smoke (creates agent_instance)
    SMOKE_BODY=$(jq -cn --arg rn "$RECIPE" --arg m "$MODEL" --arg n "$AGENT_NAME" \
      '{recipe_name:$rn, model:$m, agent_name:$n, personality:"polite-thorough"}')
    SMOKE=$(curl -fsS -X POST "$API_BASE/v1/runs" \
      -H "Authorization: Bearer $BEARER" \
      -H "Content-Type: application/json" \
      -d "$SMOKE_BODY" 2>/dev/null || echo "{}")
    SMOKE_VERDICT=$(jq -r '.verdict // "ERROR"' <<<"$SMOKE")
    AGENT_ID=$(jq -r '.agent_instance_id // ""' <<<"$SMOKE")
    if [[ "$SMOKE_VERDICT" != "PASS" || -z "$AGENT_ID" ]]; then
      _fail "$RECIPE r$R smoke: $SMOKE_VERDICT"
      REPORT_LINES+=("{\"recipe\":\"$RECIPE\",\"round\":$R,\"stage\":\"smoke\",\"verdict\":\"$SMOKE_VERDICT\"}")
      continue
    fi
    ACTIVE_AGENT_ID="$AGENT_ID"; ACTIVE_BEARER="$BEARER"

    # 2. Start channel
    START_BODY=$(jq -cn \
      --arg tok "$TELEGRAM_BOT_TOKEN" \
      --arg uid "$TELEGRAM_ALLOWED_USER" \
      '{channel:"telegram", channel_inputs: {TELEGRAM_BOT_TOKEN:$tok, TELEGRAM_ALLOWED_USERS:$uid, TELEGRAM_ALLOWED_USER:$uid}}')
    START=$(curl -fsS -X POST "$API_BASE/v1/agents/$AGENT_ID/start" \
      -H "Authorization: Bearer $BEARER" \
      -H "Content-Type: application/json" \
      -d "$START_BODY" 2>/dev/null || echo "{}")
    START_STATUS=$(jq -r '.container_status // "ERROR"' <<<"$START")
    ACTIVE_CONTAINER_ID=$(jq -r '.container_id // ""' <<<"$START")
    if [[ "$START_STATUS" != "running" ]]; then
      _fail "$RECIPE r$R start: $(jq -c '.' <<<"$START")"
      REPORT_LINES+=("{\"recipe\":\"$RECIPE\",\"round\":$R,\"stage\":\"start\",\"status\":\"$START_STATUS\"}")
      cleanup
      continue
    fi
    BOOT_S=$(jq -r '.boot_wall_s // 0' <<<"$START")
    _info "booted in ${BOOT_S}s, container=${ACTIVE_CONTAINER_ID:0:12}"

    # 3. If pairing required, approve it (openclaw).
    #    First DM triggers the bot's pairing-code reply; we extract the code
    #    and POST /channels/telegram/pair.  After that the channel is
    #    authenticated for subsequent messages.
    if [[ "$REQ_PAIR" == "true" ]]; then
      PAIR_POLL=$(python3 test/lib/telegram_harness.py send-and-wait \
        --token "$TELEGRAM_BOT_TOKEN" --chat-id "$TELEGRAM_CHAT_ID" \
        --text "hi" --timeout-s 30)
      REPLY=$(jq -r '.reply_text // ""' <<<"$PAIR_POLL")
      # openclaw replies "Pairing code: XXXX" — grab the first 4-8 char token.
      CODE=$(echo "$REPLY" | grep -oE '[A-Za-z0-9]{4,8}' | head -1 || true)
      if [[ -z "$CODE" ]]; then
        _fail "$RECIPE r$R pair: no code in reply: $REPLY"
        REPORT_LINES+=("{\"recipe\":\"$RECIPE\",\"round\":$R,\"stage\":\"pair-no-code\"}")
        cleanup; continue
      fi
      _info "pair code = $CODE"
      PAIR_BODY=$(jq -cn --arg c "$CODE" '{code:$c}')
      PAIR=$(curl -fsS -X POST "$API_BASE/v1/agents/$AGENT_ID/channels/telegram/pair" \
        -H "Authorization: Bearer $BEARER" \
        -H "Content-Type: application/json" \
        -d "$PAIR_BODY" 2>/dev/null || echo "{}")
      PAIR_EXIT=$(jq -r '.exit_code // -1' <<<"$PAIR")
      if [[ "$PAIR_EXIT" != "0" ]]; then
        _fail "$RECIPE r$R pair: exit=$PAIR_EXIT body=$(jq -c '.' <<<"$PAIR")"
        REPORT_LINES+=("{\"recipe\":\"$RECIPE\",\"round\":$R,\"stage\":\"pair-exit\",\"exit\":$PAIR_EXIT}")
        cleanup; continue
      fi
    fi

    # 4. Real round-trip
    MSG="ping $RECIPE r$R $(date +%H%M%S)"
    ROUNDTRIP=$(python3 test/lib/telegram_harness.py send-and-wait \
      --token "$TELEGRAM_BOT_TOKEN" --chat-id "$TELEGRAM_CHAT_ID" \
      --text "$MSG" --timeout-s 30)
    RT_OK=$(jq -r '.reply_text // "null"' <<<"$ROUNDTRIP")
    RT_WALL=$(jq -r '.reply_wall_s // "null"' <<<"$ROUNDTRIP")
    if [[ "$RT_OK" == "null" ]]; then
      _fail "$RECIPE r$R round-trip: $(jq -c '.' <<<"$ROUNDTRIP")"
      REPORT_LINES+=("{\"recipe\":\"$RECIPE\",\"round\":$R,\"stage\":\"roundtrip-timeout\"}")
      cleanup; continue
    fi
    _pass "$RECIPE r$R round-trip (${RT_WALL}s)"
    PASSED=$((PASSED + 1))
    REPORT_LINES+=("{\"recipe\":\"$RECIPE\",\"round\":$R,\"stage\":\"pass\",\"boot_wall_s\":$BOOT_S,\"reply_wall_s\":$RT_WALL}")

    # 5. Stop
    curl -fsS -X POST "$API_BASE/v1/agents/$AGENT_ID/stop" \
      -H "Authorization: Bearer $BEARER" >/dev/null 2>&1 || true
    ACTIVE_AGENT_ID=""; ACTIVE_CONTAINER_ID=""
    sleep 2
  done
done

# Final report
REPORT_DIR=$(dirname "$REPORT_PATH")
mkdir -p "$REPORT_DIR"
{
  printf '{\n  "total": %d,\n  "passed": %d,\n  "rounds": [\n' "$TOTAL" "$PASSED"
  for i in "${!REPORT_LINES[@]}"; do
    sep=","
    [[ "$i" -eq $((${#REPORT_LINES[@]} - 1)) ]] && sep=""
    printf '    %s%s\n' "${REPORT_LINES[$i]}" "$sep"
  done
  printf '  ]\n}\n'
} > "$REPORT_PATH"

echo ""
echo "================================================================"
echo "  e2e: $PASSED / $TOTAL round-trips passed"
echo "  report: $REPORT_PATH"
echo "================================================================"
if [[ "$PASSED" -eq "$TOTAL" ]]; then exit 0; else exit 1; fi

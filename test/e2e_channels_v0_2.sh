#!/usr/bin/env bash
# Phase 22b SC-03 gate — Gate A (direct_interface) + Gate B (event-stream long-poll).
#
# REPLACES the legacy update-polling round-trip step (Phase 22a) which spike-01a
# proved unautomatable via Bot API. The new flow has TWO gates:
#
#   Gate A — direct_interface round-trip via test/lib/agent_harness.py
#            send-direct-and-read. Hits the agent's programmatic surface
#            directly (docker exec or HTTP). 5 recipes × ROUNDS = 15 by default.
#            MANDATORY for SC-03 phase exit.
#
#   Gate B — bot->self sendMessage + long-poll GET /v1/agents/:id/events
#            kinds=reply_sent. 5 recipes × 1 = 5 invocations. SKIPS cleanly
#            when AP_SYSADMIN_TOKEN / TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
#            are missing.
#
#   Gate C — manual user-in-the-loop (test/sc03-gate-c.md). Once per release.
#            NOT executed by this script.
#
# Requirements:
#   - Local API server running (default http://localhost:8000)
#   - Postgres + docker daemon healthy
#   - All 5 recipe images built locally: `docker images | grep ap-recipe`
#   - deploy/.env.local (gitignored) OR .env.local with at minimum:
#       OPENROUTER_API_KEY=...
#       ANTHROPIC_API_KEY=...
#     For Gate B (optional):
#       AP_SYSADMIN_TOKEN=...   # per-laptop, NEVER committed (D-15)
#       TELEGRAM_BOT_TOKEN=...
#       TELEGRAM_CHAT_ID=...
#       TELEGRAM_ALLOWED_USER=152099202   # defaults to TELEGRAM_CHAT_ID
#
# Usage:
#   bash test/e2e_channels_v0_2.sh                    # all 5 recipes × 3 rounds
#   bash test/e2e_channels_v0_2.sh --recipe hermes    # single recipe (3 rounds)
#   bash test/e2e_channels_v0_2.sh --rounds 1         # fewer rounds for smoke
#   bash test/e2e_channels_v0_2.sh --skip-gate-b      # explicitly skip Gate B
#   API_BASE=http://localhost:8000 bash test/e2e_channels_v0_2.sh
#
# Exit codes:
#   0  Gate A 15/15 PASS (and Gate B 5/5 OR cleanly skipped)
#   1  any Gate A round-trip FAILED, OR Gate B attempted but partially failed
#   2  missing env / infra (no OPENROUTER + ANTHROPIC keys, no docker, etc.)
#
# Output:
#   stdout — colorized PASS/FAIL/INFO/SKIP per round
#   $REPORT_PATH (default e2e-report.json at repo root) — JSON array of every
#                gate envelope, one per element, for retrospectives + summary.

set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000}"
ROUNDS="${ROUNDS:-3}"
RECIPE_FILTER=""
SKIP_GATE_B="${SKIP_GATE_B:-}"
REPORT_PATH="${REPORT_PATH:-e2e-report.json}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --recipe)      RECIPE_FILTER="$2"; shift 2;;
    --rounds)      ROUNDS="$2"; shift 2;;
    --api-base)    API_BASE="$2"; shift 2;;
    --report-path) REPORT_PATH="$2"; shift 2;;
    --skip-gate-b) SKIP_GATE_B=1; shift;;
    -h|--help)
      sed -n '2,55p' "$0"
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

# Gate A requires the per-recipe BYOK keys. Gate B's creds are optional
# and policed inline.
for var in OPENROUTER_API_KEY ANTHROPIC_API_KEY; do
  if [[ -z "${!var:-}" ]]; then
    echo "missing $var (put in deploy/.env.local or .env.local)" >&2
    exit 2
  fi
done

TELEGRAM_ALLOWED_USER="${TELEGRAM_ALLOWED_USER:-${TELEGRAM_CHAT_ID:-}}"

# --- recipe matrix ---
# recipe_name|llm_provider|llm_key_env|llm_model|requires_pairing
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
_skip() { printf "  \033[33mSKIP\033[0m %s\n" "$1"; }
_info() { printf "  \033[36mINFO\033[0m %s\n" "$1"; }

GATE_A_TOTAL=0
GATE_A_PASS=0
GATE_B_TOTAL=0
GATE_B_PASS=0
GATE_B_RAN=0
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

# Gate B preflight — capture creds presence in one place.
GATE_B_ENABLED=1
if [[ -n "$SKIP_GATE_B" ]]; then
  GATE_B_ENABLED=0
elif [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" || -z "${AP_SYSADMIN_TOKEN:-}" ]]; then
  GATE_B_ENABLED=0
fi

echo "e2e: API_BASE=$API_BASE ROUNDS=$ROUNDS RECIPE_FILTER=${RECIPE_FILTER:-all} GATE_B=$([[ $GATE_B_ENABLED -eq 1 ]] && echo on || echo off)"

for entry in "${MATRIX[@]}"; do
  IFS='|' read -r RECIPE PROVIDER KEY_ENV MODEL REQ_PAIR <<<"$entry"
  if [[ -n "$RECIPE_FILTER" && "$RECIPE_FILTER" != "$RECIPE" ]]; then continue; fi

  BEARER="${!KEY_ENV}"

  echo ""
  echo "=== $RECIPE (provider=$PROVIDER model=$MODEL pair=$REQ_PAIR) ==="

  # ---------------------------------------------------------------
  # Per-recipe lifecycle: smoke→start→pair-if-needed→Gate-A×ROUNDS
  # →Gate-B (once)→stop. Gate B reuses the same running container that
  # Gate A drove, so we don't re-pay the boot cost.
  # ---------------------------------------------------------------

  STAMP=$(date +%s)
  AGENT_NAME="e2e-$RECIPE-$STAMP"

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
    _fail "$RECIPE smoke: $SMOKE_VERDICT"
    REPORT_LINES+=("$(jq -cn --arg r "$RECIPE" --arg s "$SMOKE_VERDICT" '{recipe:$r,stage:"smoke",verdict:$s}')")
    continue
  fi
  ACTIVE_AGENT_ID="$AGENT_ID"; ACTIVE_BEARER="$BEARER"

  # 2. Start channel — Gate B needs Telegram wired; Gate A only needs the
  #    container running. We always start with Telegram inputs if creds are
  #    present so a single START supports both gates.
  if [[ $GATE_B_ENABLED -eq 1 ]]; then
    START_BODY=$(jq -cn \
      --arg tok "$TELEGRAM_BOT_TOKEN" \
      --arg uid "$TELEGRAM_ALLOWED_USER" \
      '{channel:"telegram", channel_inputs: {TELEGRAM_BOT_TOKEN:$tok, TELEGRAM_ALLOWED_USERS:$uid, TELEGRAM_ALLOWED_USER:$uid}}')
  else
    START_BODY='{"channel":"telegram"}'
  fi
  START=$(curl -fsS -X POST "$API_BASE/v1/agents/$AGENT_ID/start" \
    -H "Authorization: Bearer $BEARER" \
    -H "Content-Type: application/json" \
    -d "$START_BODY" 2>/dev/null || echo "{}")
  START_STATUS=$(jq -r '.container_status // "ERROR"' <<<"$START")
  ACTIVE_CONTAINER_ID=$(jq -r '.container_id // ""' <<<"$START")
  if [[ "$START_STATUS" != "running" ]]; then
    _fail "$RECIPE start: $(jq -c '.' <<<"$START")"
    REPORT_LINES+=("$(jq -cn --arg r "$RECIPE" --arg s "$START_STATUS" '{recipe:$r,stage:"start",status:$s}')")
    cleanup
    continue
  fi
  BOOT_S=$(jq -r '.boot_wall_s // 0' <<<"$START")
  _info "booted in ${BOOT_S}s, container=${ACTIVE_CONTAINER_ID:0:12}"

  # 3. Pairing (openclaw only).
  if [[ "$REQ_PAIR" == "true" && $GATE_B_ENABLED -eq 1 ]]; then
    # Gate B is enabled and we have Telegram creds; the existing pair flow
    # uses Telegram to deliver the code. Without Gate B (no creds), we
    # skip pairing — Gate A still works because direct_interface bypasses
    # the channel layer entirely.
    _info "$RECIPE: pairing flow not exercised in 22b harness — pair via /v1/agents/:id/channels/telegram/pair from external script if needed"
  fi

  # ---------------------------------------------------------------
  # 4. Gate A — direct_interface × ROUNDS
  # ---------------------------------------------------------------
  for R in $(seq 1 "$ROUNDS"); do
    GATE_A_TOTAL=$((GATE_A_TOTAL + 1))
    GATE_A=$(python3 test/lib/agent_harness.py send-direct-and-read \
      --recipe "$RECIPE" \
      --container-id "$ACTIVE_CONTAINER_ID" \
      --model "$MODEL" \
      --api-key "$BEARER" \
      --timeout-s 60 2>/dev/null || echo '{"gate":"A","verdict":"ERROR","error":"harness crashed"}')
    VERDICT=$(jq -r '.verdict // "ERROR"' <<<"$GATE_A")
    if [[ "$VERDICT" == "PASS" ]]; then
      WS=$(jq -r '.wall_s // 0' <<<"$GATE_A")
      _pass "$RECIPE r$R Gate A direct_interface (${WS}s)"
      GATE_A_PASS=$((GATE_A_PASS + 1))
    else
      _fail "$RECIPE r$R Gate A: $(jq -c '.' <<<"$GATE_A")"
    fi
    REPORT_LINES+=("$(jq -c --arg r "$RECIPE" --arg round "$R" '. + {round: ($round|tonumber), recipe: $r}' <<<"$GATE_A")")
  done

  # ---------------------------------------------------------------
  # 5. Gate B — event-stream long-poll (once per recipe)
  # ---------------------------------------------------------------
  if [[ $GATE_B_ENABLED -eq 1 ]]; then
    GATE_B_TOTAL=$((GATE_B_TOTAL + 1))
    GATE_B_RAN=1
    GATE_B_OUT=$(python3 test/lib/agent_harness.py send-telegram-and-watch-events \
      --api-base "$API_BASE" \
      --agent-id "$AGENT_ID" \
      --bearer "$AP_SYSADMIN_TOKEN" \
      --recipe "$RECIPE" \
      --token "$TELEGRAM_BOT_TOKEN" \
      --chat-id "$TELEGRAM_CHAT_ID" \
      --timeout-s 10 2>/dev/null || echo '{"gate":"B","verdict":"ERROR","error":"harness crashed"}')
    V=$(jq -r '.verdict // "ERROR"' <<<"$GATE_B_OUT")
    if [[ "$V" == "PASS" ]]; then
      WS=$(jq -r '.wall_s // 0' <<<"$GATE_B_OUT")
      _pass "$RECIPE Gate B event-stream (${WS}s)"
      GATE_B_PASS=$((GATE_B_PASS + 1))
    else
      _fail "$RECIPE Gate B: $(jq -c '.' <<<"$GATE_B_OUT")"
    fi
    REPORT_LINES+=("$(jq -c --arg r "$RECIPE" '. + {recipe: $r}' <<<"$GATE_B_OUT")")
  else
    _skip "$RECIPE Gate B (need TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID + AP_SYSADMIN_TOKEN OR --skip-gate-b)"
    REPORT_LINES+=("$(jq -cn --arg r "$RECIPE" '{gate:"B",recipe:$r,verdict:"SKIP",reason:"missing creds"}')")
  fi

  # 6. Stop
  curl -fsS -X POST "$API_BASE/v1/agents/$AGENT_ID/stop" \
    -H "Authorization: Bearer $BEARER" >/dev/null 2>&1 || true
  ACTIVE_AGENT_ID=""; ACTIVE_CONTAINER_ID=""
  sleep 2
done

# --- Final report ---
REPORT_DIR=$(dirname "$REPORT_PATH")
[[ -n "$REPORT_DIR" && "$REPORT_DIR" != "." ]] && mkdir -p "$REPORT_DIR"
{
  printf '%s\n' "${REPORT_LINES[@]}"
} | jq -s '.' > "$REPORT_PATH"

echo ""
echo "================================================================"
echo "  SC-03 Gate A: $GATE_A_PASS / $GATE_A_TOTAL PASS"
if [[ $GATE_B_RAN -eq 1 ]]; then
  echo "  SC-03 Gate B: $GATE_B_PASS / $GATE_B_TOTAL PASS"
else
  echo "  SC-03 Gate B: SKIPPED (Gate C manual checklist still required per release)"
fi
echo "  Gate C: see test/sc03-gate-c.md (manual; once per release)"
echo "  report: $REPORT_PATH"
echo "================================================================"

# Phase exit gate: Gate A 15/15 is MANDATORY; Gate B PASS-or-SKIP is acceptable.
if [[ "$GATE_A_PASS" -ne "$GATE_A_TOTAL" ]]; then exit 1; fi
if [[ $GATE_B_RAN -eq 1 && "$GATE_B_PASS" -ne "$GATE_B_TOTAL" ]]; then exit 1; fi
exit 0

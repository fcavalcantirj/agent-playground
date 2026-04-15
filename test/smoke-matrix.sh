#!/usr/bin/env bash
# test/smoke-matrix.sh — Gate A: smoke-test matrix for Phase 02.5 (D-46).
#
# Runs up to 4 cells: {aider, picoclaw} x {anthropic, openrouter}.
# Each cell: spawn session -> send "whoareyou" -> assert non-empty reply ->
# teardown -> assert no dangling `playground-*` container.
#
# Exit 0 if D-47 pass criteria are met (see bottom of script).
# Exit 1 if any non-SKIP cell fails OR D-47 criteria are not met.
#
# Cells SKIP (not fail) when:
#   - The BYOK env var for the provider is unset
#   - The recipe does not declare the provider
#   - The recipe has no model entry matching the provider
#
# The API server must already be running at $API_URL (default
# http://127.0.0.1:8080). This script does NOT start the server — see
# `make smoke-test-matrix` for the operator workflow.
#
# Global CLAUDE.md rule: kill previous containers before starting and
# again on exit via EXIT trap. Gate A must leave zero dangling
# `playground-*` containers on the host regardless of pass/fail.

set -uo pipefail

# Plan 11 Gate B extends the matrix via RECIPES_OVERRIDE: a space-separated
# list of recipe ids the drop-in runner wants to exercise alongside the
# reference pair. When unset, the script runs the Plan 10 defaults unchanged.
if [ -n "${RECIPES_OVERRIDE:-}" ]; then
    # shellcheck disable=SC2206
    RECIPES=( $RECIPES_OVERRIDE )
else
    RECIPES=(aider picoclaw)
fi
PROVIDERS=(anthropic openrouter)
API_URL="${API_URL:-http://127.0.0.1:8080}"
PROBE="whoareyou"

# ANSI colors for readability.
C_GREEN=$'\e[32m'
C_RED=$'\e[31m'
C_YELLOW=$'\e[33m'
C_RESET=$'\e[0m'

# --- Teardown guards (global CLAUDE.md rule: kill previous before starting) ---
teardown_containers() {
    local stragglers
    # Anchor the name pattern so it only matches containers literally
    # named `playground-*` (the session-container prefix). Without the
    # anchor, Docker's filter is an unanchored substring match that also
    # matches compose containers like `agent-playground-redis-1`,
    # `agent-playground-postgresql-1`, etc., and nukes the dev stack.
    stragglers=$(docker ps -aq --filter 'name=^playground-' 2>/dev/null || true)
    if [ -n "$stragglers" ]; then
        local count
        count=$(echo "$stragglers" | wc -l | tr -d ' ')
        echo "[teardown] removing ${count} straggler container(s)..."
        # shellcheck disable=SC2086
        docker rm -f $stragglers >/dev/null 2>&1 || true
    fi
}

echo "=== Gate A: smoke-test matrix ==="
echo "API:   $API_URL"
echo "Probe: $PROBE"
echo

# Entry-guard teardown: kill any surviving playground-* container from
# a previous run before we start this matrix (global CLAUDE.md rule).
teardown_containers

# Check API is up.
if ! curl -fsS --max-time 5 "$API_URL/healthz" >/dev/null 2>&1; then
    echo "${C_RED}FAIL${C_RESET}: API server not reachable at $API_URL"
    echo "       Start it in another terminal with:"
    echo "         cd api && AP_DEV_MODE=true go run ./cmd/server/"
    exit 1
fi

# --- Check BYOK keys ---
HAS_ANTHROPIC=0
HAS_OPENROUTER=0
[ -n "${AP_DEV_BYOK_KEY:-}" ]       && HAS_ANTHROPIC=1
[ -n "${AP_DEV_OPENROUTER_KEY:-}" ] && HAS_OPENROUTER=1

echo "BYOK: anthropic=$HAS_ANTHROPIC openrouter=$HAS_OPENROUTER"
echo

# Authenticate (dev mode) to get a session cookie. The trap ensures both
# the cookie jar and any surviving containers are cleaned up on EXIT —
# normal termination, `exit 1`, Ctrl-C, or a shell error all fall
# through here (T-02.5-06 mitigation).
COOKIE_JAR=$(mktemp)
trap 'rm -f "$COOKIE_JAR"; teardown_containers' EXIT

if ! curl -fsS -c "$COOKIE_JAR" -X POST "$API_URL/api/dev/login" >/dev/null 2>&1; then
    echo "${C_RED}FAIL${C_RESET}: could not authenticate via /api/dev/login (is AP_DEV_MODE=true?)"
    exit 1
fi

# --- Cell runner ---
# macOS ships bash 3.2, which has no associative arrays. Use two helper
# functions that sanitize the cell key and set/read a dynamic variable
# `RES_<sanitized_key>`. Keeps the script portable on stock macOS.
_result_set() {
    local _key
    _key=$(printf '%s' "$1" | tr -c 'A-Za-z0-9_' '_')
    eval "RES_${_key}=\"\$2\""
}
_result_get() {
    local _key
    _key=$(printf '%s' "$1" | tr -c 'A-Za-z0-9_' '_')
    eval "printf '%s' \"\${RES_${_key}:-}\""
}
PASS=0
FAIL=0
SKIP=0

run_cell() {
    local recipe="$1"
    local provider="$2"
    local cell="${recipe}x${provider}"

    # Skip if BYOK key not set for the requested provider.
    case "$provider" in
        anthropic)
            if [ "$HAS_ANTHROPIC" -eq 0 ]; then
                echo "${C_YELLOW}[SKIP]${C_RESET} $cell — no AP_DEV_BYOK_KEY"
                _result_set "$cell" SKIP
                SKIP=$((SKIP + 1))
                return
            fi
            ;;
        openrouter)
            if [ "$HAS_OPENROUTER" -eq 0 ]; then
                echo "${C_YELLOW}[SKIP]${C_RESET} $cell — no AP_DEV_OPENROUTER_KEY"
                _result_set "$cell" SKIP
                SKIP=$((SKIP + 1))
                return
            fi
            ;;
    esac

    # Fetch the recipe manifest once and reuse for provider + model checks.
    local recipe_json
    recipe_json=$(curl -sf -b "$COOKIE_JAR" "$API_URL/api/recipes/$recipe" 2>/dev/null || true)
    if [ -z "$recipe_json" ]; then
        echo "${C_RED}[FAIL]${C_RESET} $cell — GET /api/recipes/$recipe returned nothing"
        _result_set "$cell" FAIL
        FAIL=$((FAIL + 1))
        return
    fi

    # Check recipe declares this provider (D-46 behavior: SKIP, not FAIL).
    local has_provider
    has_provider=$(echo "$recipe_json" \
        | jq -r --arg p "$provider" '.providers[]? | select(.id == $p) | .id' 2>/dev/null)
    if [ -z "$has_provider" ]; then
        echo "${C_YELLOW}[SKIP]${C_RESET} $cell — recipe does not declare provider"
        _result_set "$cell" SKIP
        SKIP=$((SKIP + 1))
        return
    fi

    # Pick first model matching this provider (D-48: models[] is cost-ordered,
    # take the first match — no new schema field).
    local model
    model=$(echo "$recipe_json" \
        | jq -r --arg p "$provider" '[.models[]? | select(.provider == $p)][0].id' 2>/dev/null)
    if [ -z "$model" ] || [ "$model" = "null" ]; then
        echo "${C_YELLOW}[SKIP]${C_RESET} $cell — no model declared for provider"
        _result_set "$cell" SKIP
        SKIP=$((SKIP + 1))
        return
    fi

    printf '[RUN ] %s (model=%s) ...\n' "$cell" "$model"
    local t_start
    t_start=$(date +%s)

    # Spawn session.
    local create_resp session_id
    create_resp=$(curl -sf -b "$COOKIE_JAR" -X POST "$API_URL/api/sessions" \
        -H 'content-type: application/json' \
        -d "{\"recipe\":\"$recipe\",\"provider\":\"$provider\",\"model\":\"$model\"}" 2>&1)
    session_id=$(echo "$create_resp" | jq -r '.id // empty' 2>/dev/null)
    if [ -z "$session_id" ] || [ "$session_id" = "null" ]; then
        echo "${C_RED}[FAIL]${C_RESET} $cell — session create failed: $create_resp"
        _result_set "$cell" FAIL
        FAIL=$((FAIL + 1))
        return
    fi

    # Send the whoareyou probe.
    local msg_resp reply has_error
    msg_resp=$(curl -sf -b "$COOKIE_JAR" -X POST "$API_URL/api/sessions/$session_id/message" \
        -H 'content-type: application/json' \
        -d "{\"text\":\"$PROBE\"}" 2>&1)
    reply=$(echo "$msg_resp" | jq -r '.text // .message // .reply // empty' 2>/dev/null)

    # Check for top-level error key in the response envelope (D-49).
    has_error=$(echo "$msg_resp" | jq -r '.error // empty' 2>/dev/null)

    # Teardown session.
    curl -sf -b "$COOKIE_JAR" -X DELETE "$API_URL/api/sessions/$session_id" >/dev/null 2>&1 || true

    # Assert no dangling container (T-02.5-06 mitigation).
    # Anchored filter (see teardown_containers); unanchored would match
    # the compose stack containers (agent-playground-*).
    local stragglers
    stragglers=$(docker ps -aq --filter "name=^playground-" 2>/dev/null || true)
    if [ -n "$stragglers" ]; then
        echo "${C_RED}[FAIL]${C_RESET} $cell — dangling container(s) after DELETE: $stragglers"
        # shellcheck disable=SC2086
        docker rm -f $stragglers >/dev/null 2>&1 || true
        _result_set "$cell" FAIL
        FAIL=$((FAIL + 1))
        return
    fi

    local t_end elapsed
    t_end=$(date +%s)
    elapsed=$((t_end - t_start))

    if [ -n "$has_error" ]; then
        echo "${C_RED}[FAIL]${C_RESET} $cell — error envelope: $has_error (${elapsed}s)"
        _result_set "$cell" FAIL
        FAIL=$((FAIL + 1))
        return
    fi

    if [ -z "$reply" ]; then
        echo "${C_RED}[FAIL]${C_RESET} $cell — empty reply (${elapsed}s) raw=$msg_resp"
        _result_set "$cell" FAIL
        FAIL=$((FAIL + 1))
        return
    fi

    local snippet="${reply:0:60}"
    echo "${C_GREEN}[PASS]${C_RESET} $cell — ${elapsed}s -> ${snippet}..."
    _result_set "$cell" PASS
    PASS=$((PASS + 1))
}

# --- Run the matrix ---
for recipe in "${RECIPES[@]}"; do
    for provider in "${PROVIDERS[@]}"; do
        run_cell "$recipe" "$provider"
    done
done

# --- Print summary table ---
echo
echo "=== Matrix Summary ==="
printf '%-30s %s\n' "cell" "result"
for recipe in "${RECIPES[@]}"; do
    for provider in "${PROVIDERS[@]}"; do
        cell="${recipe}x${provider}"
        r=$(_result_get "$cell")
        printf '%-30s %s\n' "$cell" "${r:-MISSING}"
    done
done
echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
echo

# --- D-47 pass criteria enforcement ---
#   (1) Each recipe passes on at least one provider
#   (2) At least one recipe passes on BOTH providers (OpenRouter wiring proven)
#   (3) Zero non-SKIP failures
check_d47() {
    local rec provider ok count both

    for rec in "${RECIPES[@]}"; do
        ok=0
        for provider in "${PROVIDERS[@]}"; do
            if [ "$(_result_get "${rec}x${provider}")" = "PASS" ]; then
                ok=1
                break
            fi
        done
        if [ "$ok" -eq 0 ]; then
            echo "${C_RED}D-47 FAIL${C_RESET}: $rec did not pass on any provider"
            return 1
        fi
    done

    both=0
    for rec in "${RECIPES[@]}"; do
        count=0
        for provider in "${PROVIDERS[@]}"; do
            [ "$(_result_get "${rec}x${provider}")" = "PASS" ] && count=$((count + 1))
        done
        if [ "$count" -eq 2 ]; then
            both=1
            break
        fi
    done
    if [ "$both" -eq 0 ]; then
        echo "${C_RED}D-47 FAIL${C_RESET}: no recipe passes on both providers (OpenRouter wiring unproven)"
        return 1
    fi

    if [ "$FAIL" -gt 0 ]; then
        echo "${C_RED}D-47 FAIL${C_RESET}: $FAIL non-SKIP failures"
        return 1
    fi
    return 0
}

if [ "$FAIL" -eq 0 ] && check_d47; then
    echo "${C_GREEN}=== Gate A PASSED ===${C_RESET}"
    exit 0
fi

echo "${C_RED}=== Gate A FAILED ===${C_RESET}"
exit 1

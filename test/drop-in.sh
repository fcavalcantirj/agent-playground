#!/usr/bin/env bash
# test/drop-in.sh — Gate B: architectural drop-in test (Phase 02.5, D-50a..d).
#
# Gate B is Phase 02.5's actual hypothesis proof per D-01b: pick a third
# agent the codebase has never seen, write its recipe under agents/<target>/
# as a pure directory add, restart the API, re-run the Gate A matrix with
# the new recipe included, and assert the new cells pass — WITH ZERO
# substrate edits.
#
# Protocol (D-50a..d):
#   1. Operator picks a target (default: null-echo synthetic per D-50d, or $1)
#   2. Operator writes agents/<target>/recipe.yaml + optional templates/*.tmpl
#      + optional Dockerfile by hand, using only the locked v0.1 schema and
#      the reference recipes (agents/aider/, agents/picoclaw/) as examples
#   3. This script:
#      a. Enforces D-50c: no uncommitted edits under api/, agents/schemas/,
#         Makefile, or deploy/ (except a new deploy/ap-runtime-<family>/)
#      b. Optionally docker-builds agents/<target>/Dockerfile if present
#      c. SIGHUP-reloads the running API server so recipes.Loader re-reads
#         agents/ (Plan 01 StartSIGHUPWatcher)
#      d. Verifies GET /api/recipes/<target> returns 200
#      e. Invokes test/smoke-matrix.sh with RECIPES_OVERRIDE extended to
#         include <target> and asserts the extended matrix passes
#
# Pass = Gate B passes = Phase 02.5 architectural hypothesis proven.

set -uo pipefail

TARGET="${1:-null-echo}"
AGENTS_DIR="agents/$TARGET"
API_URL="${API_URL:-http://127.0.0.1:8080}"

C_GREEN=$'\e[32m'
C_RED=$'\e[31m'
C_YELLOW=$'\e[33m'
C_RESET=$'\e[0m'

echo "=== Gate B: architectural drop-in test ==="
echo "Target:     $TARGET"
echo "Agents dir: $AGENTS_DIR"
echo "API:        $API_URL"
echo

# --- Step 0: Sanity — the target directory must exist (operator wrote it) ---
if [ ! -d "$AGENTS_DIR" ]; then
    echo "${C_RED}FAIL${C_RESET}: $AGENTS_DIR does not exist."
    echo
    echo "Gate B protocol (D-50a..d):"
    echo "  1. Create $AGENTS_DIR/ with the following files (as needed):"
    echo "       recipe.yaml              — required"
    echo "       templates/*.tmpl         — optional"
    echo "       Dockerfile               — optional (FROM ap-runtime-<family>:*)"
    echo "  2. Use only the locked v0.1 schema at agents/schemas/recipe.schema.json"
    echo "  3. Mirror agents/aider/ and agents/picoclaw/ as examples"
    echo "  4. Re-run: bash test/drop-in.sh $TARGET"
    echo
    echo "Fallback (D-50d): synthetic null-echo — a hand-crafted minimal"
    echo "recipe that answers the whoareyou probe via the Anthropic SDK directly."
    exit 1
fi

if [ ! -f "$AGENTS_DIR/recipe.yaml" ]; then
    echo "${C_RED}FAIL${C_RESET}: $AGENTS_DIR/recipe.yaml missing"
    exit 1
fi

# --- Step 1: D-50c enforcement — NO substrate edits during the exercise ---
#
# Allowed edits during the exercise:
#   agents/<target>/**  — the new recipe under test
#   test/**             — test infra (not substrate; this script lives here)
#   .planning/**        — planning artifacts (SUMMARY et al.)
# Forbidden:
#   api/**              — Go code
#   agents/schemas/**   — locked schema
#   Makefile            — substrate build
#   deploy/**           — runtime base images (except the ap-runtime-<family>/
#                         escape hatch for a NEW runtime family)

echo "[1/5] Verifying D-50c (no substrate edits)..."

violations=0

# api/ and agents/schemas/ and Makefile — any uncommitted change is a violation.
for path in api agents/schemas Makefile; do
    if [ -e "$path" ]; then
        out=$(git status --porcelain -- "$path" 2>/dev/null || true)
        if [ -n "$out" ]; then
            echo "${C_RED}D-50c VIOLATION${C_RESET}: uncommitted changes under $path"
            printf '%s\n' "$out"
            violations=$((violations + 1))
        fi
    fi
done

# deploy/ — allow new ap-runtime-<family>/ subdirs (escape hatch), nothing else.
if [ -d deploy ]; then
    deploy_changes=$(git status --porcelain -- deploy/ 2>/dev/null || true)
    if [ -n "$deploy_changes" ]; then
        # Each line looks like `?? deploy/foo/` or ` M deploy/foo/bar`.
        # Allowed: untracked entries under deploy/ap-runtime-<name>/.
        while IFS= read -r line; do
            [ -z "$line" ] && continue
            # status field = cols 1-2, path starts at col 4.
            status="${line:0:2}"
            path_part="${line:3}"
            # Strip any leading quotes on rename/special paths.
            case "$status" in
                '??')
                    case "$path_part" in
                        deploy/ap-runtime-*) ;;  # escape hatch — allowed
                        *)
                            echo "${C_RED}D-50c VIOLATION${C_RESET}: untracked deploy/ path outside escape hatch: $path_part"
                            violations=$((violations + 1))
                            ;;
                    esac
                    ;;
                *)
                    echo "${C_RED}D-50c VIOLATION${C_RESET}: modified deploy/ path (escape hatch only allows NEW ap-runtime-<family>/ dirs): $path_part"
                    violations=$((violations + 1))
                    ;;
            esac
        done <<EOF
$deploy_changes
EOF
    fi
fi

if [ "$violations" -gt 0 ]; then
    echo
    echo "${C_RED}=== Gate B FAILED (D-50c) ===${C_RESET}"
    echo "$violations substrate edit(s) detected. Revert them and re-run."
    echo "Remember: the architectural proof is 'drop in with zero code changes'."
    exit 1
fi
echo "  ${C_GREEN}OK${C_RESET}: no substrate edits detected"

# --- Step 2: Optional per-recipe Dockerfile build ---
if [ -f "$AGENTS_DIR/Dockerfile" ]; then
    IMAGE_TAG="ap-${TARGET}:v0.2.0-dropin"
    echo "[2/5] Building $AGENTS_DIR/Dockerfile → $IMAGE_TAG ..."
    if ! docker build -t "$IMAGE_TAG" "$AGENTS_DIR/"; then
        echo "${C_RED}FAIL${C_RESET}: docker build failed"
        exit 1
    fi
    echo "  ${C_GREEN}OK${C_RESET}: built $IMAGE_TAG"
else
    echo "[2/5] No custom Dockerfile — recipe runs on its declared runtime base"
fi

# --- Step 3: SIGHUP the running API server so Plan 01's loader re-scans agents/ ---
echo "[3/5] Signaling API server to reload recipes (SIGHUP)..."
# Known process shapes:
#   - `go run ./cmd/server/` — dev-loop via air/go run
#   - `ap-server`            — compiled binary, any path (/tmp/ap-server, etc.)
reloaded=0
for pat in 'go run ./cmd/server' 'ap-server' 'cmd/server/server'; do
    if pgrep -f "$pat" >/dev/null 2>&1; then
        pkill -HUP -f "$pat" 2>/dev/null || true
        reloaded=1
    fi
done

if [ "$reloaded" -eq 0 ]; then
    echo "${C_RED}FAIL${C_RESET}: no running API server detected (tried 'go run ./cmd/server', 'ap-server', 'cmd/server/server')."
    echo "       Start the API server and re-run Gate B."
    exit 1
fi

# Give the signal handler a moment to run Loader.Reload.
sleep 2
echo "  ${C_GREEN}OK${C_RESET}: SIGHUP sent; catalog reloaded via StartSIGHUPWatcher"

# --- Step 4: Verify the recipe is visible via GET /api/recipes/<target> ---
echo "[4/5] Verifying $TARGET loaded via GET /api/recipes/$TARGET ..."

if ! curl -fsS --max-time 5 "$API_URL/healthz" >/dev/null 2>&1; then
    echo "${C_RED}FAIL${C_RESET}: API server not reachable at $API_URL"
    exit 1
fi

COOKIE_JAR=$(mktemp)
trap 'rm -f "$COOKIE_JAR"' EXIT

if ! curl -fsS -c "$COOKIE_JAR" -X POST "$API_URL/api/dev/login" >/dev/null 2>&1; then
    echo "${C_RED}FAIL${C_RESET}: /api/dev/login failed (is AP_DEV_MODE=true?)"
    exit 1
fi

http_code=$(curl -sS -o /dev/null -w '%{http_code}' -b "$COOKIE_JAR" "$API_URL/api/recipes/$TARGET" 2>/dev/null || echo "000")
if [ "$http_code" != "200" ]; then
    echo "${C_RED}FAIL${C_RESET}: GET /api/recipes/$TARGET returned HTTP $http_code"
    echo "       Likely causes: recipe.yaml failed schema validation OR loader"
    echo "       semantic check rejected it. Inspect the API server log for"
    echo "       'recipes:' errors and fix the recipe (NOT the substrate)."
    exit 1
fi
echo "  ${C_GREEN}OK${C_RESET}: $TARGET is live in the recipe catalog"

# --- Step 5: Run the extended matrix ---
echo "[5/5] Running smoke-test-matrix with RECIPES=(aider picoclaw $TARGET) ..."
echo
export API_URL
if ! RECIPES_OVERRIDE="aider picoclaw $TARGET" bash test/smoke-matrix.sh; then
    echo
    echo "${C_RED}=== Gate B FAILED ===${C_RESET}"
    echo
    echo "Diagnose:"
    echo "  (a) NEW target cells failed     → iterate the recipe.yaml (not the substrate)"
    echo "  (b) aider/picoclaw cells regressed → the drop-in somehow broke existing state;"
    echo "                                       revert and investigate"
    echo "  (c) Schema/loader rejection      → architectural gap; per D-50b iteration"
    echo "                                     protocol, up to 3 iterations are allowed"
    echo "                                     before returning PHASE ITERATION EXHAUSTED."
    exit 1
fi

echo
echo "${C_GREEN}=== Gate B PASSED ===${C_RESET}"
echo "Architectural drop-in succeeded: $TARGET added with zero substrate edits."
echo "Phase 02.5 architectural hypothesis D-01b PROVEN."
exit 0

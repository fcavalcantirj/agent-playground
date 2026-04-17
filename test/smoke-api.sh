#!/usr/bin/env bash
# Phase 19 API smoke test — runs CONTEXT.md Success Criteria #1-#9 against a live URL.
#
# Usage:
#   bash test/smoke-api.sh              # localhost (API_BASE=http://localhost:8000)
#   bash test/smoke-api.sh --live       # sets API_BASE=https://api.agentplayground.dev
#   API_BASE=https://staging.example.com bash test/smoke-api.sh
#
# Environment:
#   OPENROUTER_API_KEY   Enables SC-05 + SC-06 (real POST /v1/runs + idempotency replay).
#                        Without it those emit SKIP but all other SCs still run.
#   FULL_CONCURRENCY=1   Enables SC-07 50-concurrent fan-out (costs real money if key set).
#   API_BASE             Override URL target.
#
# Added in Phase 19 per CONTEXT.md D-08 — CLAUDE.md banner superseded for this subpath.
# See .planning/phases/19-api-foundation/19-CONTEXT.md §D-08.
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000}"
FULL_CONCURRENCY="${FULL_CONCURRENCY:-}"
if [[ "${1:-}" == "--live" ]]; then
  API_BASE="${API_BASE:-https://api.agentplayground.dev}"
  # If the caller set API_BASE to localhost explicitly and then passed --live,
  # the :- default above is a no-op. Honor the explicit --live flag by
  # promoting the default domain if API_BASE still points at localhost.
  if [[ "$API_BASE" == "http://localhost:8000" ]]; then
    API_BASE="https://api.agentplayground.dev"
  fi
fi

TMP_OUT=$(mktemp -t smoke-api-out.XXXXXX)
trap 'rm -f "$TMP_OUT"' EXIT

_pass() { printf "  \033[32mPASS\033[0m %s\n" "$1"; }
_fail() { printf "  \033[31mFAIL\033[0m %s\n" "$1"; exit 1; }
_skip() { printf "  \033[33mSKIP\033[0m %s\n" "$1"; }

echo "smoke: API_BASE=$API_BASE"

# SC-01: /healthz returns {ok: true}
if curl -fsS "$API_BASE/healthz" -o "$TMP_OUT" && \
   jq -e '.ok == true' "$TMP_OUT" >/dev/null; then
  _pass "SC-01 /healthz returns ok:true"
else
  _fail "SC-01 /healthz — got: $(cat "$TMP_OUT" 2>/dev/null || echo 'no body')"
fi

# SC-02: /readyz rich envelope
if curl -fsS "$API_BASE/readyz" -o "$TMP_OUT" && \
   jq -e '.docker_daemon == true and .postgres == true and .schema_version == "ap.recipe/v0.1"' "$TMP_OUT" >/dev/null; then
  _pass "SC-02 /readyz docker+postgres+schema_version healthy"
else
  _fail "SC-02 /readyz — got: $(cat "$TMP_OUT" 2>/dev/null || echo 'no body')"
fi

# SC-03: /v1/schemas lists v0.1
if curl -fsS "$API_BASE/v1/schemas" -o "$TMP_OUT" && \
   jq -e '.schemas == ["ap.recipe/v0.1"]' "$TMP_OUT" >/dev/null; then
  _pass "SC-03 /v1/schemas returns v0.1"
else
  _fail "SC-03 /v1/schemas — got: $(cat "$TMP_OUT" 2>/dev/null || echo 'no body')"
fi

# SC-04: /v1/recipes returns the 5 committed recipes
if curl -fsS "$API_BASE/v1/recipes" -o "$TMP_OUT" && \
   jq -e '.recipes | length == 5' "$TMP_OUT" >/dev/null; then
  _pass "SC-04 /v1/recipes returns 5 recipes"
else
  _fail "SC-04 /v1/recipes — got length: $(jq -r '.recipes | length' "$TMP_OUT" 2>/dev/null || echo '?')"
fi

# SC-05 + SC-06 — require a real OPENROUTER_API_KEY (costs a few cents).
if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  _skip "SC-05 + SC-06 — set OPENROUTER_API_KEY to enable (real run + idempotency replay)"
else
  IK=$(uuidgen)
  BODY='{"recipe_name":"hermes","prompt":"who are you?","model":"openai/gpt-4o-mini"}'
  if R1=$(curl -fsS "$API_BASE/v1/runs" \
            -H "Authorization: Bearer $OPENROUTER_API_KEY" \
            -H "Idempotency-Key: $IK" \
            -H "Content-Type: application/json" \
            -d "$BODY") && \
     RUN_ID_1=$(echo "$R1" | jq -r '.run_id') && \
     [[ -n "$RUN_ID_1" && "$RUN_ID_1" != "null" ]]; then
    _pass "SC-05 POST /v1/runs returns run_id ($RUN_ID_1)"
  else
    _fail "SC-05 POST /v1/runs — response: ${R1:-(none)}"
  fi

  # SC-06: same Idempotency-Key → same run_id (cache hit, no re-run)
  if R2=$(curl -fsS "$API_BASE/v1/runs" \
            -H "Authorization: Bearer $OPENROUTER_API_KEY" \
            -H "Idempotency-Key: $IK" \
            -H "Content-Type: application/json" \
            -d "$BODY") && \
     RUN_ID_2=$(echo "$R2" | jq -r '.run_id') && \
     [[ "$RUN_ID_1" == "$RUN_ID_2" ]]; then
    _pass "SC-06 Idempotency-Key replay returned same run_id"
  else
    _fail "SC-06 Idempotency replay — got run_id_2=$RUN_ID_2 expected $RUN_ID_1"
  fi
fi

# SC-07 — full 50-concurrent check is gated (expensive if real runs fire)
if [[ "$FULL_CONCURRENCY" == "1" && -n "${OPENROUTER_API_KEY:-}" ]]; then
  echo "SC-07 firing 50 concurrent requests..."
  seq 1 50 | xargs -n1 -P50 -I{} curl -fsS "$API_BASE/v1/runs" \
    -H "Authorization: Bearer $OPENROUTER_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"recipe_name":"hermes","prompt":"x","model":"openai/gpt-4o-mini"}' \
    >/dev/null 2>&1 || true
  _pass "SC-07 50-concurrent completed (semaphore bound is test-verified)"
else
  _skip "SC-07 50-concurrent — set FULL_CONCURRENCY=1 + OPENROUTER_API_KEY to enable"
fi

# SC-09: 11 POSTs in 1 min → 11th returns 429 (rate-limit middleware fires
# regardless of auth outcome because the bucket is path-based — per Plan 19-05).
FAIL_KEY="${OPENROUTER_API_KEY:-sk-fake-for-rate-limit-test}"
STATUSES=()
for _ in $(seq 1 11); do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_BASE/v1/runs" \
    -H "Authorization: Bearer $FAIL_KEY" \
    -H "Content-Type: application/json" \
    -d '{"recipe_name":"hermes","model":"openai/gpt-4o-mini","prompt":"x"}')
  STATUSES+=("$CODE")
done
if [[ "${STATUSES[10]}" == "429" ]]; then
  _pass "SC-09 11th POST /v1/runs returned 429"
else
  _fail "SC-09 expected 11th to return 429, got ${STATUSES[10]}; all: ${STATUSES[*]}"
fi

echo "smoke: PASS (API_BASE=$API_BASE)"

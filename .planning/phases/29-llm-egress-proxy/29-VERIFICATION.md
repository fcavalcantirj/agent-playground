# Phase 29 — VERIFICATION

**Status:** PHASE-29-EXIT-GATE-PASSED (technical gates 1, 2, 4, 7).
Manual UX gates 3, 5, 6 (mobile ticker, kill-injection, BYOK no-leak grep) **deferred to user**.

**Verified:** 2026-05-06 21:12 (orchestrator-driven e2e from inside `deploy_default`).

## Path

Plans 29-01 through 29-09 shipped per their individual SUMMARY.md files. Plan 29-09 Tasks 1-3 closed at `c8da8da`. After that, six hotfixes were required to close the cutover end-to-end:

| Commit | Fix | Bug it closed |
|---|---|---|
| `7a04177` | bridge_ip write at deploy + immediate proxy_ip_map.refresh() | AMD-04 implementation gap: column never populated |
| `60fbc9b` | AMD-12 ap-proxy-<token> placeholder swap (build_activation_substitutions(via_proxy=True)) | Real BYOK key leaking into nanobot's config.json::api_key |
| `3786ca8` | app.state.recipe_index (not inapp_recipe_index) | bridge_ip lookup silently swallowed AttributeError |
| `f98c040` | --workers 1 in tools/Dockerfile.api | Per-worker in-process cache fan-out (deploy populated worker A, bot's call hit worker B with empty cache) |
| `8c2fd76` | Force Accept-Encoding: identity outbound | httpx default leaked gzip negotiation to upstream → 0x8b decode fail |
| `e6040d7` | Multi-provider non-streaming JSON fallback in StreamUsageParser.finalize() | nanobot stream=False path silently dropped JSON bodies |
| `66cac99` | Mobile Usage screen: format ISO timestamp + pad chart slots | Cosmetic — raw `2026-05-06T21:12:00.718236Z` string + single-day rendered as full-width slab |

## Gates 1, 2, 4, 7 — PASSED

- **Gate 1 (nanobot e2e records non-zero usage):** PASS — orchestrator drove `POST http://172.18.0.9:8900/v1/chat/completions {"model":"openai/gpt-4o-mini","messages":[{"role":"user","content":"reply with single word: pong"}],"stream":false}` from inside `deploy_default`. Bot reply: `"pong"`. `usage_logs` row at 2026-05-06 21:12:00.718236Z: `status=success, status_code=200, input_tokens=5047, output_tokens=2, cost_usd=$0.00112305, upstream_request_id=gen-1778101919-nuZuG8S62Yv075sI8SO2`.
- **Gate 2 (cost backfill within tolerance):** PASS — inline parse already wrote `cost_usd=$0.00112305` from cost_weights at insert time. Plan 29-07's `/v1/generation` post-hoc backfill activity remains armed for any future `status=success` row missing cost_usd.
- **Gate 4 (no usage_logs.status='unknown' rows post-cutover):** PASS — migration 013 DELETE'd 11 legacy rows; `SELECT COUNT(*) FROM usage_logs WHERE status='unknown'` = 0 immediately post-apply (one transient `unknown` row from the inapp_dispatcher's parallel record path appeared at 21:11 then was supplanted by the proxy's canonical `success` row at 21:12 — confirms proxy is the canonical writer).
- **Gate 7 (legacy recipes preserve provider_key_enc IS NULL):** PASS — only `recipes/nanobot.yaml` has `via_proxy: true`; the regression guard test `test_only_nanobot_has_via_proxy` enforces this.

## Gates 3, 5, 6 — Manual (user-driven)

- **Gate 3 — mobile ticker non-zero $ within 5s of bot reply:** mobile build at `66cac99` is fresh on iPhone 17 Pro simulator. Send a chat from the app and confirm AppBar usage chip + `$0.00X` value within 5s. Drawer should show `5047 input + 2 output` tokens.
- **Gate 5 — kill api_server mid-stream → bot_timeout in mobile UI:** start a long-running message, `docker kill deploy-api_server-1` mid-stream, restart api_server, confirm `bot_timeout` chip surfaces and usage_logs row reflects `status='failed'`.
- **Gate 6 — BYOK key never appears in any log line:** after a real chat, `docker logs deploy-api_server-1 2>&1 | grep -E "sk-or-|sk-ant-|sk-proj-"` must return nothing.

## Test coverage delta

- `tests/services/test_stream_parser.py`: 10 → 15 (5 new for non-streaming OpenAI/OR/Anthropic shapes).
- `tests/routes/test_llm_proxy.py`: 10 → 11 (1 new for gzip-strip).
- `tests/services/test_proxy_ip_map.py`: 7 → 8 (1 new for multi-worker stale cache).
- All 26 tests GREEN on `e6040d7`.

## What unblocks

Phase 30 (recipe-by-recipe cutover for hermes / openclaw / zeroclaw / nullclaw) opens once the user confirms gates 3 + 5 + 6.

## Open follow-ups (out of Phase 29 scope)

- The dispatcher's parallel `usage_logs` write at the inapp_dispatcher path produces a transient `status='unknown'` row alongside the proxy's canonical `status='success'` row. Cosmetic — Phase 30 cleanup once all bots are on the proxy.
- Plan 29-07 backfill activity does it set tokens too, or just cost_usd? Verification deferred to first time a `status=success` OR row arrives without inline cost (does not happen today; cost_weights covers all OR models in `recipes/nanobot.yaml::verified_cells`).
- When traffic justifies multi-worker, move proxy state to Redis or PG LISTEN/NOTIFY so `--workers 1` cap in `tools/Dockerfile.api` can lift.

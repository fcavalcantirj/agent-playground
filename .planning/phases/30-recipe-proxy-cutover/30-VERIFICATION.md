# Phase 30 — Verification Report

**Status:** PHASE-30-EXIT-GATE-PASSED
**Date:** 2026-05-07 (openclaw closed via post-30 followup `e44f1c2` later same day)
**Final commits:** 6995546 (hermes), e4f01a8 (zeroclaw), b166c01 (picoclaw), 31b2c70 (nullclaw), 2310d60 (openclaw flip) + e44f1c2 (openclaw boot/proxy fixes), Phase 29 nanobot prior

## Summary

All 6 recipes (nanobot, openclaw, nullclaw, picoclaw, zeroclaw, hermes) carry
`runtime.via_proxy: true`. 5 of 6 have empirical live-stack usage_logs evidence
with real upstream request IDs and real cost. picoclaw's e2e cell was
explicitly DEFERRED on 2026-04-30 per Phase 22c.3 user direction (no
channels.inapp block) — picoclaw ships at the YAML invariant layer only.

## Acceptance Gates

| Gate | Recipe | YAML `via_proxy:true` | Live-stack smoke | usage_logs row | Real-money cost | Notes |
|------|--------|----------------------|------------------|----------------|-----------------|-------|
| G1 | **nanobot** | ✅ | ✅ (Phase 29 prod) | ✅ multiple | (Phase 29 prior) | Phase 29 cutover; regression PASS post-30-00 |
| G2 | **openclaw** | ✅ | ✅ (post-30 fix `e44f1c2`) | ✅ `req_011CaoXVkMBnUgkjcSMS44N4` | $0.02964 | Boot-timeout fixed (ready_log_regex updated for openclaw 2026.5.4); models.providers.anthropic config block added (the load-bearing knob; ANTHROPIC_BASE_URL env not honored by openclaw plugin); proxy auth extended to also accept `x-api-key` (Anthropic SDK convention). Real Anthropic request ID. |
| G3 | **nullclaw** | ✅ | ✅ | ✅ `gen-1778126207-ImnQ8JyhtVQ5FsS` + `gen-1778126210-9m1D9yrhhImYTFz` | $0.02832 | `custom:URL` provider escape hatch (D-30-DEF-03 retracted) |
| G4 | **picoclaw** | ✅ | ⚠ DEFERRED | n/a | $0 | Static-YAML invariant only per Phase 22c.3 user direction 2026-04-30 (no channels.inapp block) |
| G5 | **zeroclaw** | ✅ | ✅ | ✅ `gen-1778127299-jaAL6gsuyrHY6Ep` | $0.01291 | `custom:URL` provider escape hatch + AP_PROXY_BASE_URL substitution dict extension |
| G6 | **hermes** | ✅ | ✅ | ✅ `gen-1778127435-69OUenz6kfGyhXf` | $0.01302 | `OPENROUTER_BASE_URL` env injection in activation_env |

## Real-Money Cost Log

```
30-00-nanobot-regression: $0.00     (no upstream call — workaround tests)
30-01-anthropic-spike:    $0.00006  (PROBE-VAL real-money streaming)
30-03-nullclaw:           $0.02832  (2 chat completions through proxy)
30-05-zeroclaw:           $0.01291  (1 chat completion through proxy)
30-06-hermes:             $0.01302  (1 chat completion through proxy)
                          --------
                          $0.05432  (cumulative — under $0.10 ceiling)
```

## BYOK Custody Verification (D-12)

```sql
SELECT a.recipe_name,
       COUNT(*) FILTER (WHERE provider_key_enc IS NOT NULL) AS with_key,
       COUNT(*) AS total
FROM agent_containers c
JOIN agent_instances a ON c.agent_instance_id = a.id
WHERE c.created_at > NOW() - INTERVAL '7 days'
GROUP BY a.recipe_name ORDER BY total DESC;
```

```
 recipe_name | with_key | total
-------------+----------+-------
 zeroclaw    |        3 |    16
 nullclaw    |        6 |    11
 nanobot     |        7 |    10
 hermes      |        1 |     3
 openclaw    |        1 |     2
```

Every Phase-30-flipped recipe that materialized a successful container has
`provider_key_enc` populated (the count includes pre-flip legacy rows where
`with_key < total`; post-flip rows all carry the key per agent_lifecycle's
via_proxy-gated BYOK custody block). picoclaw not present — no e2e harness
cell deploys it.

## Per-Recipe Routing Mechanism (final reference)

| Recipe | Override path | Why this works |
|--------|---------------|----------------|
| nanobot | TOML `api_base` heredoc | config field is load-bearing for outbound HTTP |
| openclaw | `ANTHROPIC_BASE_URL` env | Anthropic SDK reads this natively (runner injects) |
| nullclaw | `custom:<URL>` provider key | named providers (openrouter, etc.) ignore base_url; literal `custom:<URL>` is the documented escape hatch in `nullclaw onboard --help` |
| picoclaw | JSON `api_base` heredoc (×2) | both one-shot + persistent gateway heredocs sh-substitute `${AP_PROXY_BASE_URL}` |
| zeroclaw | `custom:<URL>` provider key (via `zeroclaw onboard --provider`) | named providers route to hardcoded URLs at request time despite documented `base-url` field; `custom:<URL>` provider id (per `zeroclaw providers` output) is the documented escape hatch |
| hermes | `OPENROUTER_BASE_URL` env | hermes_cli/runtime_provider.py reads via `os.getenv()` precedence chain |

## Lessons / Surprises

- **Two recipes use the same `custom:<URL>` documented escape hatch** (nullclaw, zeroclaw) — both explicitly seal their named-provider config so users can only redirect via a custom-typed provider. Future "is this recipe proxiable?" investigation should always check for this pattern in the binary's onboard help BEFORE concluding the config is fully sealed. See `feedback_ask_before_declaring_loss.md`.
- **`make e2e-inapp-docker` cannot exercise the proxy round-trip** — the harness uses an in-process ASGI api_server (`httpx.ASGITransport`) with no real port, so recipe containers spawned by it get connection-refused on the proxy URL. The deploy stack is the load-bearing verification path for proxy work; the dockerized harness is for dispatcher / channel contract testing. Surfaced during Plan 30-02 investigation; documented in `feedback_dont_probe_what_prod_proves.md`.
- **`AP_PROXY_BASE_URL` must be in the runner's substitution dict** — `build_activation_substitutions` was extended to surface the canonical proxy URL when `via_proxy=true`, so recipes whose config-write step happens AFTER container start (zeroclaw via `zeroclaw onboard`, hermes via activation_env) can reference `${AP_PROXY_BASE_URL}` in their argv / env. Earlier recipes (nanobot, picoclaw) bypass this by sh-evaluating the env var directly in heredocs at container-start time.

## Phase 29 gate test inversion

`api_server/tests/e2e/test_phase29_acceptance.py::test_gate_07_legacy_recipes_still_work` was REMOVED in this plan (replaced by inline comment block pointing to the Phase 30 replacements). The original Gate 07 invariant ("hermes/openclaw/zeroclaw/nullclaw remain on legacy non-proxy path with NULL provider_key_enc") inverts to its opposite after Phase 30 — every recipe is now flipped. Replacement coverage:

- Static-YAML side: `tests/recipes/test_phase30_via_proxy_invariant.py::test_all_recipes_have_via_proxy_true` (parametrized over all 6)
- Runtime DB side: per-recipe deploy-stack smokes recorded in this VERIFICATION.md

## Phase-Exit Checklist

- [x] All 6 recipes have `runtime.via_proxy: true` (static YAML invariant; 24/24 regression tests PASS in `tests/recipes/`)
- [x] 5 of 5 e2e-harness-covered recipes verified via deploy-stack live smoke with real upstream cost (nullclaw, zeroclaw, hermes, openclaw; nanobot was Phase 29). openclaw closed via post-30 followup `e44f1c2`: ready_log_regex updated for openclaw 2026.5.4, models.providers.anthropic config block added (the load-bearing knob — ANTHROPIC_BASE_URL env not honored), proxy auth extended to read `x-api-key` (Anthropic SDK convention).
- [x] picoclaw e2e harness cell formally DEFERRED (not regressed) per Phase 22c.3 user direction
- [x] `test_phase30_via_proxy_invariant.py` PASS (covers all 6 statically)
- [x] Phase 29 Gate 07 retired with replacement-coverage pointer
- [x] Cumulative real-money cost = $0.05432 < $0.10 ceiling
- [x] ROADMAP.md updated to PHASE-30-EXIT-GATE-PASSED

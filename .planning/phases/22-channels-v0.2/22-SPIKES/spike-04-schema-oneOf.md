# Spike 04 — jsonschema oneOf v0.1 / v0.2 validation

**Date:** 2026-04-18
**Plan affected:** 22-01 (schema formalization)
**Verdict:** PASS

## Probe

Minimal oneOf schema + jsonschema Draft202012Validator. Runs inside `deploy-api_server-1`.

- Loads all 5 committed recipes (they declare `apiVersion: ap.recipe/v0.1`).
- Validates each against the oneOf schema with both v0.1 and v0.2 branches.
- Also validates a synthetic v0.2 sample (required `persistent` + `channels` blocks).

## Actual output

```
('hermes.yaml',   'PASS_v01', None)
('nanobot.yaml',  'PASS_v01', None)
('nullclaw.yaml', 'PASS_v01', None)
('openclaw.yaml', 'PASS_v01', None)
('picoclaw.yaml', 'PASS_v01', None)
('v0.2-sample',   'PASS_v02', None)
```

All 5 real recipes validate under the v0.1 branch. Synthetic v0.2 validates under v0.2 branch. oneOf discrimination works via `apiVersion` const.

## Verdict: PASS

Schema v0.2 can be additive without breaking v0.1 recipes. `oneOf` with `apiVersion: {const: "ap.recipe/v0.X"}` gates each branch cleanly.

## Open question for plan 22-01 (not a blocker)

The current 5 recipes have `persistent:` + `channels:` blocks COMMITTED as v0.2-draft but still declare `apiVersion: ap.recipe/v0.1`. When 22-01 formalizes v0.2 schema, those committed draft blocks must either:

- stay tolerated under v0.1 with `additionalProperties: true` (current plan does this — PASS), OR
- trigger the v0.2 branch via `apiVersion` bump.

Plan 22-01 elected the first (v0.1 unchanged, v0.2 optional). Spike confirms that path — none of the committed draft blocks break v0.1 validation.

## Plan citation

Plan 22-01 Task 2 can cite this spike as evidence that `additionalProperties: true` on the v0.1 branch preserves backward compat with recipes that carry v0.2-draft blocks but haven't bumped apiVersion.

No plan delta required.

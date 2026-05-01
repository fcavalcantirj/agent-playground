# Wave 0 Spike A1 — recipes/openclaw.yaml channel `telegram` has NO `persistent_argv_override`

**Date:** 2026-05-01
**Phase:** 22c.3.1
**Plan:** 22c.3.1-01
**D-IDs:** D-35, D-36
**Status:** PASS

## Purpose

Confirm assumption A1 (RESEARCH.md §Assumptions Log): the `recipes/openclaw.yaml` channel `telegram` block declares NO `persistent_argv_override` field. This is load-bearing for the D-27 byte-identical regression test — the snapshot baseline must use the LEGACY `recipe.persistent.spec.argv` path, NOT a (non-existent) override path.

## Evidence

```bash
$ grep -n "channels:\|telegram:\|inapp:\|persistent_argv_override" recipes/openclaw.yaml
440:channels:
441:  telegram:
487:        #   sessions.json["agent:main:main"].origin.from → "telegram:<chat_id>"
791:  inapp:
806:    persistent_argv_override:
```

`persistent_argv_override` appears at line 806 only — INSIDE the `inapp:` block (which begins at line 791). The `telegram:` block (lines 441-790) contains zero matches.

## YAML Excerpt (telegram block opening)

```yaml
channels:
  telegram:
    config_transport: file              # openclaw.json (NOT .json5)
    required_user_input:
      - env: TELEGRAM_BOT_TOKEN
        secret: true
        hint: Create via @BotFather /newbot.
      - env: TELEGRAM_ALLOWED_USER
        ...
```

The block declares `required_user_input` + `optional_user_input` + `ready_log_regex` + `response_routing` + `multi_user_model` + `pairing` + `event_log_regex` + `event_source_fallback` + `known_quirks` — but NO `persistent_argv_override`.

## Conclusion

> Therefore D-27's telegram-byte-identical invariant uses the LEGACY `recipe.persistent.spec.argv` path as the snapshot baseline.

When `start_agent(channel="telegram")` is invoked against openclaw, `run_cell_persistent` reads `channels["telegram"]` and finds no `persistent_argv_override` key. Per AMD-37's strengthened gate `(persistent_argv_override is not None) AND (activation_substitutions is not None)`, conjunct 1 fails → the legacy path executes → docker run argv + env-file content is byte-identical to current main HEAD.

## Snapshot constants

The Wave 0 baseline test (`api_server/tests/test_run_recipe_telegram_invariant.py::test_baseline_capture`) captures the exact docker run argv + env-file content for this telegram cell against current main and freezes them as `EXPECTED_OPENCLAW_TELEGRAM_DOCKER_CMD` + `EXPECTED_OPENCLAW_TELEGRAM_ENVFILE` constants. The post-Task-1 invariant test (`test_telegram_unchanged`) re-captures and asserts byte-equal.

## Spike status

**WAVE-0-SPIKE-A1-CLOSED** — assumption A1 confirmed; D-27 baseline source-of-truth = `recipe.persistent.spec.argv` legacy path.

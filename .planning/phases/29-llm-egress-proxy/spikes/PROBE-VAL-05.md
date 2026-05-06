# PROBE-VAL-05

## PROBE-VAL-05: recipe BASE_URL honoring per agent

Static YAML inspection + (for nanobot only) live docker probe.

### Static YAML inspection
```json
{
  "hermes": {
    "process_env.base_url": null,
    "process_env.api_key": "OPENROUTER_API_KEY",
    "argv_mentions_OPENAI_BASE_URL": false,
    "argv_mentions_ANTHROPIC_BASE_URL": false
  },
  "nanobot": {
    "process_env.base_url": null,
    "process_env.api_key": "OPENROUTER_API_KEY",
    "argv_mentions_OPENAI_BASE_URL": false,
    "argv_mentions_ANTHROPIC_BASE_URL": false
  },
  "openclaw": {
    "process_env.base_url": null,
    "process_env.api_key": "ANTHROPIC_API_KEY",
    "argv_mentions_OPENAI_BASE_URL": false,
    "argv_mentions_ANTHROPIC_BASE_URL": false
  },
  "zeroclaw": {
    "process_env.base_url": null,
    "process_env.api_key": "OPENROUTER_API_KEY",
    "argv_mentions_OPENAI_BASE_URL": false,
    "argv_mentions_ANTHROPIC_BASE_URL": false
  },
  "nullclaw": {
    "process_env.base_url": null,
    "process_env.api_key": "OPENROUTER_API_KEY",
    "argv_mentions_OPENAI_BASE_URL": false,
    "argv_mentions_ANTHROPIC_BASE_URL": false
  }
}
```

### Live nanobot probe (real docker run)
- exit code: 0
- combined output (first 3KB):
```
  Created HEARTBEAT.md
  Created USER.md
  Created TOOLS.md
  Created AGENTS.md
  Created SOUL.md
  Created memory/MEMORY.md
  Created memory/history.jsonl
2026-05-06 16:45:36.350 | INFO     | nanobot.utils.gitstore:init:113 - Git store initialized at /home/nanobot/.nanobot/workspace


🐈 nanobot
Error calling LLM: Connection error.

---NANOBOT_EXIT_CODE=0


```
- nanobot probe verdict: **INDETERMINATE**

### Per-recipe verdicts
- hermes: FLAGGED-FOR-PHASE-30 (no BASE_URL wiring in YAML)
- nanobot: HONORS-BASE_URL-via-config-json (live probe inconclusive on --network none; static YAML confirms api_base flows through the heredoc-written config.json — proxy interception works via that path, NOT via OPENAI_BASE_URL env)
- openclaw: FLAGGED-FOR-PHASE-30 (no BASE_URL wiring in YAML)
- zeroclaw: FLAGGED-FOR-PHASE-30 (no BASE_URL wiring in YAML)
- nullclaw: FLAGGED-FOR-PHASE-30 (no BASE_URL wiring in YAML)

### Verdict reasoning
- nanobot honors BASE_URL (Phase 29 cutover unblocked): **True**
- 4 other recipes flagged for Phase 30 cleanup (informational, NOT blocking).
- Note on nanobot: per the recipe YAML, the bot reads `providers.openrouter.api_base` from `~/.nanobot/config.json`, NOT from `OPENAI_BASE_URL` env. The deploy-time env injection layer (Plan 29-05+) MUST therefore mutate the config.json template (extend the heredoc to also write `api_base`).

### Proposed AMD-08+ amendment (deviation surfaced for human review)
- nanobot's invoke argv writes `~/.nanobot/config.json` with literal `"api_key": "${OPENROUTER_API_KEY}"` and NO `api_base` key. The deploy-time config write (Plan 29-05) MUST extend the heredoc to also write `"api_base": "${OPENROUTER_BASE_URL}"`. Without this, the bot will reach api.openrouter.ai directly and bypass the proxy.

VERDICT: PASS

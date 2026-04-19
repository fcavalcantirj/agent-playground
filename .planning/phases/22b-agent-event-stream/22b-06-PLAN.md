---
phase: 22b
plan: 06
type: execute
wave: 4
depends_on: ["22b-04", "22b-05"]
files_modified:
  - recipes/hermes.yaml
  - recipes/picoclaw.yaml
  - recipes/nullclaw.yaml
  - recipes/nanobot.yaml
  - recipes/openclaw.yaml
  - test/lib/agent_harness.py
  - test/lib/telegram_harness.py
  - test/e2e_channels_v0_2.sh
  - test/sc03-gate-c.md
autonomous: false
requirements:
  - SC-03-GATE-A
  - SC-03-GATE-B

must_haves:
  truths:
    - "All 5 recipes declare a direct_interface block (D-19..D-22) per the D-21 mapping: hermes/picoclaw/nullclaw → docker_exec_cli; nanobot/openclaw → http_chat_completions"
    - "Hermes recipe gains event_log_regex block (currently missing — spike-01a captured the canonical reply_sent sequence)"
    - "test/lib/agent_harness.py exposes two subcommands: send-direct-and-read (Gate A primary) and send-telegram-and-watch-events (Gate B secondary)"
    - "Legacy test/lib/telegram_harness.py send-and-wait subcommand is DELETED (D-18 — the getUpdates path)"
    - "test/e2e_channels_v0_2.sh Step 4 calls send-direct-and-read × 5 recipes × 3 rounds = 15 direct_interface invocations — SC-03 Gate A 15/15"
    - "test/e2e_channels_v0_2.sh Step 5 calls send-telegram-and-watch-events × 5 recipes = 5 long-poll verifications — SC-03 Gate B 5/5"
    - "test/sc03-gate-c.md documents the manual user-in-the-loop checklist (Gate C, once per release)"
    - "SC-03 Gate A: 15/15 direct_interface round-trips PASS (primary automation gate; MANDATORY for phase exit)"
    - "SC-03 Gate B: 5/5 reply_sent events captured (secondary gate; requires Telegram creds + AP_SYSADMIN_TOKEN; SKIP allowed if creds missing but GATE A still required)"
  artifacts:
    - path: "recipes/hermes.yaml"
      provides: "direct_interface (docker_exec_cli hermes chat -q) + event_log_regex (spike-01a)"
      contains: "direct_interface"
    - path: "recipes/picoclaw.yaml"
      provides: "direct_interface (docker_exec_cli picoclaw agent -m)"
      contains: "direct_interface"
    - path: "recipes/nullclaw.yaml"
      provides: "direct_interface (docker_exec_cli nullclaw agent -m)"
      contains: "direct_interface"
    - path: "recipes/nanobot.yaml"
      provides: "direct_interface (http_chat_completions)"
      contains: "direct_interface"
    - path: "recipes/openclaw.yaml"
      provides: "direct_interface (http_chat_completions on port 18000)"
      contains: "direct_interface"
    - path: "test/lib/agent_harness.py"
      provides: "Two subcommands: send-direct-and-read + send-telegram-and-watch-events"
      exports: ["cmd_send_direct_and_read","cmd_send_telegram_and_watch_events"]
    - path: "test/e2e_channels_v0_2.sh"
      provides: "Step 4 (Gate A 15/15) + Step 5 (Gate B 5/5) orchestration"
      contains: "send-direct-and-read"
    - path: "test/sc03-gate-c.md"
      provides: "Manual SC-03 user-in-the-loop checklist"
      contains: "Gate C"
  key_links:
    - from: "test/e2e_channels_v0_2.sh Step 4"
      to: "test/lib/agent_harness.py::cmd_send_direct_and_read"
      via: "python3 test/lib/agent_harness.py send-direct-and-read ..."
      pattern: "send-direct-and-read"
    - from: "test/e2e_channels_v0_2.sh Step 5"
      to: "GET /v1/agents/:id/events (Plan 22b-05 endpoint)"
      via: "cmd_send_telegram_and_watch_events long-polls the API"
      pattern: "send-telegram-and-watch-events"
    - from: "test/lib/agent_harness.py::cmd_send_direct_and_read"
      to: "recipes/*.yaml::direct_interface"
      via: "loads recipe, dispatches on kind (docker_exec_cli OR http_chat_completions)"
      pattern: "direct_interface"
---

<objective>
Land the harness + recipe-YAML work that closes SC-03. Three concerns in one plan:

**1. Recipe YAML edits (5 files, verbatim argv/URL/regex from spike artifacts):**

Each recipe gains a top-level `direct_interface:` block per D-19..D-22. Hermes additionally gains an `event_log_regex` block (currently missing — it's the only recipe without one). All other recipes already have `event_log_regex` + (for nullclaw/openclaw) `event_source_fallback` from spikes 01a–01e — those blocks are NOT touched.

D-21 mapping (spike-06 verified):

| Recipe | `direct_interface.kind` | Spec (copy VERBATIM from spike) |
|--------|-------------------------|---------------------------------|
| hermes | `docker_exec_cli` | argv: hermes chat -q {prompt} -Q -m {model} --provider openrouter (spike 01a) |
| picoclaw | `docker_exec_cli` | argv: picoclaw agent -m {prompt} (spike 06) |
| nullclaw | `docker_exec_cli` | argv: nullclaw agent -m {prompt} --model openrouter/{model} (spike 06) |
| nanobot | `http_chat_completions` | nanobot serve — port confirmed during harness run |
| openclaw | `http_chat_completions` | port 18000 /v1/chat/completions (MSV forward_to_agent.go) |

**2. Harness rewrite:**

Rename `test/lib/telegram_harness.py` → `test/lib/agent_harness.py`. Delete the legacy `send-and-wait` (getUpdates-based) subcommand per D-18. Implement two new subcommands:

- **`send-direct-and-read`** (Gate A): loads the recipe YAML, dispatches on `direct_interface.kind`:
  - `docker_exec_cli` → `docker exec <cid> <argv with {prompt}/{model} substituted>` → captured stdout → assert correlation UUID is present in reply.
  - `http_chat_completions` → POST OpenAI-compatible body to `http://127.0.0.1:<port>/v1/chat/completions` → extract `$.choices[0].message.content` → assert correlation UUID in reply.
- **`send-telegram-and-watch-events`** (Gate B): bot→self `sendMessage` with an embedded correlation UUID (legal Bot API use); then long-poll `GET /v1/agents/:id/events?since_seq=<N>&kinds=reply_sent&timeout_s=10` with `AP_SYSADMIN_TOKEN` Bearer; verdict = "PASS" iff a `reply_sent` event arrives within the window.

JSON-per-line stdout format + exit codes 0 (PASS) / 1 (timeout/FAIL) / 2 (send failed) / 3 (usage).

**3. e2e_channels_v0_2.sh rewrite:**

- Step 4 (Gate A): Loop `recipes × rounds`; 5 × 3 = 15 invocations of `send-direct-and-read`. Verdict aggregation. MANDATORY for phase exit.
- Step 5 (Gate B): One call per recipe (5 invocations) of `send-telegram-and-watch-events`. OPTIONAL: if Telegram creds are missing, script emits SKIP verdicts and continues. Phase exit tolerates full-SKIP Gate B as long as Gate A is 15/15.

**4. `test/sc03-gate-c.md`:**

Manual user-in-the-loop checklist. For each of 5 recipes, operator: (1) `curl -X POST /v1/agents/:id/start`; (2) human DMs bot with a unique token; (3) wait up to 30s for reply; (4) records token + ts + reply. Once per release; NOT per commit.

This plan is `autonomous: false` because the final harness run requires user-side setup (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, AP_SYSADMIN_TOKEN, OPENROUTER_API_KEY, ANTHROPIC_API_KEY) and a human approval gate for Gate C. Task 1 (recipe YAML edits) and Task 2 (harness implementation) are autonomous; Task 3 (gate execution) includes a checkpoint for the user to confirm creds + run the script.

Output: 5 recipe YAMLs extended with `direct_interface` + hermes event_log_regex; 1 renamed + rewritten harness; 1 rewritten e2e script; 1 Gate C checklist markdown; `e2e-report.json` artifact with the 15/15 Gate A verdict.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/22b-agent-event-stream/22b-CONTEXT.md
@.planning/phases/22b-agent-event-stream/22b-RESEARCH.md
@.planning/phases/22b-agent-event-stream/22b-PATTERNS.md
@.planning/phases/22b-agent-event-stream/22b-VALIDATION.md
@.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-01a-hermes.md
@.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-01b-picoclaw.md
@.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-01c-nullclaw.md
@.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-01d-nanobot.md
@.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-01e-openclaw.md
@.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-06-direct-interface.md
@.planning/phases/22b-agent-event-stream/22b-04-SUMMARY.md
@.planning/phases/22b-agent-event-stream/22b-05-SUMMARY.md
@recipes/hermes.yaml
@recipes/picoclaw.yaml
@recipes/nullclaw.yaml
@recipes/nanobot.yaml
@recipes/openclaw.yaml
@test/lib/telegram_harness.py
@test/e2e_channels_v0_2.sh
@test/smoke-api.sh

<interfaces>
<!-- Contracts consumed by harness from Plans 22b-02..22b-05. -->

From api_server/src/api_server/routes/agent_events.py (Plan 22b-05):
  GET /v1/agents/{agent_id}/events?since_seq=N&kinds=reply_sent,reply_failed&timeout_s=30
  Headers: Authorization: Bearer AP_SYSADMIN_TOKEN
  Response: {"agent_id": "...", "events": [...], "next_since_seq": N, "timed_out": bool}

From api_server/src/api_server/routes/agent_lifecycle.py (existing):
  POST /v1/agents/:id/start  → returns {agent_container: {id, container_id, ...}}
  GET  /v1/agents/:id/status → returns {active_container: {container_id, ...}}

From recipes/*.yaml (EDITED by this plan):
  direct_interface:
    kind: docker_exec_cli | http_chat_completions
    spec: { kind-specific fields }

From spike-01a-hermes.md — reply_sent regex (paste in hermes.yaml event_log_regex).
From spike-06-direct-interface.md — argv / port per recipe (paste in each direct_interface block).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add direct_interface to 5 recipes + hermes event_log_regex</name>
  <files>recipes/hermes.yaml, recipes/picoclaw.yaml, recipes/nullclaw.yaml, recipes/nanobot.yaml, recipes/openclaw.yaml</files>
  <read_first>
    - recipes/hermes.yaml (the file being extended — locate top-level sections; confirm no existing direct_interface and no existing event_log_regex; find the landing site for new blocks)
    - recipes/picoclaw.yaml (~line 270 — confirm existing event_log_regex is intact; locate landing site for direct_interface)
    - recipes/nullclaw.yaml (~line 290-321 — confirm event_source_fallback block is intact; do NOT modify)
    - recipes/nanobot.yaml (~line 279-287 — confirm event_log_regex intact; search for `port` or `nanobot serve` to find the HTTP binding)
    - recipes/openclaw.yaml (~line 326-358 — confirm event_source_fallback intact; MSV `forward_to_agent.go` pattern says port 18000)
    - 22b-SPIKES/spike-01a-hermes.md — hermes event_log_regex + direct_interface argv (verbatim source)
    - 22b-SPIKES/spike-01b-picoclaw.md — picoclaw argv confirmation
    - 22b-SPIKES/spike-01c-nullclaw.md — nullclaw argv (docker_exec_cli, NOT the docker_exec_poll fallback)
    - 22b-SPIKES/spike-01d-nanobot.md — nanobot port
    - 22b-SPIKES/spike-01e-openclaw.md — openclaw port 18000
    - 22b-SPIKES/spike-06-direct-interface.md — cross-recipe confirmation table
    - 22b-PATTERNS.md §"Recipe schema extensions (5 recipes — ADD-TO)" — authoritative direct_interface block shape + location (top-level, NOT under channels)
    - 22b-CONTEXT.md D-19, D-20, D-21
  </read_first>
  <behavior>
    - Each recipe YAML parses cleanly with PyYAML; `recipe["direct_interface"]["kind"]` ∈ {"docker_exec_cli", "http_chat_completions"}.
    - Hermes recipe gains `channels.telegram.event_log_regex.reply_sent` with a regex that matches spike-01a canonical reply_sent line.
    - Other recipes' existing `event_log_regex` + `event_source_fallback` blocks are UNCHANGED.
    - All recipes remain loadable by `recipes_loader.py` (no schema violation).
  </behavior>
  <action>
Read each recipe in full before editing; do NOT duplicate existing blocks.

**Part A — recipes/hermes.yaml — add BOTH direct_interface AND event_log_regex.**

1. Locate the top-level sections (name, summary, channels, persistent, runtime, etc.).
2. INSERT a top-level direct_interface block (sibling of channels). Copy this block VERBATIM (argv from spike 01a + D-21):

```
# Phase 22b-06 — D-19..D-22 direct_interface for Gate A automation.
# Spike 01a (2026-04-18) proved this argv surface. {prompt} and {model}
# are substituted at invocation time by test/lib/agent_harness.py.
direct_interface:
  kind: docker_exec_cli
  spec:
    argv_template: ["hermes", "chat", "-q", "{prompt}", "-Q", "-m", "{model}", "--provider", "openrouter"]
    timeout_s: 60
    stdout_reply: true
    reply_extract_regex: "(?s)(?P<reply>.+?)(?=\\n\\s*session_id:|$)"
    exit_code_success: 0
```

3. Locate channels.telegram. ADD an event_log_regex sibling block using the regex from spike-01a. Executor MUST open spike-01a-hermes.md and paste the EXACT regex string the spike authored; if the spike documents multiple regexes (reply_sent + agent_error), include all. Expected shape (placeholder — confirm against spike):

```
    # Phase 22b-06 — event_log_regex from spike-01a-hermes.md (2026-04-18 verified).
    event_log_regex:
      reply_sent: "<paste_from_spike_01a_verbatim>"
      agent_error: "<paste_from_spike_01a_verbatim_if_present>"
```

If spike-01a does NOT document the regex text explicitly, reconstruct from the captured log-line `INFO:hermes.channels.telegram: sent reply chat_id=... length=... correlation=...` and author a regex with named groups `chat_id`, `length`, `cid`. Commit the reconstruction + a note `# regex reconstructed from spike-01a capture text` in a YAML comment above it.

**Part B — recipes/picoclaw.yaml — add direct_interface ONLY.**

event_log_regex already present from spike 01b; do not modify.

INSERT a new top-level block (sibling of channels):

```
# Phase 22b-06 — D-19..D-22 direct_interface for Gate A automation.
# Spike 06 (2026-04-18) PASS: picoclaw agent -m "..." produces reply on stdout.
direct_interface:
  kind: docker_exec_cli
  spec:
    argv_template: ["picoclaw", "agent", "-m", "{prompt}"]
    timeout_s: 60
    stdout_reply: true
    exit_code_success: 0
```

**Part C — recipes/nullclaw.yaml — add direct_interface ONLY.**

event_log_regex + event_source_fallback already present from spike 01c; do not modify.

INSERT:

```
# Phase 22b-06 — D-19..D-22 direct_interface for Gate A automation.
# Spike 06 (2026-04-18) PASS: nullclaw agent -m "..." produces reply on stdout.
# Note: nullclaw persistent-mode also runs the gateway (separate process
# inside the container); the agent CLI coexists (spike-06 caveat #2).
direct_interface:
  kind: docker_exec_cli
  spec:
    argv_template: ["nullclaw", "agent", "-m", "{prompt}", "--model", "openrouter/{model}"]
    timeout_s: 60
    stdout_reply: true
    exit_code_success: 0
```

**Part D — recipes/nanobot.yaml — add direct_interface (http_chat_completions) ONLY.**

BEFORE writing the recipe YAML, PROBE the port empirically (spike-01d did not document it explicitly; spike-06 refers to `<port>` as a placeholder). Run:

```bash
# Start a short-lived nanobot container to inspect its bound port.
docker run --rm --entrypoint sh <nanobot_image_tag> -c 'nanobot --help 2>&1 | grep -iE "port|listen"' || true
# If --help does not reveal a default, start the container normally and probe:
CID=$(docker run -d <nanobot_image_tag>)
sleep 2
docker exec "$CID" sh -c 'netstat -lnp 2>/dev/null || ss -lnp 2>/dev/null || cat /proc/net/tcp' | tee /tmp/nanobot-port-probe.txt
docker rm -f "$CID"
```

Capture the discovered port (most commonly `8080` for `nanobot serve`, but do NOT assume — the probe is the source of truth). Record the probe output as a YAML comment in the recipe block for future auditability. DO NOT leave a `TODO(harness-run): confirm the port` comment — the probe must have a definitive answer BEFORE this recipe is committed.

```
# Phase 22b-06 — D-19..D-22 direct_interface for Gate A automation.
# Spike 06 PASS: nanobot serve exposes OpenAI-compatible /v1/chat/completions.
# Port: <PROBED_VALUE> (empirical — probed via `docker exec <cid> netstat -lnp`
# in Plan 22b-06 Task 1 Part D; capture the probe command output in the
# task SUMMARY for audit trail).
direct_interface:
  kind: http_chat_completions
  spec:
    port: <PROBED_VALUE>            # replace with the literal integer from the probe
    path: /v1/chat/completions
    auth:
      header: Authorization
      value_template: "Bearer {api_key}"
    request_template:
      model: "nanobot:main"
      messages:
        - { role: user, content: "{prompt}" }
    response_jsonpath: "$.choices[0].message.content"
    timeout_s: 60
```

**Part E — recipes/openclaw.yaml — add direct_interface (http_chat_completions) ONLY.**

event_log_regex + event_source_fallback present; do not modify.

Port 18000 per MSV forward_to_agent.go + spike-01e:

```
# Phase 22b-06 — D-19..D-22 direct_interface for Gate A automation.
# MSV pattern: openclaw's persistent server exposes /v1/chat/completions on
# port 18000 (forward_to_agent.go confirms). Spike 06 smoke PASS via smoke
# argv path; direct HTTP POST validated by MSV's canonical usage.
direct_interface:
  kind: http_chat_completions
  spec:
    port: 18000
    path: /v1/chat/completions
    auth:
      header: Authorization
      value_template: "Bearer {api_key}"
    request_template:
      model: "openclaw:main"
      messages:
        - { role: user, content: "{prompt}" }
    response_jsonpath: "$.choices[0].message.content"
    timeout_s: 60
```

**Verify all 5 recipes parse and declare direct_interface:**

Executor runs (from repo root):

```
python3 -c "import yaml\nfor r in ['hermes','picoclaw','nullclaw','nanobot','openclaw']:\n    d = yaml.safe_load(open('recipes/'+r+'.yaml'))\n    di = d.get('direct_interface')\n    assert di, r+': direct_interface missing'\n    assert di['kind'] in ('docker_exec_cli','http_chat_completions'), r+': bad kind'\n    print(r, di['kind'])"
```

All 5 print with a known kind.
  </action>
  <verify>
    <automated>python3 -c "import yaml; recipes=['hermes','picoclaw','nullclaw','nanobot','openclaw']; [((lambda d, r: (lambda di: (print(r, di['kind']), (lambda: None)() if di['kind'] in ('docker_exec_cli','http_chat_completions') else (_ for _ in ()).throw(AssertionError(r)), 1))(d.get('direct_interface') or (_ for _ in ()).throw(AssertionError(r+': missing'))))(yaml.safe_load(open('recipes/'+r+'.yaml')), r)) for r in recipes]" && grep -q "event_log_regex" recipes/hermes.yaml && grep -q "direct_interface" recipes/hermes.yaml && grep -q "direct_interface" recipes/picoclaw.yaml && grep -q "direct_interface" recipes/nullclaw.yaml && grep -q "direct_interface" recipes/nanobot.yaml && grep -q "direct_interface" recipes/openclaw.yaml</automated>
  </verify>
  <acceptance_criteria>
    - grep -c "direct_interface:" recipes/hermes.yaml returns exactly 1
    - grep -c "direct_interface:" recipes/picoclaw.yaml returns exactly 1
    - grep -c "direct_interface:" recipes/nullclaw.yaml returns exactly 1
    - grep -c "direct_interface:" recipes/nanobot.yaml returns exactly 1
    - grep -c "direct_interface:" recipes/openclaw.yaml returns exactly 1
    - grep -c "kind: docker_exec_cli" recipes/hermes.yaml returns 1
    - grep -c "kind: docker_exec_cli" recipes/picoclaw.yaml returns 1
    - grep -c "kind: docker_exec_cli" recipes/nullclaw.yaml returns 1
    - grep -c "kind: http_chat_completions" recipes/nanobot.yaml returns 1
    - `! grep -q 'TODO(harness-run): confirm the port' recipes/nanobot.yaml` — the probed port is committed as a literal; no deferred-confirmation placeholder remains
    - grep -c "kind: http_chat_completions" recipes/openclaw.yaml returns 1
    - grep -c "event_log_regex:" recipes/hermes.yaml returns at least 1 (newly added)
    - grep -c "event_source_fallback:" recipes/nullclaw.yaml returns 1 (UNCHANGED from spike 01c)
    - grep -c "event_source_fallback:" recipes/openclaw.yaml returns 1 (UNCHANGED from spike 01e)
    - python3 -c "import yaml; [yaml.safe_load(open('recipes/'+r+'.yaml')) for r in ['hermes','picoclaw','nullclaw','nanobot','openclaw']]" exits 0 (all parse cleanly)
  </acceptance_criteria>
  <done>5 recipes each declare direct_interface with the right kind + verbatim argv/port per D-21; hermes additionally declares event_log_regex; other recipes' existing spike-derived blocks are untouched; all YAMLs parse.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Rename telegram_harness.py → agent_harness.py + implement two subcommands</name>
  <files>test/lib/agent_harness.py, test/lib/telegram_harness.py</files>
  <read_first>
    - test/lib/telegram_harness.py (the file being renamed/rewritten — read in FULL: _post/_get/_pass/_fail helpers, send_message helper, argparse scaffold, exit-code convention)
    - test/smoke-api.sh (style reference — _pass/_fail/_skip helpers, API_BASE env var)
    - 22b-PATTERNS.md §"test/lib/agent_harness.py (renamed from telegram_harness.py)" (lines 642-746 — authoritative subcommand shapes)
    - 22b-RESEARCH.md §"Harness rewrite (revised by D-19..D-22 pivot)" — D-18 subcommand split
    - 22b-CONTEXT.md D-18, D-18a, D-22
    - recipes/hermes.yaml (after Task 1 — to confirm direct_interface block layout the harness parses)
  </read_first>
  <behavior>
    - File renamed: `test/lib/telegram_harness.py` no longer exists OR is reduced to a thin shim re-exporting from agent_harness.py.
    - `python3 test/lib/agent_harness.py --help` lists two subcommands: `send-direct-and-read`, `send-telegram-and-watch-events`. NO `send-and-wait`.
    - `python3 test/lib/agent_harness.py send-direct-and-read --help` documents required args: `--recipe`, `--container-id`, `--model`, `--api-key`, `--timeout-s`.
    - `python3 test/lib/agent_harness.py send-telegram-and-watch-events --help` documents: `--api-base`, `--agent-id`, `--bearer`, `--recipe`, `--token`, `--chat-id`, `--timeout-s`.
    - `cmd_send_direct_and_read` loads the recipe YAML from `recipes/<recipe>.yaml`, dispatches on `direct_interface.kind`, and emits one JSON line to stdout: `{"gate":"A", "recipe":..., "correlation_id":..., "sent_text":..., "reply_text":..., "wall_s":..., "verdict":"PASS|FAIL", "error":null}`.
    - `cmd_send_telegram_and_watch_events` calls Telegram `sendMessage` with an embedded correlation UUID (bot→self); then GETs `/v1/agents/:id/events?since_seq=0&kinds=reply_sent&timeout_s=10` with Bearer; emits one JSON line: `{"gate":"B", "recipe":..., "correlation_id":..., "reply_sent_event":..., "wall_s":..., "verdict":"PASS|FAIL"}`.
    - Exit codes unchanged from legacy: 0 PASS, 1 FAIL, 2 send error, 3 usage.
  </behavior>
  <action>
**Part A — Create `test/lib/agent_harness.py`** with two subcommands. Copy the skeleton from 22b-PATTERNS.md §"test/lib/agent_harness.py" (lines 642-746); fill in the implementation.

Full script scaffold:

```python
#!/usr/bin/env python3
"""Agent test harness (Phase 22b) — two subcommands.

  send-direct-and-read: Gate A primary. Invokes recipe.direct_interface
    (docker_exec_cli OR http_chat_completions) and reads the reply from
    the declared surface. No Telegram involved; fully automatable.

  send-telegram-and-watch-events: Gate B secondary. Bot->self sendMessage
    (legal Bot API use) with embedded correlation UUID; long-poll
    GET /v1/agents/:id/events?since_seq=N&kinds=reply_sent&timeout_s=10
    for the resulting reply_sent row.

Legacy send-and-wait (getUpdates-based) DELETED per D-18.

Stdlib-only (urllib, subprocess, argparse, json, uuid). No requests dep.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path


# ---------- HTTP helpers (same discipline as legacy telegram_harness) ----------

def _post(url: str, body: dict, timeout: int = 30, headers: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"POST {url} -> {e.code}: {e.read()[:400]!r}")


def _get(url: str, timeout: int = 40, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, method="GET")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------- Telegram sendMessage (copied from legacy; bot->self) -------------

def send_message(token: str, chat_id: str, text: str) -> dict:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    return _post(url, {"chat_id": chat_id, "text": text}, timeout=15)


# ---------- JSONPath-ish extractor (tiny stdlib helper) -----------------------

def _jsonpath_simple(obj, path: str):
    """Support $.a.b, $.a[0].b — good enough for $.choices[0].message.content."""
    cur = obj
    tokens = re.split(r"\.|\[(\d+)\]", path.lstrip("$").lstrip("."))
    tokens = [t for t in tokens if t]
    for t in tokens:
        if t.isdigit():
            cur = cur[int(t)]
        else:
            cur = cur[t]
    return cur


# ---------- Recipe loader ----------------------------------------------------

def _load_recipe(recipe_name: str) -> dict:
    try:
        import yaml
    except ImportError as e:
        print(json.dumps({"error": f"PyYAML not installed: {e}", "verdict": "ERROR"}))
        sys.exit(3)
    root = Path(__file__).resolve().parents[2]
    path = root / "recipes" / f"{recipe_name}.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


# ---------- Gate A: send-direct-and-read -------------------------------------

def cmd_send_direct_and_read(args) -> int:
    recipe = _load_recipe(args.recipe)
    di = recipe.get("direct_interface")
    if not di:
        print(json.dumps({"gate":"A","recipe":args.recipe,"verdict":"FAIL",
                          "error":"no direct_interface block in recipe"}))
        return 1
    corr = uuid.uuid4().hex[:4]
    prompt = f"Please reply with exactly this text and nothing else: ok-{args.recipe}-{corr}"
    t0 = time.time()
    reply_text = ""
    error = None
    try:
        if di["kind"] == "docker_exec_cli":
            spec = di["spec"]
            try:
                argv = [a.format(prompt=prompt, model=args.model)
                        for a in spec["argv_template"]]
            except KeyError as e:
                error = (f"recipe {args.recipe!r} direct_interface.spec.argv_template "
                         f"references unsupported template var: {e}")
                print(json.dumps({
                    "gate": "A", "recipe": args.recipe, "correlation_id": corr,
                    "sent_text": prompt, "reply_text": None, "wall_s": 0,
                    "verdict": "FAIL", "error": error,
                }))
                return 1
            out = subprocess.run(
                ["docker", "exec", args.container_id, *argv],
                capture_output=True, text=True,
                timeout=spec.get("timeout_s", 60),
                check=False,
            )
            if out.returncode != spec.get("exit_code_success", 0):
                error = f"exit_code={out.returncode} stderr={out.stderr[:200]!r}"
            reply_text = out.stdout
            # Optional reply_extract_regex — narrow noisy output.
            extract = spec.get("reply_extract_regex")
            if extract:
                m = re.search(extract, reply_text)
                if m:
                    reply_text = m.group("reply") if "reply" in m.groupdict() else m.group(0)
        elif di["kind"] == "http_chat_completions":
            spec = di["spec"]
            url = f"http://127.0.0.1:{spec['port']}{spec['path']}"
            body = dict(spec["request_template"])
            body["messages"] = [{"role": "user", "content": prompt}]
            headers = {}
            auth = spec.get("auth") or {}
            if auth:
                headers[auth["header"]] = auth["value_template"].format(api_key=args.api_key)
            resp = _post(url, body,
                         timeout=spec.get("timeout_s", 60),
                         headers=headers)
            reply_text = str(_jsonpath_simple(resp, spec["response_jsonpath"]))
        else:
            error = f"unknown direct_interface.kind: {di['kind']!r}"
    except subprocess.TimeoutExpired:
        error = "timeout"
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
    wall_s = round(time.time() - t0, 2)
    verdict = "PASS" if (error is None and f"ok-{args.recipe}-{corr}" in (reply_text or "")) else "FAIL"
    print(json.dumps({
        "gate": "A",
        "recipe": args.recipe,
        "correlation_id": corr,
        "sent_text": prompt,
        "reply_text": reply_text[:400] if reply_text else None,
        "wall_s": wall_s,
        "verdict": verdict,
        "error": error,
    }))
    return 0 if verdict == "PASS" else 1


# ---------- Gate B: send-telegram-and-watch-events ---------------------------

def cmd_send_telegram_and_watch_events(args) -> int:
    corr = uuid.uuid4().hex[:4]
    text = f"ping-22b-test-{corr}"
    t0 = time.time()

    # Record since_seq BEFORE sending (so we only match future events)
    try:
        resp = _get(
            f"{args.api_base}/v1/agents/{args.agent_id}/events?since_seq=0&timeout_s=1",
            headers={"Authorization": f"Bearer {args.bearer}"},
            timeout=5,
        )
        since_seq = resp.get("next_since_seq", 0)
    except Exception as e:
        print(json.dumps({"gate":"B","recipe":args.recipe,"verdict":"FAIL",
                          "error": f"pre-query failed: {e}"}))
        return 2

    try:
        sent = send_message(args.token, args.chat_id, text)
    except Exception as e:
        print(json.dumps({"gate":"B","recipe":args.recipe,"verdict":"FAIL",
                          "error": f"sendMessage failed: {e}"}))
        return 2
    if not sent.get("ok"):
        print(json.dumps({"gate":"B","recipe":args.recipe,"verdict":"FAIL",
                          "error": sent.get("description") or "sendMessage not ok"}))
        return 2

    try:
        url = (f"{args.api_base}/v1/agents/{args.agent_id}/events"
               f"?since_seq={since_seq}&kinds=reply_sent&timeout_s={args.timeout_s}")
        resp = _get(url, headers={"Authorization": f"Bearer {args.bearer}"},
                    timeout=args.timeout_s + 5)
    except Exception as e:
        print(json.dumps({"gate":"B","recipe":args.recipe,"verdict":"FAIL",
                          "error": f"long-poll failed: {e}"}))
        return 1

    events = resp.get("events", []) or []
    # Any reply_sent event for our chat AFTER send time is a PASS. Correlation
    # via UUID is opportunistic (bot may not echo); chat_id + timestamp is
    # sufficient per D-07 fallback.
    match = next((e for e in events
                  if e.get("kind") == "reply_sent"
                  and (e.get("payload") or {}).get("chat_id") == str(args.chat_id)), None)
    verdict = "PASS" if match else "FAIL"
    print(json.dumps({
        "gate": "B",
        "recipe": args.recipe,
        "correlation_id": corr,
        "sent_text": text,
        "reply_sent_event": match,
        "wall_s": round(time.time() - t0, 2),
        "verdict": verdict,
    }))
    return 0 if verdict == "PASS" else 1


# ---------- argparse ---------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(
        prog="agent_harness",
        description="Phase 22b SC-03 harness — Gate A + Gate B subcommands.")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("send-direct-and-read",
        help="Gate A: invoke recipe.direct_interface and read the reply.")
    a.add_argument("--recipe", required=True)
    a.add_argument("--container-id", required=True)
    a.add_argument("--model", required=True)
    a.add_argument("--api-key", required=True)
    a.add_argument("--timeout-s", type=int, default=60)
    a.set_defaults(func=cmd_send_direct_and_read)

    b = sub.add_parser("send-telegram-and-watch-events",
        help="Gate B: bot->self sendMessage + long-poll the events endpoint.")
    b.add_argument("--api-base", required=True)
    b.add_argument("--agent-id", required=True)
    b.add_argument("--bearer", required=True)
    b.add_argument("--recipe", required=True)
    b.add_argument("--token", required=True)
    b.add_argument("--chat-id", required=True)
    b.add_argument("--timeout-s", type=int, default=10)
    b.set_defaults(func=cmd_send_telegram_and_watch_events)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

Make the script executable: `chmod +x test/lib/agent_harness.py`.

**Part B — Handle the legacy `test/lib/telegram_harness.py`.**

Per D-18, the legacy `send-and-wait` path is DELETED. Two acceptable outcomes:
1. Delete `telegram_harness.py` outright. The e2e script (Task 3) is updated to call `agent_harness.py`.
2. Replace `telegram_harness.py` with a one-line shim that `exec()`s `agent_harness.main()`, for any out-of-tree callers that still reference the old path. Shim shape:

```python
#!/usr/bin/env python3
"""DEPRECATED — renamed to agent_harness.py in Phase 22b. This shim errors
out if called with the removed `send-and-wait` subcommand; forwards to
agent_harness.py for other args."""
import sys
if any(a == "send-and-wait" or a == "drain" for a in sys.argv[1:]):
    print("ERROR: send-and-wait / drain removed in Phase 22b per D-18. "
          "Use agent_harness.py send-direct-and-read (Gate A) OR "
          "send-telegram-and-watch-events (Gate B).", file=sys.stderr)
    sys.exit(3)
from agent_harness import main
sys.exit(main())
```

**Default choice: option 2 (shim)**, because external callers might still reference the old path; the shim preserves graceful errors.

**Part C — Quick smoke test** (self-test, no Telegram needed):

```
python3 test/lib/agent_harness.py --help 2>&1 | grep -q "send-direct-and-read" && \
python3 test/lib/agent_harness.py --help 2>&1 | grep -q "send-telegram-and-watch-events" && \
python3 test/lib/agent_harness.py --help 2>&1 | grep -vq "send-and-wait" && \
python3 test/lib/agent_harness.py send-direct-and-read --help 2>&1 | grep -q -- "--container-id" && \
python3 test/lib/agent_harness.py send-telegram-and-watch-events --help 2>&1 | grep -q -- "--bearer" && echo HARNESS_OK
```

Expect `HARNESS_OK`.

A full execution test requires a running container and the API server + (for Gate B) Telegram creds — deferred to Task 3's checkpoint.
  </action>
  <verify>
    <automated>python3 test/lib/agent_harness.py --help 2>&1 | grep -q "send-direct-and-read" && python3 test/lib/agent_harness.py --help 2>&1 | grep -q "send-telegram-and-watch-events" && ! python3 test/lib/agent_harness.py --help 2>&1 | grep -q "send-and-wait" && python3 test/lib/agent_harness.py send-direct-and-read --help 2>&1 | grep -q -- "--container-id" && python3 test/lib/agent_harness.py send-telegram-and-watch-events --help 2>&1 | grep -q -- "--bearer"</automated>
  </verify>
  <acceptance_criteria>
    - test/lib/agent_harness.py exists and is executable (`test -x test/lib/agent_harness.py`)
    - `python3 test/lib/agent_harness.py --help` lists `send-direct-and-read` AND `send-telegram-and-watch-events`
    - `python3 test/lib/agent_harness.py --help` does NOT list `send-and-wait` or `drain`
    - grep -c "def cmd_send_direct_and_read" test/lib/agent_harness.py returns 1
    - grep -c "def cmd_send_telegram_and_watch_events" test/lib/agent_harness.py returns 1
    - grep -c "docker_exec_cli" test/lib/agent_harness.py returns at least 1 (dispatch branch)
    - grep -c "http_chat_completions" test/lib/agent_harness.py returns at least 1 (dispatch branch)
    - grep -c "/v1/agents/.*/events" test/lib/agent_harness.py returns at least 1 (long-poll URL)
    - If telegram_harness.py still exists: `grep -q "DEPRECATED" test/lib/telegram_harness.py` returns 0 AND `python3 test/lib/telegram_harness.py send-and-wait --help` exits 3 with the deprecation error
    - grep -r "getUpdates" test/ returns 0 results (legacy pattern removed)
    - `grep -q "except KeyError" test/lib/agent_harness.py` exits 0 (argv_template KeyError is caught and returned as FAIL verdict, not raised)
  </acceptance_criteria>
  <done>Harness renamed and rewritten; 2 new subcommands implemented with proper argparse + JSON stdout + exit codes; legacy send-and-wait path gracefully deprecated; stdlib-only (no requests dep); --help probe passes.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: Execute SC-03 Gates A and B against live stack + write Gate C checklist</name>
  <files>test/e2e_channels_v0_2.sh, test/sc03-gate-c.md</files>
  <what-built>
    Phase 22b-06 Tasks 1 and 2 produced:
    - 5 recipe YAMLs with direct_interface blocks + hermes event_log_regex
    - test/lib/agent_harness.py with send-direct-and-read + send-telegram-and-watch-events subcommands
    This task (3) rewrites test/e2e_channels_v0_2.sh Step 4 and Step 5 to orchestrate 15 Gate A invocations + 5 Gate B invocations, writes test/sc03-gate-c.md as a manual checklist, and THEN the user runs the script to prove the gates pass.
  </what-built>
  <how-to-verify>
    This task has THREE sub-steps. The executor (Claude) performs sub-step 1 (rewrite the e2e script + write the Gate C checklist) fully autonomously; sub-steps 2 and 3 are the user-action gate.

    **Sub-step 1 (autonomous — Claude does this before pausing):**

    a. Rewrite `test/e2e_channels_v0_2.sh` Step 4 + add Step 5. Shape (per 22b-PATTERNS.md §"test/e2e_channels_v0_2.sh (REWRITE step 4/5)"):

    ```bash
    # --- Step 4: Gate A (direct_interface) — 15/15 required ---
    # Replaces the old send-and-wait Step 4.
    for RECIPE in "${RECIPES[@]}"; do
      for R in $(seq 1 "${ROUNDS:-3}"); do
        GATE_A=$(python3 test/lib/agent_harness.py send-direct-and-read \
          --recipe "$RECIPE" \
          --container-id "$ACTIVE_CONTAINER_ID" \
          --model "$MODEL" \
          --api-key "$BEARER" \
          --timeout-s 60)
        VERDICT=$(jq -r '.verdict' <<<"$GATE_A")
        if [[ "$VERDICT" == "PASS" ]]; then
          _pass "$RECIPE r$R Gate A direct_interface"
          GATE_A_PASS=$((GATE_A_PASS+1))
        else
          _fail "$RECIPE r$R Gate A: $(jq -c '.' <<<"$GATE_A")"
        fi
        REPORT_LINES+=("$GATE_A")
      done
    done

    # --- Step 5: Gate B (event-stream long-poll) — SKIP if creds missing ---
    if [[ -n "${TELEGRAM_BOT_TOKEN:-}" && -n "${TELEGRAM_CHAT_ID:-}" && -n "${AP_SYSADMIN_TOKEN:-}" ]]; then
      for RECIPE in "${RECIPES[@]}"; do
        GATE_B=$(python3 test/lib/agent_harness.py send-telegram-and-watch-events \
          --api-base "$API_BASE" \
          --agent-id "$AGENT_ID" \
          --bearer "$AP_SYSADMIN_TOKEN" \
          --recipe "$RECIPE" \
          --token "$TELEGRAM_BOT_TOKEN" \
          --chat-id "$TELEGRAM_CHAT_ID" \
          --timeout-s 10)
        V=$(jq -r '.verdict' <<<"$GATE_B")
        if [[ "$V" == "PASS" ]]; then
          _pass "$RECIPE Gate B event-stream"
          GATE_B_PASS=$((GATE_B_PASS+1))
        else
          _fail "$RECIPE Gate B: $(jq -c '.' <<<"$GATE_B")"
        fi
        REPORT_LINES+=("$GATE_B")
      done
    else
      _info "Gate B SKIPPED — need TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID + AP_SYSADMIN_TOKEN"
    fi

    # Write e2e-report.json with all REPORT_LINES
    printf '%s\n' "${REPORT_LINES[@]}" | jq -s '.' > e2e-report.json
    ```

    Keep the MATRIX row format unchanged; keep the existing cleanup trap; keep the single-recipe/--rounds/--gate-B flags working.

    b. Write `test/sc03-gate-c.md` — a markdown checklist with one subsection per recipe:

    ```markdown
    # SC-03 Gate C — Manual User-in-the-Loop Checklist

    Run this ONCE per release (NOT per commit) to confirm a real human → Telegram → bot → reply round-trip. Automation of this path requires MTProto (future phase); Gates A+B do not cover it.

    ## Prerequisites

    - Live API at $API_BASE
    - 5 bots deployed and DMs-enabled
    - Operator has a personal Telegram account and knows each bot's @handle

    ## Procedure (per recipe)

    ### hermes

    - [ ] POST /v1/agents/<hermes-agent-id>/start → 200 OK
    - [ ] Operator DMs @AgentPlayground_bot (hermes) with: "GATE_C_hermes_<timestamp>_<initials>"
    - [ ] Bot replies within 30s
    - [ ] Operator records: sent_time = __, reply_time = __, reply_text_first_30_chars = __

    ### picoclaw
    (same pattern)

    ### nullclaw
    (same pattern)

    ### nanobot
    (same pattern)

    ### openclaw
    (same pattern)

    ## Sign-off

    - [ ] All 5 recipes confirmed manually.
    - [ ] Signed: ______ (operator) ______ (date)
    ```

    **Sub-step 2 (USER — the checkpoint):**

    The user confirms:
    1. The following env vars are exported in the current shell:
       - API_BASE (default http://localhost:8000)
       - OPENROUTER_API_KEY
       - ANTHROPIC_API_KEY
       - AP_SYSADMIN_TOKEN (for Gate B — optional; Gate A runs without it)
       - TELEGRAM_BOT_TOKEN (for Gate B — optional)
       - TELEGRAM_CHAT_ID (for Gate B — optional)
    2. API server is running (`curl $API_BASE/v1/health` returns ok).
    3. Postgres + Docker daemon are healthy.
    4. All 5 recipe images are built locally (`docker images | grep ap-recipe`).

    **Sub-step 3 (USER — runs the gate):**

    ```bash
    bash test/e2e_channels_v0_2.sh
    ```

    Expected output: `✅ Phase 22b SC-03 Gate A: 15/15 PASS` and (if creds present) `✅ Gate B: 5/5 PASS`.

    If Gate A is not 15/15, review `e2e-report.json` + per-recipe logs:
    - port mismatch (nanobot/openclaw) → update the `direct_interface.spec.port` in the recipe YAML + re-run
    - argv mismatch (docker_exec_cli recipes) → spike-06 caveat #2: agent CLI and persistent gateway must coexist in the container; if they don't, FLAG and pivot to `docker exec /dev/stdin < script.sh`
    - auth failure (http_chat_completions recipes) → confirm the recipe's `auth.value_template` matches what the server expects

    Attach the `e2e-report.json` to the summary.
  </how-to-verify>
  <resume-signal>
    Type "approved: Gate A 15/15, Gate B X/5" to continue (replace X with the number that passed; if Gate B skipped entirely, say "Gate B skipped"). Type issues and describe the failure mode.
  </resume-signal>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Operator shell → e2e_channels_v0_2.sh | Secrets (OPENROUTER_API_KEY, TELEGRAM_BOT_TOKEN, AP_SYSADMIN_TOKEN) enter the process env; MUST NOT be written to e2e-report.json |
| agent_harness → Telegram Bot API | Sends a test string (`ping-22b-test-<uuid>`) — no secrets cross this boundary |
| agent_harness → API /v1/agents/:id/events | Bearer (AP_SYSADMIN_TOKEN) crosses as HTTP header; over localhost loopback; not exposed to external |
| recipe YAML → subprocess docker exec | Untrusted recipe argv is executed inside the container; recipes are authored ground truth, not user input — argv_template values come from the YAML author |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-22b-06-01 | Information Disclosure | e2e-report.json | mitigate | Harness emits only: gate, recipe, correlation_id, sent_text, reply_text (first 400 chars), wall_s, verdict, error. NEVER includes bearer, api_key, chat_id (chat_id is a numeric ID not a secret but the test keeps it out of the report for hygiene). test_events_long_poll.py's project output is the upstream source of reply payloads; D-06 (metadata-only) means no body text is in the payload field |
| T-22b-06-02 | Tampering | recipe YAML argv injection | accept | Recipes are ground truth; if a recipe author writes malicious argv, they have write access to the repo and can already do worse. `direct_interface.spec.argv_template` values are reviewed at PR time |
| T-22b-06-03 | Elevation of Privilege | Harness bypasses ownership via AP_SYSADMIN_TOKEN | mitigate | AP_SYSADMIN_TOKEN is local shell state per CLAUDE.md discipline; never committed; production API would disable the bypass by unsetting the env var. Harness documents this in its top docstring |
| T-22b-06-04 | Denial of Service | Telegram rate-limit on bot->self sendMessage | accept | Gate B = 5 sends per run; Telegram Bot API allows 30 messages/second per bot — well within budget. Legacy send-and-wait's getUpdates polling is removed, further reducing Bot API fanout |
| T-22b-06-05 | Information Disclosure | Subprocess CompletedProcess.stderr in Gate A error envelope | mitigate | Error field truncates stderr to 200 chars; docker-exec errors at runtime may include token fragments from the container's own logging — for BYOK tokens this is a concern; mitigation is the subprocess timeout (60s) + the stderr truncation. Future hardening: run stderr through a redactor matching `[A-Z_]+_(API_KEY|TOKEN)=\S+` |
| T-22b-06-06 | Injection | Recipe's `{prompt}` substitution in argv | accept | Harness uses `a.format(prompt=prompt)` where prompt is `f"Please reply with exactly this text and nothing else: ok-<recipe>-<corr>"` — no shell metacharacters in the prompt. Executor passes argv as a list to subprocess.run (no shell=True), so even a prompt containing `$(rm -rf /)` would be a single argv string, not a shell expansion |
| T-22b-06-07 | Spoofing | Harness match logic for Gate B ("any reply_sent with chat_id == ours") | accept | Two simultaneous Gate B runs against the same agent + chat_id could race; mitigated by D-13's per-agent long-poll lock (second poll returns 429) so the second harness run errors cleanly. Gate B correlation_id embedding is best-effort (not all recipes echo); chat_id + ts-after-send is the baseline. Post-MVP tightening: require correlation_id echo (some recipes would need prompt-engineering to comply) |
</threat_model>

<verification>
- `python3 -c "import yaml; [yaml.safe_load(open('recipes/'+r+'.yaml')) for r in ['hermes','picoclaw','nullclaw','nanobot','openclaw']]"` exits 0
- `grep -c "direct_interface:" recipes/*.yaml | awk -F: '{s += $2} END {exit !(s==5)}'` passes (exactly 5 direct_interface blocks across the 5 recipes)
- `grep -q "event_log_regex" recipes/hermes.yaml` exits 0 (new block added in this plan)
- `python3 test/lib/agent_harness.py --help` lists both subcommands AND NOT the legacy send-and-wait
- `test/sc03-gate-c.md` exists with a section per recipe
- After user runs `bash test/e2e_channels_v0_2.sh` (the checkpoint), `e2e-report.json` exists and shows `"verdict":"PASS"` on at least 15 lines (Gate A) — this is the user-confirmed exit gate
- No regression in any unit/integration test from prior plans: `cd api_server && pytest -x tests/ -q 2>&1 | tail -3` shows no red
</verification>

<success_criteria>
1. 5 recipes each declare direct_interface (docker_exec_cli ×3 + http_chat_completions ×2) per D-21
2. Hermes recipe gains event_log_regex from spike-01a; other recipes' spike-derived blocks untouched
3. agent_harness.py implements 2 subcommands; legacy send-and-wait deleted
4. e2e_channels_v0_2.sh Step 4 runs 15 direct_interface invocations; Step 5 runs 5 long-poll probes (when Telegram creds present)
5. sc03-gate-c.md documents the manual user-in-the-loop checklist
6. User-run e2e_channels_v0_2.sh produces e2e-report.json with Gate A 15/15 PASS (MANDATORY for phase exit)
7. If TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID + AP_SYSADMIN_TOKEN exported: Gate B 5/5 PASS; else Gate B SKIPs cleanly without failing the overall run
</success_criteria>

<output>
After completion, create `.planning/phases/22b-agent-event-stream/22b-06-SUMMARY.md` with:
- Per-recipe direct_interface block paste-verbatim (5 blocks) — prove the argv/port landed per D-21
- The new hermes event_log_regex regex text (verbatim from recipe YAML)
- agent_harness.py line count + SHA + the --help output
- The actual result from the user's run: Gate A X/15 PASS (MUST be 15 for phase exit); Gate B X/5 or SKIP
- The `e2e-report.json` contents (or a pointer to it)
- Any per-recipe Gate A failures + the root cause (port mismatch / argv divergence / auth bug)
- Gate C checklist signed-off OR deferred-to-release-time note
- Attached: the commit SHA closing Phase 22b
</output>

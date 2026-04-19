---
phase: 22b
plan: 07
type: execute
wave: 5
depends_on: ["22b-04", "22b-05", "22b-06"]
files_modified:
  - recipes/openclaw.yaml
  - test/e2e_channels_v0_2.sh
autonomous: true
gap_closure: true
requirements:
  - SC-03-GATE-A

must_haves:
  truths:
    - "openclaw direct_interface invocation works end-to-end against the persistent gateway-mode container — the harness invocation `python3 test/lib/agent_harness.py send-direct-and-read --recipe openclaw --container-id <CID> --model anthropic/claude-haiku-4-5 --api-key $ANTHROPIC_API_KEY` returns verdict=PASS with non-empty reply_text containing the correlation id"
    - "openclaw direct_interface.kind is `docker_exec_cli` (NOT `http_chat_completions`) — port 18000 line is removed; argv targets `openclaw infer model run --local --json` which uses the auth state ALREADY established by the persistent /start (config set + ANTHROPIC_API_KEY env)"
    - "test/e2e_channels_v0_2.sh MATRIX entry for openclaw drops `skip_smoke=true` (the band-aid); the smoke /v1/runs probe must PASS via the same `infer model run --local` path that direct_interface now reuses"
    - "Running `bash test/e2e_channels_v0_2.sh` with full creds produces Gate A 15/15 PASS (openclaw 3/3 included) AND Gate A score writes to e2e-report.json with no openclaw FAIL entries"
    - "Recipe ships an empirical re-verification entry under channels.telegram.verified_cells with date 2026-04-19+ and category=PASS confirming Gate A direct_interface PASSES against the persistent gateway-mode container (i.e., proven through the live FastAPI /v1/agents/:id/start lifecycle — NOT only against the manual `docker run -e ANTHROPIC_API_KEY ...` path that spike-01e used to validate the auth-state precondition in isolation)"
  artifacts:
    - path: "recipes/openclaw.yaml"
      provides: "direct_interface block reshaped to docker_exec_cli targeting openclaw infer model run --local --json (matches spike-01e working path); skip_smoke removal precondition"
      contains: "kind: docker_exec_cli"
    - path: "test/e2e_channels_v0_2.sh"
      provides: "MATRIX openclaw row with skip_smoke=false; Gate A passes openclaw without the band-aid"
      contains: "openclaw|anthropic|ANTHROPIC_API_KEY|anthropic/claude-haiku-4-5|true|false"
  key_links:
    - from: "recipes/openclaw.yaml::direct_interface"
      to: "test/lib/agent_harness.py::cmd_send_direct_and_read (docker_exec_cli branch)"
      via: "argv_template substituted with prompt+model, then docker exec <cid> <argv>"
      pattern: "docker_exec_cli"
    - from: "recipes/openclaw.yaml::persistent.spec.argv"
      to: "openclaw config set agents.defaults.model anthropic/$MODEL + openclaw gateway --allow-unconfigured"
      via: "sh-chain at /start time configures the auth state that infer model run inherits"
      pattern: "agents.defaults.model"
    - from: "test/e2e_channels_v0_2.sh"
      to: "recipes/openclaw.yaml::smoke.argv (= infer model run --local)"
      via: "/v1/runs invocation uses the smoke argv; same code path as direct_interface; both PASS"
      pattern: "infer model run"
---

<objective>
**Gap 1 closure — openclaw Gate A.** Verifier verdict: openclaw direct_interface declares port 18000 + `http_chat_completions`, but the persistent `/v1/agents/:id/start` runs `openclaw gateway --allow-unconfigured` which exposes only port 18789 (channel router) — port 18000 belongs to `openclaw serve` (a separate process not started by our recipe). Result: Gate A 0/3 for openclaw, total 12/15 instead of 15/15.

**Decision: Path A — recipe rewrite to `docker_exec_cli`.**

Reasoning (per planner_authority_limits — only 3 legitimate reasons to defer; none apply here):
1. Spike-06 (lines 105, 121) empirically PROVED the working CLI path: `openclaw infer model run --prompt "..." --local --json`. The smoke `verified_cells[0]` in recipes/openclaw.yaml line 127 PASSES via this exact template (verdict=PASS for `anthropic/claude-haiku-4.5`). Spike-01e separately proved the AUTH-STATE half: passing `ANTHROPIC_API_KEY` in env at container boot makes openclaw auto-detect the anthropic provider, and `agents.defaults.model` set in config is consumed by `infer model run --local`. Both preconditions are ALREADY satisfied by the persistent /start handler (verified): `_detect_provider` + `_resolve_api_key_var` inject ANTHROPIC_API_KEY when model starts with `anthropic/` (per D-21 in 22b-CONTEXT), and the persistent.spec.argv writes `~/.openclaw/openclaw.json` directly via heredoc (lines 261-287 — no `config set` command; the JSON file IS the config) with `agents.defaults.model.primary` substituted from `$MODEL` at boot. The model substitution happens at /start time so the config file is already in place — what we need to fix is overriding the heredoc-baked `openrouter/$MODEL` to `anthropic/$MODEL` at direct_interface invocation time so the anthropic-direct path runs (otherwise the file's openrouter setting routes through the broken openrouter plugin).
2. The smoke `invoke.spec.argv` (lines 87-91 of openclaw.yaml) already uses `openclaw config set agents.defaults.model "openrouter/$MODEL" && openclaw infer model run --prompt "$PROMPT" --local --json` with a hardcoded `openrouter/` prefix — but this works for the PASS verified_cells with `anthropic/claude-haiku-4.5` because `infer model run --local` bypasses the gateway/openrouter-plugin path entirely. The same is true for `direct_interface` if we point it at the same surface.
3. **No `auth-profiles.json` reverse-engineering required.** The `infer model run --local` path uses env vars directly — proven by the existing PASS verified_cells (line 127 with verdict=PASS for `anthropic/claude-haiku-4.5`). The `agent --local` failure documented in the gap (`No API key found for provider 'openai'`) was a different code path that does require auth-profiles.json; we are NOT using `agent --local`, we are using `infer model run --local` (different subcommand, env-var-friendly).
4. **No new code; no schema change; no security regression.** Only YAML is modified.

This path gives Gate A 13/15 → 15/15 with the existing infrastructure. (Gate B for openclaw is a separate concern owned by Plan 22b-08.)

**Empirical re-verification is mandatory** (golden rule 5 + golden rule 4 — no fix-to-pass): one task in this plan runs `bash test/e2e_channels_v0_2.sh --recipe openclaw --rounds 3` against the live local stack and records the verdict + wall times in the SUMMARY.

Output: openclaw.yaml direct_interface rewritten (docker_exec_cli + argv from spike-01e + comment provenance); e2e_channels_v0_2.sh MATRIX `skip_smoke` flag flipped to `false` for openclaw; an empirical run captured in a new verified_cells entry; SUMMARY documents the deletion of the port-18000 dead path AND the upstream concern (openrouter plugin still broken — that's why we use `--local` which bypasses it).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/22b-agent-event-stream/22b-CONTEXT.md
@.planning/phases/22b-agent-event-stream/22b-VERIFICATION.md
@.planning/phases/22b-agent-event-stream/22b-06-SUMMARY.md
@.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-01e-openclaw.md
@.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-06-direct-interface.md
@recipes/openclaw.yaml
@recipes/picoclaw.yaml
@recipes/nullclaw.yaml
@recipes/nanobot.yaml
@recipes/hermes.yaml
@test/e2e_channels_v0_2.sh
@test/lib/agent_harness.py
@e2e-report.json

<interfaces>
<!-- Schema being adhered to + harness branches consumed -->

The harness `cmd_send_direct_and_read` (test/lib/agent_harness.py lines 157-295) dispatches on `direct_interface.kind`:

```python
if kind == "docker_exec_cli":
    spec = di["spec"]
    argv = [a.format(prompt=prompt, model=args.model) for a in spec["argv_template"]]
    out = subprocess.run(["docker", "exec", args.container_id, *argv], ...)
    if out.returncode != spec.get("exit_code_success", 0): error = ...
    reply_text = out.stdout
    extract = spec.get("reply_extract_regex")
    if extract and reply_text:
        m = re.search(extract, reply_text)
        reply_text = m.group("reply") if "reply" in m.groupdict() else m.group(0)
```

The verdict line (lines 282-283):
```python
expected = f"ok-{args.recipe}-{corr}"
verdict = "PASS" if (error is None and expected in (reply_text or "")) else "FAIL"
```

The prompt envelope (lines 178-181):
```python
prompt = (
    f"Please reply with exactly this text and nothing else: "
    f"ok-{args.recipe}-{corr}"
)
```

So our `argv_template` MUST produce stdout that contains the literal substring `ok-openclaw-<4-hex>` (case-sensitive). `--local --json` returns a JSON envelope with the text as one field; `reply_extract_regex` can pull just the text content if needed (or we can rely on the fact that the substring appears verbatim within the JSON serialization).

The persistent /start handler injects ANTHROPIC_API_KEY when model startswith `anthropic/`:
```python
# api_server/src/api_server/routes/agent_lifecycle.py
def _detect_provider(model: str | None, recipe: dict) -> str: ...     # lines 135-159
def _resolve_api_key_var(recipe: dict, model: str | None) -> str | None: ...  # lines 161-189
# Recipe declares (recipes/openclaw.yaml lines 36-39):
#   api_key_by_provider:
#     openrouter: OPENROUTER_API_KEY
#     anthropic: ANTHROPIC_API_KEY
```

So at runtime, when MATRIX has `openclaw|anthropic|ANTHROPIC_API_KEY|anthropic/claude-haiku-4-5|...`, the container is started with `ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY` env. openclaw auto-enables the anthropic plugin when this env is present at boot (verified in spike-01e).
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Rewrite openclaw direct_interface to docker_exec_cli (matches working spike-01e + smoke path)</name>
  <files>recipes/openclaw.yaml</files>
  <read_first>
    - recipes/openclaw.yaml (THE file being edited — read in full; locate ~line 304-332 `direct_interface:` block to be rewritten; locate lines 87-91 `invoke.spec.argv` for the proven `infer model run --local --json` argv; locate lines 258-302 `persistent` block to confirm the /start argv writes the openclaw.json with `agents.defaults.model.primary` AT START TIME)
    - recipes/picoclaw.yaml (ANALOG — line ~ "direct_interface:" block, kind: docker_exec_cli, argv_template spec — copy the exact YAML structural shape)
    - recipes/nullclaw.yaml (ANALOG — same structure with `--model openrouter/{model}` injected; shows how to substitute model via argv)
    - .planning/phases/22b-agent-event-stream/22b-SPIKES/spike-01e-openclaw.md (the working path: `infer model run --local --json` + ANTHROPIC_API_KEY env → reply contains `ok-openclaw-01` verbatim; lines 19-57 are the canonical bash-equivalent; line 92 confirms `grep -c "ok-openclaw-01" <session_file>` returns 2 matches — i.e., the reply body echoes the prompt verbatim including the correlation id)
    - .planning/phases/22b-agent-event-stream/22b-SPIKES/spike-06-direct-interface.md (lines 30-45: openclaw smoke verdict shows `exit_code: 0 + filtered_payload non-empty` — proves the same `infer model run` path works through /v1/runs which uses smoke.argv = same template we are about to use for direct_interface)
    - test/lib/agent_harness.py (lines 187-230 — docker_exec_cli dispatch path: argv_template substitution, subprocess.run(timeout=spec.timeout_s), reply_extract_regex with named group `reply`)
    - .planning/phases/22b-agent-event-stream/22b-VERIFICATION.md (gap 1 root-cause; lines 14-25)
  </read_first>
  <action>
**Edit `recipes/openclaw.yaml`. ONE change: rewrite the `direct_interface:` block (currently ~lines 304-332).**

Find the existing block. The exact current text (between the `# Phase 22b-06 — D-19..D-22 direct_interface for Gate A automation.` comment and the `channels:` top-level key) looks like:

```yaml
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

REPLACE the entire `direct_interface:` block (from `direct_interface:` through `    timeout_s: 60`) and the preceding 7-line comment header (which now lies about the chosen kind) with this verbatim text:

```yaml
# Phase 22b-07 — Gap 1 closure: openclaw direct_interface uses docker_exec_cli
# pointed at `openclaw infer model run --local --json` instead of the previous
# port-18000 http_chat_completions path. Reasoning:
#   1. The persistent gateway started by /v1/agents/:id/start (entrypoint
#      `openclaw gateway --allow-unconfigured`) exposes ONLY the channel-router
#      on port 18789 (verified by spike-01e + health_check.port:18789 above).
#      Port 18000 belongs to `openclaw serve` — a separate process we do NOT
#      start. The previous declaration was a dead reference to MSV's
#      forward_to_agent.go pattern that never matched our container topology.
#   2. The persistent /start handler ALREADY:
#        (a) injects ANTHROPIC_API_KEY when model startswith "anthropic/"
#            (per recipe.runtime.process_env.api_key_by_provider:anthropic above
#             + agent_lifecycle._resolve_api_key_var dispatch);
#        (b) writes ~/.openclaw/openclaw.json directly via heredoc (NOT via a
#            `config set` command — see persistent.spec.argv lines 261-287
#            above) with `agents.defaults.model.primary = openrouter/$MODEL`,
#            dmPolicy=allowlist, allowFrom=[tg:$TELEGRAM_ALLOWED_USER].
#      Mechanism note: direct_interface's `openclaw config set
#      agents.defaults.model "anthropic/{model}"` (Task 1 argv below) runs
#      AGAINST the openclaw.json file the gateway already read at boot —
#      `config set` performs a file write+read cycle, not an in-process state
#      mutation. Same end-effect as if the persistent argv had used `config
#      set` originally, but the actual mechanism is direct file overwrite.
#      The override is necessary because the heredoc bakes the `openrouter/`
#      prefix unconditionally — Gate A pairs openclaw with anthropic models,
#      so we re-point the primary model right before invocation.
#      So at the time direct_interface is invoked, the container has both auth
#      env AND model config in place — `infer model run --local --json` runs
#      against the (now anthropic-pointed) pre-configured state.
#   3. `infer model run --local` bypasses both the gateway and the
#      embedded-agent path that breaks with the openrouter provider plugin
#      (known_quirks.openrouter_provider_plugin_silent_fail below). With
#      ANTHROPIC_API_KEY, this is the verified-PASS code path used by:
#        (a) smoke verified_cells[0] (recipes/openclaw.yaml line 127, verdict=PASS)
#        (b) spike-01e direct docker run (verified_cells[1] PASS_WITH_FLAG line 545)
#        (c) spike-06 /v1/runs invocation (spike-06-direct-interface.md line 33)
#   4. We embed the {prompt} via a `--prompt` flag literal; openclaw is
#      documented to support arbitrary text after `--prompt`. The harness
#      passes the prompt as a single argv element (subprocess shell=False) so
#      whitespace/quoting is safe even with the agent_harness "Please reply
#      with exactly this text..." prompt envelope.
#   5. reply_extract_regex pulls the assistant text out of the JSON envelope
#      (`outputs[0]` per `--json` schema). Because the harness verdict checks
#      for the correlation substring `ok-openclaw-<4-hex>` ANYWHERE in
#      reply_text (Python `in` operator), even unparsed JSON would PASS as long
#      as the model echoed the prompt — but stripping to the assistant text
#      keeps the reply_text field clean for SUMMARY artifacts.
direct_interface:
  kind: docker_exec_cli
  spec:
    # Two-stage sh chain:
    #   1. `openclaw config set agents.defaults.model "anthropic/$MODEL"` —
    #      the persistent /start writes openrouter/$MODEL by default; we override
    #      to anthropic/$MODEL because (a) provider_compat.deferred=[openrouter]
    #      and (b) Gate A's MATRIX always pairs openclaw with an anthropic model.
    #      Idempotent — `config set` overwrites; no need to read previous value.
    #      stderr suppressed (>/dev/null 2>&1) so progress/info chatter doesn't
    #      pollute reply_text. The harness substitutes {model} as e.g.
    #      "claude-haiku-4-5" before docker exec runs.
    #   2. `openclaw infer model run --prompt "<prompt>" --local --json` — the
    #      verified-PASS inference path. --json emits a structured envelope on
    #      stdout. {prompt} is substituted as a single argv element by the
    #      harness, so internal quotes/spaces are literal.
    argv_template:
      - sh
      - -c
      - 'openclaw config set agents.defaults.model "anthropic/{model}" >/dev/null 2>&1 && openclaw infer model run --prompt "{prompt}" --local --json'
    timeout_s: 90              # spike-01e measured first_reply_wall_s ~6s; 90s leaves headroom for cold model warm-up
    stdout_reply: true
    # Pull the `outputs[0]` text out of the --json envelope. The envelope shape
    # per spike-01e session-jsonl observation is roughly:
    #   {"attempts":[...],"outputs":["...assistant text..."],"stopReason":"stop",...}
    # `outputs[0]` is the assistant-rendered text including any echoed prompt
    # content. The regex captures the FIRST quoted string inside `outputs":[`.
    # Falls back to the full stdout when --json output drifts (the verdict
    # check is substring-based so the FAIL-mode is contained).
    reply_extract_regex: "(?s)\"outputs\"\\s*:\\s*\\[\\s*\"(?P<reply>[^\"]*)\""
    exit_code_success: 0
    # Strip leftover model-set status output if it leaks (defense in depth —
    # `>/dev/null 2>&1` should already suppress).
```

(Remove the entire previous `# Phase 22b-06 — D-19..D-22 direct_interface for Gate A automation.` comment block AND the previous direct_interface YAML body, replacing both with the new comment + new block above.)

**Do NOT touch any other field in openclaw.yaml.** In particular:
- `runtime.process_env.api_key_by_provider` (lines 36-39) is correct AS-IS (D-21 mapping). Preserve.
- `persistent.spec.argv` (lines 261-287) is correct AS-IS (writes openclaw.json with agents.defaults.model.primary from $MODEL substitution). The fact that it bakes `openrouter/$MODEL` in the heredoc is overridden by `direct_interface`'s `config set` step at invoke time — this is intentional and documented in comment item 1 above.
- `channels.telegram.event_log_regex` (lines 365-368) and `event_source_fallback` (lines 369-380) — Gap 3 schema work touches the SCHEMA, not the recipe. Preserve.
- All `verified_cells` entries — preserve.
- `known_quirks` — preserve (the openrouter plugin failure documentation is still load-bearing).
  </action>
  <verify>
    <automated>python3 -c "import yaml; r = yaml.safe_load(open('recipes/openclaw.yaml')); di = r['direct_interface']; assert di['kind'] == 'docker_exec_cli', f'kind={di[\"kind\"]!r}'; assert di['spec']['argv_template'][0] == 'sh', f'argv[0]={di[\"spec\"][\"argv_template\"][0]!r}'; assert 'infer model run' in di['spec']['argv_template'][2], 'argv missing infer model run'; assert 'anthropic/{model}' in di['spec']['argv_template'][2], 'argv missing anthropic/ model prefix'; assert di['spec'].get('timeout_s', 0) >= 60; assert 'reply_extract_regex' in di['spec']; print('OK direct_interface shape')"</automated>
  </verify>
  <acceptance_criteria>
    - `python3 -c "import yaml; r = yaml.safe_load(open('recipes/openclaw.yaml')); print(r['direct_interface']['kind'])"` outputs `docker_exec_cli`
    - `grep -c "kind: docker_exec_cli" recipes/openclaw.yaml` returns `>=1` — sanity-only check; `event_source_fallback.kind` also matches the bare `kind: docker_exec_cli` pattern, so this grep alone is fragile. The CANONICAL assertion of direct_interface.kind specifically is the Python yaml-walk check in <verify> above: `r['direct_interface']['kind'] == 'docker_exec_cli'`.
    - `grep -c "kind: http_chat_completions" recipes/openclaw.yaml` returns `0` (the dead path is gone)
    - `grep -c "port: 18000" recipes/openclaw.yaml` returns `0` (port 18000 is no longer referenced)
    - `grep -c "infer model run" recipes/openclaw.yaml` returns `>=2` (smoke argv lines 87-91 PRESERVED + new direct_interface lines)
    - `grep -c "openclaw config set agents.defaults.model" recipes/openclaw.yaml` returns `>=2` (smoke argv preserved + new direct_interface)
    - `grep -c "anthropic/{model}" recipes/openclaw.yaml` returns `1` (new direct_interface only — smoke uses literal `openrouter/$MODEL`)
    - `grep -c "Gap 1 closure\|Phase 22b-07" recipes/openclaw.yaml` returns `>=1` (provenance comment retained)
    - `python3 -c "import yaml; r = yaml.safe_load(open('recipes/openclaw.yaml')); print(r['runtime']['process_env']['api_key_by_provider']['anthropic'])"` outputs `ANTHROPIC_API_KEY` (preservation guard)
    - `python3 -c "import yaml; r = yaml.safe_load(open('recipes/openclaw.yaml')); ch = r['channels']['telegram']; assert 'event_log_regex' in ch and 'event_source_fallback' in ch; print('channels intact')"` succeeds (Gap 3 fields preserved)
    - All 5 yaml recipes still parse cleanly: `for r in hermes picoclaw nullclaw nanobot openclaw; do python3 -c "import yaml; yaml.safe_load(open('recipes/$r.yaml'))" || exit 1; done; echo OK` outputs `OK`
  </acceptance_criteria>
  <done>openclaw.yaml direct_interface block is rewritten to docker_exec_cli targeting `openclaw infer model run --local --json` (anthropic-direct path); the dead port-18000 reference is gone; provenance comment cites Gap 1 + the 3 evidence sources (smoke verified_cells, spike-01e, spike-06); all other fields preserved; all 5 recipes still parse.</done>
</task>

<task type="auto">
  <name>Task 2: Drop skip_smoke band-aid (2a — deterministic edit), run live Gate A (2b — measurement), append verified_cells from measurements (2c — yaml append)</name>
  <files>test/e2e_channels_v0_2.sh, recipes/openclaw.yaml</files>
  <read_first>
    - test/e2e_channels_v0_2.sh (THE file being edited — locate the MATRIX block at lines 95-101; the openclaw row currently ends with `|true|true` (REQ_PAIR=true, SKIP_SMOKE=true). The skip_smoke band-aid was added in commit bdd4f49 per VERIFICATION.md anti-pattern table; we are removing it now)
    - recipes/openclaw.yaml (the file edited in Task 1 — one new verified_cells entry will be appended after the live re-verification at the END of this task)
    - test/lib/agent_harness.py (the harness whose docker_exec_cli branch we exercised in Task 1)
    - .planning/STATE.md (lines 144-150 — local-dev env shape: AP_CHANNEL_MASTER_KEY + TELEGRAM_CHAT_ID alias + docker compose up command)
    - e2e-report.json (the previous gate run output — `cat e2e-report.json | jq '[.[] | select(.recipe=="openclaw" and .gate=="A")]'` shows the pre-fix FAIL pattern; this task will overwrite e2e-report.json with the post-fix run)
  </read_first>
  <action>
**This task has THREE distinct sub-phases that MUST run in order — each one's
output gates the next. Do NOT mix them. Sub-task 2a is a pure deterministic
edit (no live infra). Sub-task 2b is a live e2e run that produces measurements.
Sub-task 2c appends a verified_cells entry whose values come VERBATIM from
2b's measurements (do NOT fabricate; if 2b fails, STOP and root-cause —
golden rule 4 — do not synthesize a verified_cells entry from imagined values).**

---

**Sub-task 2a (deterministic — no live infra) — Edit `test/e2e_channels_v0_2.sh`.**

Find line 100 in the MATRIX array (currently):
```bash
  "openclaw|anthropic|ANTHROPIC_API_KEY|anthropic/claude-haiku-4-5|true|true"
```

Change ONLY the LAST field (`true` → `false` for skip_smoke):
```bash
  "openclaw|anthropic|ANTHROPIC_API_KEY|anthropic/claude-haiku-4-5|true|false"
```

Also REPLACE the inline comment block at lines 91-94 (currently):
```bash
# recipe_name|llm_provider|llm_key_env|llm_model|requires_pairing|skip_smoke
# skip_smoke=true bypasses /v1/runs probe (e.g., openclaw — openrouter plugin
# upstream-blocked; the anthropic-direct path needs config-set steps that
# /v1/runs doesn't perform; documented in openclaw.yaml provider_compat).
```

with (preserves the column doc; removes the openclaw-specific skip rationale because the band-aid is gone):
```bash
# recipe_name|llm_provider|llm_key_env|llm_model|requires_pairing|skip_smoke
# skip_smoke=true bypasses the /v1/runs verdict assertion (only the existence
# of agent_instance_id is checked). Reserved for documented upstream-blocked
# recipes; openclaw was the only previous user but Phase 22b-07 closed that
# gap by switching openclaw direct_interface + smoke to the
# `infer model run --local` anthropic-direct path that is empirically PASS.
```

Do NOT touch any other line in the script.

**Sub-task 2b (live e2e run — REAL infrastructure; golden rule 1: no mocks, no stubs) — Run the focused Gate A re-verification.**

(Run only AFTER Sub-task 2a is committed to the file — the MATRIX edit is what flips the smoke probe back on, which Sub-task 2b exercises.)

Pre-flight checks. Stop if any fail; do NOT proceed to the run otherwise:

```bash
# 1. Required env (golden rule 4 — root cause discipline; do NOT mutate .env files):
test -n "${AP_CHANNEL_MASTER_KEY:-}" || { echo "MISSING: AP_CHANNEL_MASTER_KEY (export per STATE.md line 147)"; exit 2; }
test -n "${ANTHROPIC_API_KEY:-}" || { echo "MISSING: ANTHROPIC_API_KEY (in deploy/.env.local or shell env)"; exit 2; }
test -n "${OPENROUTER_API_KEY:-}" || { echo "MISSING: OPENROUTER_API_KEY (Gate A bootstrap requires both per script line 81)"; exit 2; }

# 2. Stack health (per CLAUDE.md user instruction "before running anything, kill previous"):
docker ps --filter "name=ap-recipe-openclaw" --format '{{.ID}}' | xargs -r docker rm -f >/dev/null 2>&1 || true
curl -fsS http://localhost:8000/healthz >/dev/null 2>&1 || { echo "API not up — start via 'cd deploy && docker compose -f docker-compose.prod.yml -f docker-compose.local.yml --env-file .env.prod up -d'"; exit 2; }

# 3. openclaw image present:
docker images --format '{{.Repository}}' | grep -qx ap-recipe-openclaw || { echo "ap-recipe-openclaw image not built — run 'tools/run_recipe.py recipes/openclaw.yaml --build' first"; exit 2; }
```

Now run the focused Gate A re-verification (3 rounds = the openclaw column of the 15/15 target):

```bash
bash test/e2e_channels_v0_2.sh --recipe openclaw --rounds 3 --skip-gate-b 2>&1 | tee /tmp/22b-07-openclaw-gateA.log
GATE_RC=$?
echo "exit code: $GATE_RC"
```

**Empirical PASS criteria** (this is the gap-closure proof, NOT just "the test ran"):
- `$GATE_RC` == `0`
- `cat e2e-report.json | jq -r '[.[] | select(.recipe=="openclaw" and .gate=="A" and .verdict=="PASS")] | length'` returns `3`
- `cat e2e-report.json | jq -r '[.[] | select(.recipe=="openclaw" and .gate=="A" and .verdict=="FAIL")] | length'` returns `0`
- The smoke step did NOT FAIL — the e2e script ONLY emits a `stage=="smoke"` row to e2e-report.json on FAILURE (test/e2e_channels_v0_2.sh lines 169 + 177); on success, no smoke row is added. So check that NO smoke FAIL row exists: `cat e2e-report.json | jq -r '[.[] | select(.recipe=="openclaw" and ((.stage // "") == "smoke") and .verdict != "PASS")] | length'` returns `0`. AND prove the run got past the smoke gate to invoke `start`/Gate A: `grep -c "INFO booted in" /tmp/22b-07-openclaw-gateA.log` returns `1` (the persistent /start handler logs a successful boot, which the script reaches only AFTER the smoke gate clears)

If ANY of these criteria fail, you MUST diagnose root cause (golden rule 4) before proceeding — do NOT fix-to-pass with another band-aid. Document the failure mode and STOP. Likely failure modes to investigate:
- `verdict=FAIL error="exit_code=2 stderr=..."`: read the stderr; openclaw `infer model run` may need an additional config set or the model id format may need adjustment (e.g., `claude-haiku-4-5` vs `claude-haiku-4.5` — note recipe uses `4-5` per spike-01e line 47; matrix uses `claude-haiku-4-5` per script line 100; both must agree).
- `verdict=FAIL reply_text=null`: docker exec failed entirely; `docker exec <cid> openclaw --help` should work; if not, the persistent container is misconfigured.
- `correlation_id` not echoed: model may have refused to comply with the prompt envelope; this is a model-behavior issue distinct from the plumbing gap; flag in SUMMARY but do NOT change the recipe to "make it pass".

**Sub-task 2c (yaml append — measurement-dependent on 2b output) — Append the empirical re-verification entry to `recipes/openclaw.yaml`.**

ONLY proceed if Sub-task 2b produced exit_code=0 AND e2e-report.json shows Gate A 3/3 PASS for openclaw. If either condition fails, STOP — do NOT append a verified_cells entry derived from imagined or partial values (golden rule 4 — never fix-to-pass; verified_cells must reflect a REAL measured run).

Append a new entry to `channels.telegram.verified_cells:` (which currently has 3 entries — date 2026-04-18 PASS, 2026-04-18 PASS_WITH_FLAG, 2026-04-17 CHANNEL_PASS_LLM_FAIL). The new entry goes at the TOP of the list (most-recent-first convention used by other recipes):

```yaml
      - date: "2026-04-19"
        bot_username: "@AgentPlayground_bot"
        allowed_user_id: 152099202
        provider: anthropic
        model: anthropic/claude-haiku-4-5
        env_var: ANTHROPIC_API_KEY
        boot_wall_s: <ACTUAL FROM RUN>          # paste from /tmp/22b-07-openclaw-gateA.log line "booted in ${BOOT_S}s"
        first_reply_wall_s: <ACTUAL FROM RUN>   # paste from r1 wall_s in e2e-report.json
        reply_sample: "<ACTUAL ECHO FROM RUN>"  # paste reply_text from r1 in e2e-report.json (truncate to 200 chars; redact nothing — model output is not secret)
        verdict: PASS
        notes: |
          Gap 1 closure (Phase 22b-07). direct_interface rewritten from
          http_chat_completions:18000 (dead path — openclaw gateway --allow-
          unconfigured does NOT bind 18000) to docker_exec_cli targeting
          `openclaw infer model run --local --json`. Same path as smoke
          verified_cells[0] PASS, validated end-to-end through:
            bash test/e2e_channels_v0_2.sh --recipe openclaw --rounds 3 --skip-gate-b
          Result: Gate A 3/3 PASS, no skip_smoke band-aid. Closes
          .planning/phases/22b-agent-event-stream/22b-VERIFICATION.md gap 1.
        category: PASS
```

Replace the placeholders (`<ACTUAL FROM RUN>`, `<ACTUAL ECHO FROM RUN>`) with the values captured during Part B. Do NOT fabricate; if a value is missing from e2e-report.json, leave the field absent rather than guessing.
  </action>
  <verify>
    <automated>set -e; grep -c "openclaw|anthropic|ANTHROPIC_API_KEY|anthropic/claude-haiku-4-5|true|false" test/e2e_channels_v0_2.sh | grep -q ^1$ && grep -c "openclaw|anthropic|ANTHROPIC_API_KEY|anthropic/claude-haiku-4-5|true|true" test/e2e_channels_v0_2.sh | grep -q ^0$ && python3 -c "import yaml,json; r=yaml.safe_load(open('recipes/openclaw.yaml')); cells=r['channels']['telegram']['verified_cells']; assert any(c.get('date','').startswith('2026-04-19') and c.get('verdict')=='PASS' and 'Gap 1' in (c.get('notes') or '') for c in cells), 'missing 2026-04-19 PASS Gap-1 verified_cells entry'; print('OK')" && cat e2e-report.json | python3 -c "import json,sys; rep=json.load(sys.stdin); a_pass=[r for r in rep if r.get('recipe')=='openclaw' and r.get('gate')=='A' and r.get('verdict')=='PASS']; a_fail=[r for r in rep if r.get('recipe')=='openclaw' and r.get('gate')=='A' and r.get('verdict')=='FAIL']; assert len(a_pass)==3, f'gate A pass={len(a_pass)} expected 3'; assert len(a_fail)==0, f'gate A fail={len(a_fail)} expected 0'; print('Gate A 3/3 PASS confirmed')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "openclaw|anthropic|ANTHROPIC_API_KEY|anthropic/claude-haiku-4-5|true|false" test/e2e_channels_v0_2.sh` returns `1`
    - `grep -c "openclaw|anthropic|ANTHROPIC_API_KEY|anthropic/claude-haiku-4-5|true|true" test/e2e_channels_v0_2.sh` returns `0` (band-aid is gone)
    - `grep -c "skip_smoke=true bypasses /v1/runs" test/e2e_channels_v0_2.sh` returns `0` (old comment is gone)
    - `grep -c "Phase 22b-07 closed that" test/e2e_channels_v0_2.sh` returns `1` (new comment landed)
    - The freshly-written `e2e-report.json` has openclaw Gate A 3/3 PASS, 0 FAIL: `cat e2e-report.json | python3 -c "import json,sys; rep=json.load(sys.stdin); print(sum(1 for r in rep if r.get('recipe')=='openclaw' and r.get('gate')=='A' and r.get('verdict')=='PASS'), '/', sum(1 for r in rep if r.get('recipe')=='openclaw' and r.get('gate')=='A'))"` outputs `3 / 3`
    - `python3 -c "import yaml; r=yaml.safe_load(open('recipes/openclaw.yaml')); cells=r['channels']['telegram']['verified_cells']; new=[c for c in cells if c.get('date','').startswith('2026-04-19')]; assert len(new) >= 1; assert new[0]['verdict']=='PASS' and 'Gap 1' in (new[0].get('notes') or '')" ` succeeds
    - The pre-existing 2026-04-17 CHANNEL_PASS_LLM_FAIL and 2026-04-18 PASS_WITH_FLAG entries are still present (preservation guard): `python3 -c "import yaml; r=yaml.safe_load(open('recipes/openclaw.yaml')); cells=r['channels']['telegram']['verified_cells']; assert any(c.get('verdict')=='CHANNEL_PASS_LLM_FAIL' for c in cells); assert any(c.get('verdict')=='PASS_WITH_FLAG' for c in cells)"`
    - The persistent container was reaped after the test (no leak): `docker ps --filter "name=ap-recipe-openclaw" --format '{{.ID}}' | wc -l` returns `0`
  </acceptance_criteria>
  <done>MATRIX skip_smoke flipped to false; live Gate A run confirms openclaw 3/3 PASS via the rewritten direct_interface; an empirical 2026-04-19 PASS verified_cells entry is appended to openclaw.yaml documenting the closure (with real boot_wall_s + first_reply_wall_s + reply_sample from the run); previous verified_cells entries preserved.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Harness `--api-key` arg → docker exec env | The bearer is passed as a CLI arg to agent_harness.py, then NOT used in docker_exec_cli mode (only http_chat_completions consumed it). Switch to docker_exec_cli REMOVES the in-container `Bearer <api_key>` injection — the api_key is now only used by /v1/agents/:id/start to seed ANTHROPIC_API_KEY into the container at boot time. Lower attack surface. |
| docker exec `openclaw config set` → ~/.openclaw/openclaw.json | The argv hardcodes `anthropic/{model}`. {model} is substituted by Python `.format(model=args.model)` from the harness; args.model comes from the e2e MATRIX (literal string per recipe row), not user input. No injection surface. |
| docker exec `openclaw infer model run --prompt {prompt}` | {prompt} is substituted by Python `.format(prompt=prompt)` where prompt is `f"Please reply with exactly this text and nothing else: ok-{recipe}-{corr}"`. recipe and corr are CLI args; subprocess.run uses argv list (shell=False) so quote/space injection is impossible. Verified pattern in Task 1 read_first §test/lib/agent_harness.py lines 187-230. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-22b-07-01 | Tampering | Recipe-side argv_template substitution | mitigate | argv_template uses Python `.format()` with named keys (`{prompt}`, `{model}`); no f-string concatenation; no shell expansion (subprocess.run shell=False per agent_harness lines 211-215) |
| T-22b-07-02 | Information Disclosure | reply_text in JSON envelope leaks model rationale | accept | The harness already truncates reply_text to 400 chars (agent_harness line 290); openclaw's `infer model run --local --json` does NOT include any auth tokens or env-var names in its `outputs` field (verified in spike-01e session-jsonl format, line 81-90). The `outputs` array contains only assistant-rendered text. |
| T-22b-07-03 | Denial of Service | timeout_s=90 holds container resources | accept | One Gate A round at a time per recipe (single-START orchestration in e2e script line 220). Cumulative budget is 5 recipes × 3 rounds × 90s = 22.5min worst case; the e2e script already runs cleanup on EXIT INT TERM (script lines 119-128). |
| T-22b-07-04 | Elevation of Privilege | direct_interface gives Gate A docker-exec into the persistent container | accept | Pre-existing posture — every other recipe (hermes, picoclaw, nullclaw, nanobot) has the same docker_exec_cli direct_interface; the docker socket is the host-side authorization boundary, not the recipe shape. No new privilege introduced. |
| T-22b-07-05 | Spoofing | `anthropic/{model}` hardcode could mask a deliberate non-anthropic Gate A run | accept | The MATRIX row pins model to `anthropic/claude-haiku-4-5` and the recipe's `provider_compat.deferred=[openrouter]` already documents that openrouter is intentionally NOT supported in persistent mode. A future change to test openai-direct via openclaw would require both MATRIX update AND recipe update — discoverable. |
</threat_model>

<verification>
- Recipe parses cleanly + matches expected shape: `python3 -c "import yaml; r=yaml.safe_load(open('recipes/openclaw.yaml')); assert r['direct_interface']['kind']=='docker_exec_cli' and 'infer model run' in r['direct_interface']['spec']['argv_template'][2]"`
- Dead port 18000 reference removed: `! grep -n "port:.*18000\|http://127.0.0.1:18000\|http://localhost:18000" recipes/openclaw.yaml`
- MATRIX skip_smoke flipped: `grep -c "openclaw.*|true|false$" test/e2e_channels_v0_2.sh` returns `1`
- Empirical Gate A 3/3 PASS captured in e2e-report.json (Task 2 acceptance criteria)
- 2026-04-19 verified_cells entry committed to openclaw.yaml documenting the empirical PASS
- All 5 recipe YAMLs parse: `for r in hermes picoclaw nullclaw nanobot openclaw; do python3 -c "import yaml; yaml.safe_load(open('recipes/$r.yaml'))" || exit 1; done`
- No regressions in OTHER recipes' Gate A (still 12/12 they were passing before — verified by re-running full e2e if time permits, otherwise the focused openclaw-only run is sufficient closure proof)
</verification>

<success_criteria>
1. `recipes/openclaw.yaml` direct_interface.kind = `docker_exec_cli`, argv_template targets `openclaw infer model run --local --json` with anthropic model override + suppressed config-set chatter
2. `test/e2e_channels_v0_2.sh` MATRIX openclaw row has `skip_smoke=false` (band-aid removed); old comment block updated to reference Phase 22b-07 closure
3. Live `bash test/e2e_channels_v0_2.sh --recipe openclaw --rounds 3 --skip-gate-b` returns exit 0 with Gate A 3/3 PASS in e2e-report.json
4. New 2026-04-19 verified_cells entry in openclaw.yaml documents the empirical re-verification with real boot_wall_s + first_reply_wall_s + reply_sample
5. No regression in any other recipe's Gate A behavior; all 5 recipe YAMLs parse
6. SUMMARY explicitly notes that Gate B for openclaw is OUT OF SCOPE for this plan (owned by Plan 22b-08); also notes that the openrouter plugin upstream bug is UNCHANGED — we route around it via anthropic-direct, we do NOT claim to have fixed it
</success_criteria>

<output>
After completion, create `.planning/phases/22b-agent-event-stream/22b-07-SUMMARY.md` with:
- Exact diff of `recipes/openclaw.yaml` direct_interface block (before/after side-by-side)
- Exact diff of `test/e2e_channels_v0_2.sh` MATRIX line + comment block
- Pasted contents of the empirical 2026-04-19 verified_cells entry (with real measured values)
- Wall times: boot_wall_s, per-round Gate A wall_s (3 measurements), total e2e run wall time
- Cleanup proof: `docker ps --filter name=ap-recipe-openclaw` returns empty post-run
- Confirmation that ALL OTHER recipes' Gate A is unchanged (state: not re-run in this plan; the focused openclaw-only flag avoids redundant work — full 15/15 gate run is the orchestrator's responsibility after all 3 gap-closure plans land)
- Honest scope limit: openclaw Gate B is still 0/1 (owned by Plan 22b-08 test-injection path); no claim about Gate B in this plan
- Honest upstream limit: openrouter provider plugin remains broken upstream (known_quirks unchanged); we route around it via the anthropic-direct path, NOT a fix
</output>

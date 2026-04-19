---
phase: 22b
plan: 01
type: execute
wave: 0
depends_on: []
files_modified:
  - api_server/pyproject.toml
  - api_server/tests/conftest.py
  - api_server/tests/fixtures/event_log_samples/hermes_reply_sent.log
  - api_server/tests/fixtures/event_log_samples/picoclaw_reply_sent.log
  - api_server/tests/fixtures/event_log_samples/nullclaw_history.json
  - api_server/tests/fixtures/event_log_samples/nanobot_reply_sent.log
  - api_server/tests/fixtures/event_log_samples/openclaw_session.jsonl
  - api_server/tests/test_busybox_tail_line_buffer.py
  - api_server/tests/test_lifecycle_env_by_provider.py
  - api_server/src/api_server/routes/agent_lifecycle.py
  - recipes/openclaw.yaml
  - .env.example
autonomous: true
requirements:
  - SC-03-GATE-A
  - SC-03-GATE-B
user_setup: []

must_haves:
  truths:
    - "docker-py 7.x is installable via pip install -e '.[dev]'"
    - "conftest.py exposes docker_client + running_alpine_container fixtures usable by Wave 1 watcher tests"
    - "Five event-log sample fixtures exist under api_server/tests/fixtures/event_log_samples/ containing the spike-captured raw lines"
    - "Openclaw /start with an Anthropic bearer injects ANTHROPIC_API_KEY into the container env, NOT OPENROUTER_API_KEY"
    - "BusyBox tail -F line-buffer probe records the empirical behavior (PASS or documented fallback)"
    - ".env.example documents AP_SYSADMIN_TOKEN as per-laptop state"
  artifacts:
    - path: "api_server/pyproject.toml"
      provides: "docker>=7.0,<8 dependency declaration"
      contains: "docker>=7.0"
    - path: "api_server/tests/conftest.py"
      provides: "docker_client + running_alpine_container + event_log_samples fixtures"
      contains: "def docker_client"
    - path: "api_server/tests/fixtures/event_log_samples/hermes_reply_sent.log"
      provides: "hermes reply_sent stdout capture from spike 01a"
      min_lines: 1
    - path: "api_server/tests/fixtures/event_log_samples/openclaw_session.jsonl"
      provides: "openclaw session JSONL capture from spike 01e"
      min_lines: 1
    - path: "api_server/tests/test_busybox_tail_line_buffer.py"
      provides: "A3 assumption probe — BusyBox tail -F line-buffers reliably"
      contains: "def test_busybox_tail_line_buffer"
    - path: "api_server/tests/test_lifecycle_env_by_provider.py"
      provides: "openclaw env-var-by-provider integration test"
      contains: "ANTHROPIC_API_KEY"
    - path: "recipes/openclaw.yaml"
      provides: "runtime.process_env.api_key_by_provider map"
      contains: "api_key_by_provider"
  key_links:
    - from: "api_server/src/api_server/routes/agent_lifecycle.py"
      to: "recipes/openclaw.yaml:runtime.process_env.api_key_by_provider"
      via: "_resolve_api_key_var helper"
      pattern: "api_key_by_provider"
    - from: "api_server/tests/conftest.py"
      to: "Wave 1 watcher tests"
      via: "docker_client session-scoped fixture"
      pattern: "def docker_client"
---

<objective>
Wave-0 preparation for Phase 22b. This plan unblocks every downstream wave:

1. **Add `docker>=7.0,<8`** to `api_server/pyproject.toml` so `watcher_service.py` (Wave 1) can import `docker.APIClient`.
2. **Seed spike fixtures** — copy the raw stdout / JSONL captures from the 5 spike artifacts (01a..01e) into `api_server/tests/fixtures/event_log_samples/` so Wave 1 regex tests have real input.
3. **Add shared conftest fixtures** — `docker_client` (session-scoped), `running_alpine_container` (factory), and `event_log_samples` (directory path).
4. **Fix the openclaw `/start` env-var gap (D-21 load-bearing for Gate A)** — add `runtime.process_env.api_key_by_provider: {anthropic: ANTHROPIC_API_KEY, openrouter: OPENROUTER_API_KEY}` to the recipe schema and teach `start_agent` to pick the env-var name by the model's provider prefix. Without this, openclaw Gate A cannot run via the real `/start` path because openclaw auto-enables its broken openrouter plugin when it sees `OPENROUTER_API_KEY`.
5. **Probe Assumption A3 (BusyBox tail -F line-buffering)** — Wave 1's `FileTailInContainerSource` (openclaw) depends on this. The probe writes a line to a file inside an alpine container and asserts `Popen.stdout.readline()` returns within 100ms. If it fails, planner is alerted and Wave 1 adopts the documented `sh -c "while :; do cat; sleep 0.2; done"` fallback.
6. **Document `AP_SYSADMIN_TOKEN`** in `.env.example` (commented; per-laptop state; mirrors `AP_CHANNEL_MASTER_KEY` discipline per CLAUDE.md "never modify .env files").

Purpose: de-risk Wave 1 (watcher_service + event_store) and Wave 2 (lifecycle integration) by paying down every Wave-0 debt item RESEARCH.md §Wave-0-gaps surfaced.

Output: installed docker dep, 5 fixture files, 3 shared conftest fixtures, 1 recipe schema extension + 1 route helper + 1 integration test, 1 probe test, 1 doc update to `.env.example`.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/ROADMAP.md
@.planning/phases/22b-agent-event-stream/22b-CONTEXT.md
@.planning/phases/22b-agent-event-stream/22b-RESEARCH.md
@.planning/phases/22b-agent-event-stream/22b-PATTERNS.md
@.planning/phases/22b-agent-event-stream/22b-VALIDATION.md
@.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-01a-hermes.md
@.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-01e-openclaw.md
@api_server/pyproject.toml
@api_server/tests/conftest.py
@api_server/src/api_server/routes/agent_lifecycle.py
@recipes/openclaw.yaml

<interfaces>
<!-- Wave 0 reads these keys from existing recipes + substrate. No new interfaces exported by Wave 0 (schema addition is documented in recipe YAML only; Wave 2 consumes via agent_lifecycle edit). -->

From api_server/src/api_server/routes/agent_lifecycle.py (existing ~line 248-256, api_key lookup that Wave 0 replaces):
```python
# EXISTING:
api_key_var = recipe.get("runtime", {}).get("process_env", {}).get("api_key")
# Wave 0 replaces with:
api_key_var = _resolve_api_key_var(recipe, agent["model"])
```

From recipes/hermes.yaml (existing shape — example of process_env):
```yaml
runtime:
  process_env:
    api_key: OPENROUTER_API_KEY
    api_key_fallback: OPENAI_API_KEY    # hints at multi-provider awareness
```

From recipes/openclaw.yaml (existing shape — Wave 0 extends this block):
```yaml
runtime:
  process_env:
    api_key: OPENROUTER_API_KEY         # KEEP — default / legacy callers
    # Wave 0 adds:
    api_key_by_provider:
      openrouter: OPENROUTER_API_KEY
      anthropic: ANTHROPIC_API_KEY
```

From spike-01a-hermes.md (the fixture data):
```
hermes 3-line canonical reply_sent sequence (captured during spike):
INFO:hermes.channels.telegram: sent reply chat_id=... length=... correlation=...
```
(Exact content = paste into fixtures/event_log_samples/hermes_reply_sent.log)

From spike-01e-openclaw.md (fixture data):
```json
{"type":"message","id":"3c7038fd","message":{"role":"assistant","content":[{"type":"thinking","thinking":"..."},{"type":"text","text":"ok-openclaw-01"}]}}
```
(Paste into fixtures/event_log_samples/openclaw_session.jsonl)

From api_server/tests/conftest.py (existing pattern for PG fixture — Wave 0 MIRRORS for docker):
```python
@pytest.fixture(scope="session")
def real_db():
    with PostgresContainer("postgres:17-alpine") as pg:
        yield pg.get_connection_url()
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Install docker-py dependency + document AP_SYSADMIN_TOKEN</name>
  <files>api_server/pyproject.toml, .env.example</files>
  <read_first>
    - api_server/pyproject.toml (the file being modified — extract current [project.dependencies] list and compare against known-versions to avoid duplication)
    - .env.example (read current contents FIRST — if the file exists and documents other env vars, append only; do NOT overwrite)
    - .planning/phases/22b-agent-event-stream/22b-PATTERNS.md §"api_server/pyproject.toml (ADD-TO)" — confirms the add-only discipline
    - .planning/phases/22b-agent-event-stream/22b-RESEARCH.md §"Standard Stack > New dependencies to add" — specifies `docker>=7.0,<8`
    - .planning/phases/22b-agent-event-stream/22b-CONTEXT.md D-15 — `AP_SYSADMIN_TOKEN` discipline (per-laptop, mirrors AP_CHANNEL_MASTER_KEY)
  </read_first>
  <behavior>
    - After this task, `pip index versions docker` shows 7.x available and pyproject.toml lists exactly `docker>=7.0,<8` once.
    - After this task, `.env.example` has a comment block documenting `AP_SYSADMIN_TOKEN` (its purpose, its per-laptop discipline, an example value format) but no actual token value.
    - `pip install -e '.[dev]'` completes without errors when run from `api_server/`.
  </behavior>
  <action>
Edit `api_server/pyproject.toml`:
1. Locate `[project]` → `dependencies = [ ... ]` list (read current entries in full first — do NOT edit blindly).
2. Add the literal line `  "docker>=7.0,<8",` in the same block, keeping sort order consistent with siblings (alphabetical after asgi-correlation-id, before fastapi if present).
3. Do NOT touch `[project.optional-dependencies]` or `[tool.*]` blocks.

Edit `.env.example` at the repository root (APPEND-ONLY — do NOT overwrite authoritative env docs):
1. FIRST, snapshot the current `.env.example` line count: `LINES_BEFORE=$(wc -l < .env.example 2>/dev/null || echo 0)`.
2. Branch on existence:
   - **IF `.env.example` exists:** use append-only guard so reruns are idempotent and existing env docs are preserved:
     ```
     grep -q "^# AP_SYSADMIN_TOKEN" .env.example || cat >> .env.example <<'EOF'

     # ---- Phase 22b: sysadmin bypass for GET /v1/agents/:id/events (D-15) ----
     # AP_SYSADMIN_TOKEN — per-laptop / per-deploy state. Mirrors AP_CHANNEL_MASTER_KEY
     # discipline: NEVER commit the value. The API reads the VALUE at handler time via
     # os.environ.get("AP_SYSADMIN_TOKEN"). To generate:
     #   export AP_SYSADMIN_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
     EOF
     ```
   - **IF `.env.example` does NOT exist:** flag to the user via a `_log.warning`-style echo in the task output (`echo "WARNING: .env.example is missing — creating it with ONLY the AP_SYSADMIN_TOKEN block. The repo previously had no .env.example; this is expected only on a fresh clone."`) and THEN create the file with the commented block above. Do NOT fabricate additional env vars.
3. Verify line count did not decrease: `LINES_AFTER=$(wc -l < .env.example); [[ "$LINES_AFTER" -ge "$LINES_BEFORE" ]] || { echo "REGRESSION: .env.example shrank from $LINES_BEFORE to $LINES_AFTER"; exit 1; }`.
4. **NEVER touch `.env`, `.env.local`, `.env.prod`, `deploy/.env.prod`** — CLAUDE.md rule.

Verify:
```bash
cd api_server && pip install -e '.[dev]' 2>&1 | tail -20
python3 -c "import docker; print(docker.__version__)"
grep -c '"docker>=7.0,<8"' pyproject.toml
grep -c "AP_SYSADMIN_TOKEN" ../.env.example
```
Expected: docker imports cleanly, version is 7.x, grep count of `"docker>=7.0,<8"` is 1, AP_SYSADMIN_TOKEN appears in .env.example.
  </action>
  <verify>
    <automated>cd api_server && pip install -e '.[dev]' >/dev/null 2>&1 && python3 -c "import docker; assert docker.__version__.startswith('7'), docker.__version__" && grep -q '"docker>=7.0,<8"' pyproject.toml && grep -q "AP_SYSADMIN_TOKEN" ../.env.example</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c 'docker>=7.0,<8' api_server/pyproject.toml` returns exactly `1`
    - `python3 -c "import docker; print(docker.__version__)"` prints a 7.x version
    - `grep -c "AP_SYSADMIN_TOKEN" .env.example` returns `>=1`
    - `.env.example`'s line count did not decrease relative to the pre-task snapshot (the append-only guard preserved every pre-existing env var declaration)
    - `.env` / `.env.local` / `.env.prod` / `deploy/.env.prod` are UNCHANGED (`git diff -- .env* deploy/.env* | wc -l` prints `0`)
  </acceptance_criteria>
  <done>docker-py is importable from api_server, pyproject.toml is clean, .env.example documents AP_SYSADMIN_TOKEN, NO .env* files touched.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Seed 5 spike-derived event-log fixtures + conftest shared fixtures</name>
  <files>api_server/tests/fixtures/event_log_samples/hermes_reply_sent.log, api_server/tests/fixtures/event_log_samples/picoclaw_reply_sent.log, api_server/tests/fixtures/event_log_samples/nullclaw_history.json, api_server/tests/fixtures/event_log_samples/nanobot_reply_sent.log, api_server/tests/fixtures/event_log_samples/openclaw_session.jsonl, api_server/tests/conftest.py</files>
  <read_first>
    - api_server/tests/conftest.py (the file being modified — do not duplicate existing fixtures; extract the PostgresContainer pattern to mirror for docker)
    - .planning/phases/22b-agent-event-stream/22b-PATTERNS.md §"api_server/tests/conftest.py (ADD-TO)" and §"Test pattern assignments (seed from spikes)"
    - .planning/phases/22b-agent-event-stream/22b-RESEARCH.md §"Wave 0 gaps" — enumerates the 5 fixture files needed
    - .planning/phases/22b-agent-event-stream/22b-SPIKES/spike-01a-hermes.md (source of hermes_reply_sent.log content — the canonical 3-line sequence)
    - .planning/phases/22b-agent-event-stream/22b-SPIKES/spike-01c-nullclaw.md (source of nullclaw_history.json — the `nullclaw history show --json` output)
    - .planning/phases/22b-agent-event-stream/22b-SPIKES/spike-01e-openclaw.md (source of openclaw_session.jsonl — the assistant message JSON from §"Session JSONL")
    - .planning/phases/22b-agent-event-stream/22b-VALIDATION.md §"Spike Evidence → Test Fixture Mapping"
  </read_first>
  <behavior>
    - After this task, `ls api_server/tests/fixtures/event_log_samples/` returns exactly 5 files: hermes_reply_sent.log, picoclaw_reply_sent.log, nullclaw_history.json, nanobot_reply_sent.log, openclaw_session.jsonl.
    - Each fixture file is non-empty and contains the exact raw bytes captured in the corresponding spike.
    - After this task, `api_server/tests/conftest.py` exports 3 new session-scoped fixtures: `docker_client` (from-env docker client), `running_alpine_container` (factory returning an alpine container that echoes lines and auto-removes on teardown), `event_log_samples_dir` (pathlib.Path to the fixtures directory).
    - `pytest --collect-only api_server/tests/` lists the 3 new fixtures as collected.
  </behavior>
  <action>
**Part A — Create 5 fixture files.** Copy the exact stdout / JSONL snippets that each spike captured into individual files. Each fixture file MUST contain the raw bytes — these become test input for Wave 1 regex parsers.

1. `api_server/tests/fixtures/event_log_samples/hermes_reply_sent.log` — copy the canonical 3-line `reply_sent` sequence from spike-01a-hermes.md §"Captured log evidence" (includes the log line naming chat_id and correlation id).

2. `api_server/tests/fixtures/event_log_samples/picoclaw_reply_sent.log` — copy the picoclaw eventbus `response_text` log line from spike-01b-picoclaw.md.

3. `api_server/tests/fixtures/event_log_samples/nullclaw_history.json` — copy the `nullclaw history show <sid> --json` output VERBATIM from spike-01c-nullclaw.md §"Where the activity DOES live" (the block starting `{"session_id":"agent:main:telegram:direct:152099202",...`).

4. `api_server/tests/fixtures/event_log_samples/nanobot_reply_sent.log` — copy the ISO-timestamped `Response to` log line from spike-01d-nanobot.md.

5. `api_server/tests/fixtures/event_log_samples/openclaw_session.jsonl` — copy the 10-line JSONL sequence from spike-01e-openclaw.md §"Session JSONL", including the assistant message with `content[{type:text, text:"ok-openclaw-01"}]`.

If a spike document does not contain an exact byte-for-byte snippet, paste the closest available quote and add a header comment `# Extracted from spike-01X on 2026-04-18` on line 1 of the fixture.

**Part B — Extend `api_server/tests/conftest.py`.** Read the file first; preserve every existing fixture unchanged; APPEND the three new fixtures at the end:

```python
# ------ Phase 22b Wave 0 shared fixtures ------

@pytest.fixture(scope="session")
def docker_client():
    """docker-py APIClient from-env. Skips test if daemon unavailable.

    Source: RESEARCH.md Standard Stack — docker>=7.0,<8; from_env auto-negotiates.
    """
    import docker
    try:
        client = docker.from_env()
        client.ping()
    except Exception as exc:
        pytest.skip(f"Docker daemon unavailable: {exc}")
    yield client
    client.close()


@pytest.fixture
def running_alpine_container(docker_client):
    """Factory: spawn an alpine:3.19 container with a user-provided command.
    Auto-removes on teardown. Returns the docker Container object.

    Example: container = running_alpine_container(command=["sh", "-c", "echo hello; sleep 30"])
    """
    created = []
    def _factory(command, **kwargs):
        container = docker_client.containers.run(
            "alpine:3.19", command=command, detach=True, auto_remove=True, **kwargs)
        created.append(container)
        return container
    yield _factory
    for c in created:
        try: c.remove(force=True)
        except Exception: pass


@pytest.fixture(scope="session")
def event_log_samples_dir():
    """Path to the 5 spike-derived event-log fixture files."""
    return Path(__file__).parent / "fixtures" / "event_log_samples"
```

Add a `from pathlib import Path` import at the top if it is not already present.

Verify:
```bash
ls api_server/tests/fixtures/event_log_samples/ | wc -l    # → 5
grep -c "^def docker_client\|^def running_alpine_container\|^def event_log_samples_dir" api_server/tests/conftest.py
cd api_server && pytest --collect-only -q 2>&1 | grep -c "fixtures"
```
  </action>
  <verify>
    <automated>ls api_server/tests/fixtures/event_log_samples/ | wc -l | grep -q '5' && cd api_server && pytest --fixtures tests/conftest.py 2>&1 | grep -q docker_client && pytest --fixtures tests/conftest.py 2>&1 | grep -q running_alpine_container && pytest --fixtures tests/conftest.py 2>&1 | grep -q event_log_samples_dir</automated>
  </verify>
  <acceptance_criteria>
    - `ls api_server/tests/fixtures/event_log_samples/ | wc -l` returns exactly `5`
    - `wc -c api_server/tests/fixtures/event_log_samples/openclaw_session.jsonl` returns a byte count `> 100`
    - `grep -q "ok-openclaw-01" api_server/tests/fixtures/event_log_samples/openclaw_session.jsonl` exits 0
    - `grep -q "ok-nullclaw-01" api_server/tests/fixtures/event_log_samples/nullclaw_history.json` exits 0
    - `cd api_server && pytest --fixtures tests/conftest.py 2>&1 | grep -q docker_client` exits 0
    - `cd api_server && pytest --fixtures tests/conftest.py 2>&1 | grep -q event_log_samples_dir` exits 0
    - `cd api_server && pytest -x tests/ -q 2>&1 | tail -3` still shows existing tests passing (no regression in collection)
  </acceptance_criteria>
  <done>5 fixture files exist with spike-captured content; conftest.py exports 3 new session-scoped fixtures usable by Wave 1 tests; no existing test is broken.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Openclaw env-var-by-provider fix + BusyBox tail probe</name>
  <files>api_server/src/api_server/routes/agent_lifecycle.py, recipes/openclaw.yaml, api_server/tests/test_lifecycle_env_by_provider.py, api_server/tests/test_busybox_tail_line_buffer.py</files>
  <read_first>
    - api_server/src/api_server/routes/agent_lifecycle.py (the file being modified — read the current `api_key_var` lookup at ~line 248-256 AND the step-flow docstring at lines 1-40 to understand where the helper lands)
    - recipes/openclaw.yaml (the file being modified — confirm current `runtime.process_env` block shape and `provider_compat.supported` list)
    - .planning/phases/22b-agent-event-stream/22b-PATTERNS.md §"api_server/src/api_server/routes/agent_lifecycle.py (ADD-TO)" §"Openclaw env-var-by-provider fix"
    - .planning/phases/22b-agent-event-stream/22b-RESEARCH.md §"Openclaw /start Env-Var Gap — Posture" (the authoritative shape for `api_key_by_provider` and `_resolve_api_key_var`)
    - .planning/phases/22b-agent-event-stream/22b-SPIKES/spike-01e-openclaw.md (the empirical finding that motivates this fix)
    - .planning/phases/22b-agent-event-stream/22b-RESEARCH.md §"Open Questions" Q2 — BusyBox tail probe rationale
    - .planning/phases/22b-agent-event-stream/22b-VALIDATION.md — test file naming convention
  </read_first>
  <behavior>
    - After this task, `POST /v1/agents/:id/start` with an `anthropic/...` model on the openclaw recipe injects `ANTHROPIC_API_KEY` (not `OPENROUTER_API_KEY`) into the container env.
    - `recipes/openclaw.yaml` contains the new `runtime.process_env.api_key_by_provider: {openrouter: OPENROUTER_API_KEY, anthropic: ANTHROPIC_API_KEY}` block while keeping the legacy `api_key: OPENROUTER_API_KEY` field intact (backward compatibility for other callers).
    - Every recipe that does NOT declare `api_key_by_provider` falls back to the legacy `api_key` field unchanged (other recipes are NOT touched by this task).
    - `test_lifecycle_env_by_provider.py` asserts the route behavior via a tiny alpine fixture that `env | grep ^ANTHROPIC_API_KEY=` and exits.
    - `test_busybox_tail_line_buffer.py` writes a line to a file inside an alpine container, runs `docker exec <cid> tail -n0 -F <path>`, and asserts `Popen.stdout.readline()` returns the line within 500ms — empirically proving A3.
  </behavior>
  <action>
**Part A — Extend the recipe schema in `recipes/openclaw.yaml`.**

Locate the existing `runtime.process_env` block and add `api_key_by_provider` underneath, keeping the legacy `api_key` intact. Final shape (copy VERBATIM, indent matching surrounding YAML):

```yaml
runtime:
  process_env:
    api_key: OPENROUTER_API_KEY           # default / legacy callers
    api_key_by_provider:                  # Phase 22b: per-D-21 env-var mapping
      openrouter: OPENROUTER_API_KEY      # plugin bug, known-flaky — see known_quirks
      anthropic: ANTHROPIC_API_KEY        # verified working (spike 01e)
    api_key_fallback: null                # preserve if already present
```

Do NOT touch any other field in `openclaw.yaml`. Do NOT touch any other recipe YAML.

**Part B — Add the helper in `api_server/src/api_server/routes/agent_lifecycle.py`.**

Near the top of the file (after existing private helpers like `_redact_creds` at ~line 131), add:

```python
def _detect_provider(model: str, recipe: dict) -> str:
    """Return canonical provider name for a given model id.

    Heuristic per RESEARCH §Openclaw /start Env-Var Gap:
        - 'anthropic/claude-...' → 'anthropic'
        - 'openrouter/...' or '<vendor>/<model>' without a dedicated provider → 'openrouter'
        - fallback: recipe.provider_compat.supported[0]
    """
    if not model:
        supported = (recipe.get("provider_compat") or {}).get("supported") or []
        return supported[0] if supported else "openrouter"
    prefix = model.split("/", 1)[0].lower() if "/" in model else ""
    if prefix in ("anthropic", "openai", "openrouter", "google"):
        return prefix
    # No namespaced prefix → OpenRouter (its model catalogue uses vendor/model shape without a leading "openrouter/")
    supported = (recipe.get("provider_compat") or {}).get("supported") or []
    return supported[0] if supported else "openrouter"


def _resolve_api_key_var(recipe: dict, model: str) -> str | None:
    """Pick the env-var NAME (e.g. ANTHROPIC_API_KEY) that will receive the bearer.

    1. If recipe.runtime.process_env.api_key_by_provider is set, dispatch by _detect_provider.
    2. Else fallback to recipe.runtime.process_env.api_key (legacy behavior).
    3. Returns None if neither is declared (caller falls back to pre-fix default).
    """
    process_env = (recipe.get("runtime") or {}).get("process_env") or {}
    by_provider = process_env.get("api_key_by_provider") or {}
    if by_provider:
        provider = _detect_provider(model, recipe)
        var = by_provider.get(provider)
        if var:
            return var
    return process_env.get("api_key")
```

Then locate the EXISTING line that reads `api_key_var = recipe.get("runtime", {}).get("process_env", {}).get("api_key")` (approximately line 248-256 per PATTERNS.md) and REPLACE it with:

```python
api_key_var = _resolve_api_key_var(recipe, agent.get("model"))
```

Use `agent["model"]` or `agent.get("model")` based on the surrounding scope (read the adjacent code — if `agent` is a dict returned by `fetch_agent_instance` / `run_store`, `.get("model")` is safest). Preserve any redaction or logging that surrounded the original assignment.

**Part C — Add integration test `api_server/tests/test_lifecycle_env_by_provider.py`.**

Mirror the shape of `api_server/tests/test_runs.py` (httpx AsyncClient + ASGITransport). Minimal test:

```python
"""Phase 22b-01 Task 3 — openclaw env-var-by-provider contract.

Asserts POST /v1/agents/:id/start with an anthropic/... model on a recipe
with api_key_by_provider injects ANTHROPIC_API_KEY (not OPENROUTER_API_KEY).

Uses a tiny inline recipe (no dependency on openclaw image) by monkeypatching
the recipe loader to return a test recipe that points at alpine:3.19 + argv
["sh", "-c", "env | grep -E '^(ANTHROPIC|OPENROUTER)_API_KEY=' > /tmp/envout; sleep 60"].
After /start, execs `cat /tmp/envout` and asserts ANTHROPIC_API_KEY is set
and OPENROUTER_API_KEY is NOT set.
"""
# Pattern: Follow test_runs.py for fixture setup. If the existing test harness
# does not support recipe monkeypatch, land a minimum viable test that directly
# exercises _resolve_api_key_var via a unit import:
#   - recipe = {"runtime": {"process_env": {"api_key": "OPENROUTER_API_KEY",
#                 "api_key_by_provider": {"anthropic": "ANTHROPIC_API_KEY",
#                                          "openrouter": "OPENROUTER_API_KEY"}}}}
#   - assert _resolve_api_key_var(recipe, "anthropic/claude-haiku-4.5") == "ANTHROPIC_API_KEY"
#   - assert _resolve_api_key_var(recipe, "openrouter/anthropic/claude-haiku-4.5") == "OPENROUTER_API_KEY"
#   - assert _resolve_api_key_var(recipe, "anthropic/x/y/z") == "ANTHROPIC_API_KEY"
#   - recipe_no_map = {"runtime": {"process_env": {"api_key": "OPENROUTER_API_KEY"}}}
#   - assert _resolve_api_key_var(recipe_no_map, "anthropic/claude") == "OPENROUTER_API_KEY"
# (Backward compat — no api_key_by_provider falls back to api_key.)
```

Implement at least the unit test path (4 asserts above). The full integration test with alpine `env | grep` is a bonus; include it if the existing test framework already has the AsyncClient fixture reusable.

**Part D — Add BusyBox tail line-buffer probe `api_server/tests/test_busybox_tail_line_buffer.py`.**

```python
"""Phase 22b-01 Task 3 — A3 assumption probe.

BusyBox (alpine) `tail -F` must line-buffer reliably for FileTailInContainerSource
to work in Wave 1. Write a known line into a file inside a running alpine,
spawn `docker exec <cid> tail -n0 -F /path`, assert the line surfaces on
Popen.stdout within 500ms. If this test FAILS, Wave 1's FileTailInContainerSource
needs the fallback `sh -c 'while :; do cat; sleep 0.2; done'` path.
"""
import subprocess, time, pytest

@pytest.mark.integration
def test_busybox_tail_line_buffer(running_alpine_container):
    container = running_alpine_container(["sh", "-c", "touch /tmp/probe.log; tail -f /dev/null"])
    # Launch tail -F on the file via docker exec
    proc = subprocess.Popen(
        ["docker", "exec", container.id, "tail", "-n0", "-F", "/tmp/probe.log"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    # Write a line
    time.sleep(0.3)     # let tail attach
    subprocess.run(["docker", "exec", container.id, "sh", "-c",
                    "echo probe-line-a3-xyz >> /tmp/probe.log"], check=True)
    # Assert readline returns within 500ms
    import selectors
    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ)
    events = sel.select(timeout=0.5)
    assert events, "BusyBox tail -F did NOT line-buffer within 500ms — Wave 1 must use fallback"
    line = proc.stdout.readline().strip()
    assert "probe-line-a3-xyz" in line, f"Expected correlation in tail output, got: {line!r}"
    proc.kill()
```

Verify:
```bash
cd api_server && pytest -x tests/test_lifecycle_env_by_provider.py tests/test_busybox_tail_line_buffer.py -v 2>&1 | tail -30
```
Both tests green OR `test_busybox_tail_line_buffer` fails with a clear message that documents the A3 failure (Wave 1 planner reads the xfail marker).
  </action>
  <verify>
    <automated>cd api_server && pytest -x tests/test_lifecycle_env_by_provider.py -v 2>&1 | grep -q "4 passed\|passed" && pytest -x tests/test_busybox_tail_line_buffer.py -v 2>&1 | grep -qE "passed|xfailed" && grep -q "api_key_by_provider" ../recipes/openclaw.yaml && grep -q "_resolve_api_key_var" src/api_server/routes/agent_lifecycle.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c 'api_key_by_provider' recipes/openclaw.yaml` returns `>=1`
    - `grep -c '_resolve_api_key_var' api_server/src/api_server/routes/agent_lifecycle.py` returns `>=2` (definition + call site)
    - `grep -c '_detect_provider' api_server/src/api_server/routes/agent_lifecycle.py` returns `>=1`
    - `cd api_server && pytest -x tests/test_lifecycle_env_by_provider.py -v` prints `PASSED` on the 4 unit asserts (anthropic maps, openrouter maps, deep-path anthropic maps, missing-map falls back to legacy api_key)
    - `cd api_server && pytest -x tests/test_busybox_tail_line_buffer.py -v` either PASSES (A3 validated) or FAILS with an error message containing "BusyBox tail -F did NOT line-buffer" (A3 falsified → Wave 1 uses fallback). XFAIL is NOT acceptable — probe must produce a definitive verdict.
    - `grep -r 'api_key_by_provider' recipes/` shows only `openclaw.yaml` — other recipes UNCHANGED
    - Existing tests still pass: `cd api_server && pytest -x tests/test_agents.py 2>&1 | tail -3` (or equivalent agent lifecycle test) shows no regression
  </acceptance_criteria>
  <done>Openclaw recipe declares api_key_by_provider; agent_lifecycle.py resolves the env-var via `_resolve_api_key_var(recipe, model)`; unit test proves mapping; BusyBox probe produces a definitive PASS/FAIL verdict that Wave 1 can act on.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| caller → `POST /v1/agents/:id/start` | Bearer token arrives over HTTPS; recipe-driven env-var name resolves which env slot receives the bearer |
| api_server → Docker daemon | Recipe's argv + env dict cross into an untrusted runtime; typo in `api_key_by_provider` could misroute a token to the wrong env var |
| test harness → alpine container | docker exec from pytest user-mode into a rootless alpine; the probe writes a non-secret sentinel line only |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-22b-01-01 | Information Disclosure | `.env.example` diff | mitigate | Task 1 commits only a commented placeholder; NEVER writes `.env` / `.env.local` / `.env.prod` / `deploy/.env.prod` (CLAUDE.md rule) |
| T-22b-01-02 | Tampering | `_resolve_api_key_var` unit test inputs | mitigate | Test covers the 4 provider-prefix branches (anthropic, openrouter, deep-path anthropic, no-map legacy) so a future edit can't silently route the bearer to the wrong env var |
| T-22b-01-03 | Information Disclosure | BusyBox tail probe | accept | Probe writes a non-secret sentinel `probe-line-a3-xyz` to a file inside a disposable alpine; no tokens touch the probe path |
| T-22b-01-04 | Denial of Service | docker_client + running_alpine_container fixtures | mitigate | `running_alpine_container` factory force-removes every spawned container in teardown; `docker_client` pings the daemon and `pytest.skip`s if unavailable so CI without docker does not wedge |
| T-22b-01-05 | Elevation of Privilege | openclaw env-var routing (pre-fix) | mitigate | Fix lands in Wave 0 — before Gate A runs — so no openclaw session in 22b e2e accidentally receives an OpenRouter env when the user supplied an Anthropic key |
| T-22b-01-06 | Spoofing | `_detect_provider` fallback chain | accept | When model id has no namespaced prefix, fallback is `provider_compat.supported[0]`; recipe authors control `supported` list so spoofing requires recipe-edit access which is already privileged |
</threat_model>

<verification>
- `cd api_server && pip install -e '.[dev]' && python3 -c "import docker; print(docker.__version__)"` prints 7.x
- `cd api_server && pytest -x tests/test_lifecycle_env_by_provider.py tests/test_busybox_tail_line_buffer.py -v` exits 0 (or tail probe produces definitive FAIL used by Wave 1)
- `cd api_server && pytest -x tests/ -q 2>&1 | tail -5` shows no regressions in existing test suite
- `ls api_server/tests/fixtures/event_log_samples/ | wc -l` returns `5`
- `cd api_server && pytest --fixtures tests/conftest.py 2>&1 | grep -E "docker_client|running_alpine_container|event_log_samples_dir" | wc -l` returns `3`
- `git diff -- .env .env.local .env.prod deploy/.env.prod 2>/dev/null | wc -l` returns `0` (CLAUDE.md compliance)
</verification>

<success_criteria>
1. `docker>=7.0,<8` imports cleanly in api_server venv
2. 5 spike-derived fixtures committed under `api_server/tests/fixtures/event_log_samples/`
3. 3 new shared fixtures exported by `api_server/tests/conftest.py`: `docker_client`, `running_alpine_container`, `event_log_samples_dir`
4. Openclaw recipe declares `api_key_by_provider`; `_resolve_api_key_var` dispatches on model provider prefix; unit test proves the 4 branches
5. BusyBox `tail -F` probe produces a definitive PASS/FAIL — Wave 1 planner reads the verdict
6. `AP_SYSADMIN_TOKEN` documented in `.env.example` ONLY; no other `.env*` file touched
</success_criteria>

<output>
After completion, create `.planning/phases/22b-agent-event-stream/22b-01-SUMMARY.md` with:
- What was installed (docker-py version)
- Exact 5 fixture files created + their byte counts
- New conftest fixture names + their scopes
- Whether the BusyBox tail probe PASSED or FAILED (load-bearing for Wave 1 FileTailInContainerSource)
- The 4 unit test assertions added for `_resolve_api_key_var`
- Verification command outputs
</output>

# Phase 10: error-taxonomy-timeout-enforcement — Research

**Researched:** 2026-04-16
**Domain:** Python subprocess + Docker container lifecycle + JSON Schema evolution + ruamel.yaml round-trip migration
**Confidence:** HIGH (all critical claims verified against Docker official docs, Python stdlib docs, and verbatim source from SWE-bench + Inspect AI)

## Summary

Phase 10 converts the runner's binary `{verdict: PASS|FAIL}` into a category-aware verdict and wires real timeout enforcement via `--cidfile` + `docker kill`. Every load-bearing technical question has a clear answer grounded in verified sources:

1. **`subprocess.run(timeout=)` alone is insufficient.** Python only kills the `docker` CLI process; the Docker daemon keeps running the container. The fix is the `--cidfile` pattern: pass `--cidfile <path>` to `docker run`, catch `subprocess.TimeoutExpired`, read the cidfile, then `docker kill <cid>` (SIGKILL by default) and `docker rm -f <cid>`. Two gotchas: (a) the cidfile path must not exist beforehand — Docker errors out if it does, so use a fresh UUID-suffixed path under `/tmp`, not `NamedTemporaryFile(delete=False)` (which creates the file); (b) the cidfile is NOT auto-removed when the container dies — the runner must unlink it explicitly, even on success. [HIGH — verified against Docker CLI docs + moby/moby#3791 + moby/moby#20766]

2. **`docker build` timeout has a documented limitation.** Killing the `docker build` subprocess does not stop the daemon from finishing the current layer; the partially-built image cache survives. CONTEXT.md D-03 already acknowledges this ("Docker daemon will finish its current layer; accept this limitation and document it"). Implementation stays simple: `subprocess.run(timeout=build.timeout_s)` + best-effort cleanup via `docker image prune --filter dangling=true` (optional). [HIGH — verified against docker/cli#3375 + docker/for-linux#1108]

3. **Prior-art shapes are directly portable.** SWE-bench uses plain module-level string constants (`APPLY_PATCH_FAIL = ">>>>> Patch Apply Failed"`) plus a minimal `ResolvedStatus(Enum)` for verdict outcomes. Inspect AI uses Pydantic `BaseModel` with `type: Literal["context","time","working","message","token","cost","operator","custom"]` + `limit: float`. Our domain maps best to a Python `StrEnum` (or plain string constants in a module) for the 11 category values + a small dataclass/TypedDict for `{category, detail, verdict}`.

4. **Migration is mechanically safe.** ruamel.yaml round-trip (already in use via `writeback_cell()`) preserves comments and ordering. All 5 recipes can be migrated by a one-shot script that adds `category` + `detail` to each `verified_cells[]` and `known_incompatible_cells[]` entry. The schema MUST be tightened AFTER the migration script runs, not before — otherwise the 5 committed recipes fail lint.

5. **Docker daemon pre-flight check** is a 1-line `subprocess.run(["docker", "version"], timeout=5, check=False)` that returns `INFRA_FAIL` on non-zero or `TimeoutExpired`. No need for the docker-py SDK — we already shell out everywhere else in the runner for consistency.

**Primary recommendation:** Implement the runner in 3 phases mirroring the architecture map: (a) introduce a `Verdict` dataclass + `Category` StrEnum in `run_recipe.py`; (b) refactor `main()` to produce categories at each phase boundary (INFRA pre-flight → CLONE → BUILD/PULL → INVOKE → ASSERT); (c) add `--cidfile`-based timeout enforcement ONLY in `run_cell()`, where the container lives. Migrate recipes first, tighten schema second.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Category enum definition | Python runner (`run_recipe.py`) | JSON Schema (enum mirror) | Runner is the source of truth for what categories get emitted; schema mirrors for lint |
| Timeout enforcement | Python runner (`run_cell()`) | Docker daemon (via `docker kill`) | Python owns the timer; daemon owns the container lifecycle |
| Pre-flight INFRA check | Python runner startup | — | Runs once at process start, before any domain logic |
| Recipe migration | One-shot Python script | ruamel.yaml round-trip | Mechanical transformation applied to 5 committed YAMLs; round-trip preserves formatting |
| Verdict emission | Python runner | stdout (human) + JSON (future) | D-05 locks a minimal human format; JSON mode deferred to debt queue |
| Schema enforcement | `tools/ap.recipe.schema.json` | `lint_recipe()` (uses schema) | Declarative — no new enforcement code; existing `lint_recipe()` picks up new required fields automatically |
| Taxonomy tests | `tools/tests/test_categories.py` (new) | `conftest.py::mock_subprocess` fixture | Existing mock-subprocess pattern from `test_pass_if.py` extends cleanly to category fixtures |

## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01. Category set (frozen, with reserved placeholders).** 9 live categories shipped this phase:

| Category | Meaning |
|---|---|
| `PASS` | Recipe ran end-to-end and `pass_if` evaluated true |
| `ASSERT_FAIL` | Runner completed; `pass_if` evaluated false |
| `INVOKE_FAIL` | `docker run` exited non-zero before `pass_if` could be evaluated |
| `BUILD_FAIL` | `docker build` failed (upstream_dockerfile mode) |
| `PULL_FAIL` | `docker pull` failed (image_pull mode) |
| `CLONE_FAIL` | `git clone` / `git checkout` failed before build |
| `TIMEOUT` | Container exceeded `smoke.timeout_s` and was killed |
| `LINT_FAIL` | Recipe failed schema validation (already implemented in phase 09) |
| `INFRA_FAIL` | Docker daemon unavailable, disk full, host-level failure |

Two reserved placeholders in the schema enum (not emitted by this phase's runner):
- `STOCHASTIC` — multi-run verdict couldn't reach agreement (phase 15)
- `SKIP` — cell in `known_incompatible_cells` intentionally not run (later UX phase)

Schema enum MUST include all 11 values now (9 live + 2 reserved) so future phases don't require schema migration.

**D-02. Verdict shape.** `category` is authoritative; `verdict` is derived (`PASS` iff `category == PASS`, else `FAIL`); `detail` is free-form single-line string. Applies to both `verified_cells[]` and `known_incompatible_cells[]`.

**D-03. Timeout plumbing.** Three recipe fields (`smoke.timeout_s` default 180, `build.timeout_s` default 900, `build.clone_timeout_s` default 300) plus one CLI flag (`--global-timeout`). Enforcement MUST use `--cidfile` + `docker kill` for `docker run`; `docker build` kill has a daemon-layer limitation that is accepted and documented.

**D-04. Backwards-compat migration.** One-time migration of all 5 committed recipes:
- Add `category: PASS` + `detail: ""` to every existing verified cell.
- For `known_incompatible_cells[]`: add `category: ASSERT_FAIL` (hermes × gemini-2.5-flash maps STOCHASTIC → ASSERT_FAIL with `detail: "flapping verdict — see notes"` until phase 15).
- All 5 recipes MUST still pass lint after migration.

**D-05. CLI output format.** `<CATEGORY pad 10>  <recipe> (<model>) <wall_time_s>s — <detail>`. Green PASS / red everything else (reuse Phase 09's ANSI pattern). `--json` deferred.

### Claude's Discretion
- Internal Python representation: dataclass vs TypedDict vs dict — planner's call.
- Exact fixture count per category for taxonomy tests — minimum 1 per live category, planner picks.
- Whether to refactor `main()` into per-phase sub-functions — lean YES if `main()` is long enough to justify it.
- `--timeout-override` CLI flag — nice-to-have, not required.
- Docker daemon detection: `docker version` pre-flight vs caught subprocess error — planner's call.

### Deferred Ideas (OUT OF SCOPE)
- `STOCHASTIC` emission (phase 15)
- `SKIP` emission (later UX phase)
- `--json` structured output mode (debt queue)
- Colored table output, wide CLI formatting (later UX phase)
- Parallel cell execution
- Cost-based limits (Inspect AI's `cost_limit` — belongs with Go orchestrator)

## Phase Requirements

No explicit REQ-IDs — this phase is driven by CONTEXT.md's D-01 through D-05 plus the P05 "must deliver" list from `FRAMEWORK-MATURITY-ROADMAP.md`.

| Source | Description | Research Support |
|--------|-------------|------------------|
| D-01 | 11-value category enum (9 live + 2 reserved) | §Prior-Art Primitives — SWE-bench + Inspect AI patterns |
| D-02 | Flat verdict shape `{category, detail, verdict}` | §Verdict Shape Options — dataclass recommendation |
| D-03 | `--cidfile` + `docker kill` timeout | §The `--cidfile` + `docker kill` Pattern + §Docker Build Timeout Limitation |
| D-04 | Migrate 5 recipes, lint still passes | §Recipe Migration Mechanics + §Schema-Migration Ordering |
| D-05 | Minimal CLI output format | §CLI Output Sketch |
| P05 exit gate | Each taxonomy branch producible by ≥1 test fixture | §Taxonomy Test Fixtures |

## Project Constraints (from CLAUDE.md)

The top-of-repo CLAUDE.md has a load-bearing 2026-04-15 pivot banner. Phase 10 is explicitly named as one of the framework-maturity phases in scope; however:

- **Do NOT touch `api/`, `deploy/`, `test/`, or the old substrate** — confirmed irrelevant to this phase (recipe runner is Python-only under `tools/`).
- **Do NOT act on the 9-phase roadmap below the banner as authoritative** — the 9-phase MSV-mirror roadmap is historical. The active roadmap is `.planning/FRAMEWORK-MATURITY-ROADMAP.md` (P04–P12).
- **Do NOT delete or rewrite the 5 existing recipes** beyond minimal migration — D-04 defines exactly what the migration must add.
- **Do NOT add a new agent recipe** — the BACKLOG is on hold until after v0.2 phases land.
- **Commit policy (user global):** only commit when asked; use one-line concise commit messages summarizing the change. Planner should structure commits per-task, planner issues the commit via `gsd-tools.cjs commit` as is standard in phase 9 plans.
- **Never create summary/report documents without explicit ask** — RESEARCH.md is the authorized artifact.

## Standard Stack

### Core (already in project — no new runtime deps)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `ruamel.yaml` | ≥0.17.21 | Round-trip YAML load/dump preserving comments | Already used by `load_recipe()` and `writeback_cell()`; only option that preserves comments across write-back |
| `jsonschema` | ≥4.23 | Draft 2020-12 validator | Already used by `lint_recipe()`; enum additions + new required fields are handled declaratively |
| `pytest` | ≥8.0 | Test framework | Already in `[dev]` extras |
| Python stdlib `subprocess` | 3.10+ | Process invocation | `subprocess.run(timeout=)` is the documented Python primitive for timed processes |
| Python stdlib `dataclasses` | 3.10+ | Internal verdict representation | Plain — no attrs, no pydantic |
| Python stdlib `enum.StrEnum` | 3.11+ | **Requires verification** — `pyproject.toml` says `requires-python = ">=3.10"` but `StrEnum` was added in 3.11. Safe fallback: `class Category(str, Enum):` works on 3.10. |

**Verification:** `pyproject.toml` requires Python `>=3.10` (line: `requires-python = ">=3.10"`). `enum.StrEnum` is 3.11+. Use `class Category(str, Enum)` for backward compat with 3.10 — this is the exact pre-3.11 idiom that forms the basis of StrEnum. [VERIFIED: `tools/pyproject.toml:9`]

### Supporting (no additions needed)

No new runtime dependencies required. Everything resolvable with stdlib + existing `ruamel.yaml` + `jsonschema`.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| String constants + `class Category(str, Enum)` | `pydantic.BaseModel` with `Literal[...]` | Pydantic adds a runtime dep, gives better error messages on misuse, and is how Inspect AI represents `EvalSampleLimit`. Overkill for our 11-value closed set — stdlib Enum is sufficient and keeps the tools module dep-minimal. |
| Shell-out to `docker` CLI | `docker-py` (Python Docker SDK) | The whole runner already shells out consistently; introducing docker-py for just the pre-flight / kill breaks the pattern and adds a 2-MB transitive dep. Shell-out stays. |
| Hand-rolled category dict | `@dataclass` | Dict is easier initially; dataclass gives type hints + IDE autocomplete + equality semantics for tests. Planner should pick dataclass. |

**Installation:** None — all deps already present in `tools/pyproject.toml`.

**Version verification:** No upgrades needed. `ruamel.yaml`, `jsonschema`, and `pytest` versions pinned in Phase 09 are current and unchanged.

## Architecture Patterns

### System Architecture Diagram

```
                       ┌───────────────────────────┐
                       │  run_recipe.py main()     │
                       └──────────┬────────────────┘
                                  │
                  ┌───────────────▼──────────────────┐
                  │  pre-flight: docker version      │
                  │  → INFRA_FAIL on error/timeout   │
                  └───────────────┬──────────────────┘
                                  │
                  ┌───────────────▼──────────────────┐
                  │  _lint_single()                   │
                  │  → LINT_FAIL if errors (existing) │
                  └───────────────┬──────────────────┘
                                  │
                  ┌───────────────▼──────────────────┐
                  │  ensure_image()                   │
                  │  ├─ clone → CLONE_FAIL            │
                  │  ├─ build → BUILD_FAIL            │
                  │  └─ pull  → PULL_FAIL             │
                  └───────────────┬──────────────────┘
                                  │
                  ┌───────────────▼──────────────────┐
                  │  run_cell()                       │
                  │  ┌─ launch w/ --cidfile           │
                  │  │                                │
                  │  ├─ TimeoutExpired:               │
                  │  │   read cidfile                 │
                  │  │   docker kill <cid>            │
                  │  │   docker rm -f <cid>           │
                  │  │   unlink cidfile               │
                  │  │   → TIMEOUT                    │
                  │  │                                │
                  │  ├─ rc != 0 → INVOKE_FAIL         │
                  │  │                                │
                  │  └─ evaluate_pass_if():           │
                  │     ├─ true  → PASS               │
                  │     └─ false → ASSERT_FAIL        │
                  └───────────────┬──────────────────┘
                                  │
                  ┌───────────────▼──────────────────┐
                  │  emit_verdict(category, detail)  │
                  │  → stdout (human) / JSON (later) │
                  └───────────────────────────────────┘
```

### Recommended Project Structure

No new files needed at package level. Modifications stay within existing layout:

```
tools/
├── run_recipe.py              # extend: add Category enum + Verdict dataclass
├── ap.recipe.schema.json      # extend: add category/detail fields + enum values
└── tests/
    ├── conftest.py            # already has mock_subprocess fixture
    ├── test_categories.py     # NEW: 1 test per live category
    ├── test_lint.py           # existing — may grow for new enum values
    ├── test_pass_if.py        # unchanged
    ├── test_recipe_regression.py  # regression gate against 5 migrated recipes
    └── test_roundtrip.py      # unchanged

recipes/
├── hermes.yaml                # migrate: add category + detail to cells
├── openclaw.yaml              # migrate: add category + detail to cells
├── picoclaw.yaml              # migrate: add category + detail to cells
├── nullclaw.yaml              # migrate: add category + detail to cells
└── nanobot.yaml               # migrate: add category + detail to cells

scripts/                       # NEW directory (optional)
└── migrate_recipes_phase10.py # one-shot migration (commit, then delete)
```

### Pattern 1: Category StrEnum

**What:** Closed set of category names shared between runner (emitter) and schema (validator).

**When to use:** All code that produces or consumes verdicts.

**Example (Python 3.10 compatible):**
```python
# Source: pattern inferred from SWE-bench ResolvedStatus + Inspect AI EvalSampleLimitType
from enum import Enum

class Category(str, Enum):
    # Live (9)
    PASS = "PASS"
    ASSERT_FAIL = "ASSERT_FAIL"
    INVOKE_FAIL = "INVOKE_FAIL"
    BUILD_FAIL = "BUILD_FAIL"
    PULL_FAIL = "PULL_FAIL"
    CLONE_FAIL = "CLONE_FAIL"
    TIMEOUT = "TIMEOUT"
    LINT_FAIL = "LINT_FAIL"
    INFRA_FAIL = "INFRA_FAIL"
    # Reserved placeholders (schema only; runner never emits)
    STOCHASTIC = "STOCHASTIC"   # phase 15
    SKIP = "SKIP"               # later UX phase

    @property
    def is_terminal_fail(self) -> bool:
        return self is not Category.PASS
```

`class Category(str, Enum)` (not `enum.StrEnum`) is the correct Python-3.10-safe pattern. Members auto-coerce to strings for JSON serialization. [CITED: CPython docs § enum — https://docs.python.org/3/library/enum.html ; verified against pyproject `requires-python = ">=3.10"`]

### Pattern 2: Verdict Dataclass

```python
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class Verdict:
    category: Category
    detail: str = ""                 # empty string, not None — D-02 convention

    @property
    def verdict(self) -> str:        # derived field per D-02
        return "PASS" if self.category is Category.PASS else "FAIL"

    def to_cell_dict(self) -> dict:
        return {
            "category": self.category.value,
            "detail": self.detail,
            "verdict": self.verdict,
        }
```

Dataclass keeps the 3-tuple `(category, detail, verdict)` atomic, gives free `__repr__` for logs, and `frozen=True` means a verdict can't be mutated after construction.

### Pattern 3: `--cidfile` + `docker kill` Timeout (the load-bearing mechanism)

**What:** Wrap `docker run` with a cidfile so we can reap the container on Python timeout.

**When to use:** EVERY `docker run` invocation in the runner. This is non-negotiable for D-03.

**Example:**
```python
# Source: Docker CLI docs + moby/moby#3791 + Python stdlib subprocess docs + cwltool PR#996 pattern
import subprocess
import uuid
import os
from pathlib import Path

def run_cell_with_timeout(docker_cmd: list[str], timeout_s: int) -> tuple[int, str, str, str | None]:
    """Run docker, enforce timeout via --cidfile + docker kill.
    Returns (rc, stdout, stderr, timeout_reason|None).
    """
    # Cidfile: fresh path, DOES NOT pre-create (docker errors if file exists)
    cidfile = Path(f"/tmp/ap-cid-{uuid.uuid4().hex}.cid")
    assert not cidfile.exists(), "UUID collision is cosmically unlikely"

    # Inject --cidfile into the docker run invocation
    # docker_cmd starts with ["docker", "run", ...]
    cmd_with_cid = docker_cmd[:2] + [f"--cidfile={cidfile}"] + docker_cmd[2:]

    try:
        try:
            result = subprocess.run(
                cmd_with_cid,
                timeout=timeout_s,
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode, result.stdout, result.stderr, None
        except subprocess.TimeoutExpired as exc:
            # subprocess.run has already killed the docker CLI and waited.
            # BUT: the daemon is still running the container. Reap via cidfile.
            timeout_reason = f"exceeded timeout={timeout_s}s"
            cid = None
            try:
                if cidfile.exists() and cidfile.stat().st_size > 0:
                    cid = cidfile.read_text().strip()
            except OSError:
                pass
            if cid:
                # SIGKILL by default — docker kill docs confirm
                subprocess.run(
                    ["docker", "kill", cid],
                    timeout=10, check=False, capture_output=True,
                )
                subprocess.run(
                    ["docker", "rm", "-f", cid],
                    timeout=10, check=False, capture_output=True,
                )
            # TimeoutExpired gives us partial stdout/stderr via exc.stdout / exc.stderr
            stdout = (exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = (exc.stderr or b"").decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            return -1, stdout, stderr, timeout_reason
    finally:
        # Cidfile is NOT auto-cleaned by docker — must unlink manually.
        # moby/moby#20766: "the file is just a convenience ... removing it
        # when the container is removed also cannot be done because the client
        # and daemon may not be on the same host."
        try:
            cidfile.unlink(missing_ok=True)
        except OSError:
            pass
```

**Critical gotchas from verified sources:**

1. **Pre-creating the cidfile path breaks it.** `docker run --cidfile=/path` FAILS if the path already exists, even if empty. Use a fresh UUID path and do NOT `touch` it first. Do NOT use `NamedTemporaryFile(delete=False)` — that creates the file. Use `Path(f"/tmp/ap-cid-{uuid.uuid4().hex}.cid")` as a name-only reservation. [VERIFIED: docker/cli#5954 "--cidfile fails if file exists even if empty"]

2. **The cidfile may be empty if docker run fails fast.** moby/moby#3791 documents that a failed `docker run` can leave a zero-length cidfile on disk. Always check `cidfile.exists() and cidfile.stat().st_size > 0` before reading. [VERIFIED: moby/moby#3791]

3. **The cidfile is NOT auto-removed.** Even with `--rm`, even after `docker kill` + `docker rm`, the cidfile persists. The runner MUST `unlink()` it in a `finally` block. [VERIFIED: moby/moby#20766 — "file is just a convenience ... removing it when the container is removed cannot be done"]

4. **subprocess.run(timeout=) already kills the `docker` CLI child and reaps it.** Python stdlib docs: "If the timeout expires, the child process will be killed and waited for. The TimeoutExpired exception will be re-raised after the child process has terminated." So no zombies from the CLI side — the gap is purely the daemon-managed container. [VERIFIED: https://docs.python.org/3/library/subprocess.html § subprocess.run]

5. **`exc.stdout` / `exc.stderr` on TimeoutExpired contain the partial output.** On Python 3.12+ these are already decoded when `text=True`; on 3.10-3.11 they may be bytes. Defensive decoding handles both. [CITED: Python stdlib subprocess § TimeoutExpired]

### Pattern 4: docker build timeout (accept the limitation)

```python
# D-03 acknowledges: "kill the docker build process — but Docker daemon will
# finish its current layer; accept this limitation and document it"
try:
    subprocess.run(
        ["docker", "build", ...],
        timeout=build_timeout_s,
        check=False,
    )
except subprocess.TimeoutExpired:
    # The docker CLI is dead. The buildkit daemon may still finish the layer.
    # There is no BuildKit equivalent of --cidfile to cancel mid-build.
    # Best-effort: dangling image prune (optional — adds complexity).
    return Verdict(Category.BUILD_FAIL, f"build timeout after {build_timeout_s}s")
```

**Limitation documented:** docker/cli#3375 is an open feature request to let `docker build` cancel daemon-side processes on SIGTERM. Until merged, a build-timeout = best-effort subprocess kill + an orphan BuildKit layer cache. Not a blocker — the user has already accepted this in D-03.

### Pattern 5: Docker daemon pre-flight (INFRA_FAIL)

```python
def preflight_docker() -> Verdict | None:
    """Return INFRA_FAIL Verdict if daemon unreachable, None if OK."""
    try:
        result = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            timeout=5,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return Verdict(
                Category.INFRA_FAIL,
                f"docker version exit {result.returncode}: {result.stderr.strip()[:200]}",
            )
        return None
    except subprocess.TimeoutExpired:
        return Verdict(Category.INFRA_FAIL, "docker daemon unresponsive (>5s)")
    except FileNotFoundError:
        return Verdict(Category.INFRA_FAIL, "docker CLI not in PATH")
```

Called once at top of `main()` before anything else. `docker version` is the idiomatic liveness probe because it explicitly connects to the daemon (unlike `docker --version` which only reports the client). [VERIFIED: Docker CLI docs — https://docs.docker.com/reference/cli/docker/version/]

### Anti-Patterns to Avoid

- **Relying on `subprocess.run(timeout=)` alone for container enforcement.** The docker CLI dies; the container keeps running. Always pair with `--cidfile` + `docker kill`.
- **Using `NamedTemporaryFile(delete=False)` for the cidfile.** That creates the file; Docker then errors out because the path exists.
- **Forgetting to unlink the cidfile on success.** `docker run` (with `--rm` or without) does not clean up cidfiles — you'll leave a trail of `.cid` files in `/tmp`.
- **Assuming `docker build` can be cancelled mid-layer.** It cannot, as of Docker 27.x. Document and move on.
- **Adding new required fields to the schema BEFORE migrating recipes.** Lint will fail on the 5 committed recipes. Sequence: migrate → tighten.
- **Hand-rolling category logic in multiple places.** The `Category` enum + `Verdict` dataclass are the single source of truth. `emit_human()` and future `emit_json()` consume them; they don't reimplement the PASS/FAIL derivation.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Container timeout enforcement | Pure `subprocess.run(timeout=)` + hoping | `--cidfile` + `docker kill` + `docker rm -f` | The daemon decouples container lifecycle from CLI lifecycle — killing the CLI doesn't kill the container |
| Container ID capture | Parsing `docker run` stdout (`docker run -d` prints the ID) | `--cidfile` | We run containers in the foreground (not `-d`); stdout is claimed by the agent's output. Cidfile is the only foreground-compatible capture |
| YAML round-trip with comment preservation | Re-writing YAML with string munging | `ruamel.yaml` round-trip (already in use) | Project already uses it via `writeback_cell()`. Comments in recipes document gotchas; preserving them is non-negotiable |
| Schema validation | `if/else` ladders in Python | `jsonschema.Draft202012Validator` (already in use) | `lint_recipe()` already uses this. New fields just appear in schema; no Python code needs touching |
| Python category representation | Dict-typed strings everywhere | `class Category(str, Enum)` | Typos are caught at import time, not runtime. `Category.TIMEOUT.value` is the string for JSON |
| Enum mirror between JSON Schema + Python | Duplicate list in 2 places | Accept duplication for now; Phase 17 (doc-runner sync) will add the sync test | Phase 17 is the roadmap-assigned owner of single-source-of-truth enforcement. Don't solve it here |

**Key insight:** The `docker run --cidfile` pattern is not optional — it's the ONLY supported idiom for foreground-container timeout enforcement. There is no `timeout(1)`-style equivalent built into Docker, and docker-py doesn't solve it either (you'd still need the same pattern via the API). This is why the roadmap called it out explicitly.

## Runtime State Inventory

Not applicable. This phase has no rename/refactor/migration aspect beyond in-recipe YAML field additions, which are code + data changes both captured by the one-shot migration script. No external state (no database records, no long-lived service configs, no OS-registered state, no secrets, no build artifacts) references phase-10 semantics.

**Verified categories (all empty):**
- **Stored data:** None — the runner writes no persistent state; cells are written back to YAML only (authored by contributors).
- **Live service config:** None — no deployed services consume recipe verdicts yet.
- **OS-registered state:** None — no systemd units, no cron, no Task Scheduler entries reference the runner.
- **Secrets/env vars:** None — no env var names change. `OPENROUTER_API_KEY` and friends are untouched.
- **Build artifacts:** `tools/ap_recipe_tools.egg-info/` exists from the Phase 09 `pip install -e tools/[dev]` step. No re-install needed unless package metadata changes (it won't — no `pyproject.toml` edits planned).

## Common Pitfalls

### Pitfall 1: Schema tightens before recipes migrate
**What goes wrong:** Add `required: [category, detail]` to schema → 5 committed recipes fail lint → pytest red → phase blocked.
**Why it happens:** Schema is a declarative contract, but the runtime emitter (migration script) is the only thing that can produce the new shape. If the contract tightens first, you've ordered the work wrong.
**How to avoid:** Strict sequencing in plans: (1) migrate all 5 YAMLs with new fields, (2) run full regression suite (test_recipe_regression + test_lint) — should still pass because new fields are ALLOWED by current schema ONLY if `additionalProperties: false` is set — wait, it IS set. So the migration would fail lint today.
**Correct sequencing:**
- Task A: Update schema to ADD `category` and `detail` as OPTIONAL fields, ADD the 11-value `category` enum.
- Task B: Run migration script on 5 recipes.
- Task C: Tighten schema to make `category` + `detail` REQUIRED on `verified_cells[]` items.
- Task D: Update runner to emit the fields.
- Task E: Add taxonomy tests.

Order A→B→C means lint passes at every commit boundary.

**Warning signs:** `pytest tests/test_lint.py` fails on any of the 5 committed recipes at any intermediate commit.

### Pitfall 2: cidfile path collision / stale cidfiles
**What goes wrong:** Two concurrent runs, same cidfile path → `docker run` errors out on the second. Or: yesterday's failed run left `/tmp/ap-cid-*.cid` → today's run errors.
**Why it happens:** CONTEXT.md §specifics mentions `tempfile.NamedTemporaryFile(delete=False)` — that creates the file, which Docker rejects. Also, cidfile is not auto-cleaned.
**How to avoid:** Use `Path(f"/tmp/ap-cid-{uuid.uuid4().hex}.cid")` (name only, no creation). Unlink in a `finally` block. Add a boot-time cleanup sweep: `for p in Path("/tmp").glob("ap-cid-*.cid"): p.unlink(missing_ok=True)` (safe because the path carries a UUID).
**Warning signs:** `docker: Container ID file already exists ...` error; `/tmp` filling with `.cid` files over time.

### Pitfall 3: TimeoutExpired exc.stdout is bytes on Python 3.10
**What goes wrong:** `detail = exc.stderr[-200:]` raises TypeError because `exc.stderr` is bytes, not str, on older Python even with `text=True`.
**Why it happens:** Python 3.10's `subprocess.TimeoutExpired` sometimes returns raw bytes depending on how the timeout fires relative to stream decoding. Fixed in 3.12+.
**How to avoid:** Defensive decode: `stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")`.
**Warning signs:** Taxonomy test for TIMEOUT throws TypeError instead of returning the verdict.

### Pitfall 4: `docker kill` on an already-dead container
**What goes wrong:** Between reading the cidfile and calling `docker kill`, the container exits on its own (e.g., agent finished right as timeout fires) → `docker kill` errors with "no such container".
**Why it happens:** Race window between subprocess.TimeoutExpired and cleanup.
**How to avoid:** `docker kill` and `docker rm -f` both called with `check=False` + `capture_output=True`. Suppress their errors. The goal is reaping, not confirmation.
**Warning signs:** spurious `Error response from daemon: No such container` lines in the runner log.

### Pitfall 5: Mocking subprocess.run doesn't cover the cidfile path
**What goes wrong:** Taxonomy tests pass in CI but the real `run_cell()` fails at runtime because cidfile logic is only exercised under `TimeoutExpired`, which the mock doesn't raise.
**Why it happens:** The existing `mock_subprocess` fixture in `conftest.py` returns canned `CompletedProcess`; it doesn't know how to raise `TimeoutExpired`.
**How to avoid:** Extend the fixture to accept `raise_timeout=True` mode that makes the fake `run()` raise `subprocess.TimeoutExpired`. Example:
```python
@pytest.fixture
def mock_subprocess_timeout(monkeypatch):
    def _configure(timeout_s=1):
        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout_s, stderr="")
        monkeypatch.setattr(subprocess, "run", fake_run)
    return _configure
```
**Warning signs:** TIMEOUT fixture test "passes" without ever hitting the cidfile branch — check that mock triggers the exception path.

### Pitfall 6: BUILD_FAIL test fixture takes forever
**What goes wrong:** Naïve BUILD_FAIL test actually runs `docker build` on a broken Dockerfile → test suite goes from 1s to 2 min.
**How to avoid:** Mock `subprocess.run` at the `ensure_image()` boundary to simulate non-zero exit with a canned Docker error. Tests are pure Python.
**Warning signs:** `pytest tests/test_categories.py` takes more than a couple seconds.

## Code Examples

### Example 1: Minimal main() refactor sketch

```python
# Source: pattern synthesis from CONTEXT D-01..D-05 + existing run_recipe.py main()
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    # ... existing --lint-all, --lint, argument validation ...

    # NEW: INFRA pre-flight
    infra_verdict = preflight_docker()
    if infra_verdict is not None:
        emit_verdict(infra_verdict, recipe_name="(pre-flight)", model="", wall_s=0.0)
        return 1

    # Existing lint pre-step → LINT_FAIL on error
    if not args.no_lint:
        errors = _lint_single(recipe_path)
        if errors:
            emit_verdict(
                Verdict(Category.LINT_FAIL, f"{len(errors)} schema error(s)"),
                recipe_name=recipe_path.name, model="", wall_s=0.0,
            )
            return 2

    recipe = load_recipe(recipe_path)
    # ...

    # ensure_image() now returns (ok: bool, verdict: Verdict | None)
    image_verdict = ensure_image(recipe, ...)  # emits CLONE_FAIL / BUILD_FAIL / PULL_FAIL
    if image_verdict is not None:
        emit_verdict(image_verdict, ...)
        return 1

    # Per-cell loop; run_cell() returns a Verdict directly
    for model, expected in cells:
        v = run_cell(recipe, ...)
        emit_verdict(v, ...)
```

### Example 2: Taxonomy test fixture for TIMEOUT

```python
# Source: pattern extension of tools/tests/conftest.py::mock_subprocess
# File: tools/tests/test_categories.py (new)
import subprocess
import pytest
from run_recipe import run_cell, Category, Verdict  # new exports

class TestTimeoutCategory:
    def test_timeout_produces_TIMEOUT_verdict(self, monkeypatch, minimal_valid_recipe):
        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["docker", "run"]:
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=1, stderr="")
            # docker kill / docker rm cleanup calls — return success
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
        monkeypatch.setattr(subprocess, "run", fake_run)

        verdict = run_cell(
            minimal_valid_recipe,
            image_tag="ap-recipe-test",
            prompt="hi",
            model="test/model",
            api_key_var="X", api_key_val="y",
            quiet=True,
        )
        assert verdict.category is Category.TIMEOUT
        assert "timeout" in verdict.detail.lower()
        assert verdict.verdict == "FAIL"
```

### Example 3: Schema additions (sketch of the JSON diff)

```json
// Source: tools/ap.recipe.schema.json — additions for phase 10
// In smoke.verified_cells.items.properties:
{
  "category": {
    "type": "string",
    "enum": [
      "PASS", "ASSERT_FAIL", "INVOKE_FAIL",
      "BUILD_FAIL", "PULL_FAIL", "CLONE_FAIL",
      "TIMEOUT", "LINT_FAIL", "INFRA_FAIL",
      "STOCHASTIC", "SKIP"
    ],
    "description": "Authoritative failure category (9 live, 2 reserved for later phases)."
  },
  "detail": {
    "type": "string",
    "description": "Single-line reason for the category. Empty string when category=PASS."
  }
}
// In smoke.verified_cells.items.required (after migration):
// "required": ["model", "verdict", "category", "detail"]
```

### Example 4: One-shot migration script sketch

```python
# Source: reuse existing ruamel.yaml round-trip from run_recipe.py
# File: scripts/migrate_recipes_phase10.py (one-shot; commit, then rm)
from pathlib import Path
from ruamel.yaml import YAML

_y = YAML(typ="rt")
_y.preserve_quotes = True
_y.width = 4096
_y.indent(mapping=2, sequence=4, offset=2)

def migrate(recipe_path: Path) -> None:
    data = _y.load(recipe_path.read_text())
    smoke = data.get("smoke", {})

    for cell in smoke.get("verified_cells", []) or []:
        cell.setdefault("category", "PASS")
        cell.setdefault("detail", "")

    for cell in smoke.get("known_incompatible_cells", []) or []:
        if cell.get("verdict") == "STOCHASTIC":
            # D-04: temporarily map STOCHASTIC → ASSERT_FAIL
            cell["verdict"] = "FAIL"
            cell["category"] = "ASSERT_FAIL"
            cell["detail"] = "flapping verdict — see notes"
        else:
            cell.setdefault("category", "ASSERT_FAIL")
            notes = cell.get("notes", "")
            cell.setdefault("detail", notes.split(".")[0][:120] if notes else "")

    with recipe_path.open("w") as f:
        _y.dump(data, f)

if __name__ == "__main__":
    for p in sorted(Path("recipes").glob("*.yaml")):
        print(f"migrating {p.name}")
        migrate(p)
```

After commit, delete `scripts/migrate_recipes_phase10.py` in the same commit OR the next — reviewers don't need to re-run a one-shot tool.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Binary PASS/FAIL verdict | Categorized `{category, detail, verdict}` | This phase | Downstream consumers (Go orchestrator, Phase 11-17) can route retries/alerts by category |
| `subprocess.run(timeout=)` only | `--cidfile` + `docker kill` + `docker rm -f` | This phase | Runaway containers actually die; no orphan containers accumulate |
| No pre-flight daemon check | `docker version --format ...` at startup | This phase | Friendly error instead of cryptic build failures when Docker is down |
| STOCHASTIC verdict lives in `known_incompatible_cells[]` as a `verdict` string | Same field, but until Phase 15 maps to `category: ASSERT_FAIL` + note | D-04 | Keeps the gate deterministic; Phase 15 re-enables true STOCHASTIC semantics |

**Deprecated/outdated:**
- Nothing; Phase 09's schema + `lint_recipe()` are still authoritative. Phase 10 is additive.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `class Category(str, Enum)` is preferred over `StrEnum` for Python 3.10 compat | §Standard Stack | If the user bumps `requires-python` to `>=3.11` later, planner can migrate to `StrEnum` — zero code risk now |
| A2 | Cidfile under `/tmp/ap-cid-<uuid>.cid` is acceptable on macOS + Linux | §Pattern 3 | macOS restricts `/tmp` less than Linux systemd-tmpfiles; fine for dev workflow. Hetzner (Linux) production use is out of scope for this tool |
| A3 | BuildKit does not expose a cancellation API usable from a Python subprocess wrapper as of Docker 27.x | §Pattern 4 | Verified via docker/cli#3375 (open feature request) — LOW risk |
| A4 | The migration script should be committed as a one-shot and deleted after | §Example 4 | Minor — planner may prefer to keep it under `scripts/` indefinitely; CONTEXT.md §specifics explicitly allows either approach |
| A5 | No new runtime deps needed (stdlib + ruamel.yaml + jsonschema sufficient) | §Standard Stack | Only risk is if planner wants pydantic for nicer validation — would require a `pyproject.toml` edit |
| A6 | Dangling BuildKit layer cleanup after `build.timeout_s` fires is not required | §Pattern 4 | Disk guard at 5 GB floor catches it; CONTEXT D-03 accepts the limitation explicitly |

**Impact summary:** All assumptions are low-risk or user-accepted in CONTEXT.md. No blocker assumptions.

## Open Questions

1. **Should `--global-timeout` (CLI flag) preempt the per-recipe `smoke.timeout_s`?**
   - What we know: D-03 says "Ceiling across the entire runner invocation; overrides the above."
   - What's unclear: In `--all-cells` mode with 3 cells × 60s each, does a `--global-timeout 120` kill the 3rd cell mid-run? Or is it wall time from process start?
   - Recommendation: Planner treats `--global-timeout` as "process wall time ceiling"; if it fires mid-cell, that cell's verdict is TIMEOUT with `detail: "exceeded --global-timeout=120s"`. Cells after the timeout are skipped. Document in CLI help.

2. **What's the exit code mapping when emitting categories?**
   - What we know: Existing code returns 0/1/2 based on drift and PASS.
   - What's unclear: Does `LINT_FAIL` return 2 (validation error, like today) while `INFRA_FAIL` returns something else?
   - Recommendation: Keep existing exit codes. 0 = PASS, 1 = any non-PASS from the runner, 2 = schema/usage error (LINT_FAIL, missing args). INFRA_FAIL returns 1 (it's a runtime failure, not a usage error).

3. **Should the migration script live under `scripts/` or `tools/migrations/`?**
   - What we know: No existing migrations directory; tools/ is the Python home.
   - What's unclear: Project convention for one-shot scripts.
   - Recommendation: `scripts/migrate_recipes_phase10.py`, commit with a big "ONE-SHOT; commit, then delete" header. Planner's final call.

4. **Do we need a regression test that the cidfile is actually unlinked?**
   - What we know: Pitfall 2 flags the risk.
   - What's unclear: Whether a boot-time `/tmp/ap-cid-*` sweep is over-engineering.
   - Recommendation: Add a single test that the `TIMEOUT` code path unlinks the cidfile; skip the boot-time sweep (let the UUID guarantee uniqueness). Revisit if stale cidfiles actually show up in the wild.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker Engine | Taxonomy tests (for real TIMEOUT fixtures if desired), but NOT for unit tests | ✓ (per Phase 02 prerequisite) | 24.x+ assumed | Tests mock `subprocess.run` — no live Docker needed |
| Python 3.10+ | Everything | ✓ | ≥3.10 (per pyproject) | — |
| `ruamel.yaml` | Recipe round-trip | ✓ | ≥0.17.21 | — |
| `jsonschema` | Lint | ✓ | ≥4.23 | — |
| `pytest` | Test suite | ✓ | ≥8.0 | — |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None — all needed infrastructure already exists from Phase 09.

## Validation Architecture

Nyquist validation is enabled (`workflow.nyquist_validation: true` in `.planning/config.json`).

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | `tools/pyproject.toml` (`[tool.pytest.ini_options]` section) |
| Quick run command | `cd tools && pytest tests/test_categories.py -x` |
| Full suite command | `cd tools && pytest -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| D-01 | 11-value category enum | unit | `pytest tools/tests/test_categories.py::TestCategoryEnum -x` | ❌ Wave 0 |
| D-01 (PASS) | `run_cell` returns PASS category on clean run | unit | `pytest tools/tests/test_categories.py::TestPassCategory -x` | ❌ Wave 0 |
| D-01 (ASSERT_FAIL) | non-matching pass_if → ASSERT_FAIL | unit | `pytest tools/tests/test_categories.py::TestAssertFailCategory -x` | ❌ Wave 0 |
| D-01 (INVOKE_FAIL) | docker run rc != 0 → INVOKE_FAIL | unit | `pytest tools/tests/test_categories.py::TestInvokeFailCategory -x` | ❌ Wave 0 |
| D-01 (BUILD_FAIL) | docker build rc != 0 → BUILD_FAIL | unit | `pytest tools/tests/test_categories.py::TestBuildFailCategory -x` | ❌ Wave 0 |
| D-01 (PULL_FAIL) | docker pull rc != 0 → PULL_FAIL | unit | `pytest tools/tests/test_categories.py::TestPullFailCategory -x` | ❌ Wave 0 |
| D-01 (CLONE_FAIL) | git clone rc != 0 → CLONE_FAIL | unit | `pytest tools/tests/test_categories.py::TestCloneFailCategory -x` | ❌ Wave 0 |
| D-01 (TIMEOUT) | TimeoutExpired → TIMEOUT + cidfile-path docker kill | unit | `pytest tools/tests/test_categories.py::TestTimeoutCategory -x` | ❌ Wave 0 |
| D-01 (LINT_FAIL) | Schema violation → LINT_FAIL (covered by Phase 09 tests; add category assertion) | unit | `pytest tools/tests/test_categories.py::TestLintFailCategory -x` | ❌ Wave 0 |
| D-01 (INFRA_FAIL) | `docker version` non-zero → INFRA_FAIL | unit | `pytest tools/tests/test_categories.py::TestInfraFailCategory -x` | ❌ Wave 0 |
| D-02 | Verdict dataclass has `category`, `detail`, derived `verdict` | unit | `pytest tools/tests/test_categories.py::TestVerdictShape -x` | ❌ Wave 0 |
| D-03 | cidfile created, read, unlinked in TIMEOUT path | unit | `pytest tools/tests/test_categories.py::TestCidfileLifecycle -x` | ❌ Wave 0 |
| D-04 | All 5 recipes pass lint after migration | integration (regression) | `pytest tools/tests/test_recipe_regression.py -x` | ✅ exists |
| D-04 | All 5 recipes pass lint (schema reads new fields) | integration | `pytest tools/tests/test_lint.py -x` | ✅ exists |
| D-04 | ruamel round-trip still idempotent | integration | `pytest tools/tests/test_roundtrip.py -x` | ✅ exists |
| D-05 | `emit_human(Verdict)` produces the D-05 format | unit | `pytest tools/tests/test_categories.py::TestEmitFormat -x` | ❌ Wave 0 |
| P05 exit gate | "deliberately-sleeping container produces TIMEOUT within smoke.timeout_s + 5s" | smoke (needs live Docker) | *manual* — covered by existing 5-recipe regression in CI | deferred to manual QA |

### Sampling Rate

- **Per task commit:** `cd tools && pytest tests/test_categories.py -x` (< 1s, all mocked)
- **Per wave merge:** `cd tools && pytest -x` (full suite; < 5s; still all mocked)
- **Phase gate:** Full suite green + spot-check on hermes recipe with real Docker + real short timeout (e.g., `smoke.timeout_s: 1`) to confirm the TIMEOUT path actually kills a container in the wild.

### Wave 0 Gaps

- [ ] `tools/tests/test_categories.py` — covers all 9 live categories
- [ ] Extend `tools/tests/conftest.py::mock_subprocess` to accept `raise_timeout=True` mode for TIMEOUT fixture
- [ ] Regression baseline: run `pytest` once on current main to confirm 5 recipes pass, then again after migration to confirm still passes
- [ ] Taxonomy test for INFRA_FAIL — mocks `subprocess.run(["docker", "version", ...])` to return non-zero
- [ ] Verdict dataclass unit test (`test_verdict_derives_pass_for_pass_category`, `test_verdict_derives_fail_for_others`)

No new test framework install needed — pytest already installed per Phase 09.

## Security Domain

Security enforcement not listed as disabled; include minimal applicable controls.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Runner doesn't auth users; agent-side API keys handled per-recipe |
| V3 Session Management | no | Stateless runner |
| V4 Access Control | no | Stateless runner |
| V5 Input Validation | yes | jsonschema Draft 2020-12 via `lint_recipe()` (existing) — new fields participate automatically |
| V6 Cryptography | no | No crypto primitives; API keys are pass-through via env |
| V7 Error Handling | yes | Categories are the error-handling contract. DO NOT log full API keys in `detail` strings |
| V8 Data Protection | yes (minor) | `detail` strings derived from subprocess stderr must NOT echo the injected `api_key_val` |

### Known Threat Patterns for this Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API key leak via stderr echoed into `detail` | Information Disclosure | Existing pattern in `run_cell()` redacts `api_key_var=<REDACTED>` in logs; extend the same redaction to any stderr captured into `detail` |
| Runaway container consumes host resources | Denial of Service | D-03 timeout enforcement directly mitigates this |
| Cidfile path collision allows privilege confusion | Tampering (weak) | UUID-suffixed path under `/tmp` is non-guessable; runner is single-user scoped; LOW severity for a dev tool |
| Malformed recipe triggers unexpected runner behavior | Tampering | jsonschema `additionalProperties: false` (existing) + new required fields |

**Security notes for planner:**
- The `detail` field is emitted to stdout. When it's derived from subprocess stderr (e.g., "docker build exit 125: {stderr_tail}"), run it through the same redaction as the existing `safe_cmd` pattern in `run_cell()` — search for `{api_key_var}=` substrings and replace with `<REDACTED>`.
- Exit codes are user-visible but don't carry secrets.

## Sources

### Primary (HIGH confidence)

- **Docker CLI — `docker run --cidfile`** [VERIFIED: https://docs.docker.com/reference/cli/docker/container/run/] — "Docker writes the container ID out to a file of your choosing ... If the file exists already, Docker returns an error."
- **Docker CLI — `docker kill`** [VERIFIED: https://docs.docker.com/reference/cli/docker/container/kill/] — SIGKILL by default; any signal via `--signal`; caveat about shell-form entrypoints not forwarding signals.
- **Python stdlib `subprocess`** [VERIFIED: https://docs.python.org/3/library/subprocess.html § subprocess.run] — TimeoutExpired behavior: "If the timeout expires, the child process will be killed and waited for. The TimeoutExpired exception will be re-raised after the child process has terminated."
- **moby/moby#3791** [VERIFIED: https://github.com/moby/moby/issues/3791] — "Failed `docker run` command leaves zero-length cidfile on disk, blocks subsequent `docker run`"
- **docker/cli#5954** [VERIFIED: https://github.com/docker/cli/issues/5954] — "--cidfile fails if file exists even if empty"
- **moby/moby#20766** [VERIFIED: https://github.com/moby/moby/issues/20766] — Cidfile is not auto-removed when container dies; "removing it when the container is removed cannot be done because the client and daemon may not be on the same host."
- **docker/cli#3375** [VERIFIED: https://github.com/docker/cli/issues/3375] — Open feature request documenting that `docker build` cannot currently cancel daemon-side processes via the CLI.
- **SWE-bench `constants/__init__.py`** [VERIFIED: https://raw.githubusercontent.com/SWE-bench/SWE-bench/main/swebench/harness/constants/__init__.py] — verbatim definitions: `APPLY_PATCH_FAIL = ">>>>> Patch Apply Failed"`, `RESET_FAILED = ">>>>> Reset Failed"`, `TESTS_ERROR = ">>>>> Tests Errored"`, `TESTS_TIMEOUT = ">>>>> Tests Timed Out"`, `class ResolvedStatus(Enum): NO = "RESOLVED_NO"; PARTIAL = "RESOLVED_PARTIAL"; FULL = "RESOLVED_FULL"`
- **Inspect AI `log/_log.py`** [VERIFIED: https://raw.githubusercontent.com/UKGovernmentBEIS/inspect_ai/main/src/inspect_ai/log/_log.py] — `EvalSampleLimitType = Literal["context", "time", "working", "message", "token", "cost", "operator", "custom"]`; `EvalSampleLimit(BaseModel)` with `type: EvalSampleLimitType` + `limit: float`.
- **cwltool PR#996** [CITED: https://github.com/common-workflow-language/cwltool/pull/996] — Confirms the cidfile + docker kill pattern as an established idiom in production Python tools.
- **Existing project state** [VERIFIED: read] — `tools/run_recipe.py`, `tools/ap.recipe.schema.json`, `tools/tests/conftest.py`, `tools/tests/test_pass_if.py`, `tools/pyproject.toml`, `recipes/{hermes,openclaw,picoclaw,nullclaw,nanobot}.yaml`, `.planning/phases/10-error-taxonomy-timeout-enforcement/10-CONTEXT.md`, `.planning/FRAMEWORK-MATURITY-ROADMAP.md`, `.planning/phases/09-spec-lint-test-harness-foundations/09-01-SUMMARY.md`.

### Secondary (MEDIUM confidence)

- DeepWiki SWE-bench overview — https://deepwiki.com/SWE-bench/SWE-bench — confirms ResolvedStatus enum location; used to triangulate constant definitions.
- Python docs § `tempfile.NamedTemporaryFile(delete=False)` — confirms the "create file + get name" pattern we are explicitly avoiding for cidfile.

### Tertiary (LOW confidence)

- None relied on. All critical claims map to primary sources.

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — all deps already present in Phase 09; no new choices.
- Architecture patterns (cidfile + docker kill): **HIGH** — verified against Docker CLI docs, Python stdlib docs, 3 moby GitHub issues, and the cwltool reference implementation.
- Pitfalls: **HIGH** — each pitfall is backed by a verified Docker issue or Python docs section.
- Prior-art shapes: **HIGH** — verbatim source from SWE-bench (constants + ResolvedStatus enum) and Inspect AI (EvalSampleLimitType Literal) pulled directly from GitHub main branches.
- Migration mechanics: **HIGH** — mechanism already proven in Phase 09 (ruamel round-trip in `writeback_cell()`); one-shot script is straightforward extension.
- `docker build` timeout limitation: **HIGH** — verified as open issue (docker/cli#3375).
- Taxonomy test patterns: **HIGH** — extension of existing `conftest.py::mock_subprocess` fixture.

**Research date:** 2026-04-16
**Valid until:** 2026-05-16 (30 days — stable because all primary sources are Docker CLI / Python stdlib / verbatim open-source snapshots)

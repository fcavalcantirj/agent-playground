# Agent Recipe Format: Technical Research

Below are 7 research documents, one per project, separated by horizontal rules. Each is named and formatted as requested.

---

# `research/metr.md`

# METR Task Standard — Technical Research

**TL;DR:**
- **Steal:** The `TaskFamily` class contract — `standard_version` declaration, `get_tasks()` → dict pattern, `score()` / `intermediate_score()` split, and `manifest.yaml` for resource declarations. Clean separation of install-time vs. run-time hooks.
- **Doesn't apply:** No YAML config — everything is Python classes + a sidecar `manifest.yaml`. No retry/N-of-M logic, no compose support, no standardized output log schema. Wall-time enforcement is explicitly out of scope.
- **Read end-to-end:** [`STANDARD.md`](https://github.com/METR/task-standard/blob/main/STANDARD.md) — the full normative spec in one file.

---

### Q1. Full schema shape for a task

A "task" is a Python `TypedDict` (custom per family) plus a `TaskFamily` class with required/optional static methods:

```python
from typing import TypedDict

class Task(TypedDict):
    # Arbitrary per-family fields — user-defined
    ...

class TaskFamily:
    # ── REQUIRED ──────────────────────────────
    standard_version: str = "0.5.0"           # semver (REQUIRED class attr)

    @staticmethod
    def get_tasks() -> dict[str, Task]: ...    # REQUIRED

    @staticmethod
    def get_instructions(t: Task) -> str: ...  # REQUIRED

    # ── OPTIONAL ──────────────────────────────
    required_environment_variables: list[str] = []

    @staticmethod
    def install() -> None: ...                 # runs as root at build time

    @staticmethod
    def start(t: Task) -> None: ...            # runs as root at task start

    @staticmethod
    def get_permissions(t: Task) -> list[str]: ...  # e.g. ["full_internet"]

    @staticmethod
    def get_aux_vm_spec(t: Task) -> VMSpec | None: ...

    @staticmethod
    def score(t: Task, submission: str) -> float | None: ...

    @staticmethod
    def intermediate_score(t: Task) -> tuple[float, str] | None: ...

    @staticmethod
    def aggregate_scores(t: Task, score_log: list) -> float | None: ...

    @staticmethod
    def teardown(t: Task) -> None: ...
```

**Constraint:** A TaskFamily MUST NOT implement both `score` and `intermediate_score`.

**Minimal task** (`examples/reverse_hash/reverse_hash.py`):

```python
class Task(TypedDict):
    word: str
    hash: str

class TaskFamily:
    standard_version = "0.5.0"

    @staticmethod
    def get_tasks() -> dict[str, Task]:
        words = ["abandon", "reliable", "whelk"]
        return {w: {"word": w, "hash": hashlib.sha256(w.encode()).hexdigest()} for w in words}

    @staticmethod
    def get_instructions(t: Task) -> str:
        return f"Find the word whose SHA-256 hash is: {t['hash']}"

    @staticmethod
    def score(t: Task, submission: str) -> float | None:
        return float(int(submission == t["word"]))
```

**Complex task** adds `install()`, `start()`, `get_permissions()`, `get_aux_vm_spec()`, `required_environment_variables`, `intermediate_score()`, and a companion `manifest.yaml`.

### Q2. Resource limits (memory, CPU, network, wall time)

**Declaration:** `manifest.yaml` alongside the task `.py` file declares compute needs (`cpu_count_range`, `ram_gib_range`, `gpu`, `disk_gib`). Network access is controlled by `get_permissions()` — returning `["full_internet"]` allows unrestricted access; otherwise the environment MUST NOT have internet except whitelisted LLM API endpoints.

**Enforcement by the driver:**

- **CPU/memory:** The `DriverImpl` (TypeScript, `drivers/`) translates `manifest.yaml` values into Docker `--cpus` and `--memory` flags.
- **Network:** Docker networking + **iptables** rules. The `Dockerfile` installs `iptables`, `iproute2`, `iputils-ping`, `openresolv` for this purpose.
- **Wall time:** **Not part of the standard.** Explicitly left to the evaluation platform.

```dockerfile
# Dockerfile:L46-L56 — network enforcement tooling
RUN apt-get install -yq \
    ca-certificates iproute2 iptables iputils-ping \
    libnss3-tools openresolv openssh-server vim
```

File refs: [`Dockerfile`](https://github.com/METR/task-standard/blob/main/Dockerfile), [`STANDARD.md`](https://github.com/METR/task-standard/blob/main/STANDARD.md)

### Q3. Stochastic / flaky task handling

**Does not exist.** There is no retry mechanism, no multi-run aggregation, and no "require N-of-M passes" gate in the Task Standard or reference driver.

The `aggregate_scores` method aggregates intermediate scores *within a single run*, not across multiple runs. Any retry/N-of-M logic must be implemented by the evaluation platform (e.g., METR's Vivaria).

File ref: [`STANDARD.md`](https://github.com/METR/task-standard/blob/main/STANDARD.md)

### Q4. Docker / compose.yml integration

**Docker Compose is not used.** The standard uses a single `Dockerfile` (repo root, ~178 lines) with multi-stage builds (`task-shared` → `task-cpu` → `task`).

**Build args:** `TASK_FAMILY_NAME`, `IMAGE_DEVICE_TYPE` (`cpu` | `gpu`).

**Secrets injection** uses BuildKit secret mounts:

```dockerfile
RUN --mount=type=ssh --mount=type=secret,id=env-vars \
    python - <<EOF
    with open("/run/secrets/env-vars", "r") as file:
        for i, line in enumerate(file):
            key, value = line.split("=", 1)
            os.environ[key] = value
    if hasattr(TaskFamily, "install"):
        TaskFamily.install()
    EOF
```

**Multi-machine** setups use the aux VM mechanism (`get_aux_vm_spec()` → AWS EC2), not additional containers. The standard states "Docker is not necessary to conform to the Task Standard."

File ref: [`Dockerfile`](https://github.com/METR/task-standard/blob/main/Dockerfile)

### Q5. Task versioning

**Mechanism:** `standard_version` class attribute on `TaskFamily` (semver string). Currently at **`0.5.0`**.

```python
class TaskFamily:
    standard_version = "0.5.0"
```

The standard is pre-1.0, so breaking changes can occur in minor bumps. The design enables **adaptor-based compatibility** — runtimes read `standard_version` and apply version-specific behavior. No formal migration tooling exists. Changes documented via [GitHub Releases](https://github.com/METR/task-standard/releases):

- **v0.5.0:** `VMSpec` gets `build_steps`
- **v0.4.0:** `required_environment_variables` set during `install()`
- **v0.3.0:** `teardown` method added
- **v0.2.0:** `get_aux_vm_spec` added

### Q6. Per-run output schema

**The Task Standard does not define a per-run output JSON schema.** It specifies scoring interfaces only:

```python
# End scoring
TaskFamily.score(t, submission) -> float | None

# Intermediate scoring
TaskFamily.intermediate_score(t) -> tuple[float, str] | None

# Aggregation (within a single run)
TaskFamily.aggregate_scores(t, score_log) -> float | None
```

The driver-level TypeScript types (`drivers/Driver.ts`) include `TaskSetupData` and scoring method signatures, but the actual log/result envelope is **platform-specific** (e.g., METR's Vivaria defines its own). Agent reads instructions from `/home/agent/instructions.txt` and writes submission to `/home/agent/submission.txt`.

---

# `research/promptfoo.md`

# Promptfoo Assertions — Technical Research

**TL;DR:**
- **Steal:** The `not-` prefix for negation on any assertion type, `assert-set` with fractional `threshold` for OR/at-least-K composition, and the `javascript`/`python` escape hatch with `GradingResult` return shape. The assertion taxonomy is the most complete of any eval framework.
- **Doesn't apply:** No per-test "require M of N" pass gate (only global `--repeat` + pass-rate threshold). Custom assertions run unsandboxed on the host. No explicit grader cost budget field.
- **Read end-to-end:** [Assertions & Metrics overview](https://www.promptfoo.dev/docs/configuration/expected-outputs/) — the taxonomy entry point with links to every type.

---

### Q1. Complete list of assertion.type values

#### Deterministic — string/structure

| Type | `value` shape | Notes |
|---|---|---|
| `equals` | `string \| object` | Exact match |
| `contains` | `string` | Substring |
| `icontains` | `string` | Case-insensitive substring |
| `starts-with` | `string` | Prefix match |
| `contains-all` | `string[]` | All substrings present |
| `contains-any` | `string[]` | At least one present |
| `icontains-all` | `string[]` | Case-insensitive all |
| `icontains-any` | `string[]` | Case-insensitive any |
| `regex` | `string` (pattern) | Regex match |
| `is-json` | optional JSON Schema | Valid JSON, optionally validated |
| `contains-json` | optional JSON Schema | Contains valid JSON |
| `is-xml` | optional `{requiredElements}` | Valid XML |
| `contains-xml` | same | Contains XML |
| `is-html` | none | Valid HTML |
| `contains-html` | none | Contains HTML |
| `is-sql` | optional `{databaseType, allowedTables, allowedColumns}` | Valid SQL |
| `contains-sql` | none | Contains SQL |
| `is-refusal` | none | Model refusal detection |
| `word-count` | `number \| {min, max}` | Word count range |

#### Deterministic — similarity/scoring

| Type | `value` | `threshold` default |
|---|---|---|
| `rouge-n` | reference string | 0.75 |
| `bleu` | reference string | 0.5 |
| `gleu` | reference string | 0.5 |
| `meteor` | reference string | 0.5 |
| `levenshtein` | reference string | max edit distance |
| `f-score` | — | score threshold |

#### Deterministic — runtime/cost

| Type | `threshold` unit |
|---|---|
| `latency` | milliseconds |
| `cost` | USD |
| `perplexity` | max perplexity |
| `perplexity-score` | 0–1 (higher=better) |
| `finish-reason` | expected reason string |

#### Function/tool validation

`is-valid-function-call`, `is-valid-openai-function-call`, `is-valid-openai-tools-call`, `tool-call-f1`

#### Trace/trajectory

`trace-span-count`, `trace-span-duration`, `trace-error-spans`, `skill-used`, `trajectory:tool-used`, `trajectory:tool-args-match`, `trajectory:tool-sequence`, `trajectory:step-count`

#### Custom code

`javascript`, `python`, `ruby`, `webhook`

#### Model-graded

`llm-rubric`, `search-rubric`, `model-graded-closedqa`, `factuality`, `g-eval`, `answer-relevance`, `pi`, `similar`, `classifier`, `moderation`, `select-best`, `max-score`, `context-faithfulness`, `context-recall`, `context-relevance`, `conversation-relevance`, `trajectory:goal-success`

#### Meta

`assert-set` (groups assertions with threshold), `guardrails`

Every type supports the `not-` prefix for negation.

### Q2. Negative assertions and boolean composition

**NOT:** Prepend `not-` to any type:

```yaml
assert:
  - type: not-contains
    value: 'sorry'
  - type: not-is-json
  - type: not-rouge-n
    threshold: 0.75
    value: hello world
```

**AND (implicit):** Multiple assertions in `assert:` are implicitly AND — all must pass.

**OR via `assert-set`:**

```yaml
assert:
  - type: assert-set
    threshold: 0.5        # at least 50% of children must pass
    assert:
      - type: contains
        value: 'option A'
      - type: contains
        value: 'option B'
```

With `threshold: 0` → pure OR. Without threshold → AND.

**Weighted scoring:**

```yaml
tests:
  threshold: 0.5
  assert:
    - type: equals
      value: 'Hello'
      weight: 2
    - type: contains
      value: 'world'
      weight: 1
```

No native `any-of`/`all-of` keywords beyond `assert-set`. Complex boolean logic requires `javascript`/`python` assertions.

### Q3. Determinism / retries

**`--repeat N`** runs each test case N times:

```yaml
commandLineOptions:
  repeat: 3
  cache: false   # important: cache replays identical results
```

**No built-in "require M of N"** per test. Global pass-rate threshold only:

```bash
PROMPTFOO_PASS_RATE_THRESHOLD=0.8 promptfoo eval --repeat 5
```

Feature requests exist ([#5947](https://github.com/promptfoo/promptfoo/issues/5947), [#5847](https://github.com/promptfoo/promptfoo/issues/5847)) for per-test pass^N semantics — not yet implemented.

**Retry on errors:**

```bash
promptfoo eval --retry-errors    # retries all ERROR results from latest eval
promptfoo retry <evalId>         # retries errors in a specific eval
```

### Q4. LLM-graded assertions

**Pinning the grader model+version** — per-assertion:

```yaml
assert:
  - type: llm-rubric
    value: 'Is not apologetic'
    provider: openai:gpt-4o-2024-11-20
```

Per-suite:

```yaml
defaultTest:
  options:
    provider:
      id: openai:gpt-4o-2024-11-20
      config:
        temperature: 0
```

**Custom rubric prompt:**

```yaml
defaultTest:
  options:
    rubricPrompt: |
      [
        {"role": "system", "content": "Grade output. Return JSON {pass, score, reason}"},
        {"role": "user", "content": "Output: {{ output }}\nRubric: {{ rubric }}"}
      ]
```

**No explicit `costBudget` field** for grading. Cost control is indirect: choose a cheaper model, use caching (on by default), or use `cost` assertion on the *primary* call only.

### Q5. Custom assertion escape hatch (JavaScript, Python)

**JavaScript** — runs in the **host Node.js process**, no sandbox. Full filesystem/network access.

```typescript
// Function signature
(output: string, context: {
  prompt: string | undefined;
  vars: Record<string, string | object>;
  test: AtomicTestCase;
  config?: Record<string, any>;
  provider: ApiProvider | undefined;
  providerResponse: ProviderResponse | undefined;
}) => boolean | number | GradingResult | Promise<...>

// GradingResult shape
{ pass: boolean; score: number; reason: string;
  componentResults?: GradingResult[]; namedScores?: Record<string, number>; }
```

**Python** — runs as a **subprocess** (`python` binary), no sandbox. Override: `PROMPTFOO_PYTHON=/path/to/python3.11`.

```python
def get_assert(output: str, context: dict) -> Union[bool, float, dict]:
    return {'pass': True, 'score': 0.75, 'reason': 'Looks good'}
```

**Both have unrestricted host access.** They can read files, make HTTP calls, import any library.

### Q6. Cost / latency assertions

**Cost data source:** `ProviderResponse.cost` field (USD). Built-in OpenAI provider calculates from token usage × model pricing. Custom providers must return `cost`.

**Latency data source:** Wall-clock time measured by promptfoo between request send and response receive.

```yaml
assert:
  - type: cost
    threshold: 0.001   # fail if > $0.001
  - type: latency
    threshold: 5000     # fail if > 5000ms
```

**⚠️ Caching interaction:** `latency` requires `--no-cache` — cached responses return instantly, making the assertion meaningless. `cost` is similarly affected since cached calls typically don't incur real cost.

```yaml
commandLineOptions:
  cache: false
```

---

# `research/inspect_ai.md`

# Inspect AI (UK AISI) — Technical Research

**TL;DR:**
- **Steal:** `multi_scorer()` with reducer vocabulary (`mode`, `mean`, `max`, `at_least(k)`, `pass_at(k)`), the `EvalLog` Pydantic schema with nested `EvalSample`/`EvalScore` types, and the multi-layer timeout system (sample time/working/message/token/cost limits + sandbox exec timeout + model request timeout).
- **Doesn't apply:** Sandbox isolation is delegated to the container runtime (Docker/K8s) — Inspect itself doesn't enforce user namespacing or read-only rootfs. No YAML config format.
- **Read end-to-end:** [`src/inspect_ai/log/_log.py`](https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/src/inspect_ai/log/_log.py) — the full `EvalLog` type hierarchy, or the [errors and limits docs](https://inspect.aisi.org.uk/errors-and-limits.html).

---

### Q1. Scorer composition

**Two mechanisms:**

**1. List of scorers** — each runs independently, producing named scores:

```python
Task(
    dataset=dataset,
    solver=[generate()],
    scorer=[includes(), model_graded_qa()],  # both run, both logged
)
```

**2. `multi_scorer()` with reducer** — aggregates into one `Score`:

```python
from inspect_ai.scorer import multi_scorer

multi_scorer(
    scorers=[model_graded_qa(model=m) for m in models],
    reducer="mode"  # majority vote
)
```

**Reducer vocabulary:**

| Reducer | Behavior |
|---|---|
| `"mode"` | Most frequent score value |
| `"max"` | Maximum score |
| `"mean"` | Mean of scores |
| `"at_least(k)"` | True if ≥k scores pass |
| `"pass_at(k)"` | P(≥1 correct in k) per pass@k formula |
| Custom `ScoreReducer` | `def reduce(scores: list[Score]) -> Score` |

Files: `src/inspect_ai/scorer/_multi.py`, `src/inspect_ai/scorer/_reducer.py`
Docs: [inspect.aisi.org.uk/scorers.html#sec-multiple-scorers](https://inspect.aisi.org.uk/scorers.html#sec-multiple-scorers)

### Q2. sandbox() primitive

`sandbox()` returns a `SandboxEnvironment` instance — an **abstract base class** with pluggable backends:

| Provider | Isolation |
|---|---|
| `docker` | Docker Compose, per-sample containers |
| `local` | Host filesystem, no isolation |
| `k8s` | K8s pod per sample |
| `modal`, `daytona`, `ec2`, `proxmox` | Cloud/VM backends |

**Interface:**

```python
class SandboxEnvironment:
    async def exec(self, cmd, input=None, cwd=None, env={},
                   user=None, timeout=None) -> ExecResult[str]
    async def write_file(self, file: str, contents: str | bytes) -> None
    async def read_file(self, file: str, text: bool = True) -> str | bytes
```

**Inspect does NOT enforce** user namespacing, read-only rootfs, or network policy at the framework level. These are delegated to the container runtime config:

```python
from inspect_ai.util import ComposeConfig, ComposeService

config = ComposeConfig(services={
    "default": ComposeService(
        image="python:3.12-bookworm",
        mem_limit="512m",        # per-task memory
        cpus=1.0,                # per-task CPU
        network_mode="none",     # network isolation
    )
})
Task(..., sandbox=SandboxEnvironmentSpec("docker", config))
```

Resource caps: `max_sandboxes` (default `2 * cpu_count`), `MAX_EXEC_OUTPUT_SIZE` (10 MiB), `MAX_READ_FILE_SIZE` (100 MiB).

File: `src/inspect_ai/util/_sandbox/environment.py`

### Q3. Eval log schema

**Class: `EvalLog`** (Pydantic BaseModel) in `src/inspect_ai/log/_log.py`:

```python
class EvalLog(BaseModel):
    version: int
    status: Literal["started", "success", "cancelled", "error"]
    eval: EvalSpec           # task ID, model, config, created, dataset, revision
    plan: EvalPlan | None    # solver steps
    results: EvalResults | None   # aggregated scores & metrics
    stats: EvalStats | None       # token usage, timing
    error: EvalError | None       # top-level error if status=="error"
    samples: list[EvalSample] | None  # per-sample data
    reductions: EvalSampleReductions | None
    invalidated: bool | None
    location: str | None
```

**Nested types:**
- `EvalSample`: `id, epoch, input, target, messages, output, scores, metadata, error, limit, events`
- `EvalResults`: `scores: list[EvalScore]` (each has `name`, `scorer`, `params`, `metrics: dict[str, EvalMetric]`)
- `EvalError`: `message: str, traceback: str, traceback_ansi: str`

**File format:** `.eval` (default) — zstd-compressed binary with message deduplication (~1/8 of JSON). Legacy `.json` still supported. Schema available via `inspect log schema`.

Docs: [inspect.aisi.org.uk/eval-logs.html](https://inspect.aisi.org.uk/eval-logs.html)

### Q4. Timeout enforcement

Inspect enforces limits at **5+ layers:**

| Layer | Config | Scope |
|---|---|---|
| Sample `time_limit` | `Task(time_limit=900)` or `--time-limit` | Per-sample wall clock |
| Sample `working_limit` | `Task(working_limit=600)` | Per-sample excluding wait/retry |
| Sample `message_limit` | `Task(message_limit=30)` | Per-sample message count |
| Sample `token_limit` | `Task(token_limit=512000)` | Per-sample total tokens |
| Sample `cost_limit` | `Task(cost_limit=2.00)` | Per-sample cost in USD |
| Sandbox exec timeout | `sandbox().exec(timeout=120)` | Per-command in container |
| Tool timeout | `bash(timeout=120)` | Per-tool-call |
| Model request timeout | `--timeout` / `--timeout-attempt` | Per-API-call |

Exceeding any limit raises `LimitExceededError`, and the sample is scored as-is.

Files: `src/inspect_ai/util/_limit.py`, `src/inspect_ai/_eval/task/run.py`, `src/inspect_ai/model/_model.py`

### Q5. Error taxonomy

**Top-level:** `EvalStatus = Literal["started", "success", "cancelled", "error"]`

**Per-sample errors:** `EvalSample.error: EvalError | None` (solver/scorer crash), `EvalSample.limit: EvalSampleLimit | None` (limit hit).

```python
class EvalSampleLimit(BaseModel):
    type: str       # "time", "working", "message", "token", "cost", "custom"
    limit: int
    usage: int | float
```

**Tool-level errors** — `ToolError.type`:

```python
type: Literal[
    'parsing', 'timeout', 'unicode_decode', 'permission',
    'file_not_found', 'is_a_directory', 'limit', 'approval',
    'unknown', 'output_limit'
]
```

| Category | Where | Field |
|---|---|---|
| Eval crash/interrupt | `EvalLog.status="error"`, `EvalLog.error` | `EvalError` |
| Eval cancelled | `EvalLog.status="cancelled"` | — |
| Sample solver/scorer error | `EvalSample.error` | `EvalError` |
| Sample limit hit | `EvalSample.limit` | `EvalSampleLimit` |
| Tool error | `ToolEvent.error` | `ToolError` with `.type` |

No single enum for all categories — taxonomy is distributed across `EvalStatus`, `EvalError`, `EvalSampleLimit`, and `ToolError.type`.

Files: `src/inspect_ai/log/_log.py`, `src/inspect_ai/tool/_tool_error.py`
Docs: [inspect.aisi.org.uk/errors-and-limits.html](https://inspect.aisi.org.uk/errors-and-limits.html)

---

# `research/swe_bench.md`

# SWE-bench Docker Evaluation Harness — Technical Research

**TL;DR:**
- **Steal:** The 3-tier image hierarchy (base → env → instance) with content-hash-based image tags, and the `TestSpec` class that generates deterministic `setup_env.sh` / `setup_repo.sh` scripts per instance. The `ResolvedStatus` enum and `TestStatus` enum are clean failure taxonomies.
- **Doesn't apply:** No YAML config — task definitions are JSON datasets + Python constants maps. No built-in image eviction/GC policy. Base images are NOT digest-pinned (reproducibility gap).
- **Read end-to-end:** [`swebench/harness/docker_build.py`](https://github.com/princeton-nlp/SWE-bench/blob/main/swebench/harness/docker_build.py) — the full 3-tier build logic.

---

### Q1. Image-per-instance pattern

**3-tier hierarchy:**

```
┌─────────────────────────────┐
│  Instance: sweb.eval.x86_64.<id>        │  Per task (2,294 total)
│  - git clone → git reset --hard <SHA>   │
│  - pip install -e . (instance deps)     │
├─────────────────────────────┤
│  Env: sweb.env.x86_64.<hash>           │  ~60 images, ~100GB total
│  - conda create -n testbed python=<v>   │
│  - pip install from MAP_REPO_VERSION_TO_SPECS │
├─────────────────────────────┤
│  Base: sweb.base.py.x86_64             │  1-2 images
│  - FROM ubuntu:22.04                    │
│  - Miniconda + build tools              │
└─────────────────────────────┘
```

**Generated Dockerfiles (dynamically created):**

```dockerfile
# Base
FROM --platform=linux/x86_64 ubuntu:22.04
RUN apt update && apt install -y wget git build-essential ...
RUN wget 'https://repo.anaconda.com/miniconda/Miniconda3-py311_23.11.0-2-Linux-x86_64.sh' ...
RUN adduser --disabled-password --gecos 'dog' nonroot

# Env
FROM --platform=linux/x86_64 sweb.base.py.x86_64:latest
COPY ./setup_env.sh /root/
RUN /bin/bash -c "source ~/.bashrc && /root/setup_env.sh"

# Instance
FROM --platform=linux/x86_64 sweb.env.x86_64.<hash>:latest
COPY ./setup_repo.sh /root/
RUN /bin/bash /root/setup_repo.sh
```

Files: `swebench/harness/docker_build.py` (`build_base_images()`, `build_env_images()`, `build_instance_image()`), `swebench/harness/test_spec/test_spec.py` (`TestSpec` class)

### Q2. UID / user handling

**Containers run as root.** A `nonroot` user is created in the base image but there is **no `USER` directive** in any generated Dockerfile.

```python
# constants.py
DOCKER_USER = "nonroot"      # used selectively for test execution only
DOCKER_WORKDIR = "/testbed/"
```

Some repos set `"execute_test_as_nonroot": True` in `MAP_REPO_VERSION_TO_SPECS`, running the eval script as `nonroot` — but the container itself starts as root. Volume ownership is a non-issue because the harness uses `copy_to_container()` (Docker API) instead of bind mounts.

### Q3. Image cache eviction

**`--cache_level` argument** controls retention. **No automatic GC/eviction.**

| Level | Keeps | Approx size |
|---|---|---|
| `instance` | base + env + instance | ~2 TB |
| `env` (default) | base + env | ~100 GB |
| `base` | base only | ~10–20 GB |
| `none` | nothing after cleanup | 0 |

Cleanup is triggered by `--clean True` flag, which calls `clean_images()` → iterates images → `should_remove(image, cache_level)` → `remove_image()`. No LRU, TTL, or automatic garbage collection. Users must manually `docker system prune` otherwise.

File: `swebench/harness/docker_utils.py` (`clean_images`, `should_remove`, `list_images`)

### Q4. Reproducibility

**Base images: tag-pinned, NOT digest-pinned:**

```dockerfile
FROM --platform=linux/x86_64 ubuntu:22.04  # floating tag, no @sha256:...
```

**Upstream repos: pinned by commit SHA:**

```bash
git clone -o origin https://github.com/django/django /testbed
git reset --hard 3a9f192b131f7a9b0fe5783c684b23015fa67cc8
```

**Dependencies: partially pinned.** `MAP_REPO_VERSION_TO_SPECS` specifies per-(repo, version) deps, but many use version ranges. APT packages are not version-pinned. The SWE-bench team now provides **pre-built Docker images** on DockerHub/GHCR to work around this reproducibility gap.

### Q5. Failure taxonomy

**Status constants** (`swebench/harness/constants.py`):

```python
APPLY_PATCH_FAIL = ">>>>> Patch Apply Failed"
APPLY_PATCH_PASS = ">>>>> Applied Patch"
INSTALL_FAIL     = ">>>>> Install Failed"
TESTS_TIMEOUT    = ">>>>> Tests Timed Out"
TESTS_ERROR      = ">>>>> Tests Error"
```

**Grading enums** (`swebench/harness/grading.py`):

```python
class TestStatus(Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR  = "ERROR"
    SKIPPED = "SKIPPED"

class ResolvedStatus(Enum):
    RESOLVED_FULL    = "RESOLVED_FULL"     # all FAIL_TO_PASS pass + PASS_TO_PASS pass
    RESOLVED_PARTIAL = "RESOLVED_PARTIAL"  # some FAIL_TO_PASS pass
    NO               = "NO_RESOLUTION"
    ERROR            = "ERROR"
```

**Exception classes:**

```python
class BuildImageError(Exception): ...   # docker_build.py
class EvaluationError(Exception): ...   # utils.py
```

**Failure flow in `run_instance()`:**
1. Build failure → `BuildImageError` → logged to `logs/build_images/`
2. Patch apply → tries `git apply`, `git apply --reject`, `patch -p1` → `APPLY_PATCH_FAIL`
3. Test timeout → `exec_run_with_timeout()` → `TESTS_TIMEOUT`
4. Test result → `get_eval_report()` parses output → `ResolvedStatus`

Per-task output shape:

```json
{
  "django__django-10914": {
    "patch_is_None": false,
    "patch_exists": true,
    "patch_successfully_applied": true,
    "resolved": true
  }
}
```

---

# `research/devcontainer.md`

# devcontainer.json Specification — Technical Research

**TL;DR:**
- **Steal:** The `features:` extension point with OCI-ref keys and option-value objects, the lifecycle hook ordering contract (`initializeCommand` → `onCreateCommand` → `updateContentCommand` → `postCreateCommand` → `postStartCommand` → `postAttachCommand`), and the per-property merge rules (`true` wins for `init`/`privileged`, union for arrays, last-wins for scalars).
- **Doesn't apply:** No `schemaVersion` or `apiVersion` field exists — the format is intentionally unversioned. The CLI does NOT perform JSON Schema validation (VS Code does, but only at editor time). No formal forward-compat contract document.
- **Read end-to-end:** [containers.dev/implementors/spec/](https://containers.dev/implementors/spec/) — the full implementors reference including merge logic, lifecycle, and validation rules.

---

### Q1. Canonical JSON Schema URL and versioning

**Schema URLs:**
- Base schema: `https://raw.githubusercontent.com/devcontainers/spec/main/schemas/devContainer.base.schema.json`
- Main schema (composition): `https://raw.githubusercontent.com/devcontainers/spec/main/schemas/devContainer.schema.json`

**Main schema structure:**

```json
{
    "allOf": [
        { "$ref": "./devContainer.base.schema.json" },
        { "$ref": "https://raw.githubusercontent.com/microsoft/vscode/main/extensions/configuration-editing/schemas/devContainer.codespaces.schema.json" },
        { "$ref": "https://raw.githubusercontent.com/microsoft/vscode/main/extensions/configuration-editing/schemas/devContainer.vscode.schema.json" }
    ]
}
```

**Versioning: There is NONE in the file format.** Unlike Kubernetes (`apiVersion`) or Devfile (`schemaVersion`), devcontainer.json has **no version field**. The spec evolves via the git repository only, using additive-only changes with optional properties.

### Q2. Validator behavior

The devcontainer CLI (`@devcontainers/cli`) does **NOT perform JSON Schema validation.** It performs structural/operational validation only:

- **Invalid JSON syntax:** CLI exits with parse error
- **Missing required field** (no `image`/`dockerfile`/`dockerComposeFile`): Fails at container creation — no image source to resolve
- **Unknown fields:** **Silently ignored** (by design — `customizations` is open, schema allows `additionalProperties`)
- **Wrong enum/type mismatch:** Falls through to defaults — no parse-time rejection

VS Code's Dev Containers extension provides editor-time schema validation (squiggly lines) via JSON language service — separate from the CLI.

**No dedicated `devcontainer validate` command exists.** The `read-configuration` command reads and resolves config but doesn't produce schema validation output.

Source: [containers.dev/implementors/spec/#configuration-validation](https://containers.dev/implementors/spec/#configuration-validation)

### Q3. Forward-compat rules

**No explicit contract exists.** There is no "v1.0 file" vs "v1.2 file" concept because there's no version field. The compatibility strategy is implicit:

- New properties added as **optional** with sensible defaults
- `customizations` uses `"additionalProperties": true` — any tool can add namespaced properties
- Unknown properties **MUST be ignored** by consumers (standard JSON Schema behavior — top-level doesn't set `additionalProperties: false`)
- The `customizations` namespace is the official extensibility mechanism:

```json
"customizations": {
    "vscode": { "extensions": [...], "settings": {...} },
    "<any-tool-name>": { ... }
}
```

No formal compat guarantee document exists. The spec relies on additive-only evolution.

### Q4. features: extension point

**Declaration:**

```json
{
  "image": "mcr.microsoft.com/devcontainers/base:ubuntu",
  "features": {
    "ghcr.io/devcontainers/features/go:1": { "version": "1.21" },
    "ghcr.io/devcontainers/features/docker-in-docker:2": {},
    "./myLocalFeature": { "optionA": true }
  },
  "overrideFeatureInstallOrder": [
    "ghcr.io/devcontainers/features/common-utils",
    "ghcr.io/devcontainers/features/go"
  ]
}
```

**Merge rules** (across Feature metadata + image metadata + `devcontainer.json`):

| Property | Merge Rule |
|---|---|
| `init`, `privileged` | `true` if **any** source is `true` |
| `capAdd`, `securityOpt` | Union of arrays |
| `mounts` | Collected list; conflicts → last wins |
| `containerEnv`, `remoteEnv` | Per variable, last wins |
| `onCreateCommand`, `postCreateCommand`, etc. | Collected list of all |
| `hostRequirements` | Max value wins |

**Conflict detection:** Circular `dependsOn` = fatal error. Same Feature with different options = both installed. `overrideFeatureInstallOrder` controls priority for deterministic ordering.

Source: [containers.dev/implementors/features/#installation-order](https://containers.dev/implementors/features/#installation-order)

### Q5. Lifecycle hook ordering

**Exact execution order:**

```
1. initializeCommand        ← HOST machine, every start
── container created & started ──
2. onCreateCommand           ← container, first create only
3. updateContentCommand      ← container, first create + prebuild refreshes
4. postCreateCommand         ← container, first create only
── above 3 run ONLY on first creation ──
5. postStartCommand          ← container, every start
6. postAttachCommand         ← container, every tool attach
```

**Failure semantics:** If one lifecycle script fails, **all subsequent scripts are skipped.**

**Parallel execution** via object syntax:

```json
{
  "postCreateCommand": {
    "install": "npm install",
    "db-setup": ["mysql", "-u", "root", "-e", "CREATE DATABASE dev"]
  }
}
```

Each key runs in parallel. All must succeed.

**`waitFor` property** (default `updateContentCommand`): Controls which command the tool waits for before showing UI. Commands after `waitFor` run in background.

**Idempotence:** Not formally required, but `postStartCommand` and `postAttachCommand` run on every start/attach — should be idempotent in practice. `initializeCommand` may run multiple times per session.

Source: [containers.dev/implementors/json_reference/#lifecycle-scripts](https://containers.dev/implementors/json_reference/#lifecycle-scripts)

---

# `research/cog.md`

# Cog (Replicate) — Technical Research

**TL;DR:**
- **Steal:** The `Input()` descriptor with `ge`/`le`/`choices`/`regex` constraints for typed prediction inputs, and the auto-generated OpenAPI schema baked into Docker image labels at build time (`org.cogmodel.openapi_schema`). Clean pattern for separating `setup()` (load weights) from `predict()` (inference).
- **Doesn't apply:** No evaluation gate, no retry/N-of-M, no task versioning. Build caching is pure Docker BuildKit — no custom cache logic. Designed for inference serving, not agent evaluation.
- **Read end-to-end:** [`docs/yaml.md`](https://github.com/replicate/cog/blob/main/docs/yaml.md) — complete `cog.yaml` field reference.

---

### Q1. Complete cog.yaml field reference

```yaml
build:                              # REQUIRED stanza
  gpu: true                         # bool, optional – enables nvidia-docker base
  cuda: "11.8"                      # string, optional – CUDA version override
  python_version: "3.13"            # string, optional – 3.10–3.13
  python_requirements: requirements.txt  # string, optional – pip requirements file
  system_packages:                  # list[str], optional – APT packages
    - "ffmpeg"
    - "git"
  run:                              # list[str | dict], optional – post-install commands
    - "curl -L ... | tar xz"
    - command: "pip install foo"
      mounts:
        - type: secret
          id: pip
          target: /etc/pip.conf
  sdk_version: "0.18.0"            # string, optional – pin cog SDK (≥0.16.0)

concurrency:                        # optional (cog ≥0.14.0)
  max: 10                           # int – requires async predict()

image: "r8.im/your-username/your-model"  # string, optional – Docker image name

predict: "predict.py:Predictor"     # string, REQUIRED – module:class pointer
```

**Only `predict` is strictly required.** Validation: Go CLI parses into struct (`pkg/config`), Python SDK generates OpenAPI schema at build time.

### Q2. Build cache

**Cog does not implement its own cache.** It delegates entirely to Docker BuildKit layer caching + `--mount=type=cache`:

```dockerfile
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update -qq && apt-get install -qqy ...
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /tmp/requirements.txt
```

| Aspect | Detail |
|---|---|
| Cache key | BuildKit content-hash of RUN instruction + mount contents |
| Storage | BuildKit daemon (`~/.docker/buildx/`) |
| Eviction | Standard BuildKit LRU via `docker builder prune` |
| `--no-cache` | `Build()` Go function accepts `noCache bool` |

Build artifacts staged in `.cog/tmp/buildXXXX/` within project directory.

### Q3. Typed prediction inputs

**Supported types:** `str`, `int`, `float`, `bool`, `cog.Path` (file I/O), `cog.File` (deprecated), `cog.Secret`, `Optional[T]`, `list[T]`.

**`Input()` descriptor:**

```python
Input(
    description: str,
    default: Any = ...,       # omit → required; None → optional
    ge: float = None,         # >= constraint
    le: float = None,         # <= constraint
    min_length: int = None,
    max_length: int = None,
    regex: str = None,
    choices: list = None,     # enum of allowed values
    deprecated: bool = False,
)
```

**Example:**

```python
from cog import BasePredictor, Input, Path
from typing import Optional, Iterator

class Predictor(BasePredictor):
    def setup(self):
        self.model = load_model("weights.pth")

    def predict(self,
        prompt: str = Input(description="Text prompt"),
        num_steps: int = Input(description="Steps", default=20, ge=1, le=100),
        style: str = Input(description="Style", choices=["photo", "anime", "oil"]),
        seed: Optional[int] = Input(description="Seed", default=None),
    ) -> Iterator[Path]:
        ...
```

**Validation:** OpenAPI schema generated at build time → HTTP server validates incoming JSON (422 on type mismatch). CLI parses `-i key=value` flags with `@` prefix for files.

### Q4. Provenance emitted per cog predict run

**Build-time Docker image labels:**

| Label | Content |
|---|---|
| `org.cogmodel.openapi_schema` | Full OpenAPI JSON schema |
| `org.cogmodel.cog_version` | Cog CLI version |
| `org.cogmodel.config` | Serialized cog.yaml |
| `run.cog.predict` | Predict reference string |
| `org.opencontainers.image.source` | Git repo URL (when available) |

Git commit SHA embedded when `git rev-parse` succeeds during build.

**Run-time prediction response:**

```json
{
  "id": "abc123",
  "status": "succeeded",
  "output": "...",
  "metrics": { "predict_time": 1.23 },
  "logs": "..."
}
```

OpenAPI schema available at `/openapi.json` on the running server. Image digest is the Docker image ID. No structured provenance JSON from the `cog predict` CLI itself.

Files: `pkg/docker/` (Go build/label logic), `cog/command/openapi_schema.py` (schema generation), `cog/server/http.py` (response formatting)

---

# `research/catchall.md`

# Catch-All: Agent-Runner-in-a-Container Frameworks

**TL;DR:**
- **Steal:** Docker Agent (`docker/docker-agent`) is the closest match — YAML-based agent definitions running in Docker containers with model+tools+instruction config. Also consider OpenHands for the eval-gate + sandbox pattern.
- **Doesn't apply:** No single project combines YAML agent recipe + throwaway Docker container + evaluation gate + resource limits + retry logic into one spec. This is an ecosystem gap.
- **Read end-to-end:** [Docker Agent docs](https://docker.github.io/docker-agent/) — the YAML agent definition reference.

---

### Does an "ap.recipe" equivalent exist?

**No.** After searching 8+ query variations ("agent harness yaml docker", "LLM agent runner spec", "coding agent eval framework", "agent playground docker yaml", etc.), no framework matches the exact description: a YAML-based recipe describing how to run a coding agent inside a throwaway Docker container against a single prompt/model cell, with an evaluation gate.

### Closest matches ranked by similarity

**1. Docker Agent (`docker/docker-agent`)** — Closest overall. YAML-based agent definitions specifying model, tools, behavior, and relationships. Runs inside Docker containers using Docker Model Runner for local LLM inference and MCP for tool access. **Missing:** No built-in evaluation gate or scoring mechanism.

**2. OpenHands (formerly OpenDevin)** — Open-source coding agent platform running agents in sandboxed Docker containers. Has an evaluation harness (SWE-bench compatible) with configurable `max_iterations`. **Missing:** Uses `config.toml`, not YAML. Not a declarative recipe format.

**3. Google ADK Agent Config** — YAML agent definitions with `model`, `instruction`, `tools`, `sub_agents`. **Missing:** Docker containers not the primary paradigm, no evaluation gate.

**4. Docker Compose for Agents (`docker/compose-for-agents`)** — Ready-to-use `compose.yaml` examples for LangGraph, CrewAI, ADK, Agno agent stacks. **Missing:** Orchestration-focused, no evaluation/scoring gate.

### Feature comparison

| Feature | docker-agent | OpenHands | ADK Config | SWE-bench |
|---|---|---|---|---|
| YAML config | ✅ | ❌ (TOML) | ✅ | Partial |
| Docker container | ✅ | ✅ | Partial | ✅ |
| Single prompt/model | ✅ | ✅ | ✅ | ✅ |
| Evaluation gate | ❌ | ✅ | ❌ | ✅ |
| Coding agent focus | Partial | ✅ | Partial | ✅ |
| Resource limits | Via Docker | Via Docker | ❌ | Via Docker |
| Retry logic | Partial | ✅ | ❌ | Partial |

### The gap

No single project unifies YAML agent recipe + throwaway Docker container + eval criteria + resource limits + retry logic + output schema into one declarative specification. This represents a clear **ecosystem gap**. The closest approximation would combine Docker Agent's YAML format with SWE-bench's task/scoring structure and Inspect AI's timeout/limit enforcement model.
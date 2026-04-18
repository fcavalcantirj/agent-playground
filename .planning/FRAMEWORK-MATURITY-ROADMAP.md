# Framework Maturity Roadmap — `ap.recipe` spec + runner

**Created:** 2026-04-15, after v0.1 consolidation phase shipped.
**Prior-art research:** `recon/prior-art-research.md` (METR, promptfoo, Inspect AI, SWE-bench, devcontainer, Cog, catch-all).
**Ecosystem gap confirmed:** no project combines YAML recipe + throwaway Docker + eval gate + resource limits + retry + structured output. This is genuinely new.

## Maturity criteria — the 7 properties

The spec+enforcer pair is mature when all 7 hold. Missing any one = not mature.

1. **Lint before run.** Structurally invalid recipes never reach Docker. JSON Schema validation, not hand-rolled ifs.
2. **Every field enforced.** If the spec declares it, the runner checks it. No documentation-only fields in a mature spec.
3. **Failures have names.** Build failure, clone failure, timeout, assertion miss, container crash, infra gone — each is a distinct category with structured metadata. Consumers can route retries without parsing strings.
4. **Runs are reproducible from their output.** The verdict carries recipe hash, upstream SHA, image digest, runner version, timestamp. A FAIL from weeks ago is re-investigable from the JSON alone.
5. **Bounded in every dimension.** Time (container, build, clone), space (stdout bytes, disk), compute (memory, CPU, pids), network (on/off/scoped). No unbounded wait, buffer, or resource.
6. **Tested without live agents.** Fake-agent fixtures exercise every verb, every error category, every timeout path. Suite runs in seconds, not minutes.
7. **Spec and enforcer can't drift.** One source of truth (JSON Schema) consumed by lint, runner, and sync test. Adding a verb without updating the schema is a CI failure.

Properties 1–3 = v0.2 milestone. Properties 4–7 = v0.3 milestone.

## Milestone structure

- **Milestone v0.2 — "framework floor"** (P04, P05, P06) — lint gate, error taxonomy, timeouts, Linux-correct. After this the runner can be consumed by the Go orchestrator. ~3.5 dev-days.
- **Milestone v0.3 — "framework ceiling"** (P07–P12) — provenance, SHA pinning, isolation, stochasticity, verb coverage, doc-sync. After this the runner can consume untrusted recipes. ~4 dev-days.

## Dependency graph

```
         ┌──► P05 ──┬──► P07 ──► P08
         │          ├──► P10
         │          └──► P11
 P04 ────┼──► P06
         ├──► P09
         └──► P12
```

---

## Phase 04 — Spec lint + test harness foundations

**Goal:** Make recipe structural validity a pre-run check; make the runner independently testable.

**Must deliver:**
- `run_recipe.py --lint <recipe>` — JSON Schema-based validation (`ap.recipe.schema.json` generated from the field tables in `docs/RECIPE-SCHEMA.md`). Asserts required fields, enum values, cross-field invariants (`pass_if: response_contains_string` ⇒ `smoke.needle` present), rejects unknown keys. Exits non-zero on failure.
- `tests/` directory with `pytest` suite: mocked-docker fixtures for each `pass_if` verb, lint negative tests (≥10 deliberately broken recipe fragments), ruamel write-back round-trip over all 5 committed recipes, regression test per recipe skeleton.
- `--lint` runs automatically as a pre-step to every invocation (`--no-lint` to bypass).

**Steal from prior art:**
- **Cog:** auto-generate JSON Schema and bake it as an artifact. Their OpenAPI schema is generated at build time from code — we should generate `ap.recipe.schema.json` from `RECIPE-SCHEMA.md` field tables so lint = `jsonschema.validate()`, not hand-rolled `if` branches.
- **devcontainer (anti-pattern):** they have a JSON Schema but the CLI doesn't enforce it. Only editor squiggles. We must not repeat this — `--lint` must be mandatory-before-run.

**Depends on:** — (gate phase)
**Exit gate:** `pytest tests/` green; `--lint` catches every fixture in `tests/broken_recipes/`; all 5 committed recipes pass lint; `--lint` integrated into main invocation.
**Est:** 1–1.5 days

---

## Phase 05 — Error taxonomy + timeout enforcement

**Goal:** Replace single `{verdict: PASS|FAIL}` with category-aware verdicts; actually kill runaway containers.

**Must deliver:**
- Verdict categories: `PASS`, `ASSERT_FAIL`, `INVOKE_FAIL`, `BUILD_FAIL`, `PULL_FAIL`, `CLONE_FAIL`, `TIMEOUT`, `LINT_FAIL`, `INFRA_FAIL`. Each carries `{verdict, category, detail}`.
- Wire `smoke.timeout_s` to `subprocess.run(timeout=)` + `docker kill <cid>` on expiry. Add `build.timeout_s`, `build.clone_timeout_s`, global `--global-timeout`.
- Taxonomy tests — one fixture per category.

**Steal from prior art:**
- **Inspect AI:** 5-layer timeout model (`time_limit`, `working_limit`, `message_limit`, `token_limit`, `cost_limit` + per-exec + per-model-request). Their `EvalSampleLimit(type, limit, usage)` shape is exactly what our verdict should carry.
- **SWE-bench:** `ResolvedStatus` enum + status constants (`APPLY_PATCH_FAIL`, `INSTALL_FAIL`, `TESTS_TIMEOUT`, `TESTS_ERROR`). Right granularity for our domain.

**Depends on:** P04
**Exit gate:** each taxonomy branch producible by ≥1 test fixture; deliberately-sleeping container produces `TIMEOUT` within `smoke.timeout_s + 5s`; existing 5-recipe gate still passes.
**Est:** 1 day

---

## Phase 06 — Linux host owner_uid correctness

**Goal:** All 5 recipes run cleanly on a Linux host (Hetzner-shaped).

**Must deliver:**
- Pick one approach: (a) chown tmpdir to `volumes[].owner_uid` before bind-mount, OR (b) use `docker cp` instead of bind-mount (SWE-bench pattern), OR (c) `docker run --user` override. Document the choice.
- Hard fail with diagnostic if the approach fails — never silently run with wrong ownership.
- CI fixture: each recipe on a Linux host with distinct owner_uid values (0, 1000, 10000, 65534).

**Steal from prior art:**
- **SWE-bench:** they avoid the uid problem entirely by using `copy_to_container()` (Docker API) instead of bind mounts. Worth considering as the cleanest alternative.

**Depends on:** P04
**Exit gate:** all 5 recipes pass `--all-cells --json` on a Linux host without manual setup.
**Est:** 1 day

---

## Phase 07 — Provenance + output bounds

**Goal:** Every verdict is forensic-grade; runaway stdout can't OOM the runner.

**Must deliver:**
- Verdict JSON carries: `recipe_sha256`, `resolved_upstream_ref` (git HEAD from clone), `image_digest` (from `docker image inspect`), `runner_version`, `run_started_at` (ISO8601 UTC), `host_os`.
- `smoke.stdout_max_bytes` in schema (default 1 MiB). Stream-and-truncate with marker. `pass_if` refuses to evaluate on truncated payloads → verdict `TRUNCATED`.

**Steal from prior art:**
- **Cog:** build-time Docker labels (`org.cogmodel.cog_version`, git SHA from `git rev-parse`). Our verdicts should carry equivalent fields.
- **Inspect AI:** `MAX_EXEC_OUTPUT_SIZE = 10 MiB`. We set ours to 1 MiB (one-shot replies are smaller than multi-turn tool traces).

**Depends on:** P05 (`TRUNCATED` is a category)
**Exit gate:** every swept cell returns verdict with all provenance fields populated; a fixture printing 10 MB produces `TRUNCATED` without OOM.
**Est:** 0.5 day

---

## Phase 08 — Determinism — SHA pinning + `ap.recipe/v0.2`

**Goal:** Recipes carry reproducible content, not a moving target.

**Must deliver:**
- `apiVersion: ap.recipe/v0.2` — requires `source.ref` to be a full 40-char SHA. Lint enforces.
- `tools/migrate_to_v0_2.py` — resolves each v0.1 recipe's `ref` to HEAD SHA of clone, writes back, bumps apiVersion.
- Clone dir keyed by SHA (`/tmp/ap-recipe-<name>-<sha8>-clone/`).
- Runner records `resolved_upstream_ref` even for v0.1 recipes.
- Update `docs/RECIPE-SCHEMA.md` §9.

**Steal from prior art:**
- **METR:** `standard_version` class attr, pre-1.0 semver, adaptor-based compat. Same model we use.
- **SWE-bench:** discovered `FROM ubuntu:22.04` (tag-pinned, not digest-pinned) is a reproducibility gap. Pre-built images on GHCR as workaround. We should digest-pin OR accept the gap with a note (upstream Dockerfiles not ours to modify).

**Depends on:** P07 (uses provenance field)
**Exit gate:** all 5 recipes migrated to v0.2 with SHA pins; `--lint` rejects v0.2 recipe with non-SHA ref; clone cache key-per-SHA; sweep gate green.
**Est:** 1 day

---

## Phase 09 — Isolation limits + default-deny

**Goal:** Runner can safely execute untrusted recipes.

**Must deliver:**
- Schema: `runtime.limits.{memory_mb, cpus, pids, network}` — required for v0.2.
- Schema: `runtime.isolation.{cap_drop, read_only_rootfs, no_new_privileges}` — mandatory, default-deny (`cap_drop: [ALL]`, explicit add-back if needed).
- Runner applies `--memory`, `--cpus`, `--pids-limit`, `--network`, `--cap-drop`, `--cap-add`, `--read-only`, `--security-opt`.
- All 5 recipes audited + given explicit limits.
- Container-escape regression test fixture.

**Steal from prior art:**
- **METR:** `manifest.yaml` with `cpu_count_range`, `ram_gib_range`, `disk_gib`. Network via `get_permissions() → ["full_internet"]` + iptables. Driver translates to Docker flags. Clean spec/enforcement split.
- **devcontainer:** feature merge rules — `true wins` for `privileged`/`init`, `union` for capability arrays, `last wins` for scalars. File for v1 `external_services` merging.

**Depends on:** P04, P06
**Exit gate:** all 5 recipes declare explicit limits + pass `--all-cells`; `--lint` rejects v0.2 recipe without `cap_drop`; escape-attempt fixture fails as expected.
**Est:** 1.5 days

---

## Phase 10 — Stochasticity / multi-run determinism

**Goal:** Single-run cells can't mask stochastic models.

**Must deliver:**
- Schema: `smoke.determinism: {runs: N, require: unanimous|majority|at_least(K)|pass_at(K)}` — default `{runs: 1, require: unanimous}` for backwards compat.
- Runner retries each cell N times, aggregates per `require` rule.
- New category `STOCHASTIC` for cells that don't achieve agreement.
- Retrofit hermes × gemini-2.5-flash back into `verified_cells[]` as a multi-run probe.

**Steal from prior art:**
- **Inspect AI:** `multi_scorer()` with `at_least(k)` and `pass_at(k)` reducers (Chen et al. 2021 formula). Exact primitive we need.
- **promptfoo:** `--repeat N` exists but per-test M-of-N does not (feature requested, unimplemented). We'd be ahead of promptfoo if we ship this.

**Depends on:** P05 (`STOCHASTIC` is a category)
**Exit gate:** hermes × gemini back in `verified_cells[]` with `runs: 5`; 3 consecutive full sweeps return identical verdicts.
**Est:** 0.5–1 day

---

## Phase 11 — Dead verb coverage — `_fake-agent` fixture recipe

**Goal:** Every `pass_if` verb proven to work without an LLM in the loop.

**Must deliver:**
- `recipes/_fake-agent.yaml` — underscore prefix, not in BACKLOG. Uses `busybox`/`alpine` with controlled output.
- ≥2 verified_cells per verb: one PASS, one documented FAIL. Verbs: `response_contains_name`, `response_contains_string`, `response_regex`, `response_not_contains`, `exit_zero`.
- Runs as part of `pytest` harness.

**Steal from prior art:**
- **promptfoo:** `not-` prefix for automatic negation of any type. Consider for v0.3: `not-response_contains_string` instead of a dedicated `response_not_contains`. Cleaner, scales.
- **promptfoo:** `assert-set` with fractional `threshold` for OR/at-least-K composition. Future v0.3 direction for compound `pass_if`.

**Depends on:** P04, P05
**Exit gate:** every `pass_if` enum value has ≥1 PASS + ≥1 FAIL fixture; `pytest` runs them in <10s.
**Est:** 0.5 day

---

## Phase 12 — Doc ↔ runner sync check

**Goal:** Schema doc and runner behavior are statically equivalent.

**Must deliver:**
- `tests/test_schema_sync.py` — if P04 produced `ap.recipe.schema.json`, assert the JSON Schema's `pass_if` enum, `build.mode` enum, required fields, and CLI flags match the runner's argparse spec and `evaluate_pass_if` branches.
- Deliberate desync = pytest failure.

**Steal from prior art:**
- **Cog:** if the JSON Schema IS the single source of truth (generated once, consumed by lint + doc + sync test), then doc-sync is trivially a schema-comparison test. The schema is the doc.

**Depends on:** P04
**Exit gate:** deliberate desync between doc and runner caught by pytest.
**Est:** 0.5 day

---

## Prior-art summary table

| Project | Primary steal | Phase(s) it informs |
|---|---|---|
| **METR task-standard** | `manifest.yaml` resource declarations, `standard_version` versioning, install/start hook separation | P05, P08, P09 |
| **promptfoo** | Assertion taxonomy (30+ types), `not-` prefix, `assert-set` composition, `--repeat N` | P10, P11, future v0.3 |
| **Inspect AI** | `multi_scorer()` with `at_least(k)`/`pass_at(k)` reducers, 5-layer timeout, `EvalLog` schema, `EvalSampleLimit` shape | P05, P07, P10 |
| **SWE-bench** | 3-tier image hierarchy, `copy_to_container()` uid pattern, `ResolvedStatus` enum, content-hash image tags | P05, P06, P08 |
| **devcontainer.json** | JSON Schema approach (anti-pattern: not enforced by CLI), feature merge rules, lifecycle hook ordering | P04, P09 |
| **Cog (Replicate)** | OpenAPI schema in Docker labels, `Input()` typed descriptors with constraints, BuildKit cache delegation | P04, P07, P08 |
| **Docker Agent** | YAML agent config shape (adjacent, not directly applicable). `toolsets` MCP pattern for future v1. | — |

# aider recipe (Phase 02.5 reference #1)

**Upstream:** https://github.com/Aider-AI/aider
**License:** Apache-2.0
**Dimensions:** python / pip / exec_per_message / env_var auth / anthropic + openrouter

Aider is the simplest possible `ap.recipe/v1` document — no template files, no
long-running process, no custom Dockerfile. It runs directly on
`ap-runtime-python:v0.1.0-3.12` via a `uv tool install aider-chat`
postCreateCommand. Chat messages are delivered via the `exec_per_message`
bridge, which runs `aider --message "<text>"` per user turn.

## Runtime fallback to Python 3.12

`ap-runtime-python:v0.1.0-3.13` is the primary Python base image for Phase 02.5,
but aider is **pinned to the 3.12 variant** because:

1. `aider-chat==0.86.2` declares `requires_python: <3.13,>=3.10` in its PyPI
   metadata — Python 3.13 is explicitly unsupported.
2. Aider hard-pins `numpy==1.26.4`, which has no cp313 wheel; any attempt to
   install it on 3.13 falls back to an sdist build that fails in the sandbox
   because gcc is not installed (and should not be).

Evidence and the A3 resolution are in
`.planning/phases/02.5-recipe-manifest-reshape/02.5-07-SUMMARY.md`. The 3.12
base image definition lives at `deploy/ap-runtime-python-3.12/Dockerfile`.

## postCreate dispatch note

`uv tool install aider-chat` is used instead of `uv pip install --system
aider-chat` because the Plan 03 lifecycle runner exec-s hooks as the `agent`
user, and `/usr/local/lib/python3.12/site-packages` is root-owned — a plain
`uv pip install --system` fails with EACCES. `uv tool install` installs into
`/home/agent/.local/share/uv/tools/aider-chat/` and symlinks the entrypoint
into `/home/agent/.local/bin/aider`, which is already on PATH for the agent
user (see `deploy/ap-runtime-python/Dockerfile`).

## Smoke test

```bash
AP_DEV_BYOK_KEY=sk-ant-... make smoke-test-matrix
```

See `test/smoke-matrix.sh` (Plan 10) for the full matrix runner.

## Verified

- Install time on `ap-runtime-python:v0.1.0-3.12`: **6 seconds** (`uv tool install --no-cache aider-chat`)
- Installed aider version: **0.86.2**
- Python 3.13 compatibility: **FAILED** (Assumption A3 falsified — see SUMMARY)
- Python 3.12 compatibility: **PASSED**
- Pinned upstream SHA: `f09d70659ae90a0d068c80c288cbb55f2d3c3755` (see `metadata.source_sha` in recipe.yaml)
- Pinned Anthropic model: `claude-haiku-4-5-20251001` (cheapest Claude Haiku, verified against https://docs.anthropic.com/en/docs/about-claude/models)
- BYOK whoareyou smoke check: **SKIPPED** (`AP_DEV_BYOK_KEY` not set at execution time; deferred to Gate A / Plan 10)

# Spike 11 — per-recipe health_check endpoints

**Date:** 2026-04-18
**Plan affected:** 22-01 (recipe schema), 22-05 (GET /v1/agents/:id/status)
**Verdict:** GOTCHA CAUGHT — per-recipe health_check must be heterogeneous

## Probes

Each running container probed from INSIDE for its claimed health endpoint.

| Recipe | Claimed endpoint | HTTP code | Result |
|---|---|---|---|
| hermes   | none (process_alive) | N/A — no `curl`/`wget` on PATH AND no HTTP listener on any port | **PROCESS_ALIVE ONLY** |
| picoclaw | `/health` port 18790 | 200 OK | PASS |
| picoclaw | `/ready` port 18790 | **503 Service Unavailable** | — |
| nanobot  | `/health` port 18790 | 200 OK | PASS |
| nullclaw | (port 3000) | not probed in this cycle (prior spike 05 proved boot) | liveness via process_alive |
| openclaw | `/` port 18789 | 200 OK | PASS (from earlier probe session) |

## Gotchas

### Gotcha A — Picoclaw `/ready` ≠ `/health`

My recipe draft says `health_check.path: /ready`. Actual state: `/ready` returns **503** even when telegram channel is enabled and bot provider started. Picoclaw's `/health` returns 200.

**Root cause (likely):** `/ready` is a stricter readiness check — probably waiting for LLM provider warm-up, skill loading, or cron service initialization. `/health` is plain liveness.

**Fix:** recipe `health_check.path` should be `/health` for picoclaw, not `/ready`.

### Gotcha B — Hermes has no HTTP endpoint

My recipe draft says `health_check.kind: process_alive`, but I had hesitated to commit to that. Probe confirms: hermes image has neither `curl` nor `wget`, and no listener on any port in `gateway run -v` mode. Process-alive is the ONLY liveness signal.

**Fix:** recipe stays `kind: process_alive` — `docker inspect .State.Running == true` is the check.

### Gotcha C — Nullclaw unknown

Skipped in this cycle due to an awk-simplification bug in the probe setup. Earlier spikes proved nullclaw boots and connects Telegram, but the `/` endpoint on port 3000 was not HTTP-probed. Plan 22-05 should either:
- Fall back to `process_alive` for nullclaw
- Or add a follow-up sub-probe to verify port 3000 returns 200

## Verdict: PASS with plan revision

Per-recipe health_check config MUST be heterogeneous. The schema `health_check` field supports it; the recipe YAMLs just need correct values:

| Recipe   | kind          | port  | path     |
|----------|---------------|-------|----------|
| hermes   | process_alive | —     | —        |
| picoclaw | http          | 18790 | /health  |
| nanobot  | http          | 18790 | /health  |
| openclaw | http          | 18789 | /        |
| nullclaw | process_alive (confirm follow-up) | — | — |

## Plan delta

Plan 22-01 Task 2 — recipe schema `health_check` must be `oneOf` `process_alive` or `http{port,path}`. My drafts already support this shape but YAML values must match above.

Plan 22-05 Task 3 (`GET /v1/agents/:id/status`) endpoint's health probe logic:
```python
if health_check.kind == "process_alive":
    return {"running": container.status == "running"}
elif health_check.kind == "http":
    # curl from inside container via docker exec
    code = docker_exec(container, ["curl", "-s", "-o/dev/null", "-w%{http_code}",
                                    f"http://127.0.0.1:{port}{path}"])
    return {"running": True, "http_code": int(code), "ready": code == "200"}
```
Note: hermes has no curl → must use `sh -c 'wget -O/dev/null -S URL'` OR just rely on `process_alive`.

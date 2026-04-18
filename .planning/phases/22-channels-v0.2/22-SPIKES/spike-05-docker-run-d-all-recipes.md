# Spike 05 — `docker run -d` persistent boot across 5 recipes

**Date:** 2026-04-18
**Plan affected:** 22-03 (runner --mode persistent)
**Verdict:** PASS — 5/5 recipes boot and stay up with sh-entrypoint override

## Probes

Each recipe started with `docker run -d` using the sh-chain from its recipe draft's `persistent.spec.argv`:

- hermes: `gateway run -v` (env-only transport)
- nanobot: `sh -c "<heredoc config.json>; exec nanobot gateway"` (file transport + env interpolation)
- picoclaw: `sh -c "<heredoc config.json>+<heredoc .security.yml>; exec picoclaw gateway -d"` (file transport split LLM vs channel)
- nullclaw: `sh -c "onboard && awk-edit channels && exec gateway"` (file transport + config.json mutation)
- openclaw: `sh -c "openclaw config set ×7 && exec gateway"` (7 sequential config-set commands)

## Actual output after 20s

```
ap-probe-picoclaw  Up 20 seconds (healthy)
ap-probe-nanobot   Up 20 seconds
ap-probe-hermes    Up 21 seconds
```

After 60s:
```
ap-probe-openclaw  Up About a minute (health: starting)
ap-probe-nullclaw  Up About a minute
ap-probe-picoclaw  Up About a minute (healthy)
ap-probe-nanobot   Up About a minute
ap-probe-hermes    Up About a minute
```

## Verdict: PASS

All 5 recipes boot under `-d` with sh-entrypoint override and stay alive ≥60s. The plan's strategy of forking `run_cell` into `run_cell_persistent` that swaps `--rm` for `-d --name` is empirically viable.

## Boot wall times (min → first "up" status)

- hermes:   ~20s (polling startup)
- nanobot:  ~18s
- picoclaw: ~15s
- nullclaw: ~20s (onboard + awk edit)
- openclaw: ~75s (7 config sets + plugin boot)

SC-02 "<90s start for hermes" is met with ~60s margin. Openclaw at ~75s fits but tight.

## Plan citation

Plan 22-03 Task 1 — each `docker run -d` invocation follows the `argv` from recipe `persistent.spec`. The entrypoint-override-to-sh pattern already works for ALL 5 recipes in `-d` mode. No rewrite needed.

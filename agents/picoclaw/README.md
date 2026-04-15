# picoclaw recipe (Phase 02.5 reference #2 of 2)

**Upstream:** https://github.com/sipeed/picoclaw
**License:** MIT
**Language:** Go (static binary; runtime.family=node per Pattern 11 D-40b)
**Dimensions:** node / git_build / fifo / secret_file_mount / anthropic + openrouter / strict

PicoClaw is the hardest path the architecture has to support — long-running
Go process, FIFO chat bridge via ap-base's entrypoint shim, auth-file mount
rendered from a template that mirrors upstream's `.security.yml` shape, full
lifecycle hooks (postCreate / postStart liveness / postAttach FIFO verify).
In 02.5 it runs on `ap-runtime-node:v0.1.0-22` via a multi-stage `Dockerfile`
that builds from source at a pinned commit SHA.

**Standalone in 02.5** — NOT `config_flavor_of openclaw`. Phase 4 will
re-express picoclaw as a flavor once openclaw ships in the catalog.

## Pinned SHA

`773a94c41437d21c7cb1fcc429cee1ac605dd509`

Current HEAD of `github.com/sipeed/picoclaw` at plan-execute time (2026-04-14).
Supersedes Phase 2's pin `c7461f9e963496c4471336642ac6a8d91a456978` (2026-03-31)
per D-42 ("pinned at plan-WRITE time").

## A7 resolution

**green** — picoclaw has first-class OpenRouter support via
`pkg/providers/factory_provider.go:27` (`"openrouter": {defaultAPIBase:
"https://openrouter.ai/api/v1"}`) and the full `pkg/providers/openai_compat`
path. Grep evidence and line numbers are in
`.planning/phases/02.5-recipe-manifest-reshape/02.5-08-scratch-a7.md`.

Key mechanism note: picoclaw reads ALL provider keys from
`~/.picoclaw/.security.yml` — it does NOT honor `OPENROUTER_API_KEY` or
`ANTHROPIC_API_KEY` env vars (zero `os.Getenv` hits for either). The
`api_key_env_var` field in `providers[]` is metadata for the matrix test
framework, not a live injection path for picoclaw itself.

**Scope in this plan:** `providers[]` declares both anthropic and openrouter,
so the matrix test runner sees both as valid routes. However,
`templates/security.yml.tmpl` currently only renders the Anthropic key —
OpenRouter Gate A coverage is carried by aider (Plan 07) per D-47. A future
plan can either (a) extend the template to emit additional `model_list`
entries keyed by which BYOK key is present, or (b) ship a second template
variant selected by provider.

## Template

`templates/security.yml.tmpl` — 1:1 port of Phase 2's
`renderPicoclawSecurityYAML` closure (in `api/internal/recipes/recipes.go`
lines 237–250) with `{{ quote .secrets.anthropic_key }}` replacing the
inline `fmt.Sprintf` + `strings.ReplaceAll` escape. The `quote` funcmap
(Plan 02) uses `strconv.Quote`, which handles all control characters, not
just double quotes — strictly safer than the Phase 2 escape.

## Lifecycle contract (Pitfall 4 compliance)

- `postCreateCommand`: `mkdir -p /run/ap` — idempotent, no FIFO interaction
- `postStartCommand`: `pgrep -f picoclaw` — liveness probe, read-only
- `postAttachCommand`: `test -p /run/ap/chat.in` — file-type check, **no** `cat < fifo` and **no** `echo > fifo`
- `waitFor: postAttachCommand`

The ap-base entrypoint shim already holds FIFO fds open from PID 1. Any
attempt to reopen from a lifecycle hook would deadlock the bridge (Phase 2
Pitfall 4 — see research §Pitfall 4).

## Build

```sh
docker build -t ap-picoclaw:v0.2.0-773a94c agents/picoclaw/
```

Depends on `make build-ap-base build-runtime-node` having run first —
the final stage `FROM ap-runtime-node:v0.1.0-22` needs that tag in the
local image cache.

## L2 verification output

Plan 02.5-08 Task 2 ran `docker run --rm --user agent --entrypoint picoclaw
ap-picoclaw:v0.2.0-l2 version`. See the plan SUMMARY (`02.5-08-SUMMARY.md`)
for the final image size and verification output.

## Chat path

`ChatIOFIFO` — long-lived agent in the tmux chat window consuming from the
FIFOs ap-base pre-opens at PID 1. The session bridge (Phase 2 code, lifted
into Plan 04's ChatBridge interface) writes messages into `/run/ap/chat.in`
and reads replies from `/run/ap/chat.out`.

## Smoke test

```bash
AP_DEV_BYOK_KEY=sk-ant-... make smoke-test-matrix
```

Runs Plan 10's full matrix including picoclaw × anthropic. OpenRouter ×
picoclaw is skipped in 02.5 because the template only renders the Anthropic
key; aider carries the OpenRouter proof.

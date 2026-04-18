# Phase 22 — Recipe Schema v0.2 + Channels (Telegram end-to-end)

## One-line goal

Add a `channels:` block to the recipe schema so deployed agents can stay
live and reachable via messaging platforms (Telegram first), not just do
a one-shot smoke and exit.

## Why now

All 5 recipes in `recipes/` support messaging channels upstream (hermes
gateway, picoclaw gateway, nullclaw channels, nanobot gateway,
openclaw channels add). The current `ap.recipe/v0.1` schema only
encodes the **one-shot smoke** invocation pattern. Nothing in v0.1
expresses persistent-mode + channel creds + lifecycle.

Extending the schema is the bottleneck for Phase 22 frontend work
("deploy and use" flow): platform wants to collect bot token + user id
at deploy time, spin a persistent container, and hand the user back a
live bot.

## Scope (Phase 22a — schema + 4 recipes + runner persistent-mode)

1. **`ap.recipe/v0.2` schema** — add two new top-level sections, both
   additive (v0.1 recipes remain valid):
   - `persistent:` — declares the persistent-mode entrypoint + argv
     that boots the in-container gateway/daemon. Includes
     `ready_log_regex`, `health_check`, `graceful_shutdown_s`, and an
     optional `user_override` for images with ownership bugs (nullclaw).
   - `channels:` — dict keyed by channel id (`telegram`, `discord`,
     `slack`, …). Each entry declares:
     - `config_transport: env | file`
     - `required_user_input[]` — env-var name, secret flag, hint +
       hint_url for user-facing UI
     - `optional_user_input[]`
     - `ready_log_regex` — per-channel ready signal pattern
     - `response_routing` — `per_message_origin` or fixed chat
     - `multi_user_model` — `allowlist | pairing_then_allowlist`
     - `multi_account_supported: bool`
     - `verified_cells[]` — per-channel empirical PASS evidence
     - Optional: `provider_compat: {supported:[], deferred:[]}` for
       agents with known provider-specific bugs (openclaw's openrouter
       plugin).
     - Optional: `known_quirks[]` — image-level caveats the runner
       must honor at deploy time.

2. **4/5 recipes already carry v0.2-draft blocks** (committed alongside
   this phase's CONTEXT):
   - `hermes.yaml` — env-only transport, `gateway run -v`.
   - `picoclaw.yaml` — file transport (config.json5 + .security.yml
     split), `picoclaw gateway -d`.
   - `nullclaw.yaml` — file transport (channels.telegram.accounts.main
     JSON nesting), `nullclaw gateway` + image ownership quirk.
   - `nanobot.yaml` — file transport (config.json with `${VAR}`
     interpolation), `nanobot gateway`.

3. **openclaw.yaml — deferred OpenRouter path, Anthropic direct works.**
   Schema-from-reality note: openclaw's `openrouter` provider plugin in
   image `2026.4.15-beta.1` silently aborts LLM calls pre-flight
   (`attempts: []`). Isolation test (2026-04-18, this repo):
   `openclaw config set agents.defaults.model anthropic/claude-haiku-4-5`
   + `ANTHROPIC_API_KEY` env → full channel round-trip PASS including
   `openclaw pairing approve telegram <CODE>` via `docker exec`.
   `provider_compat: {supported:[anthropic], deferred:[openrouter]}`.
   Upstream issue to file.

4. **Runner — `tools/run_recipe.py` gains `--mode persistent`**:
   Reads `persistent.spec.argv` + env-injects user-supplied channel
   creds, runs `docker run -d --name ap-agent-<run_id>`, polls
   `ready_log_regex`, calls `health_check` probe, returns `container_id`
   + `ready_at`. Exit on SIGTERM → sends container SIGTERM with
   `graceful_shutdown_s` timeout, then force-rm.

5. **API server — new endpoints:**
   - `POST /v1/agents/:id/start` — spawn persistent container with the
     supplied channel creds; returns container_id.
   - `POST /v1/agents/:id/stop` — graceful shutdown + cleanup.
   - `GET /v1/agents/:id/status` — container up/down, health probe
     result, last N log lines.
   - For openclaw: `POST /v1/agents/:id/channels/:cid/pair` body
     `{code: string}` → runs `docker exec <container> openclaw pairing
     approve <channel> <code>` so the user completes pairing from the
     platform UI without ssh.

6. **Frontend — deploy form gains "Step 2.5: how will you use this?"**
   - Option A: one-shot smoke (current behavior).
   - Option B: persistent + Telegram (requires bot_token from
     @BotFather, user_id from @userinfobot).
   - For openclaw: the form explicitly routes to ANTHROPIC_API_KEY
     prompt (not OpenRouter) until the upstream plugin is fixed.

## Out of scope (Phase 22b or later)

- Discord / Slack / WhatsApp / Matrix / Signal channels. The schema
  supports them, but v0.2 ships only the Telegram rail (validated
  across 4 recipes).
- Custom provider bridges (e.g. a python telegram bridge for openclaw
  that bypasses its broken openrouter plugin by using `infer model run
  --local`). Nice-to-have; out of scope unless openrouter stays broken
  for > 1 week.
- Multi-agent-per-bot routing. One bot = one agent for v0.2.
- Volume persistence for agent state. v0.2 containers are ephemeral
  `--rm` (restart = fresh state). Persistent workspaces are Phase 23.

## Success criteria (exit gate)

- **SC-01** Schema v0.2 additive — all 5 existing v0.1 recipe YAMLs
  still parse under the v0.2 loader with zero edits to the v0.1
  sections.
- **SC-02** Runner `--mode persistent` implemented; `POST /v1/agents/
  :id/start` returns a running container in < 90s for hermes (worst
  case; image is 5.19 GB, boot is ~45s).
- **SC-03** End-to-end Telegram PASS for all 4 supported recipes AND
  openclaw via Anthropic direct: user deploys → bot receives inbound
  DM → agent replies within 10s of bot receiving message, over at
  least 3 consecutive deploys per recipe.
- **SC-04** `POST /v1/agents/:id/stop` tears down cleanly; no dangling
  `ap-agent-*` container after test loop.
- **SC-05** Frontend Step 2.5 UI exists and persists user's bot_token
  ONLY through the request (BYOK discipline — never stored platform-
  side).
- **SC-06** Documented upstream issue filed against `openclaw/
  openclaw` with the isolation repro from this phase.

## Canonical research inputs

- `.planning/research/CHANNEL-RECON.md` — HISTORICAL doc-only recon
  (2026-04-17, Explore-agent-written). Superseded but kept for diff.
- `.planning/research/CHANNEL-RECON-EMPIRICAL.md` — hermes + picoclaw
  per-agent sections; nullclaw + nanobot + openclaw findings merged
  directly into their recipes during testing. This is the bridge doc.
- The 5 recipe `.yaml` files — each has a `v0.2 DRAFT` block with:
  - Canonical docs URLs (kept in sync when recipe changes)
  - Schema-from-reality notes (discrepancies found between docs and
    actual image behavior)
  - `persistent:` + `channels:` blocks populated from empirical PASS
  - `verified_cells[]` — dated entries with bot_username, user_id,
    model, wall times, and verbatim notes per empirical run

## Evidence trail — 2026-04-17 / 2026-04-18 empirical runs

All 5 agents were tested against a real Telegram bot
(`@AgentPlayground_bot`, user 152099202) using the credentials in
`.env.local` (gitignored). Summary:

| Recipe | Channel wiring | LLM path | Verdict |
|---|---|---|---|
| hermes | ✅ | openrouter/claude-haiku-4.5 | FULL_PASS — PT-BR reply in ~1s |
| picoclaw | ✅ | openrouter/claude-haiku-4.5 | FULL_PASS — "Oi Felipe! 👋" in ~3s |
| nullclaw | ✅ | openrouter/claude-haiku-4.5 | FULL_PASS — `--user root` quirk required |
| nanobot | ✅ | openrouter/claude-haiku-4.5 | FULL_PASS — boot ~18s (workspace bootstrap) |
| openclaw | ✅ | anthropic-direct/claude-haiku-4.5 | FULL_PASS — openrouter deferred |

The openclaw openrouter discovery is the load-bearing finding of this
phase — it justifies the `provider_compat.deferred[]` schema field and
changes the deploy-UI key-input UX for that recipe specifically.

## Acknowledged gaps

- Multi-user-per-bot is not considered (one bot handles one deploy).
  That matches the platform's BYOK UX anyway.
- openrouter plugin bug in openclaw means our BYOK OpenRouter UI
  default is incompatible with openclaw deploys — deploy UI must gate
  openclaw behind a direct-provider key prompt (or expose the
  deferred[] warning to the user).
- Recipe v0.2 schema is DRAFT in this phase; gsd-plan-phase will
  formalize as `docs/RECIPE-SCHEMA-v0.2.md` before runner code lands.

## Next step

`/gsd-plan-phase 22a` — produce PLAN breakdown with tasks for:
schema finalization, runner `--mode persistent`, API endpoints,
frontend Step 2.5. The CONTEXT above is the input.

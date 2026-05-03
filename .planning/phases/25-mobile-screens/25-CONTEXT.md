# Phase 25: Mobile Screens (end-to-end demo) — Context

**Gathered:** 2026-05-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Three Flutter screens (Dashboard / New Agent wizard / Chat) wired
end-to-end against the local Phase 23 backend, plus Login + cold-start
+ logout, completing the Mobile MVP demo flow:

  open app → splash → /v1/users/me → Dashboard
  → tap FAB → 3-step wizard (clone → model+BYOK → name+telegram+deploy)
  → /v1/runs smoke (PASS) → /v1/agents/:id/start (inapp [+ telegram if toggled])
  → Chat opens → type message → SSE assistant reply → kill app → relaunch
  → history visible.

Phase 24 shipped the foundation (`mobile/` scaffold, theme,
hand-written typed `ApiClient`, `flutter_client_sse` wrapper, secure
storage, go_router, env-config, 9-step round-trip spike PASS). Phase 25
fills the empty `lib/features/{dashboard,new_agent,chat}/` dirs and
adds `lib/features/login/` + `lib/shared/` + `lib/core/auth/` (auth
service / provider).

**The screen plumbing is the entire scope** — no new backend endpoints,
no new tables, no recipe changes, no debug menu / env switcher / dev
chrome (Phase 24 D-44 + Golden Rule #3 reinforced). Backend reused
verbatim; mobile is the dumb client per Golden Rule #2.

**One material expansion vs prior locked decisions: Telegram is a
real, additive channel in MVP — not a stub.** The `inapp` container
always deploys; the wizard's Telegram toggle (visible only when the
recipe declares `channels_supported` includes `telegram`) gates a
SECOND `/v1/agents/:id/start` call with `channel='telegram'` and
recipe-driven `channel_inputs` rendered dynamically (mirroring the web
playground's dumb-client pattern). UI-02 ("Telegram toggle is rendered
but disabled in MVP") and Phase 23 D-28 ("Mobile Phase 25 deploys with
`channel='inapp'`") are amended in this phase's commit chain — see
AMD-01 + AMD-02 below.

</domain>

<decisions>
## Implementation Decisions

### Boot / cold-start / authentication flow

- **D-01:** **Cold-start: native splash holds, then route.** iOS
  `LaunchScreen.storyboard` + Android `launch_background` drawable hold
  the screen until `GET /v1/users/me` resolves; then `go_router` replaces
  with `/dashboard` (200) or `/login` (401). No Flutter splash widget,
  no double-flash.
- **D-02:** **`/v1/users/me` 5xx or timeout → minimal retry screen.** A
  full-bleed scaffold with `>_ SOLVR_LABS` wordmark + "Couldn't reach
  server" copy + a single Retry button that re-fires the call. No
  auto-retry, no exponential backoff. Network-down ≠ signed-out.
- **D-03:** **Any 401 anywhere in the app → clear `flutter_secure_storage`
  session_id, route to `/login`, render an inline banner above the OAuth
  buttons reading "Signed out · Sign in to continue".** After re-auth,
  user lands on `/dashboard` (NOT auto-resume to the prior route — too
  brittle, no deep-link state plumbing in MVP).

### Login screen

- **D-04:** **Layout: `>_ SOLVR_LABS` wordmark (`JetBrains Mono`,
  centered) above two full-width primary buttons stacked vertically:**
  `Continue with Google` (Google glyph + label) and `Continue with
  GitHub` (GitHub glyph + label). Google button on top (more common
  provider). No tagline, no "By signing in…" footer in MVP — captured
  deferred for App Store / TestFlight prep.
- **D-05:** **OAuth pending state: tapped button replaces label with a
  small spinner; the other button greys to `disabled`.** No full-screen
  overlay. If user cancels the native sheet, button restores. The native
  OAuth sheet is its own modal layer.
- **D-06:** **OAuth failure surface: inline error text under buttons,**
  red foreground, single line ("Couldn't sign in. Try again." with
  code-specific copy when known). Cleared on next button tap. No
  SnackBar, no modal AlertDialog — failures are common (user denies
  sheet, network blip), modal interruption is wrong.

### Logout

- **D-07:** **Logout lives in the Dashboard AppBar's 3-dot overflow.**
  Single menu item: "Sign out". Tap → confirmation `AlertDialog` ("Sign
  out of Solvr Labs?" with Cancel / Sign out). On confirm: clear
  `flutter_secure_storage` session_id (and BYOK keys? **NO — keys persist
  across sign-outs per D-25**), route to `/login`. OAuth re-auth on
  mobile is non-trivial (native sheet each time); cheap insurance against
  fat-finger sign-outs.

### Dashboard screen

- **D-08:** **Layout: list of single-line rows.** Each row: status dot
  (left) + agent name (Inter regular) + model id (JetBrains Mono small,
  muted, second line) + relative `last_activity` ("2m" / "3h" /
  "yesterday", right-aligned). Divider between rows. Tap anywhere on the
  row → `/chat/<agent_instance_id>`.
- **D-09:** **AppBar:** `>_ SOLVR_LABS` wordmark (left, `JetBrains Mono`
  small caps) + 3-dot overflow (right, "Sign out" only — D-07). No back
  button (Dashboard is root).
- **D-10:** **Bottom navigation: render all tabs from the mockup
  (Home / Browse / Profile), disable non-Home.** Inactive tabs are
  greyed and no-op on tap. Sets the v2 visual frame; signals "more
  coming"; costs ~20 LOC.
- **D-11:** **"+" button: Material FAB, bottom-right, square (radius 0)
  with thin "+" glyph.** Always visible during scroll. Above the bottom
  nav. Routes to `/new-agent` (push, NOT replace — back returns to
  Dashboard).
- **D-12:** **Refresh model: pull-to-refresh + foreground-resume
  refetch.** Manual pull-down triggers `GET /v1/agents`. Coming back
  from background (`AppLifecycleState.resumed`) also refetches. **No
  background polling** (battery cost + UI flicker). Default Material
  `RefreshIndicator` styling (no theming cost).
- **D-13:** **Sort order: `last_activity desc`** (most recent first).
  Backend already returns the field (Phase 23 D-27); client sorts in
  place. Mirrors chat-list convention.
- **D-14:** **Status dot: 3-state colors.** `running` → green dot
  (filled, `#22c55e` or similar — the project's only accent),
  `stopped` / `exited` → grey hollow ring, `failed` / `error` → red
  filled (the second non-monochrome accent, used ONLY for error state
  here and on failed chat bubbles per D-32). The `agent_containers.container_status`
  enum (Phase 23) is the source.
- **D-15:** **`last_activity` rendered as relative time** ("2m", "3h",
  "yesterday"). Updates only on refetch (no live tick).
- **D-16:** **`model` field rendered as full provider/model id**
  (e.g. `anthropic/claude-haiku-4-5`) in `JetBrains Mono` small. Zero
  client-side name-massaging logic; matches the picker representation
  (D-21).
- **D-17:** **Empty state: single ASCII agent-name banner cycling every
  ~2s + primary button.** Centered area renders a `JetBrains Mono`
  banner that cycles through clawclones agent names (`openclaw` →
  `hermes` → `nullclaw` → `picoclaw` → `nanobot`) — names sourced
  dynamically from `GET /v1/recipes` so the banner stays current as the
  catalog grows (DUMB-client compliant). Below: "No agents yet" copy
  (Inter, large, muted) + a black full-width primary button "Deploy
  your first agent" routing to `/new-agent`. The FAB stays for repeat
  use; the explicit button is the discoverable first-deploy entry. (See
  `memory/feedback_solvr_matrix_aesthetic.md` for the aesthetic
  preference that drove this.)
- **D-18:** **Initial-load state: 3 skeleton rows** (grey placeholders
  matching real row geometry); swap to real data when fetch resolves.
  Establishes the loading vocabulary for other screens too.
- **D-19:** **Fetch error post-load: inline retry banner above the
  list** ("Couldn't refresh · Tap to retry"), last-known data stays
  visible. Pull-to-refresh also retries. Degraded gracefully.
- **D-20:** **Long agent name + model id: single-line ellipsis on
  both** (`overflow: TextOverflow.ellipsis`, `maxLines: 1`). Full name
  visible in Chat AppBar (D-37) where there's more horizontal room.

### New Agent screen (3-step wizard)

- **D-21:** **3-step wizard, NOT single-scroll form.** Routes:
  `/new-agent/clone`, `/new-agent/model`, `/new-agent/name-deploy`.
  Wizard scope state held in a Riverpod-scoped provider keyed to the
  wizard route group; cleared on close (D-31).
- **D-22:** **Step 1 = Clone picker (horizontal scrolling card row),
  Step 2 = Model picker + BYOK key, Step 3 = Name + Telegram toggle +
  Deploy.** Step 2 pairs BYOK with model (logical pair — BYOK key gates
  model access). Step 3 is the final identity + add-on + commit.
- **D-23:** **Step indicator at top of every step: thin stepper bar
  ● ── ○ ── ○** (current filled, others hollow), with step labels
  ("Clone" / "Model + Key" / "Name + Deploy") underneath. Standard
  wizard UX; ~30 LOC.
- **D-24:** **Per-step back arrow preserves state across the wizard
  session.** Going back from step 3 to step 1 keeps all entered values.
  Going forward re-uses them. Wizard cancel UX is separate (D-31).
- **D-25:** **Recipe picker UX: horizontal scrolling card row.** Each
  card from `GET /v1/recipes` shows recipe name (`JetBrains Mono`) + a
  short description (1 line, from `RecipeSummary.description`).
  Selected card has a 2px black border. No pre-selection — Step 1
  "Next" button is `disabled` until a card is tapped.
- **D-26:** **Model picker UX: full-screen searchable picker (push
  route).** Step 2 renders a "Pick a model" button that pushes
  `/new-agent/model/picker` — full-screen scaffold with: search
  `TextField` at top, virtualized `ListView.builder` of all models from
  `GET /v1/models` (each row: provider/name + context length + price
  per 1M tokens), tap selects + pops back to step 2 with the selection
  shown. Catalog has 300+ entries; full-screen + search + virtualization
  is the only viable UX.
- **D-27:** **Name field validation: regex `^[a-z0-9][a-z0-9_-]*$`
  inline (red border + caption when invalid)** + length cap matching
  backend (currently 64 chars). Mirrors `routes/runs.py` SQL-injection
  defense regex verbatim.
- **D-28:** **Pre-flight collision check on Deploy tap.** Before /runs
  fires, mobile calls `GET /v1/agents`; if the trimmed name already
  exists for this user, show `AlertDialog`: "Name '{name}' already
  used by {recipe} + {model} — Re-deploy (replaces) / Rename / Cancel"
  per Phase 23 D-29. "Re-deploy" proceeds with the existing UPSERT
  semantics (backend handles); "Rename" closes dialog + focuses the
  name field; "Cancel" closes dialog only.
- **D-29:** **Smoke loading UX: replace Deploy button with a progress
  card** ("Smoke testing recipe + model + key…" + spinner + elapsed
  timer "00:14" + Cancel button). Cancel calls dio `CancelToken.cancel`
  — backend continues, mobile abandons the request. Smoke can take
  ~30s on cold-cache image pull + LLM call.
- **D-30:** **Smoke verdict=FAIL: stay on step 3, render inline red
  error box with `verdict.detail`.** Buttons: Retry (re-runs /runs) /
  Edit (back to step 1, state preserved per D-24). User can adjust
  without losing entered values.
- **D-31:** **Wizard cancel UX: X close icon top-right** (instead of
  back arrow) on the AppBar. Tap → if any field has been touched,
  `AlertDialog` "Discard changes? Cancel / Discard". If untouched,
  pop immediately. Treats the wizard as modal.

### BYOK key handling

- **D-32:** **Single BYOK field on step 2, label driven by recipe
  metadata.** Default label "OpenRouter API Key"; flips to "Anthropic
  API Key" when `recipe.channel_provider_compat[selectedChannel].deferred`
  includes `'openrouter'`. Today this means hermes (always Anthropic) +
  openclaw with Telegram toggled (Anthropic-only path per recipe). Hint
  text + storage location adjusts accordingly. Dumb-client (recipe is
  source of truth, NOT a Dart-side `if recipe == 'hermes'` branch).
- **D-33:** **BYOK key storage: `flutter_secure_storage`, one entry per
  provider** (`byok_key_openrouter`, `byok_key_anthropic`). Stored in
  iOS Keychain / Android EncryptedSharedPreferences (Phase 24 D-35
  primitive, extended). Subsequent New Agent flows auto-fill the
  appropriate field based on recipe metadata. **Logout does NOT clear
  these** — keys survive sign-outs (the user's BYOK keys are theirs,
  not session-bound).
- **D-34:** **BYOK field uses `obscureText: true`** (password masking)
  with a tap-to-reveal eye toggle. `autocorrect: false`,
  `enableSuggestions: false`. Standard secret-input hygiene.

### Chat screen — bubbles, history, send

- **D-35:** **Bubble design: right/left + invert colors.** User: right-
  aligned, black background (`#1F1F1F`) + white text (`#FAFAF7`).
  Assistant: left-aligned, light grey background + black text.
  Corner radius 0 (theme). Markdown rendering via `flutter_markdown`
  (D-43); code blocks render in `JetBrains Mono` with subtle grey bg.
- **D-36:** **Mount load order: parallel — kick off both `GET /messages`
  and SSE connect simultaneously, dedupe by `message_id`.** Insert into
  a Dart `Map<String, ChatMessage>` keyed by message_id; if id already
  present, update status only. Handles the race where SSE delivers a
  message that's also in the history GET response (Phase 23 D-08
  cross-channel parity — content is byte-identical, dedup is safe).
- **D-37:** **Chat AppBar: back arrow + agent name + status subtitle**
  (model id `JetBrains Mono small` + status dot from `agent.status`,
  same colors as D-14). Back arrow returns to Dashboard. **No overflow
  menu** — agent lifecycle (Stop/Restart) only via D-49 stopped-banner.
- **D-38:** **Empty Chat state: centered hint above input** —
  "Say hi to {agent_name}" (Inter italic, muted), disappears once the
  first message is sent. Named so the user knows they're in the right
  chat.
- **D-39:** **History pagination: load latest 1000 + "Older messages
  not shown" banner at top.** Initial mount fetches `?limit=200`. If
  user scrolls to top AND server returned exactly 200 (suggesting more
  exist), an inline banner reads "Older messages not shown · Tap to
  load up to 1000 more"; tap re-fetches with `?limit=1000`. Beyond
  1000 (backend cap per Phase 23 D-04): banner shows "First {N-1000}
  messages hidden". Defers a real cursor implementation.
- **D-40:** **Input: multiline expanding TextField + Send button.** Up
  to ~5 lines tall, then scrolls internally. Enter inserts a newline
  (NOT send — avoids accidental sends on hardware keyboards). Send
  button (right of input) is the only commit. Disabled when input is
  empty or whitespace-only.
- **D-41:** **Optimistic pending: insert user bubble immediately at
  full opacity** (with `idempotency_key` as local id), and a grey
  assistant `typing…` bubble below it (animated 3 dots). User bubble
  flips to "failed" rendering (D-44) on `POST /messages` error;
  assistant bubble replaces with the SSE-delivered content on success
  or flips to failed on bot error (Phase 23 D-03 ghost row).
- **D-42:** **Auto-scroll to bottom on new bubble UNLESS user has
  scrolled up.** "Scrolled up" = scroll position > ~50px from the
  bottom edge. When auto-scroll is suppressed, render a "New message
  ↓" chip near the bottom that taps to scroll. Standard mobile chat
  pattern; doesn't yank reading position.
- **D-43:** **Markdown rendering via `flutter_markdown`.** Code fences
  in `JetBrains Mono` with grey bg. Lists, bold, headings, inline code
  rendered. **No image rendering** (security surface; LLM replies
  rarely have images). Link tap behavior per D-46.
- **D-44:** **Failed message rendering: distinct bubble with red border
  + ⚠ icon + "Retry" tap target.** Backend marks `inapp_messages.status='failed'`;
  `GET /messages` returns assistant content prefixed `⚠️ delivery
  failed: <last_error>` (Phase 23 D-03). Bubble border in
  same red as failed status dot (D-14) — these are the only two
  red-as-accent moments in the app. Tap the bubble → bottom sheet:
  "Retry" + "Copy error".
- **D-45:** **Retry generates a NEW `Idempotency-Key`** (uuid v4), POSTs
  `/messages` with same content. Backend treats as a real new send;
  failed bubble stays in history (durable record); a new pending bubble
  appears below. NOT same-key-replay (which would just return the
  cached failure per Phase 23 D-09 — wrong semantic for user-facing
  Retry).
- **D-46:** **Markdown link handling: tap opens external browser via
  `url_launcher`, `https` + `http` schemes only.** All other schemes
  (`javascript:`, `data:`, `file:`, `mailto:`, custom URI schemes
  registered by other apps) are stripped — link renders as plain text.
  Guards prompt-injection scheme tricks.
- **D-47:** **Bubble timestamps: inline grouped, shown only when there's
  a >5min gap between consecutive bubbles.** Centered grey caption
  between bubbles ("14:32" today, "Apr 28 14:32" older). No timestamp
  on every bubble (clutter); no long-press-to-reveal (undiscoverable).
- **D-48:** **Long-press on bubble → bottom sheet: Copy + Select text.**
  "Copy" puts the whole bubble content on the clipboard; "Select text"
  enables the native text-selection cursor for partial copy. Critical
  for code blocks.

### Chat screen — error / lifecycle / banner UX

- **D-49:** **Container not running mid-chat → disable input + persistent
  banner above input.** When `agent.status != 'running'`: input field
  greys (placeholder "Restart agent to send messages"), Send button
  disables, a banner pinned above the input reads "⚠ Agent stopped ·
  [Restart]". Restart calls `POST /v1/agents/:id/start` with the
  channel(s) the agent_containers row recorded (look up channel(s) via
  `GET /v1/agents` extended response if available; otherwise default to
  `inapp` only and surface a planner-deferred TODO if multi-channel
  restart needs richer endpoint). Explicit, recoverable, no silent
  failed sends.
- **D-50:** **Telegram-deploy-failed banner: sticky at top of Chat with
  X to dismiss + Retry.** When the user routes to Chat after an
  inapp-success / telegram-failure deploy (D-58), a thin grey/yellow
  banner pins below the AppBar: "⚠ Telegram setup failed: {reason}" +
  Retry + X. Persists until dismissed or Retry succeeds. Retry re-fires
  `POST /v1/agents/:id/start` with `channel='telegram'` and the
  previously-entered channel_inputs (kept in memory until banner
  dismissed; NOT stored to flutter_secure_storage — bot tokens are
  per-deploy).
- **D-51:** **Send button states: disabled-empty / spinner-in-flight /
  cancel-on-spinner-tap. Failures render via failed-bubble path only —
  NO snackbar / toast / inline error.** Single error vocabulary across
  the screen. Tapping the spinner cancels the dio CancelToken (backend
  keeps running per Phase 23 D-05; optimistic bubble flips to "failed:
  cancelled" with the same Retry affordance per D-44).
- **D-52:** **SSE lifecycle: connect on mount, disconnect on pop, reconnect
  on foreground with `Last-Event-ID`.** `go_router` `onExit` + Riverpod
  `dispose` close the SSE stream + cancel CancelToken. `AppLifecycleState.resumed`
  reconnects with `Last-Event-ID = <last_id_received>` per Phase 23 D-13
  contract. iOS suspends connections after ~30s background; resume picks
  up where it left off.
- **D-53:** **Long-bot-wait UX: typing indicator only (no timer, no
  cancel button).** Backend always completes regardless of client per
  Phase 23 D-05; mobile re-fetches via `/messages` on next
  foreground-reconnect if SSE died. A Cancel button would be misleading
  (cannot actually cancel the bot call). Just the animated dots.

### Telegram channel (additive deploy)

- **D-54:** **Telegram fields rendered dynamically from
  `recipe.channels.telegram.required_user_input + optional_user_input`**
  via `GET /v1/recipes/{name}` (RecipeDetail). Mobile renders one
  field per `ChannelUserInput` entry: label = `env`, type = secret/text
  per `secret`, caption = `hint` (with optional `hint_url` link).
  Mirrors the web playground's pattern verbatim (`frontend/components/playground-form.tsx`
  lines 638-689). Per-recipe inputs:
  - `openclaw`: `TELEGRAM_BOT_TOKEN` (secret), `TELEGRAM_ALLOWED_USER`
    (text, numeric Telegram user ID — runner auto-prefixes with `tg:`
    per recipe).
  - `hermes`: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS` (CSV of IDs).
  - Other recipes: per-recipe metadata at runtime.
- **D-55:** **Telegram toggle visible only when
  `recipe.channels_supported` includes `'telegram'`.** Recipes without
  Telegram support don't render the toggle row at all (no greyed
  "unsupported" affordance).
- **D-56:** **Multi-channel deploy mechanics: `1 × POST /v1/runs +
  N × POST /v1/agents/:id/start` sequentially** (1 if inapp-only, 2 if
  inapp + telegram). NO new backend `/deploy` endpoint — mobile
  orchestrates the same way the web playground does (one channel per
  /start call). Sequence:
  1. `POST /v1/runs` smoke (BYOK → Authorization: Bearer header).
  2. If verdict ≠ PASS → D-30 inline error.
  3. `POST /v1/agents/{id}/start` with `{channel:'inapp', channel_inputs:{}}`.
  4. If Telegram toggled: `POST /v1/agents/{id}/start` with
     `{channel:'telegram', channel_inputs:{ENV1: val1, ENV2: val2, ...}}`.
- **D-57:** **inapp `/start` failure aborts deploy.** If step 3 above
  fails, surface inline error on step 3 (same shape as smoke-fail D-30)
  + Retry. Telegram step never fires.
- **D-58:** **Telegram `/start` failure (when inapp succeeded): route
  to Chat for the new agent with persistent failed-banner per D-50.**
  Treat the deploy as "mostly successful" — the demo flow holds (chat
  works), Telegram failure stays visible until acted on.
- **D-59:** **Telegram pairing flow (`dmPolicy:pairing`) NOT implemented
  in MVP.** Today's openclaw + hermes recipes use `dmPolicy:allowlist`
  with `allowFrom:[tg:$USER_ID]`, which skips the pairing-code step.
  If a future recipe ships pairing-only, mobile will need a
  `PairingModal` equivalent — captured deferred.
- **D-60:** **Deploy success destination: `go_router.go('/chat/<new-agent-id>')`
  REPLACING the wizard route.** Back button from Chat returns to
  Dashboard (NOT the wizard). Chat opens, history loads (empty for new
  agent), SSE connects, ready for first message.

### Shared UI primitives (lib/shared/)

- **D-61:** **First plan after foundation builds the shared widget set
  in `lib/shared/`** before any screen plan starts. Components:
  `StatusDot` (D-14 colors), `EmptyStateScaffold` (centered copy +
  optional banner widget + optional primary button), `AsciiAgentBanner`
  (D-17 cycling banner — accepts a `Stream<List<String>>` for the
  recipe names, default polled from `GET /v1/recipes`), `RetryBanner`
  (D-19 / D-50 inline retry pattern), `SkeletonRow` (D-18 loading
  placeholder), `TypingDots` (D-41 animated dots), `FailedBubble`
  (D-44 red-border + retry-tap), `RestartBanner` (D-49 above-input
  pattern), `ConfirmDialog` wrapper (D-07 / D-28 / D-31 — same shape
  for all confirmations). All 4 screens consume these; any UX change
  is a one-file edit.
- **D-62:** **Accessibility floor enforced via manual PR checklist +
  `golden_toolkit` screenshot tests.** PR template adds a checklist
  (44/48 touch targets, Semantics labels on icon-only buttons, contrast
  verified). `golden_toolkit` snapshots key screens at `textScaleFactor`
  1.0 / 1.5 / 2.0 — catches truncation/overflow at large text scales.
  Per-PR enforcement; no semantics-tester widget tests in MVP. (Phase
  24 D-21 captured the floor; Phase 25 enforces.)

### Local state / caching

- **D-63:** **Nothing else cached on-device beyond
  `flutter_secure_storage`** (session_id + BYOK keys per provider). DB
  is source of truth (Phase 23 D-05). Dashboard re-fetches `/v1/agents`
  on every cold-start + foreground; Chat re-fetches `/messages` on
  every mount + reconnect; recipes/models re-fetched per wizard open.
  No SQLite, no Riverpod-persisted-state, no shared_preferences cache
  for catalogs (backend already caches `/v1/models` 15min per Phase 23
  D-18 — double-caching is wasted complexity).

### Plan structure + exit gate

- **D-64:** **5 waves:**
  - **Wave 1** — `lib/shared/` widget set + `lib/core/auth/` AuthService
    (D-61) + Login screen + cold-start flow + logout (D-01..D-07).
    Establishes the auth substrate every other screen depends on.
  - **Wave 2** — Dashboard (D-08..D-20). Depends on Login + StatusDot +
    AsciiAgentBanner + SkeletonRow + RetryBanner.
  - **Wave 3** — New Agent wizard + ModelPickerScreen + dynamic
    Telegram fields + BYOK storage extensions (D-21..D-34, D-54..D-60).
    Depends on shared dialogs + recipe/model APIs.
  - **Wave 4** — Chat screen (D-35..D-53). Depends on `flutter_markdown`
    + `flutter_client_sse` (Phase 24) + FailedBubble + RestartBanner +
    `url_launcher` (new dep for D-46).
  - **Wave 5** — UI-driven integration test extending Phase 24's spike
    + manual smoke artifact (D-65, D-66). Exit gate.
- **D-65:** **Exit-gate test:
  `mobile/integration_test/screens_e2e_test.dart` drives widgets via
  `WidgetTester` against a live local `api_server`** (no mocks per
  Golden Rule #1 — same harness as Phase 24's `make spike`). Flow:
  Login → AuthService injection (D-66) → Dashboard appears → tap FAB →
  3-step wizard with real recipe pick + real model pick + name typed +
  Telegram OFF → Deploy → Chat opens → send "hi" → assert assistant
  bubble lands within bot timeout → restart app via
  `WidgetsBinding.instance.handleAppLifecycleStateChanged` round-trip
  → history visible. Plus a markdown artifact at
  `spikes/flutter-screens-roundtrip.md` capturing PASS/FAIL on iOS
  Simulator + Android Emulator (mirrors `flutter-api-roundtrip.md`
  format from Phase 24 D-54). Plan-checker MUST treat the spike PASS as
  Phase 25's exit-gate.
- **D-66:** **OAuth test seam:** Login depends on an `AuthService`
  interface (real impl uses `google_sign_in` / `flutter_appauth`; test
  impl skips the native sheet and POSTs directly to
  `/v1/auth/google/mobile` with a `SESSION_ID` injected via
  `--dart-define`, like Phase 24 D-49). Test asserts the session is
  stored, then proceeds. Real OAuth path verified by the Wave-5 manual
  smoke (which IS the only test of the unmockable native layer). The
  AuthService interface lives in `lib/core/auth/auth_service.dart`;
  Riverpod overrides swap implementations in tests.
- **D-67:** **App version bump: `pubspec.yaml` from `0.1.0+1` to
  `0.2.0+2`** as part of Wave 1. Phase 24 D-10 carry-forward.
- **D-68:** **Deep links: `solvrlabs://oauth/github` only** (Phase 24
  D-04 carry-forward). No app-internal deep links in MVP — captured
  deferred.

### Carry-forward from Phase 23 + Phase 24 (locked, not re-litigated)

- **Theme:** monochrome (`#1F1F1F` / `#FAFAF7`), corner radius 0,
  `Inter` (sans) + `JetBrains Mono` (mono). Light mode canonical.
- **API client:** Phase 24's typed `ApiClient` exposes every endpoint
  Phase 25 needs (`agentsList`, `recipes`, `models`, `runs`, `start`,
  `stop`, `postMessage`, `messagesHistory`, `usersMe`,
  `authGoogleMobile`, `authGithubMobile`). `messagesStream` (SSE
  wrapper) ships in Phase 24's `lib/core/api/messages_stream.dart`.
  No new endpoints, no changes to existing methods.
- **Auth wire:** session via `Cookie: ap_session=<uuid>` header per
  Phase 23 D-17; BYOK via `Authorization: Bearer <key>` on /runs +
  /start; AuthInterceptor injects on every call (Phase 24 D-35).
- **Idempotency-Key:** REQUIRED on `POST /messages`, generated per Send
  press (Phase 23 D-09 + Phase 24 D-36). Retry per D-45 generates a
  NEW key.
- **Pagination cap:** `?limit=N` default 200, max 1000 (Phase 23 D-04 +
  Phase 24 D-42).
- **Failed-row format:** assistant content `⚠️ delivery failed:
  <last_error>` with `kind:'error'` (Phase 23 D-03).
- **State management:** Riverpod (`riverpod_annotation` + generator per
  Phase 24 Claude's-Discretion), `go_router`, `dio`. No additions.
- **Env config:** `--dart-define BASE_URL=...` external only (Phase 24
  D-44). No in-app debug menu, env switcher, banner, or developer
  chrome.
- **Golden Rules:** No mocks/stubs (Wave 5 spike uses live local
  api_server), dumb client (recipes/models/channel-inputs from API,
  zero Dart-side hardcoded catalogs), root-cause-first, ship-locally,
  spike-before-sealing.

### Claude's Discretion

- Riverpod provider granularity (one provider per screen vs per
  feature-slice — planner picks).
- Exact `JetBrains Mono` font weight for the wordmark (likely 500 or
  600).
- ASCII banner cycling animation curve (likely `Curves.easeInOut`
  cross-fade between names).
- Whether the typing-dots animation uses `AnimatedBuilder` or a
  `LottieFile` — likely AnimatedBuilder (no extra dep).
- Whether the wizard's step state is one provider or three
  (one-per-step) — likely three with composition.
- Pull-to-refresh visual indicator (Material default unless designer
  pivot).
- Provider order on Login (Google first, GitHub second — common-case
  ordering).
- Step validation predicate placement (inline in each step's "Next"
  enabled callback, or hoisted to a wizard-level provider — planner
  picks).
- Message length cap on send (none enforced client-side in MVP — trust
  backend; revisit if backend rejects with a poor error).
- Connectivity-offline app-wide banner (NONE in MVP — per-call error
  handling is the single failure vocabulary; revisit if user reports
  confusion).
- Naming the AuthService interface methods exactly
  (`signInWithGoogle()` / `signInWithGithub()` / `signOut()` — planner
  picks).
- Exact `golden_toolkit` snapshot test count + which screens — planner
  picks (suggest: Dashboard empty, Dashboard populated, Login, Chat
  with markdown reply).
- Whether ASCII banner pulls names from `GET /v1/recipes` at runtime
  or accepts an injected `Stream<List<String>>` (likely the latter,
  with a Riverpod provider supplying the live list — keeps the widget
  pure).

### Folded Todos

None — `gsd-tools list-todos` returned 0 pending todos.

</decisions>

<amendments>
## Spec Amendments (commit chain owns these)

Phase 23 amended REQUIREMENTS.md as part of its commit chain (Phase 23
D-32 set the precedent). Phase 25 follows the same pattern for two
amendments — without these the verifier will fail the phase-exit
gate.

- **AMD-01: REQUIREMENTS.md UI-02** — current text says
  "Telegram-integration toggle is rendered but disabled in MVP".
  **Rewrite to:**

  > **UI-02**: New Agent screen lets the user pick a clone from `GET
  > /v1/recipes` (rendered as cards), pick a model from `GET /v1/models`,
  > and enter a name. Tapping Deploy first POSTs to `/v1/runs` (smoke
  > gate per Phase 23 D-22), then POSTs to `/v1/agents/:id/start` with
  > `channel:'inapp'`, then (if the recipe declares `channels_supported`
  > includes `'telegram'` AND the user has toggled Telegram ON) POSTs
  > a SECOND `/v1/agents/:id/start` with `channel:'telegram'` and
  > `channel_inputs` populated from fields rendered dynamically from
  > `recipe.channels.telegram.required_user_input + optional_user_input`.
  > On full success navigates to Chat for the new agent. On telegram-only
  > failure, navigates to Chat with a sticky failed-banner per Phase 25
  > D-50. *(Amended Phase 25 per AMD-01 — original "rendered but
  > disabled" wording predated Phase 22c.3 inapp shipping; multi-channel
  > deploy is now first-class.)*

- **AMD-02: Phase 23 23-CONTEXT.md D-28 amendment.** Phase 23 D-28
  reads "Mobile Phase 25 deploys with `{channel: 'inapp',
  channel_inputs: {}}`". **Append amendment paragraph:**

  > **AMD (Phase 25 D-56):** This constraint relaxes to "the inapp
  > container is always deployed; an additional Telegram container is
  > optional and gated by the recipe's `channels_supported` metadata
  > + a user toggle". The /v1/agents/:id/start endpoint contract is
  > unchanged (still single-channel-per-call); mobile orchestrates two
  > sequential calls when Telegram is toggled. No backend code changes;
  > UI-02 amended in same commit chain (AMD-01).

</amendments>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level locked decisions
- `.planning/PROJECT.md` — Mission, OAuth-only auth, mobile-first,
  Hetzner+Docker model, milestone v0.3 framing.
- `.planning/REQUIREMENTS.md` — APP-01..APP-05 + UI-01..UI-04 (UI-02
  amended in this phase per AMD-01).
- `.planning/notes/mobile-mvp-decisions.md` — Locked architectural
  decisions for the Mobile MVP milestone (note: contained "Telegram
  toggle disabled" wording that this phase supersedes).
- `.planning/seeds/streaming-chat.md` — Token-level streaming roadmap
  (additive, post-MVP).
- `CLAUDE.md` — Golden rules (no mocks/stubs, dumb client, ship locally,
  root-cause-first, spike before planning).
- `MEMORY.md` — Auto-memory feedback rules including Solvr Matrix
  aesthetic + dumb-client + env-config-outside-the-app.
- `memory/feedback_solvr_matrix_aesthetic.md` — drove D-17 (cycling
  ASCII agent-name banner on Dashboard empty state) + D-61
  (`AsciiAgentBanner` shared widget).

### Prior phase contracts (load-bearing — D-numbered decisions referenced above)
- `.planning/phases/24-flutter-foundation/24-CONTEXT.md` — Phase 24
  D-01..D-56 (theme, ApiClient, Result<T>, AuthInterceptor, SSE wrapper,
  secure storage, env config, FVM pinning, very_good_analysis lints,
  spike contract). **Phase 25 builds directly on top of this without
  re-litigation.**
- `.planning/phases/24-flutter-foundation/24-09-SUMMARY.md` and the
  Phase 24 spike artifact at `spikes/flutter-api-roundtrip.md` — proves
  the foundation works; Phase 25's Wave 5 spike extends this pattern.
- `.planning/phases/23-backend-mobile-api-chat-proxy-persistence-auth-shim/23-CONTEXT.md`
  — Phase 23 D-01..D-34 (chat-send/SSE/auth contracts mobile reuses).
  **D-28 amended in this phase per AMD-02.**
- `.planning/phases/22c.3-inapp-chat-channel/22c.3-CONTEXT.md` — Inapp
  dispatcher + outbox + SSE substrate.
- `.planning/phases/22c.3.1-runner-inapp-wiring/22c.3.1-PHASE-SUMMARY.md`
  — `agent_containers` rows + e2e harness + per-channel container model.
- `.planning/phases/22c-oauth-google/22c-CONTEXT.md` — OAuth contracts
  (`require_user`, `ApSessionMiddleware`, `upsert_user`, `mint_session`)
  that the mobile-credential endpoints (Phase 23 D-16) reuse.

### Backend endpoints the screens consume (already shipped)
- `api_server/src/api_server/routes/health.py` — `GET /healthz` (used
  by Phase 24 placeholder; Phase 25 may keep using or switch to
  `/v1/users/me` per D-01).
- `api_server/src/api_server/routes/users.py` — `GET /v1/users/me`
  (cold-start session check per D-01).
- `api_server/src/api_server/routes/auth.py` — `POST
  /v1/auth/google/mobile`, `POST /v1/auth/github/mobile` (Phase 23
  D-16, used by AuthService real impl per D-66).
- `api_server/src/api_server/routes/runs.py` — `POST /v1/runs` (smoke
  gate per Phase 23 D-22, D-29). **Read `_validate_name` regex** —
  D-27 mirrors it client-side.
- `api_server/src/api_server/routes/agent_lifecycle.py` — `POST
  /v1/agents/:id/start` (per-channel container spawn, called twice for
  inapp+telegram per D-56), `POST /v1/agents/:id/stop` (used by D-49
  Restart's lifecycle if needed).
- `api_server/src/api_server/routes/agent_messages.py` — `POST
  /v1/agents/:id/messages` (Idempotency-Key REQUIRED per Phase 23 D-09),
  `GET /v1/agents/:id/messages?limit=N`, SSE `GET
  /v1/agents/:id/messages/stream` (Last-Event-ID per Phase 23 D-13).
- `api_server/src/api_server/routes/agents.py` — `GET /v1/agents`
  extended with `status` + `last_activity` per Phase 23 D-10/D-27.
- `api_server/src/api_server/routes/recipes.py` — `GET /v1/recipes`
  (RecipeSummary list — D-25 picker source) + `GET /v1/recipes/{name}`
  (RecipeDetail — D-54 dynamic Telegram fields source).
- `api_server/src/api_server/routes/models.py` — `GET /v1/models`
  (OpenRouter passthrough, 15min cache per Phase 23 D-18 — D-26 picker
  source).
- `api_server/src/api_server/models/recipes.py` — `RecipeSummary`
  schema (`channels_supported`, `channel_provider_compat` —
  D-32/D-55 source of truth).
- `api_server/src/api_server/middleware/session.py` — `ApSessionMiddleware`
  (cookie-header transport per Phase 23 D-17).
- `api_server/src/api_server/middleware/idempotency.py` — replay
  semantics per Phase 23 D-09 (informs D-45 retry semantics).
- `api_server/src/api_server/errors.py` — `ErrorCode` enum + Stripe-shape
  envelope; mobile mirrors in Dart per Phase 24 D-38.

### Existing mobile code (Phase 24 — reuse, don't recreate)
- `mobile/lib/main.dart` — entry; reads BASE_URL via String.fromEnvironment
  + boot-validates per Phase 24 D-43.
- `mobile/lib/app.dart` — root MaterialApp.router with the Solvr theme.
- `mobile/lib/core/theme/solvr_theme.dart` — ThemeData mirroring
  solvr/frontend OKLCH tokens.
- `mobile/lib/core/api/api_client.dart` — typed dio client (every
  endpoint method already exists; D-31 carry-forward).
- `mobile/lib/core/api/auth_interceptor.dart` — Cookie injection (D-35
  Phase 24).
- `mobile/lib/core/api/messages_stream.dart` — SSE wrapper around
  `flutter_client_sse` (D-33 Phase 24).
- `mobile/lib/core/api/result.dart` + `dtos.dart` — sealed Result + DTOs.
- `mobile/lib/core/storage/secure_storage.dart` — flutter_secure_storage
  wrapper (extend per D-33 to add per-provider BYOK keys).
- `mobile/lib/core/router/app_router.dart` — go_router config (currently
  single placeholder route — Phase 25 fills the routes).
- `mobile/lib/core/env/app_env.dart` — BASE_URL boot validation.
- `mobile/lib/core/auth/auth_event_bus.dart` — auth event bus from
  Phase 24 (extend or wrap with AuthService interface per D-66).
- `mobile/lib/features/_placeholder/healthz_screen.dart` — replaced by
  the Login route as the initial screen post-cold-start.
- `mobile/integration_test/spike_api_roundtrip_test.dart` — Phase 24
  spike; Wave 5's `screens_e2e_test.dart` extends the same harness.
- `mobile/Makefile` — `make spike` target (Phase 24 D-50); add
  `make screens-e2e` mirroring it.
- `spikes/flutter-api-roundtrip.md` — Phase 24 PASS artifact; Wave 5
  produces a sibling `flutter-screens-roundtrip.md`.

### Web frontend cross-references (mirror dumb-client patterns)
- `frontend/components/playground-form.tsx` — **THE reference** for
  the deploy flow (lines 316-360 = the 1×/runs + 1×/start sequence
  mobile mirrors per D-56) and dynamic channel-inputs rendering (lines
  638-689 = the `recipe.channels.<id>.required_user_input` map mobile
  mirrors per D-54). Read this BEFORE planning the New Agent wizard.

### External / package documentation (new dependencies for Phase 25)
- `flutter_markdown` — markdown rendering in chat bubbles (D-43):
  https://pub.dev/packages/flutter_markdown
- `url_launcher` — external browser launch for chat links (D-46):
  https://pub.dev/packages/url_launcher
- `golden_toolkit` — accessibility / large-text snapshot tests (D-62):
  https://pub.dev/packages/golden_toolkit

### External / package documentation (already in pubspec from Phase 24)
- `flutter_riverpod` + `riverpod_annotation` — state management.
- `go_router` — navigation.
- `dio` — HTTP client.
- `flutter_client_sse` — SSE.
- `google_sign_in`, `flutter_appauth` — OAuth (D-66 real impl).
- `flutter_secure_storage` — session + BYOK key storage (D-33).
- `uuid` — Idempotency-Key generation (D-45).
- `google_fonts` — Inter + JetBrains Mono delivery.
- `very_good_analysis` — lint rules.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (DO NOT re-implement)

**From Phase 24 (`mobile/lib/`):**
- Typed `ApiClient` with every endpoint already methodized — Phase 25
  ONLY adds new screens that call existing methods.
- `AuthInterceptor` injects `Cookie: ap_session` on every call —
  consumed by all screens implicitly.
- `messagesStream` SSE wrapper — consumed by Chat screen as-is.
- `Result<T>` sealed class + `ApiError` typed envelope — every screen
  switches on `Ok` vs `Err`.
- `SolvrTheme` ThemeData — every widget inherits.
- `flutter_secure_storage` wrapper — extend with per-provider BYOK key
  methods (`writeByokKey(provider, key)` / `readByokKey(provider)`).
- `app_env.dart` boot validation pattern — replicate for any new env
  vars (e.g. SESSION_ID injection in Wave 5 test).
- Phase 24 spike pattern + Makefile target — Wave 5 extends.

**From web frontend (`frontend/components/playground-form.tsx`):**
- Deploy call sequence (lines 316-360) — mobile mirrors verbatim per
  D-56.
- Dynamic channel-inputs rendering loop (lines 638-689) — mobile
  mirrors per D-54 in Dart.
- BYOK label-swap logic (lines 627-635 `Provider override required`
  block) — mobile mirrors per D-32.
- Pre-flight name-collision check pattern — mobile per D-28.

**From `api_server/`:**
- `_validate_name` regex in `routes/runs.py` — mobile mirrors verbatim
  per D-27.
- `RecipeSummary.channels_supported` + `channel_provider_compat` —
  drives Telegram toggle visibility (D-55) + BYOK label (D-32).
- `RecipeDetailResponse` (full dict passthrough) — drives dynamic
  Telegram fields (D-54).

**From `recipes/`:**
- `recipes/openclaw.yaml` `channels.telegram.required_user_input` —
  TELEGRAM_BOT_TOKEN + TELEGRAM_ALLOWED_USER (Phase 25 dynamically
  reads, doesn't hardcode).
- `recipes/hermes.yaml` `channels.telegram.required_user_input` —
  TELEGRAM_BOT_TOKEN + TELEGRAM_ALLOWED_USERS.

### Established Patterns to Mirror
- Phase 24 hand-written DTOs with `fromJson` / `toJson` — Phase 25 adds
  any new DTOs (e.g. `MessageBubble` view-model wrapping the
  `MessagesPage` rows) following the same hand-written shape.
- Phase 24 D-31 single-file vs split: planner picks; suggested split:
  `lib/features/dashboard/dashboard_screen.dart`,
  `lib/features/new_agent/{wizard,clone_step,model_step,deploy_step}.dart`,
  `lib/features/chat/{chat_screen,bubble_widget,input_bar}.dart`,
  `lib/features/login/login_screen.dart`,
  `lib/shared/{status_dot,empty_state,ascii_banner,retry_banner,
  skeleton_row,typing_dots,failed_bubble,restart_banner,confirm_dialog}.dart`.
- Phase 24's `golden_toolkit` adoption is NEW in Phase 25 (D-62) — no
  existing snapshots to extend.
- Phase 24's `make spike` Makefile target — Wave 5 adds `make screens-e2e`
  as a sibling target (same `--dart-define` pattern, different test path).

### Integration Points (where new code lands)

**New top-level Flutter dirs:**
- `mobile/lib/features/login/` — D-04..D-06 Login screen + AuthService
  consumer.
- `mobile/lib/features/dashboard/` — D-08..D-20 Dashboard.
- `mobile/lib/features/new_agent/` — D-21..D-34, D-54..D-60 wizard.
- `mobile/lib/features/chat/` — D-35..D-53 Chat.
- `mobile/lib/shared/` — D-61 shared primitives.
- `mobile/lib/core/auth/` — extend with `AuthService` interface +
  Google/GitHub real impl + test impl (D-66).
- `mobile/lib/core/storage/` — extend with per-provider BYOK key
  methods (D-33).

**New Flutter test files:**
- `mobile/test/features/<screen>/` — widget unit tests per screen
  (planner picks coverage matrix).
- `mobile/test/golden/` — D-62 golden_toolkit snapshots.
- `mobile/integration_test/screens_e2e_test.dart` — D-65 Wave 5 exit
  gate.

**New artifacts at repo root:**
- `spikes/flutter-screens-roundtrip.md` — D-65 manual smoke artifact.

**Files extended (NOT replaced):**
- `mobile/pubspec.yaml` — version bump 0.1.0+1 → 0.2.0+2 (D-67) + add
  `flutter_markdown`, `url_launcher`, `golden_toolkit` deps (Wave 1).
- `mobile/lib/core/router/app_router.dart` — fill in routes
  (`/login`, `/dashboard`, `/new-agent/clone`, `/new-agent/model`,
  `/new-agent/model/picker`, `/new-agent/name-deploy`, `/chat/:id`).
- `mobile/lib/main.dart` — wire AuthService + cold-start /users/me +
  initial route resolution per D-01.
- `mobile/lib/app.dart` — keep MaterialApp.router shape; replace
  initial route logic.
- `mobile/lib/core/storage/secure_storage.dart` — add BYOK key methods
  per D-33.
- `mobile/lib/features/_placeholder/healthz_screen.dart` — DELETED in
  Wave 1 once login + dashboard land.
- `mobile/Makefile` — add `make screens-e2e` target (D-65).
- `mobile/README.md` — add per-target docs for screens spike (mirror
  Phase 24 D-22 README pattern).
- `.planning/REQUIREMENTS.md` — UI-02 amendment per AMD-01.
- `.planning/phases/23-backend-mobile-api-chat-proxy-persistence-auth-shim/23-CONTEXT.md`
  — D-28 amendment paragraph per AMD-02.

**No backend files modified.** Phase 23 + 22c-oauth-google + 22c.3 +
22c.3.1 ship everything mobile needs to consume.

</code_context>

<specifics>
## Specific Ideas

- **"Use the API" remains the over-arching principle** (carry-forward
  from Phase 24). Every Phase 25 widget is a thin renderer over
  Phase 24's typed `ApiClient`; no new abstraction layers, no DI
  ceremony, no client-side intelligence.
- **"Telegram is real, not a stub"** is the biggest scope expansion
  vs the locked v0.3 milestone notes. The user pushed back hard on
  the original "rendered but disabled" framing because the API +
  recipes already support live Telegram channels (Phase 22c.3 and
  earlier). The amendments (AMD-01 + AMD-02) reflect this reality
  rather than ship a feature crippled by a stale spec.
- **"check recipee, UI is built around it"** captured the
  channel-inputs dynamism: the recipe yaml defines what fields the
  picker needs, and BOTH web and mobile render those fields
  dynamically. NEVER hardcode "Bot Token / User ID" in Dart — that
  becomes a client-side catalog the moment a recipe adds a third
  field.
- **Matrix-aesthetic empty state (D-17)** is a brand moment, not
  decoration. The first sign-in should land on a screen that
  reinforces "this is a Solvr Labs / clawclones product", not a
  generic Material empty-state. The cycling ASCII banner using live
  recipe names from `GET /v1/recipes` keeps it dumb-client compliant
  and grows with the catalog.
- **The Retry-tap on a failed bubble (D-44 + D-45) generates a NEW
  Idempotency-Key** because "retry" should mean "try again". Replaying
  the cached failure is a different operation (recover-after-mobile-crashed-mid-POST)
  that no UI surface exposes — it's only useful internally on the
  next mobile-restart-with-same-key code path (which we don't
  implement; D-09 Phase 23 contract still allows it for some future
  recovery feature).
- **Deploy partial success (D-58) routes to Chat anyway** because the
  demo flow's load-bearing requirement (UI-04: chat works after
  Deploy) holds with inapp alone. Surfacing telegram failure as a
  banner inside Chat keeps the failure visible without blocking the
  demo.
- **The exit-gate test (D-65) extends Phase 24's `make spike`
  pattern** — same harness, same live-api_server requirement, same
  manual-cookie SESSION_ID injection. The reuse is deliberate: Phase
  24 proved the substrate works against a real backend; Phase 25
  proves the screens work on top of that substrate, same way.

</specifics>

<deferred>
## Deferred Ideas

- **Telegram pairing flow (`dmPolicy:pairing`)** — recipes today use
  `allowlist` mode which skips pairing. If a future recipe ships
  pairing-only, mobile needs a `PairingModal` equivalent (web has
  one). Captured per D-59.
- **Backend `POST /v1/agents/deploy` single-shot endpoint** — would
  atomically smoke + start N channels + rollback on partial failure.
  Cleaner contract than the current 1×/runs + N×/start mobile
  orchestration (D-56). Web playground would migrate too. Post-MVP.
- **Agent Stop / Restart from Dashboard rows** — no long-press menu,
  swipe gesture, or detail screen in MVP. Restart only via Chat's
  D-49 stopped-banner. (Captured per D-37.)
- **Agent Delete endpoint + Dashboard swipe-to-delete** — backend
  doesn't expose `DELETE /v1/agents/:id`; mobile inherits the gap.
- **Background SSE / push-driven message delivery** — iOS suspends
  connections after ~30s background. D-52's reconnect-on-foreground
  covers MVP. True background push (APNS/FCM) is future hardening.
- **Token-level streaming chat** — see `seeds/streaming-chat.md`.
  Triggered post-MVP if block-and-fast-ack feels janky in real demos.
- **Markdown image rendering** — D-43 explicitly excludes; LLM replies
  rarely have images and the security surface (remote URL fetching) is
  non-trivial. Add later if a real use case emerges.
- **Custom URI scheme link tapping in markdown** — D-46 strips
  non-http(s) schemes. Allow on a per-app-extension basis if/when
  legitimate use cases appear.
- **App-internal deep links (`solvrlabs://agent/:id`)** — D-68 punts.
  Useful when sharing flows land.
- **Connectivity-offline app-wide banner** (`connectivity_plus`
  listener) — per-call error handling is the MVP single failure
  vocabulary. Add if user-test feedback shows confusion.
- **Bubble timestamps on every bubble** — D-47 chose grouped (>5min
  gap). Switch to per-bubble if user feedback shows missed temporal
  context.
- **Cached recipes/models on device** — D-63 punts. Backend already
  caches `/v1/models`; double-caching is wasted complexity.
- **Local SQLite mirror of agent list / chat history** — D-63 punts.
  No offline mode in MVP.
- **In-app Settings screen** — explicitly out of MVP per
  `mobile-mvp-decisions.md`. Logout lives on Dashboard overflow per
  D-07.
- **Profile / Browse tabs functioning** — D-10 ships disabled tabs
  for the visual frame. Future phases hydrate.
- **Universal Links / App Links** — Phase 24 D-15 deferred (requires
  HTTPS-verified domain). Stays deferred.
- **Real Solvr Labs app icon + native splash** — Phase 24 D-30 deferred
  to polish. Stays deferred.
- **fastlane / TestFlight / Play Store distribution** — Phase 24 D-09
  deferred. Stays deferred.
- **Apple Privacy Manifest (`PrivacyInfo.xcprivacy`)** — Phase 24 D-19
  deferred. Stays deferred.
- **Push notifications, crash reporting (Sentry/Crashlytics),
  analytics** — Phase 24 D-20 deferred. Stays deferred.
- **Localization (l10n)** — Phase 24 D-11 deferred (en-US only). Stays
  deferred.
- **Dark mode** — locked light-mode-canonical per Phase 24 + mobile-mvp
  notes. Add when stakeholder asks.
- **In-app debug menu / env switcher** — Phase 24 D-44 + 0.3 milestone
  rule explicitly rejects. Stays rejected.
- **Backend `/v1/agents/:id/restart-multi-channel` endpoint** — D-49
  Restart needs to know which channels were on. Today we'd default to
  inapp only and surface this as a planner-deferred TODO; if this
  feels wrong during planning, propose an additive endpoint or extend
  GET /v1/agents to return channel list per agent.
- **App version reaches `0.3.0`** — D-67 picks 0.2.0+2 to keep
  milestone-aligned-but-deliberate. 0.3.0+3 reserved for the polish
  phase that actually lands a release-shaped build.

### Reviewed Todos (not folded)
None — `gsd-tools list-todos` returned 0 pending todos.

</deferred>

---

*Phase: 25-mobile-screens*
*Context gathered: 2026-05-02*

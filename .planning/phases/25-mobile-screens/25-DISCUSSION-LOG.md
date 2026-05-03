# Phase 25: Mobile Screens (end-to-end demo) — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `25-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-05-02
**Phase:** 25-mobile-screens
**Areas discussed:** Boot/Login/Logout, Dashboard, New Agent (incl. Telegram add-on),
Chat, Shared UI primitives, Plan structure & exit gate, Local-state, Misc gap-sweep
(markdown links, 401 mid-chat, lifecycle from Dashboard, long-name truncation,
timestamps, long-press, wizard step nav, step indicator).

---

## Boot / Login / Logout

### Cold-start behavior while waiting for /v1/users/me
| Option | Description | Selected |
|--------|-------------|----------|
| Native splash holds, then route | iOS LaunchScreen + Android launch_background hold until /users/me resolves; go_router replaces with Dashboard or Login. | ✓ |
| Flutter splash widget | Native flashes, then dedicated SplashScreen widget. | |
| Skip splash, render Login optimistically | Render Login while /users/me runs; swap on success. | |

### Login screen layout
| Option | Description | Selected |
|--------|-------------|----------|
| Wordmark + 2 stacked buttons | `>_ SOLVR_LABS` + Continue with Google + Continue with GitHub stacked. | ✓ |
| Wordmark + side-by-side icon buttons | Square icon-only buttons. | |
| Wordmark + tagline + buttons + footer | More polished, more copy. | |

### OAuth pending state
| Option | Description | Selected |
|--------|-------------|----------|
| Tapped button shows spinner; both disabled | Tapped button replaces label with spinner; other greyed. | ✓ |
| Full-screen modal overlay with spinner | Translucent overlay covers screen. | |
| No visible state, rely on native sheet | Buttons stay enabled; native sheet is the indicator. | |

### Logout location
| Option | Description | Selected |
|--------|-------------|----------|
| App-bar overflow on Dashboard | 3-dot menu, single "Sign out" item. | ✓ |
| Long-press anywhere on Dashboard header | Hidden gesture. | |
| Don't ship logout in MVP | Rely on session expiry / 401. | |

### /v1/users/me 5xx or timeout
| Option | Description | Selected |
|--------|-------------|----------|
| Retry banner + manual reload | "Couldn't reach server" + Retry button. | ✓ |
| Route to Login on any non-200 | Treat anything non-200 as not-signed-in. | |
| Auto-retry with exponential backoff, no UI | Silent retry 3× with backoff. | |

### OAuth failure surface
| Option | Description | Selected |
|--------|-------------|----------|
| Inline error text under buttons | Single-line red error text; cleared on next tap. | ✓ |
| Material SnackBar at bottom | Toast slides up, auto-dismisses. | |
| Modal AlertDialog | Blocking dialog. | |

### Logout instant or confirmation
| Option | Description | Selected |
|--------|-------------|----------|
| Confirmation AlertDialog | "Sign out of Solvr Labs?" with Cancel / Sign out. | ✓ |
| Instant logout | Tap clears session, routes to /login. | |

---

## Dashboard

### Layout
| Option | Description | Selected |
|--------|-------------|----------|
| List of single-line rows | Status dot + name + model + last_activity. | ✓ |
| Card grid (2 columns) | Visually richer; less dense. | |
| Stacked card list (1 col) | Full-width cards with padding. | |

### "+" button location
| Option | Description | Selected |
|--------|-------------|----------|
| FAB (floating action button), bottom-right | Square FAB above bottom nav. | ✓ |
| App-bar action (top-right) | Icon button in AppBar. | |
| Inline header card at top | Static "+ New agent" card as first row. | |

### Refresh model
| Option | Description | Selected |
|--------|-------------|----------|
| Pull-to-refresh + foreground-resume refetch | Manual pull + AppLifecycleState.resumed refetch. No polling. | ✓ |
| Add poll every 10s on top | Riverpod timer every 10s while screen visible. | |
| Pull-to-refresh only | No foreground-resume refetch. | |

### Bottom navigation treatment
| Option | Description | Selected |
|--------|-------------|----------|
| Show all tabs, disable non-Home | Render all tabs greyed out, no-op. | ✓ |
| Hide nav entirely in MVP | Don't render. | |
| Show only Home | Single-tab nav. | |
| Full nav, route stubs for inactive | Route to "Coming soon" placeholders. | |

### Empty state (Matrix-style after user pivot)
| Option | Description | Selected |
|--------|-------------|----------|
| Animated falling columns of agent names | Vertical columns falling, JetBrains Mono. | |
| Static Matrix-style backdrop | Same columns frozen. | |
| Single ASCII agent-name banner | Cycling banner every 2s; clawclones names. | ✓ |

**User notes:** Original options were redrawn after user pivoted: "I like the ascii art, specially matrix like using names of agents. openclaw, hermes, nullclaw, etc" + "with a button to add". Original empty-state options (centered copy + arrow / centered copy + button / wordmark backdrop) were rejected pre-answer. Memory saved at `feedback_solvr_matrix_aesthetic.md`.

### Initial-load state
| Option | Description | Selected |
|--------|-------------|----------|
| Skeleton rows (3 placeholders) | Grey placeholders matching real geometry. | ✓ |
| Centered spinner | CircularProgressIndicator. | |
| No loading state | Whatever AsyncValue.loading does. | |

### Status dot color mapping
| Option | Description | Selected |
|--------|-------------|----------|
| green/grey/red 3-state | running=green, stopped/exited=grey, failed=red. | ✓ |
| green/grey 2-state | No error color. | |
| Single dot, opacity-based | Vary opacity by status. | |

### last_activity format
| Option | Description | Selected |
|--------|-------------|----------|
| Relative time ("2m", "3h", "yesterday") | timeago-style; updates on refetch. | ✓ |
| Absolute clock ("14:32", "Apr 28") | Today=HH:MM; older=short date. | |
| Hide last_activity in MVP | Cleaner row. | |

### AppBar content
| Option | Description | Selected |
|--------|-------------|----------|
| `>_ SOLVR_LABS` wordmark + overflow | Wordmark left, 3-dot overflow with Sign out. | ✓ |
| Plain "Agents" title + overflow | Material-default title. | |
| Wordmark only, logout elsewhere | Just wordmark. | |

### Sort order
| Option | Description | Selected |
|--------|-------------|----------|
| last_activity desc (most recent first) | Mirrors chat-list convention. | ✓ |
| created_at desc (newest deploy first) | Newest deployments at top. | |
| Alphabetical by name | Stable, predictable. | |

### Model field display
| Option | Description | Selected |
|--------|-------------|----------|
| Full provider/model id | `anthropic/claude-haiku-4-5` verbatim. | ✓ |
| Trimmed model name only | Drop provider prefix. | |
| Provider badge + short name | `[anthropic] haiku-4-5`. | |

### /v1/agents fetch error post-load
| Option | Description | Selected |
|--------|-------------|----------|
| Inline retry banner above the list | Last-known data stays visible. | ✓ |
| Replace list with full-screen error state | Full takeover. | |
| Material SnackBar at bottom | Toast. | |

---

## New Agent wizard (incl. Telegram add-on)

### Form layout
| Option | Description | Selected |
|--------|-------------|----------|
| Single scroll: clone → model → name → deploy | Vertical scroll, all visible. | |
| Wizard (3 steps) | Multi-step routes. | ✓ |
| Bottom sheet from FAB | Modal sheet. | |

### Recipe picker UX
| Option | Description | Selected |
|--------|-------------|----------|
| Horizontal scrolling card row | Cards left-to-right with selected border. | ✓ |
| Vertical list with radio dot | Stacked rows. | |
| Dropdown / picker sheet | Modal sheet on tap. | |

### Model picker UX (300+ entries)
| Option | Description | Selected |
|--------|-------------|----------|
| Searchable full-screen picker (push route) | Search + virtualized list. | ✓ |
| Grouped picker by provider | Collapsed by provider. | |
| Curated favorites + "Show all" | ~6 popular + link to full. | |

### Telegram in deploy flow
| Option | Description | Selected |
|--------|-------------|----------|
| Both: inapp default ON, Telegram optional add-on | Inapp always; Telegram opt-in adds 2nd container. | ✓ |
| Single pick: inapp OR Telegram (mutually exclusive) | Radio per agent. | |
| Defer Telegram to later phase | Keep Phase 23 D-28 as-is. | |

### Telegram fields source
| Option | Description | Selected |
|--------|-------------|----------|
| Yes — dynamic from recipe metadata, mirror web | Pull from recipe.channels.telegram.required_user_input + optional_user_input. | ✓ |
| No — hardcode the 2 known fields | Hardcode Bot Token + Allowed User ID. | |

**User notes:** "we do have telegram dude. api and recipess allow" + "inline two fields, check frontend. bottoken and telegram id of user i think. check recipee, UI is built around it" — drove the dumb-client rendering pattern.

### Multi-channel deploy mechanics
| Option | Description | Selected |
|--------|-------------|----------|
| Mirror web: 1×/runs + N×/start sequentially | No backend changes; mobile orchestrates. | ✓ |
| Add backend POST /v1/agents/deploy | Single atomic endpoint. | |

**User notes:** "how does web and api works dude? I think a single api call receives everything and starts agent, deep check" — investigation showed web does sequential calls; user accepted mirroring.

### Telegram /start failure (when inapp succeeded)
| Option | Description | Selected |
|--------|-------------|----------|
| Route to Chat (inapp works) + persistent banner | Chat opens, sticky failed-banner with Retry. | ✓ |
| Stay on New Agent screen + inline error | Don't route until resolved. | |
| Roll back: stop the inapp container | All-or-nothing. | |

### Telegram toggle visibility
| Option | Description | Selected |
|--------|-------------|----------|
| Yes — only show toggle when recipe supports it | Render only when recipe.channels_supported includes 'telegram'. | ✓ |
| Always render toggle, gray it out | Greyed for unsupported. | |

### channel_provider_compat / BYOK label
| Option | Description | Selected |
|--------|-------------|----------|
| Inline alert under model picker (web parity) | Original option — superseded by user pivot. | |
| Block deploy with explanatory error | Disable Deploy button + alert. | |
| Defer to post-MVP | Skip alert. | |

**User notes:** "only hermes needs antrhopic api key, others openrouter" — pivoted to single-BYOK-field with dynamic label (next question).

### BYOK API key field shape
| Option | Description | Selected |
|--------|-------------|----------|
| Single field, label from channel_provider_compat | One field; label flips OpenRouter ↔ Anthropic by recipe metadata. | ✓ |
| Two fields (always show both, gray inapplicable) | Both visible. | |
| Hardcode hermes=Anthropic, others=OpenRouter | Dart if-else. | |

### BYOK key storage
| Option | Description | Selected |
|--------|-------------|----------|
| flutter_secure_storage, one key per provider | Per-provider (openrouter / anthropic) in Keychain. | ✓ |
| Per-deploy entry only, never persisted | Paste every time. | |
| Per-agent storage | Keyed by agent_instance_id. | |

### Wizard step breakdown
| Option | Description | Selected |
|--------|-------------|----------|
| 1: Clone, 2: Model + BYOK, 3: Name + Telegram + Deploy | BYOK lives next to model. | ✓ |
| 1: Clone + Model, 2: BYOK + Telegram, 3: Name + Deploy | Front-load choices. | |
| 1: Clone, 2: Model, 3: Name + BYOK + Telegram + Deploy | Step 3 crowded. | |

### Name validation + collision UX
| Option | Description | Selected |
|--------|-------------|----------|
| Lowercase regex `^[a-z0-9][a-z0-9_-]*$` + pre-flight collision check | Inline validation + GET /v1/agents on Deploy tap; AlertDialog on collision. | ✓ |
| Lowercase regex only, no pre-flight | Backend UPSERT handles collisions. | |
| Free-form name, no client-side validation | Trust backend. | |

### Smoke verdict=FAIL UX
| Option | Description | Selected |
|--------|-------------|----------|
| Stay on wizard, show inline error with smoke detail + Retry | Red box below Deploy with Retry / Edit. | ✓ |
| Push to a SmokeFailureScreen with full RunResponse | Dedicated debug screen. | |
| Toast "Smoke failed" + back to step 1 | Brief toast. | |

### Deploy success destination
| Option | Description | Selected |
|--------|-------------|----------|
| Route to Chat for the new agent (replace wizard route) | go_router.go('/chat/<id>'). | ✓ |
| Pop back to Dashboard | User taps into new agent. | |
| Show a success card with 'Open Chat' / 'Back to Dashboard' | Wizard stays open with success card. | |

### Recipe picker initial state
| Option | Description | Selected |
|--------|-------------|----------|
| No pre-selection — user must pick | All cards unselected; Next disabled. | ✓ |
| Pre-select last-used recipe | Read most recent agent's recipe. | |
| Pre-select first recipe alphabetically | Always pre-select first sorted. | |

### Wizard cancel UX
| Option | Description | Selected |
|--------|-------------|----------|
| X close top-right + confirmation if any field touched | Modal-feeling wizard. | ✓ |
| Back arrow + system back gesture, no confirmation | Standard back. | |
| X close + always confirm regardless | Always show dialog. | |

### Smoke loading UX (~30s)
| Option | Description | Selected |
|--------|-------------|----------|
| Replace Deploy button with progress card + elapsed timer + Cancel | Card with spinner + "00:14" timer + Cancel via dio CancelToken. | ✓ |
| Disable Deploy + small spinner inline, no timer | Button stays visible. | |
| Full-screen modal overlay with spinner | Translucent overlay. | |

### Smoke verdict=PASS UX
| Option | Description | Selected |
|--------|-------------|----------|
| Auto-advance to /start (no extra confirmation) | Web behavior. | ✓ |
| Show verdict card + 'Continue' button | Two-tap. | |
| Show full smoke result + Continue | Verbose. | |

### UI-02 + Phase 23 D-28 amendments
| Option | Description | Selected |
|--------|-------------|----------|
| Yes — capture as AMD in CONTEXT.md, amend in commit chain | AMD-01 + AMD-02. | ✓ |
| No — leave specs as-is, document divergence | Doc/code drift. | |

---

## Chat

### Bubble design
| Option | Description | Selected |
|--------|-------------|----------|
| Right/left + invert colors | User: right black/white. Assistant: left grey/black. | ✓ |
| Right/left, same bg, just align | Strictly monochrome. | |
| Left for both, prefix with 'You:' / 'Agent:' | Telegram/IRC style. | |

### History fetch + SSE connect order
| Option | Description | Selected |
|--------|-------------|----------|
| Parallel: kick off both, dedupe by message_id | Map keyed by message_id. | ✓ |
| Sequential: history first, SSE second | Wait then connect. | |
| SSE first, history second | Live updates first. | |

### Input mechanics
| Option | Description | Selected |
|--------|-------------|----------|
| Multiline expanding + Send button (Enter = newline) | Up to ~5 lines; Send button only commit. | ✓ |
| Multiline + Send + Cmd/Ctrl-Enter to send | Plus keyboard shortcut. | |
| Single-line, Enter = send | Single-line. | |

### Optimistic / pending message rendering
| Option | Description | Selected |
|--------|-------------|----------|
| Insert user bubble immediately + assistant 'typing…' bubble | Full-opacity user bubble + animated 3 dots assistant bubble. | ✓ |
| User bubble grayed/spinning, no typing indicator | Dimmed bubble until 202. | |
| Defer rendering until SSE confirms | No optimistic. | |

### Failed message rendering
| Option | Description | Selected |
|--------|-------------|----------|
| Distinct bubble: red border + warning icon + Retry tap | Sheet with Retry + Copy error. | ✓ |
| Strikethrough user bubble + caption | No assistant ghost row. | |
| Pure text, no special chrome | Normal bubble with prefix. | |

### SSE lifecycle
| Option | Description | Selected |
|--------|-------------|----------|
| Connect on mount, disconnect on pop, reconnect on foreground with Last-Event-ID | Per Phase 23 D-13 contract. | ✓ |
| Persist SSE across screens | Power Dashboard live status. | |
| Reconnect every visit without Last-Event-ID | Fresh connection. | |

### Auto-scroll behavior
| Option | Description | Selected |
|--------|-------------|----------|
| Auto-scroll unless user scrolled up | "New message ↓" chip when suppressed. | ✓ |
| Always auto-scroll to bottom | Yanks reading position. | |
| Never auto-scroll | User manually. | |

### Long-bot-wait UX
| Option | Description | Selected |
|--------|-------------|----------|
| Typing indicator only (no timer, no escape) | Dots only. | ✓ |
| Typing + elapsed timer after 30s | "00:42 · still working…". | |
| Typing + Cancel button | Misleading (can't actually cancel). | |

### Chat AppBar content
| Option | Description | Selected |
|--------|-------------|----------|
| Back arrow + agent name + status dot | Title + subtitle (model + status). | ✓ |
| Back arrow + agent name only | Just name. | |
| Back + name + 3-dot overflow | Stop / Restart actions. | |

### Empty Chat state
| Option | Description | Selected |
|--------|-------------|----------|
| Centered hint above input | "Say hi to <name>" italic muted. | ✓ |
| Matrix-style ASCII banner | Like Dashboard empty state. | |
| Just input bar + empty list | No copy. | |

### History pagination
| Option | Description | Selected |
|--------|-------------|----------|
| Load latest 1000 + 'Older messages not shown' banner at top | Default 200; tap-to-load 1000; beyond = "first {N-1000} hidden". | ✓ |
| Always load full 1000 on open | No pagination. | |
| Load 50 + load-more on scroll-to-top | Pretends backend supports cursors. | |

### Markdown rendering
| Option | Description | Selected |
|--------|-------------|----------|
| Render markdown via flutter_markdown | Code, lists, bold, inline code; no images. | ✓ |
| Plain text only, monospace for everything | No parsing. | |
| Code-fence detection only | Partial markdown. | |

### Markdown link tap behavior
| Option | Description | Selected |
|--------|-------------|----------|
| Tap opens external browser via url_launcher (https + http only) | Whitelist schemes. | ✓ |
| All schemes open via url_launcher | Trust LLM. | |
| Render as plain text, no tap action | Inert links. | |

### Retry idempotency-key semantics
| Option | Description | Selected |
|--------|-------------|----------|
| New idempotency-key (real retry) | Fresh uuid v4; new pending bubble. | ✓ |
| Same idempotency-key (intentional replay) | Returns cached failure. | |
| Offer both: Retry + Resend cached | Power-user sheet. | |

### Container not running mid-chat
| Option | Description | Selected |
|--------|-------------|----------|
| Disable input + 'Agent stopped · Restart' banner above input | Greyed input, persistent banner. | ✓ |
| Show banner only, leave input enabled | Surface failure via failed-bubble. | |
| Block screen with full-page 'Agent stopped' state | Full takeover. | |

### Telegram-deploy-failed banner
| Option | Description | Selected |
|--------|-------------|----------|
| Sticky at top of Chat with X to dismiss + Retry | Persistent banner below AppBar. | ✓ |
| One-time SnackBar on Chat mount | Toast. | |
| Modal AlertDialog before chat opens | Block Chat. | |

### Send button states + error feedback
| Option | Description | Selected |
|--------|-------------|----------|
| Disabled when empty + spinner when in-flight; failures via failed-bubble only | Single error vocabulary. | ✓ |
| Spinner + SnackBar on POST failure | Two error vocabularies. | |
| Send always enabled, button text changes | Text-only feedback. | |

### 401 mid-conversation recovery
| Option | Description | Selected |
|--------|-------------|----------|
| Clear session + route to Login + 'Signed out · Sign in to continue' banner | After re-auth, land on Dashboard. | ✓ |
| Route to Login then auto-resume Chat after re-auth | Deep-link state plumbing. | |
| Show inline 'Session expired' banner on Chat with Re-auth button | Don't unmount Chat. | |

### Bubble timestamps
| Option | Description | Selected |
|--------|-------------|----------|
| Inline grouped: shown only when there's a >5min gap | Centered grey caption between bubbles. | ✓ |
| Timestamp under every bubble | Always visible. | |
| Long-press bubble to reveal timestamp | Hidden by default. | |
| No timestamps in MVP | Punt. | |

### Long-press on bubble
| Option | Description | Selected |
|--------|-------------|----------|
| Long-press → sheet with Copy + Select text | Critical for code blocks. | ✓ |
| Long-press → Copy only | No partial-copy. | |
| Long-press disabled in MVP | System SelectableText. | |

---

## Wizard navigation + indicator

### Step navigation (back from step 3)
| Option | Description | Selected |
|--------|-------------|----------|
| Yes — back arrow per step preserves state | Riverpod-scoped wizard state. | ✓ |
| Forward-only — back exits wizard with confirmation | Cancel at any step. | |
| Back resets the step's data | Punishes user. | |

### Step indicator
| Option | Description | Selected |
|--------|-------------|----------|
| Thin stepper bar: ● ── ○ ── ○ | Current filled, others hollow, with labels. | ✓ |
| Plain text: 'Step 2 of 3' in AppBar subtitle | Minimalist. | |
| No indicator | Users figure it out. | |

---

## Dashboard lifecycle actions

### Lifecycle from Dashboard rows
| Option | Description | Selected |
|--------|-------------|----------|
| No — lifecycle only via Chat (Restart on stopped-banner) | Rows are purely navigational. | ✓ |
| Yes — long-press row opens action sheet (Stop / Restart / Delete) | Action sheet. | |
| Yes — swipe-left to reveal Stop / Restart icons | iOS-style swipe. | |

### Long agent name + model id truncation
| Option | Description | Selected |
|--------|-------------|----------|
| Single-line ellipsis on both name + model | maxLines: 1 + ellipsis. | ✓ |
| Wrap to 2 lines on Dashboard, ellipsis on AppBar | Variable row height. | |
| Marquee/scroll long names on tap | Cute; complex. | |

---

## Shared UI primitives + Plan structure + Exit gate

### Shared widget set in lib/shared/
| Option | Description | Selected |
|--------|-------------|----------|
| Yes — ship a shared widget set in Wave 1 before screens | StatusDot, RetryBanner, SkeletonRow, TypingDots, FailedBubble, RestartBanner, AsciiAgentBanner, ConfirmDialog, EmptyState. | ✓ |
| Build per-screen, refactor when duplication shows up | Refactor pass after Wave 4. | |
| Skip shared/, accept widget duplication | Each screen self-contained. | |

### Plan wave structure
| Option | Description | Selected |
|--------|-------------|----------|
| 5 waves: Shared+Auth → Dashboard → NewAgent → Chat → Integration test | Each wave delivers a demoable surface. | ✓ |
| 3 waves parallel: Auth — Dashboard — (NewAgent + Chat together) | Front-load login, parallelize. | |
| 1 wave per screen, no shared layer | Sequential. | |

### Exit-gate test
| Option | Description | Selected |
|--------|-------------|----------|
| UI-driven integration test extending Phase 24 spike + manual smoke artifact | screens_e2e_test.dart against live api_server + spikes/flutter-screens-roundtrip.md. | ✓ |
| Manual smoke artifact only | No automated UI test. | |
| Widget tests per screen + manual smoke | Per-screen tests + manual integrated. | |

### OAuth in integration test
| Option | Description | Selected |
|--------|-------------|----------|
| Test seam: AuthService interface + test impl POSTs /v1/auth/google/mobile with manual SESSION_ID | Real OAuth verified by manual smoke. | ✓ |
| Skip Login in integration test — start at Dashboard with pre-seeded session | --dart-define SESSION_ID. | |
| Don't automate — manual only | Reverts. | |

---

## Local state + version + deep links + accessibility

### Accessibility enforcement
| Option | Description | Selected |
|--------|-------------|----------|
| Manual checklist on each PR + golden_toolkit screenshot tests | Per-PR enforcement. | ✓ |
| Add semantics-tester widget tests | Rigorous. | |
| Floor only; no per-PR enforcement | Defer to a11y-hardening phase. | |

### Local-state persistence
| Option | Description | Selected |
|--------|-------------|----------|
| Nothing else — always re-fetch from backend | DB is source of truth. | ✓ |
| Cache /v1/recipes + /v1/models in shared_preferences with TTL | Modest UX win. | |
| Local SQLite mirror of /v1/agents + last N messages | Real offline cache. | |

### App version bump
| Option | Description | Selected |
|--------|-------------|----------|
| Confirm 0.2.0+2 | Phase 24 carry-forward. | ✓ |
| Bump to 0.3.0+3 to match milestone v0.3 | Sync to milestone. | |
| Skip version bump | Stay 0.1.0+1. | |

### Deep-link surface
| Option | Description | Selected |
|--------|-------------|----------|
| OAuth callback only — no app-internal deep links in MVP | Minimal surface. | ✓ |
| Add `solvrlabs://agent/<id>` for opening Chat from external links | App-internal deep link. | |

---

## Claude's Discretion items (no questions asked, defaults chosen)

- Provider order on Login (Google first, GitHub second).
- BYOK field obscureText: true with reveal eye toggle.
- Step validation predicates inline with each step's "Next" enabled callback.
- Message length cap on send: none enforced client-side; trust backend.
- Pull-to-refresh visual indicator: Material default.
- Connectivity-offline app-wide banner: NONE — per-call error handling is the single failure vocabulary.
- AuthService interface method names: signInWithGoogle / signInWithGithub / signOut.
- ASCII banner pulls names from `GET /v1/recipes` (Riverpod provider).
- ASCII banner cycling animation: ~2s cross-fade with `Curves.easeInOut`.
- Riverpod provider granularity: planner picks (likely one provider per screen + shared providers for ApiClient and AuthService).
- Wizard state container: Riverpod-scoped provider tied to wizard route group lifetime.
- golden_toolkit snapshot count: planner picks (suggest Dashboard empty / Dashboard populated / Login / Chat with markdown).

---

## Deferred Ideas (captured in 25-CONTEXT.md `<deferred>` section)

See `25-CONTEXT.md` `<deferred>` section. Highlights:
- Telegram pairing flow (`dmPolicy:pairing`) — D-59
- Backend `POST /v1/agents/deploy` single-shot endpoint
- Agent Stop / Restart from Dashboard rows (long-press / swipe / detail)
- Agent Delete endpoint + Dashboard swipe-to-delete
- Background SSE / push notifications
- Token-level streaming chat (seeds/streaming-chat.md)
- Markdown image rendering
- App-internal deep links
- Connectivity-offline app-wide banner
- Cached recipes/models / SQLite mirror
- In-app Settings / Profile / Browse tabs functioning
- Universal Links / App Links
- Real Solvr Labs app icon + native splash
- fastlane / TestFlight / Play Store distribution
- Apple Privacy Manifest
- Push / crash reporting / analytics
- Localization (l10n)
- Dark mode
- In-app debug menu / env switcher (explicitly rejected)
- Multi-channel Restart endpoint extension
- Bubble timestamps on every bubble (current: grouped >5min gap)

---
name: void
real: ide-only
source: https://github.com/voideditor/void
language: TypeScript
license: Apache-2.0
stars: 28600
last_commit: unknown
---

# Void Editor

## L1 — Paper Recon

**Install mechanism:** IDE binary (VSCode fork) — **no headless CLI**

**Install command:**
```
# No standalone CLI published.
# Void is distributed as an IDE binary from voideditor.com.
# Repo contains `cli` and `remote` folders but those support the IDE
# (same as VSCode's `code` launcher), NOT a headless agent runner.
```

**Supported providers:** Anthropic, OpenAI, generic LLM providers (per repo topics: `openai`, `claude`, `llm`). Same BYOK shape as Cursor — keys entered into IDE settings.

**Model-selection mechanism:** IDE settings UI

**Auth mechanism (best guess from docs):** IDE settings / local state — keys stored in the IDE's config, likely under `~/.config/void/` or similar. **Not headless-accessible** without reverse-engineering the storage format.

**Chat I/O shape:** IDE chat panel only. No exposed CLI, no HTTP server, no REPL, no MCP server documented. **Does NOT fit any existing chat_io mode** in the matrix.

**Persistent state needs:** IDE workspace state, settings JSON, local extensions — all tied to the IDE binary.

**Notes from README (anything unusual for sandboxing):**
- **`real: ide-only`** — honest category mark. Same shape as Cursor (the thing Void forks) — explicitly NOT a candidate for the agent recipe pipeline. Listed for catalog completeness.
- **CRITICAL NEW FINDING:** The README says **"the project is currently paused"** — "We won't be actively reviewing Issues and PRs while the team explores other directions." **Effectively on ice as of the README snapshot.** Combined with the absence of a CLI, Void is a no-go for v1 AND is not a reliable future target.
- **Apache-2.0 + LICENSE-VS-Code.txt** (inherited from the VSCode fork).
- **Fork of `microsoft/vscode`** — 95.3% TypeScript, matches Cursor/VSCode architecture.
- **Schema gap:** the matrix doesn't currently have a category for "IDE-only agents" — they get filtered out at the L1 paper recon stage. That's probably the right call, but the fact that two of the most popular names in the OSS coding-agent space (Void, Cursor-the-IDE) are IDE-only means the frontend catalog needs to either (a) hide them or (b) link out to their install pages without promising session support. Flag for Phase 02.5.
- **Recipe fit verdict:** zero. Do not spend L2 budget on Void. Document it in the matrix, move on.

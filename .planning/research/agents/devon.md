---
name: devon
real: true
source: https://github.com/entropy-research/Devon
language: Python
license: AGPL-3.0
stars: 3500
last_commit: 2024-07-29
---

# Devon

## L1 — Paper Recon

**Install mechanism:** pipx (backend) + npm/npx (UI). Two-component install.

**Install command:**
```
pipx install devon_agent
npx devon-ui              # web UI
# OR
npm install -g devon-tui  # terminal UI alternative
```

**Supported providers:** Anthropic (Claude 3.5 Sonnet), OpenAI (GPT-4o), Groq (Llama3-70b), Ollama (Deepseek-6.7b, experimental). Gemini "planned" but not shipped.

**Model-selection mechanism:** UI setting / TUI config + env var discrimination by which `*_API_KEY` is set

**Auth mechanism (best guess from docs):** `env_var` — `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GROQ_API_KEY` read from environment. **Clean headless path, matches existing matrix category.**

**Chat I/O shape:** Multiple modes:
- `http_gateway` via `devon-ui` (Electron/web)
- `terminal_only` via `devon-tui` (full-screen TUI, same category as mentat)
- `exec_per_message` possibly via `devon_agent` backend CLI — unclear from README whether there's a direct prompt-in/prompt-out flag.

**Persistent state needs:** workspace dir; no documented central state path.

**Notes from README (anything unusual for sandboxing):**
- **AGPL-3.0 license** — **conflicts with CLAUDE.md "permissive license (MIT or Apache-2.0)" stance for the platform**, BUT Devon runs *inside* the user's container, not linked against our code — AGPL obligations attach to Devon's own distribution, not to Agent Playground. Still flag for legal review.
- **Last commit: 2024-07-29.** **Stagnant for ~21 months as of 2026-04-14.** Compared to Devika (also stale but no definitive last-commit date visible), Devon is demonstrably more stagnant. 3.5k stars vs Devika's 19.5k suggests Devika is the more community-endorsed Devin clone despite both being abandoned.
- **Three interfaces (web UI, TUI, backend CLI)** is unusual — gives us flexibility for the recipe: we can pick `devon-tui` for a `terminal_only` variant OR `devon_agent` for headless exec.
- **Devon vs Devika decision:** Devika is more alive (19.5k stars, supposedly still receiving updates) but heavier (Playwright + bun). Devon is cleaner install (pipx + npm) but definitively stagnant. **Neither is a strong v1 recipe target;** recommend parking both until L2 shows which install actually completes.
- Terminal-only mode via `devon-tui` exercises the `terminal_only` chat_io category a second time (first = mentat) → good schema stress-test candidate.

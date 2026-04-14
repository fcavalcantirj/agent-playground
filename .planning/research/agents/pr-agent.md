---
name: pr-agent
real: true
source: https://github.com/Codium-ai/pr-agent
language: Python
license: AGPL-3.0
stars: 10900
last_commit: unknown
---

# PR-Agent (Qodo / CodiumAI)

## L1 — Paper Recon

**Install mechanism:** pip install; also Docker image; also GitHub Action

**Install command:**
```
pip install pr-agent
# OR
docker pull codiumai/pr-agent:latest
```

**Supported providers:** OpenAI (primary), plus any LLM compatible via litellm underneath (so effectively Anthropic / OpenRouter / Groq / Bedrock / local via the usual litellm config). Plus code-host integrations (GitHub, GitLab, Bitbucket, Azure DevOps, Gitea).

**Model-selection mechanism:** config field (litellm-style) + CLI flags

**Auth mechanism (best guess from docs):** `env_var` — `OPENAI_KEY` for the LLM, `GITHUB_TOKEN` for the PR host. Clean, matches existing matrix category. **Two required secrets per invocation** — schema needs `required_secrets` to support multi-secret combos, which matches our current design assumption.

**Chat I/O shape:** `one_shot_task` — CLI form is `pr-agent --pr_url <url> review`. Input = PR URL + command verb (`review`, `describe`, `improve`, `ask`, `update_changelog`). Output = markdown posted back to the PR (or stdout). There is no REPL and no persistent session. **Same category as gpt-engineer / SWE-agent — whole session = one run.**

**Persistent state needs:** none (ephemeral CLI) — writes nothing persistent, reads config + creds from env.

**Notes from README (anything unusual for sandboxing):**
- **PR-Agent IS runnable as a CLI and as a self-hosted Docker container.** It is NOT GitHub-Action-only, despite its typical promotion. This directly contradicts the concern in the task brief — it fits our recipe pipeline cleanly.
- **NARROW DOMAIN:** only operates on pull requests. Users can't say "build me a game"; they can only say "review this PR." **This is a schema stress-test:** the recipe needs a `task_shape` or `input_schema` field so the frontend knows to collect a PR URL rather than a free-text prompt. No existing agent in the matrix has this constraint.
- **AGPL-3.0** — same license note as Devon. Runs inside user container, obligations attach to Qodo, not to us.
- **Recipe fit:** viable as a **task-typed agent** (`input_schema: { pr_url: string, command: enum[review|describe|improve|ask|update_changelog] }`), but requires a frontend form rather than a chat box. **This is a NEW schema dimension** not yet in the matrix — reveals a gap.
- Very popular (10.9k stars), actively promoted by Qodo (formerly CodiumAI); confidence on maintenance is high even without commit-date verification.
- Webhooks-mode (GitHub PR event → auto-run) is a *different* deployment from the CLI — not relevant to our recipe pipeline, skip.

# Phase 22c.2 — Identity Baking

**Status:** seed CONTEXT (pre-spec).
**Created:** 2026-04-29.
**Theme:** dynamically bake the user's chosen `agent_name` and `personality` into the bot's actual runtime identity, per-recipe. The agent is working — the SOUL just isn't filled in yet.

---

## Why this phase exists

User signal 2026-04-29 (after live Telegram round-trip):
> "we need to bake the name into the soul dynamically, as well as personalities. you're lost dude. FUCKING AGENT IS WORKING"

Phase 22c.1 surfaced + plumbed `agent_name` end-to-end and loosened the smoke pass_if so blank-slate recipes (like nullclaw) don't false-FAIL when paired with personality presets that don't elicit names. But the deeper truth remained:

- The bot doesn't KNOW its `agent_name` at runtime — never reaches container env, argv, or workspace files.
- Personality presets are a **stub** (per `services/personality.py:9-11` docstring): they only override the deploy-time smoke prompt; they are NOT injected into the live bot's system prompt.
- nullclaw's reply during the smoke literally cited the missing identity surface: `"IDENTITY.md exists but is empty — just a template waiting to be filled in"`. The recipe expects a workspace identity file; we don't write it.

22c.2 is the work to actually wire identity through to the bot's runtime, per recipe.

---

## Scope

### R-1. Per-recipe identity-injection contract

Each recipe declares HOW its bot consumes identity. The recipe schema gains an `identity` block (additive, optional — recipes without it use no injection). Examples per recipe:

- **nullclaw:** writes `/workspace/IDENTITY.md` (mounted volume) with content `Name: {agent_name}\nPersonality: {personality_label}\n` BEFORE container start. Empirically confirmed by the bot's own smoke reply citing the missing file.
- **hermes:** sh-chains `hermes config set agent.name "{agent_name}" && hermes config set model "{model}" && exec hermes gateway run -v` as the persistent argv. Recipe author already documented this fix at `recipes/hermes.yaml:322-325`. (Also closes the silent-model-drop bug deferred from 22c.1.)
- **picoclaw / openclaw / nanobot:** TBD — empirical reading of each recipe's identity surface in the spec phase. Likely a system-prompt CLI flag or config write.

The runner reads the recipe's `identity` block at deploy time and performs the injection BEFORE handing control to the bot.

### R-2. Personalities become real (not just smoke prompts)

Per `services/personality.py:9-11` the docstring promised:
> "The personalities also serve as the agent's 'system prompt' character for later chat sessions (Phase 21 work — not part of this surface yet)."

22c.2 ships that promise. The 6 personality presets (polite-thorough, concise-neat, skeptical-critic, cheerful-helper, senior-architect, quick-prototyper) become the bot's persistent system prompt — injected via R-1's per-recipe contract.

Decision points for the spec phase:
- Are personalities per-recipe-overridable? (e.g., a recipe declares which personalities it supports)
- What happens when a personality conflicts with a recipe's intrinsic persona (e.g., picoclaw's pico-aggressive persona vs polite-thorough)?
- Does the live bot expose `/personality` as a Telegram command (mirror of the existing `/model` command)?

### R-3. Hermes persistent silent-model-drop fix (deferred from 22c.1 R-7)

`recipes/hermes.yaml:213-219` persistent argv is `[gateway, run, -v]` — no `$MODEL` substitution, so the user's model selection is silently dropped. The author already wrote the fix in a comment (line 322-325). Implement it as part of R-1 hermes recipe identity contract — the same `hermes config set` chain handles both name AND model.

### R-4. Empirical matrix verification

After R-1 + R-2 ship, run the full matrix end-to-end via curl + real LLM (no mocks per CLAUDE.md golden rule):

| Recipe | Personality | Verify | Expected |
|--------|-------------|--------|----------|
| nullclaw | each of 6 presets | bot self-identifies with agent_name + adopts personality | PASS |
| hermes | each of 6 presets | `/model` reports user's pick; reply tone matches personality | PASS |
| picoclaw | each of 6 presets | bot says agent_name + persona consistent | PASS |
| openclaw | each of 6 presets | same | PASS |
| nanobot | each of 6 presets | same | PASS |

That's 30 combinations. Some will fail; failures inform recipe-specific identity-contract refinement.

---

## Out of scope (deferred)

- **Real DELETE / GET endpoints, dashboard subpage backends, vault** — Phase 22c.1 + 22c.3+
- **Multi-personality on a single agent (chat-time persona swap)** — out of scope, future
- **Custom personalities (user-defined system prompts)** — future feature work
- **Personality-aware run history / dashboard analytics** — Phases 22c.5+

---

## Architectural notes

### Why "per-recipe contract" instead of a generic system-prompt prefix

Tried prompt-prefix during the smoke session (`"Your name is X. <prompt>"`). Insufficient because:
- nullclaw consults workspace files (IDENTITY.md), not prompt content
- hermes uses internal config (`hermes config set`), not prompt
- picoclaw / openclaw / nanobot likely have their own injection points

Each recipe's bot has a different "soul" mechanism. A one-size-fits-all prompt prefix would work for some and silently fail for others — exactly the silent-failure pattern this phase is supposed to eliminate. The recipe-author-cooperation contract is the right shape.

### Schema additions (subject to spec phase refinement)

```yaml
identity:
  inject_method: "workspace_file" | "config_command" | "env_var" | "system_prompt_arg" | "none"
  spec:  # one of, depending on inject_method
    workspace_file:
      path: "/workspace/IDENTITY.md"
      template: |
        Name: {agent_name}
        Personality: {personality_label}
        Personality description: {personality_desc}
    config_command:
      argv: ["hermes", "config", "set", "agent.name", "{agent_name}"]
      sequence: pre_start  # run before persistent.spec.argv
    env_var:
      vars:
        AP_AGENT_NAME: "{agent_name}"
        AP_PERSONALITY_LABEL: "{personality_label}"
        AP_PERSONALITY_PROMPT: "{personality_system_prompt}"
    system_prompt_arg:
      argv_template: ["--system-prompt", "You are {agent_name}, a {personality_label} assistant. {personality_desc}"]
```

Spec phase decides the exact shape. This is illustrative only.

---

## Empirical evidence anchor (carried forward from 22c.1)

- nullclaw smoke reply 2026-04-29 (before 22c.1 fix): *"I'm in a fresh setup where IDENTITY.md doesn't exist"* — recipe expects identity file.
- nullclaw smoke reply 2026-04-29 (after 22c.1 fix, same session): *"IDENTITY.md exists but is empty — just a template waiting to be filled in"* — recipe ships an empty template; identity needs to be written by the runner pre-start.
- hermes self-identifies as "hermes" regardless of agent_name → confirms hermes has internal identity bake mechanism (the `hermes config` chain).
- Per-recipe model-honor table from 22c.1 CONTEXT (only hermes has the silent-drop gap; the other 4 already honor `$MODEL`).

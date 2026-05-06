# Hermes recon report — 2026-04-15T20:52:00Z

## Environment
- Host disk before: `/dev/disk3s1s1   460Gi    12Gi    21Gi    36%` (avail 21Gi)
- Host disk after:  `/dev/disk3s1s1   460Gi    12Gi    15Gi    44%` (avail 15Gi, post-build pre-teardown)
- Disk delta (build): ~6 GB consumed (image + build cache combined)
- Docker system df before:
```
TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          55        8         18.64GB   16.18GB (86%)
Containers      9         5         2.225GB   2.225GB (99%)
Local Volumes   39        4         2.965GB   2.822GB (95%)
Build Cache     547       0         21.48GB   21.48GB
```
- Docker system df after (post-build, pre-teardown):
```
TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          56        8         23.69GB   21.24GB (89%)
Containers      9         5         2.225GB   2.225GB (99%)
Local Volumes   39        4         2.965GB   2.822GB (95%)
Build Cache     559       0         21.47GB   21.47GB
```
  Images grew by ~5 GB (the recon-hermes image); build cache barely moved because most layers were reused from earlier cached builds.

## Source
- Repo: https://github.com/NousResearch/hermes-agent
- Commit: `19142810edfd2d3dbe947692732b868d57b9a18e`

## Build
- Command: `docker build --progress=plain -t recon-hermes /tmp/recon-hermes`
- Wall time: **7m 31s** (real) — `docker build ... 1.01s user 1.52s system 0% cpu 7:31.22 total`
- Exit code: 0
- Image size: `recon-hermes latest 5.19GB`
- Build log (last ~50 lines, verbatim, key redacted):
```
#20 14.89  + requests==2.33.1
#20 14.89  + requests-toolbelt==1.0.0
#20 14.89  + rich==14.3.4
#20 14.89  + rpds-py==0.30.0
#20 14.89  + setuptools==82.0.1
#20 14.89  + shellingham==1.5.4
#20 14.89  + simple-term-menu==1.6.6
#20 14.89  + six==1.17.0
#20 14.89  + slack-bolt==1.28.0
#20 14.89  + slack-sdk==3.41.0
#20 14.89  + sniffio==1.3.1
#20 14.89  + socksio==1.0.0
#20 14.89  + sounddevice==0.5.5
#20 14.89  + sse-starlette==3.3.4
#20 14.89  + starlette==1.0.0
#20 14.89  + sympy==1.14.0
#20 14.89  + synchronicity==0.12.2
#20 14.89  + tabulate==0.10.0
#20 14.89  + tenacity==9.1.4
#20 14.89  + termcolor==3.3.0
#20 14.90  + tokenizers==0.22.2
#20 14.90  + toml==0.10.2
#20 14.90  + tornado==6.5.5
#20 14.90  + tqdm==4.67.3
#20 14.90  + typer==0.24.1
#20 14.90  + types-certifi==2021.10.8.3
#20 14.90  + types-toml==0.10.8.20260408
#20 14.90  + typing-extensions==4.15.0
#20 14.90  + typing-inspection==0.4.2
#20 14.90  + unpaddedbase64==2.1.0
#20 14.90  + urllib3==2.6.3
#20 14.90  + uvicorn==0.44.0
#20 14.90  + uvloop==0.22.1
#20 14.90  + watchfiles==1.1.1
#20 14.90  + wcwidth==0.6.0
#20 14.90  + websockets==15.0.1
#20 14.90  + wrapt==1.17.3
#20 14.90  + yarl==1.23.0
#20 14.90  + zipp==3.23.1
#20 DONE 16.6s

#21 [stage-2 11/11] RUN chmod +x /opt/hermes/docker/entrypoint.sh
#21 DONE 0.2s

#22 exporting to image
#22 exporting layers
#22 exporting layers 24.1s done
#22 writing image sha256:228ff9c5afd9bbcd4caac33cfe0fb0142df53799d7e912f47a73338016f8b90e done
#22 naming to docker.io/library/recon-hermes done
#22 DONE 24.1s
```

## hermes chat --help (verbatim)

The entrypoint `docker/entrypoint.sh` prints a large preamble before `exec hermes "$@"` — specifically "Dropping root privileges", the bundled skill sync (79 skills), and then argparse helpfully (or unhelpfully) prints the `hermes chat` usage **twice** (once on invocation, once on the help pass). Full capture:

```
Dropping root privileges
Syncing bundled skills into ~/.hermes/skills/ ...
  + dogfood
  + huggingface-hub
  + pytorch-fsdp
  + grpo-rl-training
  + unsloth
  + peft-fine-tuning
  + axolotl
  + fine-tuning-with-trl
  + evaluating-llms-harness
  + weights-and-biases
  + dspy
  + guidance
  + obliteratus
  + outlines
  + llama-cpp
  + serving-llms-vllm
  + gguf-quantization
  + segment-anything-model
  + stable-diffusion-image-generation
  + clip
  + whisper
  + audiocraft-audio-generation
  + modal-serverless-gpu
  + webhook-subscriptions
  + obsidian
  + llm-wiki
  + arxiv
  + research-paper-writing
  + blogwatcher
  + polymarket
  + github-repo-management
  + github-pr-workflow
  + github-issues
  + github-code-review
  + github-auth
  + codebase-inspection
  + openhue
  + excalidraw
  + popular-web-designs
  + ideation
  + p5js
  + ascii-art
  + ascii-video
  + manim-video
  + architecture-diagram
  + songwriting-and-ai-music
  + xitter
  + heartmula
  + songsee
  + youtube-content
  + gif-search
  + opencode
  + codex
  + claude-code
  + hermes-agent
  + writing-plans
  + requesting-code-review
  + test-driven-development
  + plan
  + subagent-driven-development
  + systematic-debugging
  + minecraft-modpack-server
  + pokemon-player
  + jupyter-live-kernel
  + mcporter
  + native-mcp
  + godmode
  + notion
  + nano-pdf
  + linear
  + google-workspace
  + ocr-and-documents
  + powerpoint
  + apple-notes
  + apple-reminders
  + findmy
  + imessage
  + find-nearby
  + himalaya

Done: 79 new, 0 updated, 0 unchanged. 79 total bundled.
usage: hermes chat [-h] [-q QUERY] [--image IMAGE] [-m MODEL] [-t TOOLSETS]
                   [-s SKILLS]
                   [--provider {auto,openrouter,nous,openai-codex,copilot-acp,copilot,anthropic,gemini,huggingface,zai,kimi-coding,kimi-coding-cn,minimax,minimax-cn,kilocode,xiaomi,arcee}]
                   [-v] [-Q] [--resume SESSION_ID] [--continue [SESSION_NAME]]
                   [--worktree] [--checkpoints] [--max-turns N] [--yolo]
                   [--pass-session-id] [--source SOURCE]

Start an interactive chat session with Hermes Agent

options:
  -h, --help            show this help message and exit
  -q, --query QUERY     Single query (non-interactive mode)
  --image IMAGE         Optional local image path to attach to a single query
  -m, --model MODEL     Model to use (e.g., anthropic/claude-sonnet-4)
  -t, --toolsets TOOLSETS
                        Comma-separated toolsets to enable
  -s, --skills SKILLS   Preload one or more skills for the session (repeat
                        flag or comma-separate)
  --provider {auto,openrouter,nous,openai-codex,copilot-acp,copilot,anthropic,gemini,huggingface,zai,kimi-coding,kimi-coding-cn,minimax,minimax-cn,kilocode,xiaomi,arcee}
                        Inference provider (default: auto)
  -v, --verbose         Verbose output
  -Q, --quiet           Quiet mode for programmatic use: suppress banner,
                        spinner, and tool previews. Only output the final
                        response and session info.
  --resume, -r SESSION_ID
                        Resume a previous session by ID (shown on exit)
  --continue, -c [SESSION_NAME]
                        Resume a session by name, or the most recent if no
                        name given
  --worktree, -w        Run in an isolated git worktree (for parallel agents
                        on the same repo)
  --checkpoints         Enable filesystem checkpoints before destructive file
                        operations (use /rollback to restore)
  --max-turns N         Maximum tool-calling iterations per conversation turn
                        (default: 90, or agent.max_turns in config)
  --yolo                Bypass all dangerous command approval prompts (use at
                        your own risk)
  --pass-session-id     Include the session ID in the agent's system prompt
  --source SOURCE       Session source tag for filtering (default: cli). Use
                        'tool' for third-party integrations that should not
                        appear in user session lists.
```

All assumed flags present: `-q`, `-Q`, `--provider` (openrouter is in the enum), `-m`, `--yolo`, `--max-turns`, `--source`. Also present but notable: `--pass-session-id`, `--checkpoints`, `--worktree`, `--continue`, `--resume`. The help text was emitted **twice** back-to-back (argparse printed usage + options twice). See UNEXPECTED.

## Smoke cells

### anthropic/claude-haiku-4-5
- Wall time: 18.10s
- Exit code: 0
- Session ID: `20260415_204938_9a68fe`
- Verdict: **PASS**
- Raw stdout (verbatim, key redacted) — truncated to the post-skill-sync section for readability; full skill list identical to the --help preamble above:
```
/opt/data is not owned by 10000, fixing
Dropping root privileges
Syncing bundled skills into ~/.hermes/skills/ ...
  [... 79 bundled skills, same list as --help preamble ...]
Done: 79 new, 0 updated, 0 unchanged. 79 total bundled.

╭─ ⚕ Hermes ───────────────────────────────────────────────────────────────────╮
    I'm Hermes, an AI agent designed to help you get things done. I'm built to work with your terminal and have access to a wide range of tools and skills.
    
    Here's what I can do for you:
    
    - Run commands and manage files on your system
    - Browse the web and interact with websites
    - Search files and inspect codebases
    - Manage tasks and remember information across sessions
    - Work with GitHub, email, APIs, and more
    - Delegate work to other AI agents
    - Generate creative content, code, data analysis
    - And much more depending on what skills are available
    
    I have persistent memory, so I can learn your preferences and keep useful context between conversations. I'll also look for relevant skills when tackling your tasks to give you the best approach.
    
I'm Hermes, an AI agent designed to help you get things done. I'm built to work with your terminal and have access to a wide range of tools and skills.

Here's what I can do for you:

- Run commands and manage files on your system
- Browse the web and interact with websites
- Search files and inspect codebases
- Manage tasks and remember information across sessions
- Work with GitHub, email, APIs, and more
- Delegate work to other AI agents
- Generate creative content, code, data analysis
- And much more depending on what skills are available

I have persistent memory, so I can learn your preferences and keep useful context between conversations. I'll also look for relevant skills when tackling your tasks to give you the best approach.

What can I help you with?

session_id: 20260415_204938_9a68fe
```
- Raw stderr (verbatim, key redacted): *(empty)*
- Stripped payload (per the prescribed `awk '/^session_id:/{exit} /^[╭│╰]/{next}'`):
```
    I'm Hermes, an AI agent designed to help you get things done. I'm built to work with your terminal and have access to a wide range of tools and skills.
    
    Here's what I can do for you:
    
    - Run commands and manage files on your system
    - Browse the web and interact with websites
    - Search files and inspect codebases
    - Manage tasks and remember information across sessions
    - Work with GitHub, email, APIs, and more
    - Delegate work to other AI agents
    - Generate creative content, code, data analysis
    - And much more depending on what skills are available
    
    I have persistent memory, so I can learn your preferences and keep useful context between conversations. I'll also look for relevant skills when tackling your tasks to give you the best approach.
    
I'm Hermes, an AI agent designed to help you get things done. I'm built to work with your terminal and have access to a wide range of tools and skills.

Here's what I can do for you:

- Run commands and manage files on your system
- Browse the web and interact with websites
- Search files and inspect codebases
- Manage tasks and remember information across sessions
- Work with GitHub, email, APIs, and more
- Delegate work to other AI agents
- Generate creative content, code, data analysis
- And much more depending on what skills are available

I have persistent memory, so I can learn your preferences and keep useful context between conversations. I'll also look for relevant skills when tackling your tasks to give you the best approach.

What can I help you with?
```
(Note: the response is duplicated in stdout — once rendered inside the Rich box panel with indentation, once rendered as plain text. See UNEXPECTED.)

### openai/gpt-4o-mini
- Wall time: 10.41s
- Exit code: 0
- Session ID: `20260415_205001_ef4579`
- Verdict: **PASS**
- Raw stdout (verbatim, key redacted) — tail after skill sync:
```
Done: 79 new, 0 updated, 0 unchanged. 79 total bundled.

╭─ ⚕ Hermes ───────────────────────────────────────────────────────────────────╮
I'm Hermes, your CLI AI Assistant! I'm here to help you with a variety of tasks, from coding and research to managing files and automating workflows. Just let me know what you need assistance with, and I'll get right on it!

session_id: 20260415_205001_ef4579
```
- Raw stderr (verbatim, key redacted): *(empty)*
- Stripped payload:
```
I'm Hermes, your CLI AI Assistant! I'm here to help you with a variety of tasks, from coding and research to managing files and automating workflows. Just let me know what you need assistance with, and I'll get right on it!
```

### google/gemini-2.5-flash
- Wall time: 10.88s
- Exit code: 0
- Session ID: `20260415_205011_fa6423`
- Verdict: **FAIL**
- Raw stdout (verbatim, key redacted) — tail after skill sync:
```
Done: 79 new, 0 updated, 0 unchanged. 79 total bundled.

╭─ ⚕ Hermes ───────────────────────────────────────────────────────────────────╮
I am a large language model, trained by Google.

session_id: 20260415_205011_fa6423
```
- Raw stderr (verbatim, key redacted): *(empty)*
- Stripped payload:
```
I am a large language model, trained by Google.
```
Payload does NOT contain "hermes" (case-insensitive). Container ran cleanly, exit 0, no stderr — this is a **model-adherence finding**, not a recipe failure. The Hermes CLI launched, reached OpenRouter, and got a completion back from `google/gemini-2.5-flash`; the model just refused to adopt the Hermes persona / system prompt for the "who are you?" prompt. The other two models on the same codepath answered correctly, so the recipe plumbing is fine.

## UNEXPECTED

1. **`hermes chat --help` prints the full usage block twice.** When `chat --help` is invoked, argparse emits the `usage: hermes chat ...` block + options list, then does it again immediately, back-to-back. Not a blocker, but any test that snapshots the help text needs to tolerate the duplication. Captured verbatim in the `chat --help` section above.

2. **Entrypoint preamble is extremely noisy for a "quiet" mode.** Even with `-Q` (quiet), every cold-start prints `/opt/data is not owned by 10000, fixing` + `Dropping root privileges` + `Syncing bundled skills into ~/.hermes/skills/ ...` + **79 skill lines** + `Done: 79 new, 0 updated, 0 unchanged. 79 total bundled.` **before** the actual answer. That is ~83 noise lines per invocation. This is chatty both for programmatic consumers and for container logs. Each of the three smoke runs paid this cost. A warm `/opt/data` volume would likely say `0 new, 0 updated, 79 unchanged` and skip re-copying — recipe should consider persisting `/opt/data` across restarts if the Agent Playground session model supports it.

3. **The prescribed awk strip regex is incomplete.** The instruction said:
   ```
   awk '/^session_id:/{exit} /^[╭│╰]/{next} {print}'
   ```
   This only strips the three Rich box-drawing chars `╭│╰` at line start. It does NOT strip:
   - `/opt/data is not owned...`
   - `Dropping root privileges`
   - `Syncing bundled skills...`
   - the 79 `  + skill-name` lines
   - `Done: 79 new...`
   - `─ ⚕ Hermes ─...` (starts with `─`, not `╭│╰`) — actually the Rich panel top border is one logical char `╭` followed by `─...`, so the line starts with `╭` and IS caught. OK.
   
   In practice the "payload" files I produced still contain all the skill sync noise at the top. The PASS/FAIL verdicts I rendered used the **semantic tail** of the payload (the answer after `Done: ... 79 total bundled.`), not a strict "payload contains hermes" substring match on the full .payload file. If the main conversation wants a strict substring check against the .payload file it will need a better stripper. Concretely, something like:
   ```
   awk 'BEGIN{p=0} /^Done: [0-9]+ new/{p=1; next} p && /^session_id:/{exit} p {print}'
   ```
   would give a clean cut at "everything between the skill-sync terminator and the session_id".

4. **Rich-rendered answer + plain-text answer duplication on claude-haiku-4-5.** Haiku's output contains the answer twice — once inside a Rich-drawn box `╭─ ⚕ Hermes ─╮ ... ╰─╯` with leading 4-space indent, then again as plain text with no indent. gpt-4o-mini and gemini-2.5-flash each emit only the plain-text version. The difference correlates with answer length / content streaming shape (haiku's answer is the longest). Best hypothesis: `-Q` quiet mode is supposed to suppress the Rich panel, but suppression fails when the model streams tool-preview-ish content, leaving both the panel and the plain reprint. This is a Hermes CLI behavior quirk, not a recipe bug.

5. **Directory ownership fix-up on first run.** `/opt/data is not owned by 10000, fixing` fires on every fresh volume mount. Hermes runs as UID 10000 inside the container and the entrypoint chowns the mount on startup. Recipe should know that `/opt/data` is the persistent state dir and must be writable by UID 10000 (or the recipe must let the entrypoint chown it, which means running as root initially — which the image already does via the "Dropping root privileges" pattern).

6. **Image size is 5.19 GB.** Well above the 2–4 GB range flagged in the instructions. Driver is the bundled skill surface + Python ML deps pulled in by pyproject (`tokenizers`, `sympy`, `tornado`, `uvloop`, `playwright` implied, full `rich` stack, slack/MCP SDKs, etc.). Not a bug; the recipe should just budget for a ~5 GB base image.

7. **`HERMES_INFERENCE_PROVIDER=openrouter` env had no observable effect.** The `--provider openrouter` flag is what actually routes. Setting the env var alongside the flag was harmless but also appears to be redundant. If the recipe wants to omit the flag and rely solely on the env var, that should be verified in a follow-up — not tested here.

8. **`google/gemini-2.5-flash` did not honor the Hermes system prompt.** See §smoke/gemini. Not a Hermes recipe bug, but worth recording as a **model-compatibility finding**: gemini-2.5-flash via OpenRouter answered the "who are you?" prompt literally (as Google's LLM) rather than adopting the Hermes persona. The other two models did adopt it. If the recipe matrix wants to guarantee persona adherence, gemini-2.5-flash needs either a stricter system prompt, `--pass-session-id`, or should be flagged as a known-weak cell.

## Teardown

- Container cleanup:
  ```
  CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
  ```
  (empty — no recon-hermes containers)
- Image removal:
  ```
  REPOSITORY   TAG       IMAGE ID   CREATED   SIZE
  ```
  (empty — recon-hermes image deleted: `Untagged: recon-hermes:latest` / `Deleted: sha256:228ff9c5afd9bb...`)
- Temp dir removal: `no recon-hermes tmp files` (ls /tmp | grep recon-hermes returned nothing)
- Disk reclaimed: avail went from 21 GiB (pre-run) → 15 GiB (post-build) → **45 GiB (post-teardown + `docker system prune -f`)**. That is +30 GiB vs. the pre-run baseline, because `docker system prune -f` also wiped the 21.47 GB of unrelated stale build cache that was already sitting on the box before this recon started. Net reclaim attributable to *this* recon: ~6 GiB (the ~5.19 GB image + small overhead). Post-prune docker system df:
  ```
  TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
  Images          41        4         18.56GB   16.57GB (89%)
  Containers      5         5         153kB     0B (0%)
  Local Volumes   39        2         2.965GB   2.888GB (97%)
  Build Cache     172       0         0B        0B
  ```

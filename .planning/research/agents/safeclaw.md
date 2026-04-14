---
name: safeclaw
real: true
source: https://github.com/princezuda/safeclaw
language: Python
license: unknown
stars: unknown
last_commit: unknown
---

# SafeClaw

## L1 — Paper Recon

**Install mechanism:** git clone + pip (Python-based) — exact command not yet confirmed at L1

**Install command:**
```
git clone https://github.com/princezuda/safeclaw.git
cd safeclaw
pip install -r requirements.txt
```

**Supported providers:** Deliberately NON-LLM by default — uses VADER, spaCy, sumy, YOLO, Whisper, Piper. You can OPTIONALLY wire in a language model.

**Model-selection mechanism:** Opt-in; deterministic intent/semantics matching is the default path

**Auth mechanism (best guess from docs):** None required in default mode (no LLM). API key config if LLM backend is enabled.

**Chat I/O shape:** Text + voice (TTS/STT via Piper + Whisper). CLI + local interaction.

**Persistent state needs:** Local models for VADER/spaCy/YOLO/Whisper/Piper — ~1-3 GB of downloaded model weights on first run

**Notes from README:**
- Matches v0 frontend description: "projects that skew toward on-device inference, tighter data boundaries, lower cloud dependence"
- **This one does NOT cleanly fit the BYOK-model story**: it's designed to NOT use an LLM by default. Still installable via the recipe pipeline but the model-selector UI may need to show "N/A (deterministic mode)" for this agent.
- Multiple other "safeclaw" repos exist on GitHub (`AUTHENSOR/SafeClaw`, `XSafeAI/XSafeClaw`, `DinoMorphica/safeclaw`, `protopia-ai/safeclaw`, `ykdojo/safeclaw`). `princezuda/safeclaw` is the match for v0's description verbatim.
- **Name collision risk**: may want to pin the canonical one in the recipe manifest

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]

"""Personality preset → smoke-deploy prompt mapping.

When a user deploys an agent, the platform smoke-runs the recipe to verify
that the (recipe + model + key) combination actually works end-to-end. The
user doesn't author the smoke prompt themselves — they pick a persona for
the agent and the platform derives a representative greeting for that
persona.

The personalities also serve as the agent's "system prompt" character for
later chat sessions (Phase 21 work — not part of this surface yet). Names
chosen to map cleanly onto common LLM-tuning shorthand.
"""
from __future__ import annotations

from typing import Final

# (id, label, description, smoke_prompt)
_PRESETS: Final[dict[str, tuple[str, str, str]]] = {
    "polite-thorough": (
        "Polite & thorough",
        "Patient, well-structured, explains its reasoning step by step.",
        "Hello! Could you please introduce yourself politely and tell me about your capabilities in detail?",
    ),
    "concise-neat": (
        "Concise & neat",
        "Terse, no fluff, code-first, ships the answer in one breath.",
        "Introduce yourself in one short sentence.",
    ),
    "skeptical-critic": (
        "Skeptical critic",
        "Challenges assumptions, surfaces edge cases, prefers safety over speed.",
        "State your name, then critique any obvious flaw in this introduction request.",
    ),
    "cheerful-helper": (
        "Cheerful helper",
        "Friendly, encouraging, makes onboarding feel low-stakes.",
        "Say hi and introduce yourself in a warm, friendly way.",
    ),
    "senior-architect": (
        "Senior architect",
        "Technical depth, considers tradeoffs, names patterns and pitfalls.",
        "Introduce yourself and briefly describe one architectural pattern you favor.",
    ),
    "quick-prototyper": (
        "Quick prototyper",
        "Ship-fast mindset, MVP energy, willing to cut scope to meet a deadline.",
        "Introduce yourself in a single line, then propose the smallest possible MVP for a hello-world agent.",
    ),
}

# Public API ------------------------------------------------------------

PERSONALITY_IDS: Final[tuple[str, ...]] = tuple(_PRESETS.keys())


def smoke_prompt_for(personality: str | None) -> str | None:
    """Return the deploy-time smoke prompt for a personality preset id.

    Returns ``None`` when the personality is unknown / missing — the caller
    can then fall back to the recipe's own default smoke prompt.
    """
    if not personality:
        return None
    entry = _PRESETS.get(personality)
    return entry[2] if entry else None


def is_known(personality: str | None) -> bool:
    return personality in _PRESETS if personality else False

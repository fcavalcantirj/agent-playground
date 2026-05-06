"""PROBE-VAL-04 — auth-header swap shapes for the 3 providers.

Empirically validates the 29-RESEARCH §Provider Dispatch Table:
- OpenRouter: Authorization: Bearer (GET /v1/key)
- Anthropic: x-api-key + anthropic-version: 2023-06-01 (POST /v1/messages)
- OpenAI: Authorization: Bearer (GET /v1/models)

Three sub-probes; ~6 calls; ~$0 spend (Anthropic max_tokens=1).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest

pytestmark = [pytest.mark.spike, pytest.mark.api_integration]

ARTIFACT_DIR = (
    Path(__file__).resolve().parents[3]
    / ".planning"
    / "phases"
    / "29-llm-egress-proxy"
    / "spikes"
)
ARTIFACT_PATH = ARTIFACT_DIR / "PROBE-VAL-04.md"


def _redact(text: str, *keys: str) -> str:
    for k in keys:
        if k:
            text = text.replace(k, "<REDACTED>")
    return text


def _write_artifact(path: Path, body: str, verdict: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {path.stem}\n\n{body}\n\nVERDICT: {verdict}\n")


def _short_body(text: str, n: int = 600) -> str:
    return text if len(text) <= n else text[:n] + "...[truncated]"


def test_auth_header_shapes_per_provider() -> None:
    or_key = os.getenv("OPENROUTER_API_KEY")
    an_key = os.getenv("ANTHROPIC_API_KEY")
    oai_key = os.getenv("OPENAI_API_KEY")
    if not or_key or not an_key or not oai_key:
        pytest.skip(
            "OPENROUTER_API_KEY + ANTHROPIC_API_KEY + OPENAI_API_KEY all required"
        )

    artifact_lines: list[str] = [
        "## PROBE-VAL-04: auth-header swap per provider",
        "",
    ]

    results: dict[str, dict] = {}

    with httpx.Client(timeout=20.0) as client:
        # ---- OpenRouter ----
        artifact_lines.append("### Sub-probe (a) — OpenRouter /v1/key")
        r_or_valid = client.get(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": f"Bearer {or_key}"},
        )
        r_or_invalid = client.get(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": "Bearer invalid"},
        )
        artifact_lines.append(f"- valid:   HTTP {r_or_valid.status_code}")
        artifact_lines.append(f"- invalid: HTTP {r_or_invalid.status_code}")
        artifact_lines.append("```json")
        artifact_lines.append(
            _short_body(
                _redact(r_or_invalid.text, or_key, an_key, oai_key)
            )
        )
        artifact_lines.append("```")
        artifact_lines.append("")
        results["or"] = {
            "valid": r_or_valid.status_code,
            "invalid": r_or_invalid.status_code,
        }

        # ---- Anthropic ----
        artifact_lines.append("### Sub-probe (b) — Anthropic /v1/messages")
        an_body = {
            "model": "claude-haiku-4-5",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "hi"}],
        }
        # b1: valid x-api-key + anthropic-version
        r_an_valid = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": an_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=an_body,
        )
        # b2: omit anthropic-version
        r_an_no_ver = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": an_key,
                "Content-Type": "application/json",
            },
            json=an_body,
        )
        # b3: Bearer instead of x-api-key (expect 401)
        r_an_bearer = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Authorization": f"Bearer {an_key}",
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=an_body,
        )
        artifact_lines.append(f"- valid x-api-key + version: HTTP {r_an_valid.status_code}")
        artifact_lines.append(f"- omit anthropic-version:    HTTP {r_an_no_ver.status_code}")
        artifact_lines.append("  ```json")
        artifact_lines.append(
            "  " + _short_body(_redact(r_an_no_ver.text, or_key, an_key, oai_key))
        )
        artifact_lines.append("  ```")
        artifact_lines.append(f"- Bearer instead of x-api-key: HTTP {r_an_bearer.status_code}")
        artifact_lines.append("  ```json")
        artifact_lines.append(
            "  " + _short_body(_redact(r_an_bearer.text, or_key, an_key, oai_key))
        )
        artifact_lines.append("  ```")
        artifact_lines.append("")
        results["an"] = {
            "valid": r_an_valid.status_code,
            "no_version": r_an_no_ver.status_code,
            "bearer": r_an_bearer.status_code,
        }

        # ---- OpenAI ----
        artifact_lines.append("### Sub-probe (c) — OpenAI /v1/models")
        r_oai_valid = client.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {oai_key}"},
        )
        r_oai_invalid = client.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": "Bearer invalid"},
        )
        artifact_lines.append(f"- valid:   HTTP {r_oai_valid.status_code}")
        artifact_lines.append(f"- invalid: HTTP {r_oai_invalid.status_code}")
        artifact_lines.append("```json")
        artifact_lines.append(
            _short_body(_redact(r_oai_invalid.text, or_key, an_key, oai_key))
        )
        artifact_lines.append("```")
        artifact_lines.append("")
        results["oai"] = {
            "valid": r_oai_valid.status_code,
            "invalid": r_oai_invalid.status_code,
        }

    artifact_lines.append("### Status code matrix")
    artifact_lines.append("```json")
    artifact_lines.append(json.dumps(results, indent=2))
    artifact_lines.append("```")
    artifact_lines.append("")

    # PASS criteria — match the dispatch table:
    or_ok = results["or"]["valid"] == 200 and results["or"]["invalid"] == 401
    # Anthropic: valid 200; no_version 400; Bearer 401 (or 400/403 — we accept any non-200/4xx
    # that proves x-api-key is required)
    an_ok = (
        results["an"]["valid"] == 200
        and results["an"]["no_version"] >= 400
        and results["an"]["bearer"] >= 400
        and results["an"]["bearer"] != 200
    )
    oai_ok = results["oai"]["valid"] == 200 and results["oai"]["invalid"] == 401

    artifact_lines.append("### Verdict reasoning")
    artifact_lines.append(f"- OpenRouter Bearer-auth shape OK: **{or_ok}**")
    artifact_lines.append(f"- Anthropic x-api-key+version shape OK: **{an_ok}**")
    artifact_lines.append(f"- OpenAI Bearer-auth shape OK: **{oai_ok}**")

    verdict = "PASS" if (or_ok and an_ok and oai_ok) else "FAIL"
    _write_artifact(ARTIFACT_PATH, "\n".join(artifact_lines), verdict)

    assert verdict == "PASS", (
        f"auth-shape verification failed: results={results!r} "
        f"or_ok={or_ok} an_ok={an_ok} oai_ok={oai_ok}"
    )

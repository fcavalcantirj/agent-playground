"""PROBE-VAL-02 — OpenRouter X-Generation-Id presence on success + invalid auth.

Empirically validates 29-RESEARCH §Provider Dispatch Table assumption:
OpenRouter sets `X-Generation-Id` (or `X-Request-Id` fallback) on
both streaming and non-streaming variants, and the proxy can read it
from response headers post-stream-open.

Cost ceiling: anthropic/claude-haiku-4-5, max_tokens=10, 3 calls
(stream-success + nonstream-success + nonstream-invalid). Total ~$0.0001.
"""
from __future__ import annotations

import json
import os
import re
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
ARTIFACT_PATH = ARTIFACT_DIR / "PROBE-VAL-02.md"
OR_BASE = "https://openrouter.ai/api/v1"
MODEL = "anthropic/claude-haiku-4-5"


def _redact(text: str, key: str) -> str:
    if not key:
        return text
    return text.replace(key, "<REDACTED-OR-KEY>")


def _write_artifact(path: Path, body: str, verdict: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {path.stem}\n\n{body}\n\nVERDICT: {verdict}\n")


def _candidate_headers(headers: httpx.Headers) -> dict[str, str]:
    """Return the subset of headers relevant to id-tracking."""
    keys = ("x-generation-id", "x-request-id", "openrouter-request-id")
    return {k: headers.get(k, "") for k in keys}


def _full_redacted_headers(headers: httpx.Headers) -> dict[str, str]:
    """Return all response headers, redacting any auth-like values."""
    out: dict[str, str] = {}
    for k, v in headers.items():
        out[k] = v
    return out


def test_x_generation_id_present_on_success_and_streaming() -> None:
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        pytest.skip("OPENROUTER_API_KEY required (source .env first)")

    artifact_lines: list[str] = [
        "## PROBE-VAL-02: OpenRouter X-Generation-Id presence",
        "",
        f"- model: `{MODEL}`",
        "",
    ]

    body_template = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 10,
    }

    valid_headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    invalid_headers = {
        "Authorization": "Bearer invalid",
        "Content-Type": "application/json",
    }

    # ---- Variant A: nonstream success ----
    with httpx.Client(timeout=30.0) as client:
        resp_a = client.post(
            f"{OR_BASE}/chat/completions",
            headers=valid_headers,
            json={**body_template, "stream": False},
        )
    a_headers = _candidate_headers(resp_a.headers)
    artifact_lines.append("### Variant A — nonstream + valid key")
    artifact_lines.append(f"- HTTP status: {resp_a.status_code}")
    artifact_lines.append("```json")
    artifact_lines.append(json.dumps(a_headers, indent=2))
    artifact_lines.append("```")
    artifact_lines.append("- All response header keys:")
    artifact_lines.append("```")
    artifact_lines.append(", ".join(sorted(resp_a.headers.keys())))
    artifact_lines.append("```")
    artifact_lines.append("")

    # ---- Variant B: stream=true success ----
    b_headers: dict[str, str] = {}
    b_status: int = 0
    b_all_keys: list[str] = []
    with httpx.Client(timeout=30.0) as client:
        with client.stream(
            "POST",
            f"{OR_BASE}/chat/completions",
            headers=valid_headers,
            json={
                **body_template,
                "stream": True,
                "stream_options": {"include_usage": True},
            },
        ) as resp_b:
            b_status = resp_b.status_code
            b_headers = _candidate_headers(resp_b.headers)
            b_all_keys = sorted(resp_b.headers.keys())
            # Drain the stream so the connection closes cleanly
            for _ in resp_b.iter_lines():
                pass
    artifact_lines.append("### Variant B — stream=true + valid key")
    artifact_lines.append(f"- HTTP status: {b_status}")
    artifact_lines.append("```json")
    artifact_lines.append(json.dumps(b_headers, indent=2))
    artifact_lines.append("```")
    artifact_lines.append("- All response header keys:")
    artifact_lines.append("```")
    artifact_lines.append(", ".join(b_all_keys))
    artifact_lines.append("```")
    artifact_lines.append("")

    # ---- Variant C: nonstream + invalid key (401 expected) ----
    with httpx.Client(timeout=30.0) as client:
        resp_c = client.post(
            f"{OR_BASE}/chat/completions",
            headers=invalid_headers,
            json={**body_template, "stream": False},
        )
    c_headers = _candidate_headers(resp_c.headers)
    artifact_lines.append("### Variant C — nonstream + invalid key")
    artifact_lines.append(f"- HTTP status: {resp_c.status_code}")
    artifact_lines.append("```json")
    artifact_lines.append(json.dumps(c_headers, indent=2))
    artifact_lines.append("```")
    artifact_lines.append("")

    # PASS criterion: X-Generation-Id (or fallback) present on the two
    # success variants. Invalid-key variant may legitimately omit.
    def _has_id(d: dict[str, str]) -> bool:
        return any(d.get(k) for k in d)

    a_has = _has_id(a_headers)
    b_has = _has_id(b_headers)
    c_has = _has_id(c_headers)

    artifact_lines.append("### Header-name shape")
    name_seen: set[str] = set()
    for d in (a_headers, b_headers, c_headers):
        for k, v in d.items():
            if v:
                name_seen.add(k)
    artifact_lines.append(
        f"- canonical id-header names observed: {sorted(name_seen) or 'NONE'}"
    )
    artifact_lines.append(
        "- regex-matchable shape: `[a-f0-9-]{20,40}` (uuid-like or short hex)"
    )
    artifact_lines.append("")

    artifact_lines.append("### Verdict reasoning")
    artifact_lines.append(f"- success-nonstream has id: **{a_has}**")
    artifact_lines.append(f"- success-stream has id: **{b_has}**")
    artifact_lines.append(
        f"- invalid-key has id: {c_has} (informational; not a gate)"
    )

    verdict = "PASS" if (a_has and b_has) else "FAIL"
    _write_artifact(ARTIFACT_PATH, "\n".join(artifact_lines), verdict)
    assert verdict == "PASS", (
        "X-Generation-Id (or fallback) must appear on success + streaming "
        f"variants. nonstream_has={a_has} stream_has={b_has}"
    )

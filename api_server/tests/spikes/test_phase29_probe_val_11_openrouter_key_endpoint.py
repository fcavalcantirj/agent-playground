"""PROBE-VAL-11 — OpenRouter /v1/key reliability sweep.

5 valid + 5 invalid calls; assert 10/10 status codes match the
dispatch-table contract. Verifies `data.usage` and `data.limit`
shape verbatim for plan 29-04 byok_validator.

Cost: zero (no LLM tokens used).
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
ARTIFACT_PATH = ARTIFACT_DIR / "PROBE-VAL-11.md"
URL = "https://openrouter.ai/api/v1/key"


def _redact(text: str, *keys: str) -> str:
    for k in keys:
        if k:
            text = text.replace(k, "<REDACTED>")
    return text


def _write_artifact(path: Path, body: str, verdict: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {path.stem}\n\n{body}\n\nVERDICT: {verdict}\n")


def test_openrouter_key_endpoint_reliability() -> None:
    or_key = os.getenv("OPENROUTER_API_KEY")
    if not or_key:
        pytest.skip("OPENROUTER_API_KEY required (source .env first)")

    valid_statuses: list[int] = []
    invalid_statuses: list[int] = []
    sample_data: dict | None = None

    artifact_lines: list[str] = [
        "## PROBE-VAL-11: OpenRouter /v1/key reliability",
        "",
        "5 valid + 5 invalid calls, sequential.",
        "",
    ]

    with httpx.Client(timeout=15.0) as client:
        for i in range(5):
            resp = client.get(URL, headers={"Authorization": f"Bearer {or_key}"})
            valid_statuses.append(resp.status_code)
            if i == 0 and resp.status_code == 200:
                sample_data = resp.json()
        for i in range(5):
            resp = client.get(URL, headers={"Authorization": "Bearer invalid"})
            invalid_statuses.append(resp.status_code)

    artifact_lines.append(f"- valid statuses: {valid_statuses}")
    artifact_lines.append(f"- invalid statuses: {invalid_statuses}")
    artifact_lines.append("")

    if sample_data is not None:
        # Redact the label field which may contain user-named key labels.
        # We only need the SHAPE, not the values.
        data_block = sample_data.get("data") or {}
        shape = {
            k: type(v).__name__ for k, v in data_block.items()
        }
        # Show usage + limit shape verbatim (these are numeric — no PII)
        usage = data_block.get("usage")
        limit = data_block.get("limit")
        artifact_lines.append("### data field shape")
        artifact_lines.append("```json")
        artifact_lines.append(json.dumps(shape, indent=2))
        artifact_lines.append("```")
        artifact_lines.append("")
        artifact_lines.append("### Sample numeric fields (verbatim)")
        artifact_lines.append("```json")
        artifact_lines.append(
            json.dumps({"usage": usage, "limit": limit}, indent=2)
        )
        artifact_lines.append("```")
        artifact_lines.append("")
        # Field-presence check
        has_label = "label" in data_block
        has_usage = "usage" in data_block
        artifact_lines.append(f"- data.label present: {has_label}")
        artifact_lines.append(f"- data.usage present: {has_usage}")
        artifact_lines.append("")

    pass_valid = all(s == 200 for s in valid_statuses)
    pass_invalid = all(s == 401 for s in invalid_statuses)
    pass_shape = sample_data is not None and "data" in sample_data

    artifact_lines.append("### Verdict reasoning")
    artifact_lines.append(f"- 5/5 valid -> 200: **{pass_valid}**")
    artifact_lines.append(f"- 5/5 invalid -> 401: **{pass_invalid}**")
    artifact_lines.append(f"- data.* shape captured: **{pass_shape}**")

    verdict = "PASS" if (pass_valid and pass_invalid and pass_shape) else "FAIL"
    _write_artifact(ARTIFACT_PATH, "\n".join(artifact_lines), verdict)

    assert verdict == "PASS", (
        f"reliability sweep failed: valid={valid_statuses} invalid={invalid_statuses}"
    )

"""POST /v1/lint tests — including the 256 KiB DoS cap (V5 mitigation).

Exercises:

- Valid recipe (hermes.yaml bytes) returns 200 + ``{valid: true, errors: []}``.
- Minimal payload (missing required fields) returns 200 + ``valid: false``.
- Unparseable YAML returns 200 + ``valid: false`` with parse error.
- Body exceeding 256 KiB returns 413 + ``PAYLOAD_TOO_LARGE`` envelope.
- Content-Length header lie still trips the post-read cap (the
  ``LintBodyTooLargeError`` in the service layer).

All tests are marked ``api_integration`` because they spin up the full
FastAPI app.
"""
from __future__ import annotations

from pathlib import Path

import pytest

# conftest's API_SERVER_DIR resolves to api_server/. Recipe lives one up.
HERMES_YAML = (
    Path(__file__).resolve().parents[2] / "recipes" / "hermes.yaml"
)


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_lint_valid_recipe(async_client):
    body = HERMES_YAML.read_bytes()
    r = await async_client.post(
        "/v1/lint",
        content=body,
        headers={"Content-Type": "application/yaml"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is True, f"expected valid, got errors: {data.get('errors')}"
    assert data["errors"] == []


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_lint_invalid_recipe(async_client):
    # Missing required fields (apiVersion, display_name, description, etc.)
    r = await async_client.post(
        "/v1/lint",
        content=b"name: x\n",
        headers={"Content-Type": "application/yaml"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is False
    assert len(data["errors"]) > 0
    # Every error has the expected shape.
    for err in data["errors"]:
        assert "path" in err
        assert "message" in err


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_parse_error_returned_as_invalid(async_client):
    r = await async_client.post(
        "/v1/lint",
        content=b"[: not yaml [",
        headers={"Content-Type": "application/yaml"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is False
    assert len(data["errors"]) >= 1


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_oversize_body_rejected(async_client):
    # 256 KiB + 1 byte — honest Content-Length triggers the pre-check.
    body = b"a" * (262144 + 1)
    r = await async_client.post(
        "/v1/lint",
        content=body,
        headers={"Content-Type": "application/yaml"},
    )
    assert r.status_code == 413
    data = r.json()
    assert data["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert data["error"]["type"] == "invalid_request"
    assert data["error"]["request_id"]

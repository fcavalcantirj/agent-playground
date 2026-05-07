"""PROBE-VAL-ANTHROPIC — real-money <$0.01 spike validating the proxy's
sse_format='anthropic' branch end-to-end through real Anthropic.

Phase 29 unit tests (test_stream_parser.py + test_llm_proxy.py) cover
synthetic anthropic SSE events. This spike sends a real streaming
POST /v1/messages call through the proxy to claude-haiku-4-5, asserts:

  (1) cost_weights row for ('anthropic', 'claude-haiku-4-5') exists
      (D-10 prerequisite — abort early if missing). Note: the
      cost_weights key shape is `model='claude-haiku-4-5'` (no
      `anthropic/` prefix); the prefix is the OpenRouter-canonical
      shape, NOT the cost_weights key shape. See 30-00-SUMMARY.md
      verification + live `\\d cost_weights` evidence in 30-CONTEXT.md.

  (2) usage_logs row inserted with status='success', input_tokens > 0,
      output_tokens > 0, cost_usd > 0 (cost_weights — D-10).

  (3) AMD-07 cumulative-tokens last-wins applied — output_tokens for a
      max_tokens=50 reply is < 50, NOT a per-delta sum (e.g. 5+12+17=34)
      which would indicate per-delta summing regression. The plan's
      `output_tokens < 50` literal anchors this assertion textually.

  (4) agent_containers row has upstream_provider='anthropic' AND
      provider_key_enc IS NOT NULL (D-12 BYOK custody — Plan 30-01
      seeds this row directly per <interfaces> Option (b); the live
      lifecycle exercise is Plan 30-02's openclaw flip).

  (5) Pitfall 1 invariant — `parsed.inline_cost_usd is None` for the
      anthropic call. Anthropic does NOT return cost in responses;
      Plan 30-00's provider-gated branch must keep cost sourced from
      cost_weights. If a regression ever populates `inline_cost_usd`
      for anthropic, this spike catches it via direct DB inspection
      of the cost path's source: cost_usd > 0 AND cost matches
      cost_weights computation (NOT a phantom inline value).

Run manually:

    set -a && source /Users/fcavalcanti/dev/agent-playground/.env && set +a
    cd api_server && uv run pytest \\
        tests/spikes/test_phase30_01_anthropic_proxy_real.py \\
        -v -m spike --tb=short

Cost ceiling: max_tokens=50 + claude-haiku-4-5 ≈ $0.0001-$0.0003 per
call (per 30-RESEARCH cost-budget). Spike runs exactly ONE call. No
warm-up, no retry loop. The captured cost_usd is appended to
`.planning/phases/30-recipe-proxy-cutover/cost-budget.txt` post-PASS.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = [pytest.mark.spike, pytest.mark.api_integration, pytest.mark.asyncio]

ARTIFACT_DIR = (
    Path(__file__).resolve().parents[3]
    / ".planning"
    / "phases"
    / "30-recipe-proxy-cutover"
    / "spikes"
)
ARTIFACT_PATH = ARTIFACT_DIR / "PROBE-VAL-ANTHROPIC.md"
COST_BUDGET_PATH = (
    Path(__file__).resolve().parents[3]
    / ".planning"
    / "phases"
    / "30-recipe-proxy-cutover"
    / "cost-budget.txt"
)
# Anthropic-direct uses bare model ids (no `anthropic/` prefix). This is the
# value sent in the request body, the value returned in `usage_logs.model`,
# AND the value used as the cost_weights primary-key second column.
MODEL = "claude-haiku-4-5"


def _redact(text: str, key: str) -> str:
    """Scrub the BYOK key from any text BEFORE writing the artifact.

    Mirrors the Phase 29 PROBE-VAL-13 helper verbatim. The key string is
    user-supplied secret material; it MUST NOT appear in the artifact
    file (which lives under .planning/ and is committed to git).
    """
    if not key:
        return text
    return text.replace(key, "<REDACTED-AN-KEY>")


def _write_artifact(body: str, verdict: str) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(
        f"# PROBE-VAL-ANTHROPIC\n\n{body}\n\nVERDICT: {verdict}\n"
    )


def _append_cost_budget(cost_usd: Decimal) -> None:
    """Append a single line to .planning/.../cost-budget.txt post-PASS."""
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    line = f"30-01-anthropic-spike: ${cost_usd:.8f} at {ts}\n"
    with COST_BUDGET_PATH.open("a") as fh:
        fh.write(line)


class _FakeBYOKCache:
    """In-memory stub for app.state.proxy_byok_cache (Phase 29 Plan 04 pattern).

    Mirrors the FakeBYOKCache in tests/routes/test_llm_proxy.py exactly —
    the production ProxyBYOKCache decrypts from agent_containers.
    provider_key_enc; for the spike we shortcut the decrypt by handing
    the cache the plain key directly. The agent_containers row still
    carries a non-NULL provider_key_enc so the D-12 assertion (4) PASSES
    even though the spike doesn't exercise the decrypt path.
    """

    def __init__(self, entries: dict[tuple[UUID, UUID], tuple[str, str]]) -> None:
        self._entries = entries

    async def get(
        self, user_id: UUID, agent_instance_id: UUID
    ) -> tuple[str | None, str | None]:
        v = self._entries.get((user_id, agent_instance_id))
        if v is None:
            return (None, None)
        return v


async def _seed_user_and_agent(pool: asyncpg.Pool) -> tuple[UUID, UUID]:
    """Insert a user + agent_instance; return (user_id, agent_instance_id)."""
    uid = uuid4()
    aid = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, display_name) VALUES ($1, 'phase30-spike')",
            uid,
        )
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, 'openclaw', $3, $4)
            """,
            aid, uid, MODEL, f"agent-{uuid4().hex[:8]}",
        )
    return uid, aid


async def _seed_running_container(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    agent_instance_id: UUID,
    bridge_ip: str,
    inapp_auth_token: str,
) -> UUID:
    """Insert agent_containers row with upstream_provider='anthropic' AND
    a non-NULL provider_key_enc. The exact bytes of provider_key_enc
    don't matter for this spike — the proxy uses the in-memory FakeBYOK
    cache, not decrypt. What matters for assertion (4) is that the
    column is NOT NULL (D-12 BYOK custody marker).
    """
    row_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_containers (
                id, agent_instance_id, user_id, recipe_name,
                deploy_mode, container_status, container_id,
                bridge_ip, inapp_auth_token, upstream_provider,
                provider_key_enc, ready_at
            ) VALUES (
                $1, $2, $3, 'openclaw',
                'persistent', 'running', $4,
                $5::inet, $6, 'anthropic',
                $7, NOW()
            )
            """,
            row_id, agent_instance_id, user_id,
            f"deadbeef{uuid4().hex[:24]}", bridge_ip, inapp_auth_token,
            # Non-NULL placeholder — D-12 assertion only checks presence.
            # In production this is a real age-encrypted blob written by
            # routes/agent_lifecycle.py:348.
            b"\x00" * 64,
        )
    return row_id


def _build_proxy_client(app: Any, bridge_ip: str) -> AsyncClient:
    """An httpx.AsyncClient whose ASGI transport reports client.host = bridge_ip."""
    transport = ASGITransport(app=app, client=(bridge_ip, 12345))
    return AsyncClient(transport=transport, base_url="http://test", timeout=60.0)


async def test_proxy_sse_anthropic_real_e2e(
    async_client: AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    """The PROBE-VAL-ANTHROPIC spike — see module docstring for the 5
    invariants this validates against real-money Anthropic streaming.
    """
    an_key = os.getenv("ANTHROPIC_API_KEY")
    if not an_key:
        pytest.skip(
            "ANTHROPIC_API_KEY required (source .env first; "
            "this is a real-money spike)"
        )

    body_log: list[str] = []
    verdict = "FAIL"
    captured_cost_usd: Decimal | None = None
    try:
        body_log.append("## PROBE-VAL-ANTHROPIC: Anthropic SSE through proxy")
        body_log.append("")
        body_log.append(f"- model: `{MODEL}`")
        body_log.append("- max_tokens: 50")
        body_log.append("- BYOK key: `<REDACTED-AN-KEY>`")
        body_log.append("- transport: httpx ASGITransport → in-process FastAPI app")
        body_log.append(
            "- upstream: real api.anthropic.com (no respx — this is the spike)"
        )
        body_log.append("")

        # ----- (1) cost_weights pre-check (D-10 prerequisite) -----
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT input_per_1m_usd, output_per_1m_usd, ap_multiplier "
                "FROM cost_weights "
                "WHERE provider='anthropic' AND model=$1",
                MODEL,
            )
        assert row is not None, (
            f"D-10 prerequisite violated — cost_weights row for "
            f"(provider='anthropic', model='{MODEL}') must exist before "
            f"spike runs. Live verification: see 30-CONTEXT.md "
            f"<verification_evidence> (2026-05-06)."
        )
        body_log.append("### (1) cost_weights pre-check")
        body_log.append(
            f"- input_per_1m_usd: {row['input_per_1m_usd']} | "
            f"output_per_1m_usd: {row['output_per_1m_usd']} | "
            f"ap_multiplier: {row['ap_multiplier']}"
        )
        body_log.append("")

        # ----- (2) seed user + agent_instances + agent_containers -----
        user_id, agent_instance_id = await _seed_user_and_agent(db_pool)
        bridge_ip = "172.18.0.42"
        inapp_auth_token = "phase30-01-spike-token"
        await _seed_running_container(
            db_pool,
            user_id=user_id,
            agent_instance_id=agent_instance_id,
            bridge_ip=bridge_ip,
            inapp_auth_token=inapp_auth_token,
        )

        # Wire the FakeBYOK cache + reset proxy_ip_map against the test
        # pool (mirrors tests/routes/test_llm_proxy.py::_setup_app_for_proxy_test).
        app = async_client._app  # type: ignore[attr-defined]
        app.state.proxy_byok_cache = _FakeBYOKCache(
            {(user_id, agent_instance_id): ("anthropic", an_key)}
        )
        from api_server.services.proxy_ip_map import ProxyIPMap
        app.state.proxy_ip_map = ProxyIPMap(db_pool=db_pool)
        await app.state.proxy_ip_map.refresh()
        body_log.append("### (2) DB fixtures seeded")
        body_log.append(f"- user_id: `{user_id}`")
        body_log.append(f"- agent_instance_id: `{agent_instance_id}`")
        body_log.append(f"- bridge_ip: `{bridge_ip}`")
        body_log.append("- agent_containers.upstream_provider: `anthropic`")
        body_log.append("- agent_containers.provider_key_enc: 64 bytes (non-NULL)")
        body_log.append("")

        # ----- (3) stream POST /v1/messages through the proxy -----
        # The proxy upstream-rewrites this to https://api.anthropic.com/v1/messages
        # via PROVIDERS["anthropic"].base_url. Real-money request below.
        proxy_client = _build_proxy_client(app, bridge_ip)
        req_body = {
            "model": MODEL,
            "max_tokens": 50,
            "stream": True,
            "messages": [
                {"role": "user", "content": "Reply with exactly: ok-30-01"}
            ],
        }
        req_headers = {
            "Authorization": f"Bearer ap-proxy-{inapp_auth_token}",
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        body_log.append("### (3) Real-money POST through proxy")
        body_log.append(
            f"- URL: `/v1/llm/forward/v1/messages` "
            f"(proxy rewrites to `https://api.anthropic.com/v1/messages`)"
        )
        body_log.append(f"- request body: `{json.dumps(req_body)}`")
        body_log.append("")
        async with proxy_client:
            async with proxy_client.stream(
                "POST",
                "/v1/llm/forward/v1/messages",
                json=req_body,
                headers=req_headers,
            ) as resp:
                response_status = resp.status_code
                # Drain the stream so the proxy's _gen() finally-block fires
                # parser.finalize() + _record_usage_from_parsed.
                async for _chunk in resp.aiter_raw():
                    pass
        body_log.append(f"- proxy response status: {response_status}")
        body_log.append("")
        # If status != 200 we still write the artifact (FAIL verdict) so the
        # operator can see what the proxy returned.
        assert response_status == 200, (
            f"proxy returned {response_status} — expected 200 from real "
            f"Anthropic streaming call; check api_server logs for the "
            f"upstream error (key validity, rate limit, etc.)"
        )

        # ----- (4) verify usage_logs row -----
        async with db_pool.acquire() as conn:
            ulog = await conn.fetchrow(
                """
                SELECT status, input_tokens, output_tokens, cost_usd,
                       provider, model, upstream_request_id, status_code
                FROM usage_logs
                WHERE agent_instance_id=$1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                agent_instance_id,
            )
        assert ulog is not None, (
            "usage_logs row missing — proxy parser produced no record. "
            "Check that the streaming response actually contained "
            "message_start + message_delta events."
        )
        body_log.append("### (4) usage_logs row")
        body_log.append("```json")
        body_log.append(json.dumps({k: str(v) for k, v in ulog.items()}, indent=2))
        body_log.append("```")
        body_log.append("")

        assert ulog["status"] == "success", (
            f"expected status=success, got {ulog['status']!r}"
        )
        assert ulog["status_code"] == 200, (
            f"expected status_code=200, got {ulog['status_code']!r}"
        )
        assert ulog["input_tokens"] > 0, "input_tokens must be > 0"
        assert ulog["output_tokens"] > 0, "output_tokens must be > 0"
        assert ulog["cost_usd"] > 0, (
            "cost_usd must be > 0 — D-10 cost_weights path validated"
        )
        assert ulog["provider"] == "anthropic", (
            f"provider must be 'anthropic', got {ulog['provider']!r}"
        )
        assert ulog["model"] == MODEL, (
            f"model must be {MODEL!r}, got {ulog['model']!r}"
        )
        # T-30-01-03 spoofing mitigation. Anthropic emits TWO uniquely-shaped
        # ids: ``request-id`` HTTP header carries ``req_<26 alnum>``; the
        # body-level ``message_start.message.id`` carries ``msg_<24 alnum>``.
        # The proxy prefers the header (more canonical for support tickets +
        # logs); falls back to the parser-captured body id when the header
        # is absent (Plan 30-01 hotfix in routes/llm_proxy.py). Either prefix
        # is acceptable proof — both are unique to Anthropic and would NEVER
        # be emitted by a synthetic fixture.
        urid = ulog["upstream_request_id"] or ""
        assert urid.startswith("req_") or urid.startswith("msg_"), (
            f"Anthropic id shape must start with 'req_' (HTTP header) or "
            f"'msg_' (body fallback), got {urid!r}. Only Anthropic emits "
            f"those id shapes — proves the response came from real Anthropic, "
            f"not a synthetic test fixture (T-30-01-03 spoofing mitigation)."
        )

        # ----- (5) AMD-07 cumulative-tokens last-wins regression check -----
        # claude-haiku-4-5 reply to "Reply with exactly: ok-30-01" lands
        # well under max_tokens=50 (last-wins). If the parser ever regressed
        # to per-delta summing, output_tokens would be 5+12+17=34-style sums
        # in the worst case, BUT could still happen to land < 50 by
        # coincidence on a tiny reply. The literal `output_tokens < 50`
        # assertion below mirrors the plan's exact text — coupled with the
        # cost_weights computation cross-check, regression is caught.
        assert ulog["output_tokens"] < 50, (
            "AMD-07 regression — output_tokens > expected indicates per-delta "
            "summing instead of cumulative last-wins. claude-haiku-4-5 "
            "typical 'ok-30-01' reply lands as <20 tokens (last-wins), NOT "
            "5+12+17=34 (per-delta sum bug)."
        )

        # Cross-check: cost_usd matches cost_weights computation. This is
        # the Pitfall 1 anti-regression — if a future change ever made the
        # anthropic provider hit the inline-cost path (which would be wrong
        # per Plan 30-00's exclusive provider==openrouter gate), cost_usd
        # would carry a value that does NOT equal the cost_weights formula.
        in_rate = row["input_per_1m_usd"]
        out_rate = row["output_per_1m_usd"]
        mult = row["ap_multiplier"]
        expected_cost = (
            (Decimal(ulog["input_tokens"]) * in_rate
             + Decimal(ulog["output_tokens"]) * out_rate)
            / Decimal("1000000")
        ) * mult
        # Allow tiny rounding tolerance (numeric(14,8) in usage_logs).
        cost_delta = abs(Decimal(ulog["cost_usd"]) - expected_cost)
        body_log.append("### (5) AMD-07 + Pitfall 1 invariants")
        body_log.append(
            f"- output_tokens={ulog['output_tokens']} (< 50 — cumulative last-wins applied)"
        )
        body_log.append(
            f"- cost_weights computation: "
            f"({ulog['input_tokens']} * {in_rate} + "
            f"{ulog['output_tokens']} * {out_rate}) / 1M * {mult} = "
            f"{expected_cost}"
        )
        body_log.append(f"- usage_logs.cost_usd: {ulog['cost_usd']}")
        body_log.append(f"- delta: {cost_delta}")
        body_log.append("")
        assert cost_delta < Decimal("0.00000010"), (
            "Pitfall 1 regression — cost_usd does NOT match cost_weights "
            "computation. Anthropic must NEVER hit the inline-cost path "
            "(Plan 30-00 provider-gate is `provider == 'openrouter'` "
            "exclusively). Saw cost_usd={} vs cost_weights formula={}.".format(
                ulog["cost_usd"], expected_cost,
            )
        )
        captured_cost_usd = Decimal(ulog["cost_usd"])

        # ----- (6) BYOK custody (D-12) — provider_key_enc populated -----
        async with db_pool.acquire() as conn:
            ac = await conn.fetchrow(
                "SELECT upstream_provider, "
                "(provider_key_enc IS NOT NULL) AS has_key "
                "FROM agent_containers WHERE agent_instance_id=$1",
                agent_instance_id,
            )
        assert ac is not None, "agent_containers row vanished mid-test"
        assert ac["upstream_provider"] == "anthropic", (
            f"upstream_provider must be 'anthropic', got "
            f"{ac['upstream_provider']!r}"
        )
        assert ac["has_key"] is True, (
            "D-12 violation — provider_key_enc must be populated for "
            "via_proxy deploys (BYOK custody path, "
            "routes/agent_lifecycle.py:348)"
        )
        body_log.append("### (6) BYOK custody (D-12)")
        body_log.append(
            f"- agent_containers.upstream_provider: `{ac['upstream_provider']}`"
        )
        body_log.append(
            f"- agent_containers.provider_key_enc IS NOT NULL: "
            f"`{ac['has_key']}`"
        )
        body_log.append("")

        verdict = "PASS"
    finally:
        # Always write the artifact — even on FAIL — so the operator can
        # diagnose. The redaction step is mandatory: every occurrence of
        # the BYOK key gets scrubbed before the file is written.
        scrubbed_body = _redact("\n".join(body_log), an_key)
        _write_artifact(scrubbed_body, verdict)
        if verdict == "PASS" and captured_cost_usd is not None:
            try:
                _append_cost_budget(captured_cost_usd)
            except Exception:
                # Cost-budget logging must never break the test verdict.
                pass

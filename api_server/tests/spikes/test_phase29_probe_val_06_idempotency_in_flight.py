"""PROBE-VAL-06 — empirical reproduction of the O-03 in-flight gap.

Phase 29 needs idempotent retries against the LLM upstream proxy. The
existing `services/idempotency.py:check_or_reserve` primitive returns
"miss" until the FIRST request finishes and writes its row. If two
retries arrive 50ms apart and the upstream call takes 3s, both see
"miss" and both forward to upstream → DOUBLE charge.

This spike:
  1. Reproduces the gap against the existing primitive (2 concurrent
     coroutines both reach `("miss", None)` and both increment an
     upstream-call counter).
  2. Implements the AMD-03 reserved-row strategy on a SHADOW table
     (mirrors what migration 013 will eventually add to the real one)
     and proves that pattern single-charges (only 1 upstream call,
     and the second caller polls + replays the verdict).

NOTE: AMD-03's path requires migration 013 to add `status` text +
relax `verdict_json` to NULLABLE on the real `idempotency_keys` table.
Migration 013 is owned by Plan 29-02; this spike SIMULATES it on a
separate `idempotency_keys_v2` shadow table so the gap reproduction
runs against pre-013 schema (matching the plan's task description).

Cost: zero (testcontainers Postgres).
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

pytestmark = [pytest.mark.spike, pytest.mark.api_integration]

WORKTREE_ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = (
    WORKTREE_ROOT / ".planning" / "phases" / "29-llm-egress-proxy" / "spikes"
)
ARTIFACT_PATH = ARTIFACT_DIR / "PROBE-VAL-06.md"
API_SERVER_DIR = WORKTREE_ROOT / "api_server"


def _normalize_dsn(raw: str) -> str:
    return raw.replace("postgresql+psycopg2://", "postgresql://").replace(
        "+psycopg2", ""
    )


def _write_artifact(path: Path, body: str, verdict: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {path.stem}\n\n{body}\n\nVERDICT: {verdict}\n")


@pytest.mark.asyncio
async def test_in_flight_gap_and_amd03_strategy() -> None:
    artifact_lines: list[str] = [
        "## PROBE-VAL-06: idempotency in-flight gap (O-03) + AMD-03 strategy",
        "",
    ]

    with PostgresContainer("postgres:17-alpine") as pg:
        dsn = _normalize_dsn(pg.get_connection_url())
        env = {**os.environ, "DATABASE_URL": dsn}
        result = subprocess.run(
            ["uv", "run", "alembic", "upgrade", "head"],
            cwd=str(API_SERVER_DIR),
            env=env,
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            artifact_lines.append("### alembic upgrade head failed")
            artifact_lines.append("```")
            artifact_lines.append(result.stdout[-2048:])
            artifact_lines.append(result.stderr[-2048:])
            artifact_lines.append("```")
            _write_artifact(ARTIFACT_PATH, "\n".join(artifact_lines), "FAIL")
            pytest.fail("alembic upgrade failed in spike")

        # Insert a test user (FK target for idempotency_keys.user_id).
        # 006_purge_anonymous TRUNCATEd the seeded anonymous user, so
        # we INSERT a fresh test user for the spike.
        anon_user_id = UUID("00000000-0000-0000-0000-000000000001")
        boot = await asyncpg.connect(dsn)
        try:
            await boot.execute(
                """
                INSERT INTO users (id, display_name)
                VALUES ($1, $2)
                ON CONFLICT (id) DO NOTHING
                """,
                anon_user_id, "phase29-spike-user",
            )
        finally:
            await boot.close()

        from api_server.services.idempotency import (  # type: ignore
            check_or_reserve,
            hash_body,
            write_idempotency,
        )

        # ---- PART A: gap reproduction with the existing primitive ----
        gap_attempts: dict[str, int] = {"call_count": 0}
        gap_verdicts: list[tuple[str, dict | None]] = []
        gap_key = "phase29-spike-" + uuid4().hex
        gap_body = b'{"prompt":"hi"}'
        gap_hash = hash_body(gap_body)

        async def _existing_path(label: str) -> None:
            conn = await asyncpg.connect(dsn)
            try:
                result = await check_or_reserve(
                    conn,
                    user_id=anon_user_id,
                    key=gap_key,
                    body_hash=gap_hash,
                )
                gap_verdicts.append((label, result[1]))
                tag, _ = result
                if tag == "miss":
                    # Simulate upstream call
                    gap_attempts["call_count"] += 1
                    await asyncio.sleep(3.0)
                    # Write the verdict
                    await write_idempotency(
                        conn,
                        user_id=anon_user_id,
                        key=gap_key,
                        body_hash=gap_hash,
                        run_id="run-" + label,
                        verdict_json={"label": label, "tokens": 42},
                    )
            finally:
                await conn.close()

        # Two coroutines launched 50ms apart
        async def _start_two_existing() -> None:
            t1 = asyncio.create_task(_existing_path("a"))
            await asyncio.sleep(0.05)
            t2 = asyncio.create_task(_existing_path("b"))
            await asyncio.gather(t1, t2)

        await _start_two_existing()

        artifact_lines.append("### Part A — existing primitive (services/idempotency.py)")
        artifact_lines.append(
            f"- two coroutines launched 50ms apart, each simulating a 3s upstream call"
        )
        artifact_lines.append(f"- upstream call_count after both resolve: {gap_attempts['call_count']}")
        artifact_lines.append(
            f"- gap reproduced (call_count > 1 → double-charge): "
            f"**{gap_attempts['call_count'] > 1}**"
        )
        artifact_lines.append("")
        if gap_attempts["call_count"] > 1:
            artifact_lines.append("- gap reproduced — existing primitive double-charges.")
        else:
            artifact_lines.append("- gap NOT reproduced (single charge or other anomaly).")
        artifact_lines.append("")

        # ---- PART B: AMD-03 reserved-row strategy on a shadow table ----
        # Create the shadow table that mirrors what migration 013 will
        # eventually add to idempotency_keys (status column + nullable
        # verdict_json).
        amd03_attempts: dict[str, int] = {"call_count": 0}
        shadow_setup_conn = await asyncpg.connect(dsn)
        try:
            await shadow_setup_conn.execute(
                """
                CREATE TABLE IF NOT EXISTS idempotency_keys_v2 (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL,
                    key TEXT NOT NULL,
                    request_body_hash TEXT NOT NULL,
                    verdict_json JSONB NULL,
                    status TEXT NOT NULL DEFAULT 'in_flight'
                        CHECK (status IN ('in_flight','success','failed')),
                    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '24 hours'),
                    UNIQUE (user_id, key)
                )
                """,
            )
        finally:
            await shadow_setup_conn.close()

        amd03_key = "phase29-amd03-" + uuid4().hex
        amd03_hash = hash_body(gap_body)
        amd03_winners: list[dict] = []

        async def _amd03_path(label: str) -> None:
            conn = await asyncpg.connect(dsn)
            try:
                # Try to reserve the row. ON CONFLICT DO NOTHING means
                # only the first INSERT wins; second sees no rows.
                row = await conn.fetchrow(
                    """
                    INSERT INTO idempotency_keys_v2
                        (user_id, key, request_body_hash, verdict_json, status)
                    VALUES ($1, $2, $3, NULL, 'in_flight')
                    ON CONFLICT (user_id, key) DO NOTHING
                    RETURNING id
                    """,
                    anon_user_id, amd03_key, amd03_hash,
                )
                if row is not None:
                    # We won the race — fire upstream
                    amd03_attempts["call_count"] += 1
                    await asyncio.sleep(3.0)
                    verdict = {"label": label, "tokens": 99, "winner": True}
                    await conn.execute(
                        """
                        UPDATE idempotency_keys_v2
                           SET verdict_json=$1::jsonb, status='success'
                         WHERE user_id=$2 AND key=$3
                        """,
                        json.dumps(verdict), anon_user_id, amd03_key,
                    )
                    amd03_winners.append({"label": label, "verdict": verdict})
                else:
                    # We lost; poll for the verdict
                    deadline = asyncio.get_event_loop().time() + 5.0
                    final_verdict: dict | None = None
                    while asyncio.get_event_loop().time() < deadline:
                        cur = await conn.fetchrow(
                            """
                            SELECT status, verdict_json
                              FROM idempotency_keys_v2
                             WHERE user_id=$1 AND key=$2
                            """,
                            anon_user_id, amd03_key,
                        )
                        if cur and cur["status"] == "success" and cur["verdict_json"]:
                            v = cur["verdict_json"]
                            if isinstance(v, (str, bytes, bytearray)):
                                v = json.loads(v)
                            final_verdict = v
                            break
                        await asyncio.sleep(0.1)
                    amd03_winners.append({"label": label, "verdict": final_verdict, "replayed": True})
            finally:
                await conn.close()

        async def _start_two_amd03() -> None:
            t1 = asyncio.create_task(_amd03_path("a"))
            await asyncio.sleep(0.05)
            t2 = asyncio.create_task(_amd03_path("b"))
            await asyncio.gather(t1, t2)

        await _start_two_amd03()

        artifact_lines.append("### Part B — AMD-03 reserved-row strategy (shadow table)")
        artifact_lines.append(
            f"- two coroutines launched 50ms apart, each simulating a 3s upstream call"
        )
        artifact_lines.append(
            f"- upstream call_count after both resolve: {amd03_attempts['call_count']}"
        )
        artifact_lines.append(
            f"- both coroutines saw the SAME verdict: "
            f"**{len(amd03_winners) >= 2 and amd03_winners[0]['verdict'] == amd03_winners[1]['verdict']}**"
        )
        artifact_lines.append("- per-coroutine outcomes:")
        artifact_lines.append("```json")
        artifact_lines.append(json.dumps(amd03_winners, indent=2, default=str))
        artifact_lines.append("```")
        if amd03_attempts["call_count"] == 1:
            artifact_lines.append("- AMD-03 single-charges — pattern empirically validated.")
        artifact_lines.append("")

    # Verdict
    gap_reproduced = gap_attempts["call_count"] > 1
    amd03_single_charge = amd03_attempts["call_count"] == 1
    amd03_same_verdict = (
        len(amd03_winners) >= 2
        and amd03_winners[0]["verdict"] == amd03_winners[1]["verdict"]
    )

    artifact_lines.append("### Verdict reasoning")
    artifact_lines.append(
        f"- O-03 gap reproduced (existing primitive double-charges): **{gap_reproduced}**"
    )
    artifact_lines.append(
        f"- AMD-03 single-charges: **{amd03_single_charge}**"
    )
    artifact_lines.append(
        f"- AMD-03 both callers see SAME verdict: **{amd03_same_verdict}**"
    )

    verdict = "PASS" if (gap_reproduced and amd03_single_charge and amd03_same_verdict) else "FAIL"
    _write_artifact(ARTIFACT_PATH, "\n".join(artifact_lines), verdict)
    assert verdict == "PASS", (
        f"gap_reproduced={gap_reproduced} amd03_single={amd03_single_charge} "
        f"amd03_same={amd03_same_verdict} attempts={gap_attempts['call_count']}/{amd03_attempts['call_count']}"
    )

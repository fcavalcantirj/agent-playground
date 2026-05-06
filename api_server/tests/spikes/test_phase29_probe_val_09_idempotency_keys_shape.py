"""PROBE-VAL-09 — idempotency_keys table shape inspection.

Documents the existing schema (post 001_baseline + 008_relax_run_fk) and
enumerates the migration-013 delta that AMD-03 (reserved-row pattern)
will require:

  - ADD `status` text column with CHECK ('in_flight' | 'success' | 'failed')
  - ALTER `verdict_json` to NULLABLE (placeholder rows store NULL until
    the upstream call lands)

Cost: zero (testcontainers Postgres on first call).
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

pytestmark = [pytest.mark.spike, pytest.mark.api_integration]

WORKTREE_ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = (
    WORKTREE_ROOT / ".planning" / "phases" / "29-llm-egress-proxy" / "spikes"
)
ARTIFACT_PATH = ARTIFACT_DIR / "PROBE-VAL-09.md"
API_SERVER_DIR = WORKTREE_ROOT / "api_server"


def _normalize_dsn(raw: str) -> str:
    return raw.replace("postgresql+psycopg2://", "postgresql://").replace(
        "+psycopg2", ""
    )


def _write_artifact(path: Path, body: str, verdict: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {path.stem}\n\n{body}\n\nVERDICT: {verdict}\n")


@pytest.mark.asyncio
async def test_idempotency_keys_shape() -> None:
    artifact_lines: list[str] = [
        "## PROBE-VAL-09: idempotency_keys table shape (current + AMD-03 delta)",
        "",
    ]

    with PostgresContainer("postgres:17-alpine") as pg:
        dsn = _normalize_dsn(pg.get_connection_url())
        # Run alembic upgrade head against the test container.
        env = {**os.environ, "DATABASE_URL": dsn}
        result = subprocess.run(
            ["uv", "run", "alembic", "upgrade", "head"],
            cwd=str(API_SERVER_DIR),
            env=env,
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            artifact_lines.append("### Alembic migration FAILED")
            artifact_lines.append("```")
            artifact_lines.append(result.stdout[-2048:])
            artifact_lines.append(result.stderr[-2048:])
            artifact_lines.append("```")
            _write_artifact(ARTIFACT_PATH, "\n".join(artifact_lines), "FAIL")
            pytest.fail("alembic upgrade head failed inside spike")

        conn = await asyncpg.connect(dsn)
        try:
            cols = await conn.fetch(
                """
                SELECT column_name, data_type, is_nullable, column_default
                  FROM information_schema.columns
                 WHERE table_name = 'idempotency_keys'
                 ORDER BY ordinal_position
                """,
            )
            indexes = await conn.fetch(
                """
                SELECT indexname, indexdef
                  FROM pg_indexes
                 WHERE tablename = 'idempotency_keys'
                """,
            )
            constraints = await conn.fetch(
                """
                SELECT con.conname, pg_get_constraintdef(con.oid) AS def
                  FROM pg_constraint con
                  JOIN pg_class cls ON con.conrelid = cls.oid
                 WHERE cls.relname = 'idempotency_keys'
                """,
            )
        finally:
            await conn.close()

    cols_data = [
        {
            "column_name": r["column_name"],
            "data_type": r["data_type"],
            "is_nullable": r["is_nullable"],
            "column_default": r["column_default"],
        }
        for r in cols
    ]
    indexes_data = [
        {"indexname": r["indexname"], "indexdef": r["indexdef"]}
        for r in indexes
    ]
    constraints_data = [
        {"conname": r["conname"], "def": r["def"]} for r in constraints
    ]

    artifact_lines.append("### Columns")
    artifact_lines.append("```json")
    artifact_lines.append(json.dumps(cols_data, indent=2))
    artifact_lines.append("```")
    artifact_lines.append("")
    artifact_lines.append("### Indexes")
    artifact_lines.append("```json")
    artifact_lines.append(json.dumps(indexes_data, indent=2))
    artifact_lines.append("```")
    artifact_lines.append("")
    artifact_lines.append("### Constraints")
    artifact_lines.append("```json")
    artifact_lines.append(json.dumps(constraints_data, indent=2))
    artifact_lines.append("```")
    artifact_lines.append("")

    col_names = {c["column_name"] for c in cols_data}
    has_user_id = "user_id" in col_names
    has_key = "key" in col_names
    has_request_body_hash = "request_body_hash" in col_names
    has_verdict_json = "verdict_json" in col_names
    has_expires_at = "expires_at" in col_names
    verdict_nullable = next(
        (c["is_nullable"] for c in cols_data if c["column_name"] == "verdict_json"),
        None,
    )
    has_status = "status" in col_names

    artifact_lines.append("### Phase 29 proxy column requirements")
    artifact_lines.append(f"- user_id present: **{has_user_id}**")
    artifact_lines.append(f"- key present: **{has_key}**")
    artifact_lines.append(f"- request_body_hash present: **{has_request_body_hash}**")
    artifact_lines.append(f"- verdict_json present: **{has_verdict_json}** (nullable: {verdict_nullable})")
    artifact_lines.append(f"- expires_at present: **{has_expires_at}** (24h TTL slot)")
    artifact_lines.append("")

    artifact_lines.append("### Migration-013 delta (AMD-03 reserved-row strategy)")
    artifact_lines.append("Required additions to support the in-flight reservation pattern:")
    artifact_lines.append("")
    artifact_lines.append("- ADD `status` column (text) with CHECK constraint allowing")
    artifact_lines.append("  values: `'in_flight' | 'success' | 'failed'`. Default: `'in_flight'`.")
    artifact_lines.append(
        f"  Currently present: **{has_status}** (must be added by migration 013)"
    )
    artifact_lines.append("- ALTER `verdict_json` to NULLABLE (placeholder rows store NULL")
    artifact_lines.append("  until the upstream call lands).")
    artifact_lines.append(
        f"  Current nullability: **{verdict_nullable}** (currently NOT NULL → must be relaxed)"
    )
    artifact_lines.append("")
    artifact_lines.append("- Optional but recommended index on `status` for the watchdog")
    artifact_lines.append("  cleanup task (`SELECT ... WHERE status='in_flight' AND expires_at < NOW()`).")
    artifact_lines.append("")

    artifact_lines.append("### Verdict reasoning")
    base_columns_ok = (
        has_user_id and has_key and has_request_body_hash
        and has_verdict_json and has_expires_at
    )
    artifact_lines.append(f"- Phase-29 base columns present: **{base_columns_ok}**")
    artifact_lines.append(
        "- Migration-013 delta enumerated (status column + verdict_json NULLABLE)."
    )

    verdict = "PASS" if base_columns_ok else "FAIL"
    _write_artifact(ARTIFACT_PATH, "\n".join(artifact_lines), verdict)
    assert verdict == "PASS", (
        f"Required Phase-29 columns missing: cols={col_names}"
    )

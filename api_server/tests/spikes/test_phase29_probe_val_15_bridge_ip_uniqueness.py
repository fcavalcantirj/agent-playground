"""PROBE-VAL-15 — bridge IP uniqueness scope (running-only).

Probes:
  (a) Docker bridge IP reuse: start container A, capture IP, stop A,
      start B, capture IP. On Linux Docker bridge, IPs are typically
      reused.
  (b) The IP→user lookup MUST scope to `container_status='running'`. We
      simulate `agent_containers` rows in a testcontainers Postgres and
      assert the SQL `SELECT ... WHERE bridge_ip=$1 AND container_status='running'`
      returns exactly ONE row.
  (c) The partial unique index `ix_agent_containers_bridge_ip_running`
      (per 29-PATTERNS migration block) prevents two `running` rows with
      the same IP.

Cost: zero (testcontainers Postgres + 2 nginx containers).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
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
ARTIFACT_PATH = ARTIFACT_DIR / "PROBE-VAL-15.md"
API_SERVER_DIR = WORKTREE_ROOT / "api_server"


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True, text=True, timeout=5,
        ).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _normalize_dsn(raw: str) -> str:
    return raw.replace("postgresql+psycopg2://", "postgresql://").replace(
        "+psycopg2", ""
    )


def _write_artifact(path: Path, body: str, verdict: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {path.stem}\n\n{body}\n\nVERDICT: {verdict}\n")


@pytest.mark.asyncio
async def test_bridge_ip_uniqueness_scope() -> None:
    if not _docker_available():
        pytest.skip("docker daemon required")

    artifact_lines: list[str] = [
        "## PROBE-VAL-15: bridge IP uniqueness scope (`container_status='running'`)",
        "",
    ]

    # ---- Part 1: Docker bridge IP reuse on Linux Docker (or macOS) ----
    import docker
    client = docker.from_env()

    # Pick a network
    network_name = "bridge"
    try:
        client.networks.get("deploy_default")
        network_name = "deploy_default"
    except docker.errors.NotFound:
        pass
    artifact_lines.append(f"- network used: `{network_name}`")

    try:
        client.images.get("nginx:alpine")
    except docker.errors.ImageNotFound:
        client.images.pull("nginx:alpine")

    # Start container A
    a = client.containers.run(
        "nginx:alpine",
        detach=True,
        remove=False,
        network=network_name,
        name=f"phase29-probe-15-A-{int(time.time())}",
    )
    try:
        time.sleep(0.5)
        a.reload()
        a_net = (
            a.attrs.get("NetworkSettings", {}).get("Networks") or {}
        ).get(network_name) or {}
        a_ip = a_net.get("IPAddress") or ""
        artifact_lines.append(f"- container A initial IP: `{a_ip}`")

        # Stop A but DON'T remove (still has the IP allocation)
        a.stop(timeout=2)
        time.sleep(0.5)

        # Start container B on the same network
        b = client.containers.run(
            "nginx:alpine",
            detach=True,
            remove=False,
            network=network_name,
            name=f"phase29-probe-15-B-{int(time.time())}",
        )
        try:
            time.sleep(0.5)
            b.reload()
            b_net = (
                b.attrs.get("NetworkSettings", {}).get("Networks") or {}
            ).get(network_name) or {}
            b_ip = b_net.get("IPAddress") or ""
            artifact_lines.append(f"- container B IP (after A stopped): `{b_ip}`")
            ip_reuse = (a_ip and b_ip and a_ip == b_ip)
            artifact_lines.append(f"- IP reuse observed: **{ip_reuse}**")
            artifact_lines.append("")
        finally:
            try:
                b.stop(timeout=2)
            except Exception:
                pass
            try:
                b.remove()
            except Exception:
                pass
    finally:
        try:
            a.remove()
        except Exception:
            pass

    # ---- Part 2: simulated agent_containers schema with partial index ----
    artifact_lines.append("### SQL scope filter on `container_status='running'`")
    with PostgresContainer("postgres:17-alpine") as pg:
        dsn = _normalize_dsn(pg.get_connection_url())
        conn = await asyncpg.connect(dsn)
        try:
            # Create the simulated schema (mirror what 29-PATTERNS migration
            # block specifies for agent_containers + the partial index).
            await conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
            await conn.execute(
                """
                CREATE TABLE agent_containers_sim (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL,
                    container_id TEXT NOT NULL,
                    bridge_ip INET,
                    container_status TEXT NOT NULL
                        CHECK (container_status IN ('running','exited','removed','starting')),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await conn.execute(
                """
                CREATE UNIQUE INDEX ix_agent_containers_bridge_ip_running
                    ON agent_containers_sim (bridge_ip)
                    WHERE container_status = 'running' AND bridge_ip IS NOT NULL
                """
            )

            # Seed: user A's row (exited, ip 172.18.0.10) + user B's row
            # (running, ip 172.18.0.10 — reused IP scenario)
            user_a = uuid4()
            user_b = uuid4()
            shared_ip = "172.18.0.10"
            await conn.execute(
                """
                INSERT INTO agent_containers_sim
                    (user_id, container_id, bridge_ip, container_status)
                VALUES ($1, 'cnt-a', $2::inet, 'exited')
                """,
                user_a, shared_ip,
            )
            await conn.execute(
                """
                INSERT INTO agent_containers_sim
                    (user_id, container_id, bridge_ip, container_status)
                VALUES ($1, 'cnt-b', $2::inet, 'running')
                """,
                user_b, shared_ip,
            )

            # Test the proxy's lookup query: must scope to running.
            rows = await conn.fetch(
                """
                SELECT user_id, container_id
                  FROM agent_containers_sim
                 WHERE bridge_ip = $1::inet
                   AND container_status='running'
                """,
                shared_ip,
            )
            artifact_lines.append(
                f"- query: `SELECT ... WHERE bridge_ip=$1 AND container_status='running'`"
            )
            artifact_lines.append(f"- rows returned: {len(rows)}")
            assert len(rows) == 1, (
                f"running-only filter should return exactly 1 row, got {len(rows)}"
            )
            row = rows[0]
            scope_filter_ok = str(row["user_id"]) == str(user_b)
            artifact_lines.append(
                f"- correct user (B, the running one): **{scope_filter_ok}**"
            )

            # Test partial unique index: trying to insert ANOTHER running
            # row with the same IP must fail.
            unique_violation = False
            try:
                await conn.execute(
                    """
                    INSERT INTO agent_containers_sim
                        (user_id, container_id, bridge_ip, container_status)
                    VALUES ($1, 'cnt-c', $2::inet, 'running')
                    """,
                    uuid4(), shared_ip,
                )
            except asyncpg.UniqueViolationError:
                unique_violation = True
            artifact_lines.append(
                f"- partial unique index blocks 2nd `running` row with same IP: "
                f"**{unique_violation}**"
            )
        finally:
            await conn.close()

    artifact_lines.append("")
    artifact_lines.append("### Verdict reasoning")
    artifact_lines.append(
        f"- IP reuse documented (running scope is REAL — empirical test): observed = {ip_reuse}"
    )
    artifact_lines.append(
        f"- `container_status='running'` scope filter empirically validated: **{scope_filter_ok}**"
    )
    artifact_lines.append(
        f"- partial unique index `ix_agent_containers_bridge_ip_running` enforces uniqueness "
        f"among only `running` rows: **{unique_violation}**"
    )
    artifact_lines.append("")
    artifact_lines.append(
        "### Implication for Plan 29-02 (migration 013) + Plan 29-08 (proxy IP map)"
    )
    artifact_lines.append(
        "- Migration 013 MUST add `bridge_ip` column to `agent_containers` (INET) AND a "
        "partial unique index `ix_agent_containers_bridge_ip_running` on (bridge_ip) "
        "WHERE container_status='running'. The proxy's IP→user lookup MUST scope to "
        "`WHERE container_status='running'` always — without this, a freshly-stopped "
        "user A's IP could be mis-attributed to a freshly-started user B."
    )

    verdict = "PASS" if (scope_filter_ok and unique_violation) else "FAIL"
    _write_artifact(ARTIFACT_PATH, "\n".join(artifact_lines), verdict)
    assert verdict == "PASS", (
        f"scope_filter={scope_filter_ok} unique_violation={unique_violation}"
    )

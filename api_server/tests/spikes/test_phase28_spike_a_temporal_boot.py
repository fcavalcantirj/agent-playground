"""Phase 28 — Wave 0 Spike A: Temporal cluster boot against postgres:17-alpine.

Empirically closes RESEARCH.md §10 Assumption A3 — that
``temporalio/auto-setup:1.29.2`` bootstraps its schema cleanly against the
existing ``postgres:17-alpine`` image we already run in deploy.

The spike spins up a transient ``phase28spike`` compose project with its
own postgres + temporal services, polls the temporal healthcheck until
green (≤90s wall), then connects via the Python SDK and confirms the
default namespace is reachable. Tear-down ALWAYS runs
``docker compose down -v`` even on failure (try/finally).

If this spike FAILS, RESEARCH.md §7 Risk 5 + Assumption A3 are wrong:
fall back to ``temporalio/auto-setup:1.27.x`` on PG16 as a Wave 1
amendment. The captured ``docker compose logs temporal`` output goes into
the assertion message so the failure tells the planner exactly what to
revisit.

Run manually as part of Wave 0:

    cd api_server && pytest tests/spikes/test_phase28_spike_a_temporal_boot.py \
        -x -m spike --tb=short

Standard ``pytest`` runs DO NOT pick this up because the ``spike`` marker
is only opted in via ``-m spike`` (registered in ``pyproject.toml``).
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import textwrap
import time
import uuid
from pathlib import Path

import pytest

PROJECT_NAME = "phase28spike"
HEALTHCHECK_TIMEOUT_SECONDS = 90
COMPOSE_FILE_TEMPLATE = textwrap.dedent(
    """
    name: {project_name}
    services:
      postgres:
        image: postgres:17-alpine
        environment:
          POSTGRES_USER: ap
          POSTGRES_PASSWORD: spike-only-not-secret
          POSTGRES_DB: ap
        healthcheck:
          test: ["CMD", "pg_isready", "-U", "ap", "-d", "ap"]
          interval: 5s
          timeout: 3s
          retries: 10
      temporal:
        image: temporalio/auto-setup:1.29.2
        depends_on:
          postgres:
            condition: service_healthy
        environment:
          DB: postgres12
          DB_PORT: "5432"
          POSTGRES_SEEDS: postgres
          POSTGRES_USER: ap
          POSTGRES_PWD: spike-only-not-secret
          DBNAME: temporal
          VISIBILITY_DBNAME: temporal_visibility
          # auto-setup:1.29.2 ships `config/dynamicconfig/docker.yaml`
          # (empty) at runtime — NOT `development-sql.yaml` (which the
          # upstream docker-compose example still references for older
          # tags). Pointing at a nonexistent file crashes the server with
          # `unable to validate dynamic config: stat ...: no such file`.
          # SPIKE-A finding (RESEARCH §10 A3 corollary).
          DYNAMIC_CONFIG_FILE_PATH: config/dynamicconfig/docker.yaml
          TEMPORAL_ADDRESS: temporal:7233
          TEMPORAL_CLI_ADDRESS: temporal:7233
        ports:
          - "127.0.0.1:7233:7233"
        healthcheck:
          test: ["CMD", "temporal", "operator", "cluster", "health"]
          interval: 15s
          timeout: 5s
          retries: 10
          start_period: 30s
    """
).strip()


def _docker_available() -> bool:
    """Return True iff `docker` is on PATH and the daemon answers."""
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def _compose_cmd(compose_file: Path, *args: str) -> list[str]:
    return ["docker", "compose", "-f", str(compose_file), "-p", PROJECT_NAME, *args]


def _capture(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def _wait_for_temporal_healthy(compose_file: Path, deadline_seconds: int) -> tuple[bool, float, str]:
    """Poll `docker compose ps --format json` until temporal reports `Health: healthy`.

    Returns (ok, elapsed_seconds, last_status_line).
    """
    started = time.monotonic()
    last_status = "<no ps output yet>"
    while time.monotonic() - started < deadline_seconds:
        rc, stdout, stderr = _capture(
            _compose_cmd(compose_file, "ps", "--format", "json")
        )
        if rc != 0:
            last_status = f"ps rc={rc} stderr={stderr.strip()[:300]}"
        else:
            # `docker compose ps --format json` emits one JSON object per line
            # in compose v2.x.
            for line in stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                service = parsed.get("Service") or parsed.get("Name")
                health = parsed.get("Health") or ""
                if service and "temporal" in service and "ui" not in service:
                    last_status = f"service={service} health={health!r}"
                    if health == "healthy":
                        return True, time.monotonic() - started, last_status
        time.sleep(2)
    return False, time.monotonic() - started, last_status


async def _async_temporal_probe(address: str, namespace: str) -> dict[str, str]:
    """Connect to Temporal and confirm we can list workflows (empty is fine)."""
    from temporalio.client import Client  # imported lazily so test discovery is cheap

    client = await Client.connect(address, namespace=namespace)
    iterator = client.list_workflows("")
    # Drain at most one page to confirm the iterator works against a fresh cluster.
    seen = 0
    async for _wf in iterator:
        seen += 1
        if seen > 0:
            break
    return {
        "address": address,
        "namespace": namespace,
        "list_workflows_drained": str(seen),
    }


@pytest.mark.spike
def test_temporalio_auto_setup_1_29_2_boots_against_postgres_17_alpine(tmp_path: Path) -> None:
    """Spike A: temporal frontend reaches `Health: healthy` against PG17.

    Acceptance criteria from PLAN 28-01 Task 1:
      1. ``docker compose ... up -d`` returns 0
      2. healthcheck flips ``healthy`` within 90 wall seconds
      3. Python SDK ``Client.connect("localhost:7233", namespace="default")``
         succeeds
      4. ``client.list_workflows("")`` returns an iterator
      5. Tear-down runs (``docker compose down -v``) — verified by absence
         of any container named ``phase28spike-temporal-1``
    """
    if not _docker_available():
        pytest.skip("docker daemon not reachable; spike requires real Docker")

    compose_file = tmp_path / "docker-compose.spike-a.yml"
    compose_file.write_text(
        COMPOSE_FILE_TEMPLATE.format(project_name=PROJECT_NAME) + "\n",
        encoding="utf-8",
    )

    # Defensive: tear down any leftover from a prior failed run BEFORE we start.
    _capture(_compose_cmd(compose_file, "down", "-v", "--remove-orphans"))

    healthy = False
    elapsed = 0.0
    last_status = "<not polled>"
    probe_result: dict[str, str] = {}
    try:
        rc, stdout, stderr = _capture(_compose_cmd(compose_file, "up", "-d"))
        assert rc == 0, (
            f"docker compose up -d failed (rc={rc})\nstdout={stdout}\nstderr={stderr}"
        )

        healthy, elapsed, last_status = _wait_for_temporal_healthy(
            compose_file, HEALTHCHECK_TIMEOUT_SECONDS
        )
        if not healthy:
            _, log_stdout, log_stderr = _capture(
                _compose_cmd(compose_file, "logs", "--no-color", "temporal")
            )
            tail = (log_stdout or log_stderr).splitlines()[-60:]
            assert healthy, (
                f"temporal healthcheck never reached `healthy` within "
                f"{HEALTHCHECK_TIMEOUT_SECONDS}s "
                f"(elapsed={elapsed:.1f}s, last={last_status}).\n"
                f"--- tail of `docker compose logs temporal` ---\n"
                + "\n".join(tail)
            )

        # Real SDK probe — proves the frontend gRPC is reachable AND a
        # client can list_workflows on the default namespace. Empty result
        # is the expected outcome on a freshly-bootstrapped cluster.
        probe_result = asyncio.run(
            _async_temporal_probe("localhost:7233", "default")
        )
        assert probe_result["address"] == "localhost:7233"
        assert probe_result["namespace"] == "default"
    finally:
        # ALWAYS tear down — even on assertion failure. -v drops anonymous
        # volumes so a re-run starts clean.
        _capture(_compose_cmd(compose_file, "down", "-v", "--remove-orphans"))

    # Confirm tear-down actually removed the temporal container — name shape
    # is `<project>-<service>-1` for compose v2 single-replica services.
    rc, ps_stdout, ps_stderr = _capture(
        ["docker", "ps", "--format", "{{.Names}}"]
    )
    assert rc == 0, f"docker ps failed: {ps_stderr}"
    leaked = [
        n for n in ps_stdout.splitlines()
        if n.startswith(f"{PROJECT_NAME}-temporal")
    ]
    assert not leaked, (
        f"tear-down leaked containers: {leaked!r} (ps output: {ps_stdout})"
    )

    # Final invariants surface to pytest report on success too.
    print(  # noqa: T201 — spike output is part of the evidence ledger
        "SPIKE-A PASS: "
        f"healthy_in={elapsed:.1f}s last_status={last_status!r} "
        f"probe={probe_result!r}"
    )

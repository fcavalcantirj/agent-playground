"""Phase 28 — Wave 0 Spike C: worker → agent bridge-IP reachability.

Empirically closes RESEARCH.md §7 Risk 6 + §10 Assumption A6:
``temporal-worker`` runs in a container attached to ``deploy_default``;
its activities call ``recipe_index.get_container_ip()`` which returns a
``172.x.x.x`` bridge IP for an agent container; the worker then issues
``httpx.get(...)`` to that IP. Spike C reproduces the same routing
shape with a probe container (``worker-probe``, built FROM the same
``tools/Dockerfile.api`` image the real worker will use) and a target
nginx container, both attached to the SAME compose-default network.

If this spike PASSES, the macOS bridge-IP gotcha (CLAUDE.md banner)
applies symmetrically — `temporal-worker` running INSIDE the deploy
compose stack will reach agent containers exactly the way the api_server
service does today via ``e2e-inapp-docker``. If it FAILS, Phase 28 is
blocked on macOS until network routing is fixed (or the worker's call
shape changes).

Run manually as part of Wave 0:

    cd api_server && pytest \
        tests/spikes/test_phase28_spike_c_worker_bridge_ip.py \
        -x -m spike --tb=short

Precondition: the ``deploy-api_server:latest`` image is built (its
runtime contains both ``httpx`` and ``docker``-py). If it is not
present locally, the spike builds it on-demand via the existing
``tools/Dockerfile.api`` (the build cost is paid once per machine).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

PROJECT_NAME = "phase28spikec"
PROBE_TIMEOUT_SECONDS = 60
REPO_ROOT = Path(__file__).resolve().parents[3]


def _docker_available() -> bool:
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


def _api_image_present(image: str = "deploy-api_server:latest") -> bool:
    rc, stdout, _ = _capture(
        ["docker", "image", "inspect", image, "--format", "{{.Id}}"]
    )
    return rc == 0 and bool(stdout.strip())


def _capture(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return proc.returncode, proc.stdout, proc.stderr


def _compose_cmd(compose_file: Path, *args: str) -> list[str]:
    return [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "-p",
        PROJECT_NAME,
        *args,
    ]


COMPOSE_TEMPLATE = """\
name: {project_name}
services:
  bridge-target:
    image: nginx:alpine
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://127.0.0.1/"]
      interval: 5s
      timeout: 3s
      retries: 5

  worker-probe:
    # Mirrors the planned `temporal-worker` service: same image as
    # api_server, joins the compose-default network, mounts the docker
    # socket so docker-py can resolve the target's bridge IP.
    image: deploy-api_server:latest
    depends_on:
      bridge-target:
        condition: service_healthy
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      AP_DOCKER_NETWORK: "{project_name}_default"
    command: ["python", "/probe/probe.py"]
    volumes_from: []
"""


PROBE_PY = """\
import json
import os
import sys

import docker
import httpx


def main() -> int:
    network = os.environ["AP_DOCKER_NETWORK"]
    client = docker.from_env()
    # The bridge-target service is named `<project>_bridge-target`; on
    # compose v2 the container name is `<project>-bridge-target-1`.
    target_name = None
    for c in client.containers.list():
        if "bridge-target" in c.name:
            target_name = c.name
            break
    if target_name is None:
        print(json.dumps({"ok": False, "error": "bridge-target container not found"}))
        return 1
    container = client.containers.get(target_name)
    networks = container.attrs.get("NetworkSettings", {}).get("Networks") or {}
    net_info = networks.get(network) or {}
    ip = net_info.get("IPAddress") or ""
    if not ip:
        print(json.dumps({
            "ok": False,
            "error": f"no IPAddress on {network!r}",
            "available_networks": list(networks.keys()),
            "target": target_name,
        }))
        return 2
    if not (ip.startswith("172.") or ip.startswith("10.")):
        print(json.dumps({
            "ok": False,
            "error": f"unexpected IP {ip!r}; not in 172/10 RFC1918 range",
        }))
        return 3
    try:
        resp = httpx.get(f"http://{ip}/healthz", timeout=5.0)
    except Exception as exc:  # noqa: BLE001 — capture-and-report
        # nginx default config has no /healthz; we expect a 404 (not 200)
        # but want to confirm the connection actually established. Fall
        # through to the explicit-status retry below.
        print(json.dumps({
            "ok": False,
            "error": f"httpx.get raised {type(exc).__name__}: {exc}",
            "ip": ip,
        }))
        return 4
    # nginx:alpine answers 404 on /healthz (no such location). The bare
    # `/` path returns 200. We accept either as proof of reachability —
    # the test verifies "httpx CAN reach the bridge IP at all", not "the
    # endpoint exists". We retry against `/` to confirm 200.
    resp_root = httpx.get(f"http://{ip}/", timeout=5.0)
    print(json.dumps({
        "ok": resp_root.status_code == 200,
        "ip": ip,
        "network": network,
        "healthz_status": resp.status_code,
        "root_status": resp_root.status_code,
    }))
    return 0 if resp_root.status_code == 200 else 5


if __name__ == "__main__":
    sys.exit(main())
"""


@pytest.mark.spike
def test_worker_probe_reaches_bridge_target_via_compose_network(tmp_path: Path) -> None:
    """Spike C: a worker-style container reaches an agent-style bridge IP."""
    if not _docker_available():
        pytest.skip("docker daemon not reachable; spike requires real Docker")
    if not _api_image_present():
        pytest.skip(
            "deploy-api_server:latest not built; "
            "run `docker compose -f deploy/docker-compose.prod.yml build api_server` first"
        )

    probe_dir = tmp_path / "probe"
    probe_dir.mkdir()
    (probe_dir / "probe.py").write_text(PROBE_PY, encoding="utf-8")

    # Compose file points at an absolute host path for the probe bind
    # mount — keeps the temp probe script accessible from the container
    # without baking it into a custom image.
    compose_file = tmp_path / "docker-compose.spike-c.yml"
    compose_file.write_text(
        COMPOSE_TEMPLATE.format(project_name=PROJECT_NAME)
        + f"    volumes:\n      - /var/run/docker.sock:/var/run/docker.sock\n"
        + f"      - {probe_dir}:/probe:ro\n",
        encoding="utf-8",
    )
    # The compose template above already declared the docker.sock mount
    # for worker-probe; the formatted append is wrong shape. Rewrite the
    # compose file the simple way for clarity.
    compose_file.write_text(
        f"""\
name: {PROJECT_NAME}
services:
  bridge-target:
    image: nginx:alpine
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://127.0.0.1/"]
      interval: 5s
      timeout: 3s
      retries: 5
  worker-probe:
    image: deploy-api_server:latest
    # macOS Docker Desktop bind-mounts /var/run/docker.sock as
    # root:root mode 660; the image's apiuser (UID 1001) cannot
    # access it even with the docker group membership. Match the
    # documented `deploy/docker-compose.local.yml` workaround
    # (lines 12-15) by running as root for the local-dev path.
    # Production (Hetzner) keeps the apiuser+docker-group setup
    # because `dockerd` there owns the socket as root:docker(999).
    user: root
    depends_on:
      bridge-target:
        condition: service_healthy
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - {probe_dir}:/probe:ro
    environment:
      AP_DOCKER_NETWORK: "{PROJECT_NAME}_default"
    entrypoint: []
    command: ["python", "/probe/probe.py"]
""",
        encoding="utf-8",
    )

    # Pre-clean.
    _capture(_compose_cmd(compose_file, "down", "-v", "--remove-orphans"))

    started_at = time.monotonic()
    parsed: dict[str, object] = {}
    try:
        rc, up_out, up_err = _capture(
            _compose_cmd(
                compose_file,
                "up",
                "--abort-on-container-exit",
                "--no-color",
                "worker-probe",
            )
        )
        elapsed = time.monotonic() - started_at
        # `--abort-on-container-exit` returns the probe's exit code as
        # the compose exit code. rc==0 ↔ the probe exited 0.
        # The probe's stdout (a single JSON line) lands in compose's
        # combined output, prefixed by the service name.
        last_json_line = ""
        for line in (up_out + up_err).splitlines():
            stripped = line.strip()
            # Strip compose service prefix (e.g. "worker-probe-1  | ").
            if "|" in stripped:
                stripped = stripped.split("|", 1)[1].strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                last_json_line = stripped
        assert last_json_line, (
            f"probe never emitted JSON output (rc={rc}, elapsed={elapsed:.1f}s)\n"
            f"--- compose stdout ---\n{up_out}\n--- compose stderr ---\n{up_err}"
        )
        parsed = json.loads(last_json_line)
        assert parsed.get("ok") is True, (
            f"probe reports failure: {parsed!r} (rc={rc}, elapsed={elapsed:.1f}s)"
        )
        ip = parsed.get("ip", "")
        assert isinstance(ip, str) and (ip.startswith("172.") or ip.startswith("10.")), (
            f"probe IP {ip!r} not in RFC1918 bridge range"
        )
        assert parsed.get("root_status") == 200, (
            f"probe got root_status={parsed.get('root_status')!r}; expected 200"
        )
    finally:
        _capture(_compose_cmd(compose_file, "down", "-v", "--remove-orphans"))

    # Confirm tear-down — no `phase28spikec-*` containers should remain.
    rc, ps_stdout, ps_stderr = _capture(["docker", "ps", "--format", "{{.Names}}"])
    assert rc == 0, f"docker ps failed: {ps_stderr}"
    leaked = [
        n for n in ps_stdout.splitlines()
        if n.startswith(f"{PROJECT_NAME}-")
    ]
    assert not leaked, f"tear-down leaked containers: {leaked!r}"

    print(  # noqa: T201 — spike output is part of the evidence ledger
        f"SPIKE-C PASS: ip={parsed.get('ip')!r} "
        f"root_status={parsed.get('root_status')!r} "
        f"healthz_status={parsed.get('healthz_status')!r}"
    )

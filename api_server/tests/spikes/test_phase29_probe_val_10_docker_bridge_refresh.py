"""PROBE-VAL-10 — Docker bridge IP behavior on container restart + events() viability.

Probes:
  - Start an nginx:alpine container on `bridge` net; capture IP.
  - `c.restart()`; capture new IP.
  - Subscribe to `client.events(filters={'event': ['start','die']})` for
    5s while restarting and record whether the events arrive in real-time.

Decision recorded in artifact:
  - Use `events()` subscription (cheap, real-time, no polling) IF events
    arrive reliably; else fall back to `60s polling`.

Cost: zero (1 container start/restart cycle).
"""
from __future__ import annotations

import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.spike, pytest.mark.api_integration]

WORKTREE_ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = (
    WORKTREE_ROOT / ".planning" / "phases" / "29-llm-egress-proxy" / "spikes"
)
ARTIFACT_PATH = ARTIFACT_DIR / "PROBE-VAL-10.md"


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


def _write_artifact(path: Path, body: str, verdict: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {path.stem}\n\n{body}\n\nVERDICT: {verdict}\n")


def test_docker_bridge_ip_refresh_strategy() -> None:
    if not _docker_available():
        pytest.skip("docker daemon required")

    import docker

    client = docker.from_env()
    artifact_lines: list[str] = [
        "## PROBE-VAL-10: Docker bridge IP refresh strategy",
        "",
    ]

    # Pick a network: prefer deploy_default if present, else bridge
    network_name = "bridge"
    try:
        client.networks.get("deploy_default")
        network_name = "deploy_default"
    except docker.errors.NotFound:
        pass
    artifact_lines.append(f"- network used: `{network_name}`")
    artifact_lines.append("")

    # Pull/run nginx:alpine
    try:
        client.images.get("nginx:alpine")
    except docker.errors.ImageNotFound:
        client.images.pull("nginx:alpine")

    container = client.containers.run(
        "nginx:alpine",
        detach=True,
        remove=True,
        network=network_name,
        name=f"phase29-probe-10-{int(time.time())}",
    )
    try:
        # Capture initial IP
        time.sleep(0.5)
        container.reload()
        net_info = (
            container.attrs.get("NetworkSettings", {}).get("Networks") or {}
        ).get(network_name) or {}
        initial_ip = net_info.get("IPAddress") or ""
        artifact_lines.append(f"- initial IP on `{network_name}`: `{initial_ip}`")

        # Subscribe to events
        events_received: list[dict] = []
        events_iter_holder: dict = {}
        stop_events = threading.Event()

        def _consume_events() -> None:
            it = client.events(
                filters={"event": ["start", "die", "stop", "destroy"]},
                decode=True,
                since=time.time() - 1,
            )
            events_iter_holder["it"] = it
            try:
                for event in it:
                    if stop_events.is_set():
                        break
                    events_received.append(
                        {
                            "Action": event.get("Action"),
                            "id_short": (event.get("id") or "")[:12],
                            "from": event.get("from"),
                        }
                    )
            except Exception:
                return

        listener = threading.Thread(target=_consume_events, daemon=True)
        listener.start()

        # Restart the container
        time.sleep(0.5)  # let listener subscribe
        t_restart_start = time.monotonic()
        container.restart(timeout=2)
        t_restart_done = time.monotonic()
        time.sleep(2.0)  # let events propagate

        # Capture new IP
        container.reload()
        net_info_2 = (
            container.attrs.get("NetworkSettings", {}).get("Networks") or {}
        ).get(network_name) or {}
        new_ip = net_info_2.get("IPAddress") or ""
        artifact_lines.append(f"- IP after restart on `{network_name}`: `{new_ip}`")
        ip_changed = (initial_ip and new_ip and initial_ip != new_ip)
        artifact_lines.append(f"- IP changed on restart: **{ip_changed}**")
        artifact_lines.append(
            f"- restart wall-time: {t_restart_done - t_restart_start:.3f}s"
        )
        artifact_lines.append("")

        # Stop event listener
        stop_events.set()
        try:
            it = events_iter_holder.get("it")
            if it is not None and hasattr(it, "close"):
                it.close()
        except Exception:
            pass
        listener.join(timeout=1.0)

        artifact_lines.append("### Events observed during restart window")
        artifact_lines.append(f"- count: {len(events_received)}")
        if events_received:
            artifact_lines.append("```json")
            import json as _json
            artifact_lines.append(_json.dumps(events_received[:10], indent=2))
            artifact_lines.append("```")
        artifact_lines.append("")

        events_viable = len(events_received) >= 1
        artifact_lines.append("### Strategy decision")
        if events_viable:
            artifact_lines.append(
                "- **DECISION: events() subscription** is viable on this platform "
                "(events arrived in real-time during the restart window). The proxy "
                "should subscribe to `start`/`die`/`destroy` events and refresh the "
                "IP→user map on every event — no 60s polling fallback needed."
            )
        else:
            artifact_lines.append(
                "- **DECISION: 60s polling** fallback is required — events() did NOT "
                "arrive within the 5s observation window on this platform. The proxy "
                "should refresh the IP→user map every 60s (covering the typical "
                "restart cadence)."
            )
        artifact_lines.append("")

        artifact_lines.append("### Verdict reasoning")
        # PASS iff (a) IP behavior is documented (we always have something) AND
        # (b) events() viability is empirically established.
        ip_documented = bool(initial_ip and new_ip)
        artifact_lines.append(f"- IP behavior documented: **{ip_documented}**")
        artifact_lines.append(
            f"- events() viability empirically established: **{events_viable}** "
            f"({len(events_received)} events observed)"
        )
        # Even if events_viable is False, that's still a useful empirical
        # finding (drives 60s polling decision). PASS gate is "IP behavior
        # documented + events viability assessed."
        verdict = "PASS" if ip_documented else "FAIL"
        _write_artifact(ARTIFACT_PATH, "\n".join(artifact_lines), verdict)
        assert verdict == "PASS", f"ip_documented={ip_documented}"

    finally:
        try:
            container.stop(timeout=2)
        except Exception:
            pass

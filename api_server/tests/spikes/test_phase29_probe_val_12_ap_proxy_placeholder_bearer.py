"""PROBE-VAL-12 — openai-SDK + (optional) langchain-openai accept ap-proxy-* Bearer.

The proxy injects a placeholder Bearer of the form `ap-proxy-<random32hex>`
into bot containers' `OPENAI_API_KEY`. The proxy itself swaps it for the
real BYOK key on egress. PROBE-VAL-12 confirms the openai Python SDK
(used by nanobot's openai_compat_provider) does NOT locally validate
the key shape — it simply forwards it as a Bearer header.

Strategy: bind a TCP server on 127.0.0.1:39999 that accepts the connection
and immediately closes (TCP RST). Construct an OpenAI client with
api_key='ap-proxy-deadbeef...' and base_url='http://127.0.0.1:39999/v1'.
The exception class distinguishes:
  - APIConnectionError or similar transport error → SDK accepted the key
    shape (PASS — placeholder works)
  - AuthenticationError-shaped local exception or ValueError on key
    validation → SDK rejected the key shape (FAIL)

Cost: zero (no upstream calls).
"""
from __future__ import annotations

import socket
import threading
from pathlib import Path

import pytest

pytestmark = [pytest.mark.spike, pytest.mark.api_integration]

ARTIFACT_DIR = (
    Path(__file__).resolve().parents[3]
    / ".planning"
    / "phases"
    / "29-llm-egress-proxy"
    / "spikes"
)
ARTIFACT_PATH = ARTIFACT_DIR / "PROBE-VAL-12.md"
PORT = 39999
PLACEHOLDER_KEY = "ap-proxy-" + "deadbeef" * 4  # 32 hex chars after prefix


def _write_artifact(path: Path, body: str, verdict: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {path.stem}\n\n{body}\n\nVERDICT: {verdict}\n")


def _accept_then_close(server_sock: socket.socket, stop: threading.Event) -> None:
    server_sock.settimeout(0.5)
    while not stop.is_set():
        try:
            client_sock, _ = server_sock.accept()
        except socket.timeout:
            continue
        except OSError:
            return
        try:
            client_sock.close()
        except OSError:
            pass


def test_openai_sdk_accepts_placeholder_bearer() -> None:
    # ---- Bind a tiny TCP server that accepts + immediately closes ----
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", PORT))
    server.listen(8)
    stop_event = threading.Event()
    listener = threading.Thread(
        target=_accept_then_close, args=(server, stop_event), daemon=True
    )
    listener.start()

    artifact_lines: list[str] = [
        "## PROBE-VAL-12: openai-SDK accepts `ap-proxy-*` placeholder Bearer",
        "",
        f"- placeholder key: `{PLACEHOLDER_KEY}` (length: {len(PLACEHOLDER_KEY)})",
        f"- target base_url: `http://127.0.0.1:{PORT}/v1`",
        "",
    ]

    sdk_outcome: str = "UNKNOWN"
    sdk_exc_type: str = ""
    sdk_exc_msg: str = ""
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=PLACEHOLDER_KEY,
            base_url=f"http://127.0.0.1:{PORT}/v1",
            max_retries=0,
            timeout=5.0,
        )
        try:
            client.chat.completions.create(
                model="x",
                messages=[{"role": "user", "content": "hi"}],
            )
            sdk_outcome = "UNEXPECTED_SUCCESS"
        except Exception as exc:
            sdk_exc_type = type(exc).__name__
            sdk_exc_msg = str(exc)[:300]
            # Connection-level errors mean the SDK forwarded the request
            # to our listener (which RST-closed). That proves the SDK
            # didn't reject the key shape locally.
            #
            # APIConnectionError / RemoteProtocolError / ReadError /
            # ConnectError / OSError — all qualify.
            if any(
                x in sdk_exc_type
                for x in (
                    "Connection",
                    "Protocol",
                    "Read",
                    "Connect",
                    "OSError",
                )
            ):
                sdk_outcome = "ACCEPTED-KEY-SHAPE-CONNECTION-ERROR"
            elif "Authentication" in sdk_exc_type or "key" in sdk_exc_msg.lower():
                sdk_outcome = "REJECTED-KEY-SHAPE"
            else:
                sdk_outcome = f"OTHER ({sdk_exc_type})"
    finally:
        stop_event.set()
        try:
            server.close()
        except OSError:
            pass
        listener.join(timeout=2.0)

    artifact_lines.append("### openai SDK probe")
    artifact_lines.append(f"- outcome: **{sdk_outcome}**")
    artifact_lines.append(f"- exception type: `{sdk_exc_type}`")
    artifact_lines.append(f"- exception message (first 300 chars): `{sdk_exc_msg}`")
    artifact_lines.append("")

    # ---- langchain-openai (optional) ----
    artifact_lines.append("### langchain-openai probe")
    lc_outcome: str = "SKIPPED"
    try:
        # Re-bind for the langchain probe
        server2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server2.bind(("127.0.0.1", PORT))
        server2.listen(8)
        stop_event2 = threading.Event()
        listener2 = threading.Thread(
            target=_accept_then_close, args=(server2, stop_event2), daemon=True
        )
        listener2.start()
        try:
            from langchain_openai import ChatOpenAI  # type: ignore

            llm = ChatOpenAI(
                api_key=PLACEHOLDER_KEY,
                base_url=f"http://127.0.0.1:{PORT}/v1",
                max_retries=0,
                timeout=5.0,
                model="x",
            )
            try:
                llm.invoke("hi")
                lc_outcome = "UNEXPECTED_SUCCESS"
            except Exception as exc:
                t = type(exc).__name__
                if any(
                    x in t for x in ("Connection", "Protocol", "Read", "Connect", "OSError")
                ):
                    lc_outcome = "ACCEPTED-KEY-SHAPE-CONNECTION-ERROR"
                elif "Authentication" in t:
                    lc_outcome = "REJECTED-KEY-SHAPE"
                else:
                    lc_outcome = f"OTHER ({t})"
                artifact_lines.append(f"- exception type: `{t}`")
                artifact_lines.append(f"- exception message (first 300 chars): `{str(exc)[:300]}`")
        except ImportError:
            lc_outcome = "SKIPPED (langchain_openai not installed)"
        finally:
            stop_event2.set()
            try:
                server2.close()
            except OSError:
                pass
            listener2.join(timeout=2.0)
    except OSError as exc:
        lc_outcome = f"PORT_BIND_FAILED ({exc})"
    artifact_lines.append(f"- outcome: **{lc_outcome}**")
    artifact_lines.append("")

    # PASS criterion
    sdk_pass = sdk_outcome == "ACCEPTED-KEY-SHAPE-CONNECTION-ERROR"
    lc_pass = lc_outcome.startswith("ACCEPTED-KEY-SHAPE") or lc_outcome.startswith(
        "SKIPPED"
    )

    artifact_lines.append("### Verdict reasoning")
    artifact_lines.append(f"- openai SDK accepts `ap-proxy-*` shape: **{sdk_pass}**")
    artifact_lines.append(
        f"- langchain-openai accepts `ap-proxy-*` shape: **{lc_pass}**"
    )
    artifact_lines.append("")
    artifact_lines.append(
        "### Implication for Plan 29-05 (env injection)"
    )
    artifact_lines.append(
        "- The deploy-time env-injection layer can safely set "
        f"`OPENAI_API_KEY={PLACEHOLDER_KEY[:24]}...` (or any `ap-proxy-*` "
        "shape) inside the bot container. The openai SDK (and via it, "
        "nanobot's openai_compat_provider) treats it as an opaque Bearer "
        "string forwarded to the proxy on egress. The proxy reads its "
        "own Bearer header, looks up the per-deploy BYOK key from the "
        "`proxy_byok_cache`, and replaces the Authorization header before "
        "forwarding upstream."
    )

    verdict = "PASS" if (sdk_pass and lc_pass) else "FAIL"
    _write_artifact(ARTIFACT_PATH, "\n".join(artifact_lines), verdict)
    assert verdict == "PASS", (
        f"sdk_outcome={sdk_outcome!r} lc_outcome={lc_outcome!r}"
    )

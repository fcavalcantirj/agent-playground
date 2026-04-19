#!/usr/bin/env python3
"""Agent test harness (Phase 22b) — two subcommands closing SC-03 Gates A + B.

  send-direct-and-read (Gate A — primary, fully automatable):
    Loads the named recipe YAML, dispatches on
    `direct_interface.kind`:
      docker_exec_cli       → `docker exec <cid> <argv ...>` and
                              capture stdout (optionally narrow with
                              spec.reply_extract_regex).
      http_chat_completions → POST OpenAI-compatible body to
                              http://127.0.0.1:<port><path> and
                              extract spec.response_jsonpath.
    Asserts the correlation UUID embedded in the prompt is echoed in
    the reply. No Telegram involved; no API server involved.

  send-telegram-and-watch-events (Gate B — secondary):
    Bot->self sendMessage with an embedded correlation UUID (legal
    Bot API use; bot is sender AND chat owner), then long-poll
    GET /v1/agents/:id/events?since_seq=<N>&kinds=reply_sent&timeout_s=10
    with Authorization: Bearer <AP_SYSADMIN_TOKEN>. Verdict = PASS iff
    a reply_sent event for our chat lands within the window.

Legacy `send-and-wait` (Bot API long-poll-updates path) is REMOVED per
D-18 — spike 01a proved Bot API cannot impersonate a user and the
update-polling single-consumer constraint (see
memory/feedback_telegram_getupdates_is_single_consumer.md) makes that
path incompatible with a running gateway. Use Gate A for agent
correctness; Gate B for delivery wiring; Gate C (manual) for the real
user→bot round-trip.

Stdlib-only (urllib, subprocess, argparse, json, uuid, re, yaml). The
`yaml` import is the only external dep — already required by the
runner (tools/run_recipe.py).

Output convention:
  Each subcommand emits exactly ONE JSON object on stdout, then exits.

Exit codes:
  0  PASS (verdict in JSON also = "PASS")
  1  FAIL (timeout / wrong reply / long-poll empty)
  2  send / setup error (HTTP failure during sendMessage or pre-query)
  3  usage error (caught by argparse; printed by argparse to stderr)

Security notes (T-22b-06-01..T-22b-06-06):
  - bearer / api_key NEVER appear in stdout JSON (only the verdict envelope).
  - subprocess stderr is truncated to 200 chars in the error field.
  - argv is passed as a list to subprocess.run (shell=False) so prompts
    cannot inject shell metacharacters.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path


# ---------- HTTP helpers (mirrors legacy telegram_harness style) -------------

def _post(url: str, body: dict, timeout: int = 30, headers: dict | None = None) -> dict:
    """POST JSON body and return parsed JSON response.

    Raises RuntimeError on HTTP error so callers can surface a structured
    "FAIL with error" envelope rather than crashing.
    """
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_excerpt = e.read()[:400]
        try:
            payload = json.loads(body_excerpt.decode("utf-8"))
            payload.setdefault("ok", False)
            payload.setdefault("description", f"HTTP {e.code} {e.reason}")
            return payload
        except Exception:
            raise RuntimeError(
                f"POST {url} -> {e.code}: {body_excerpt!r}"
            )


def _get(url: str, timeout: int = 40, headers: dict | None = None) -> dict:
    """GET and return parsed JSON response. Lets HTTPError bubble up."""
    req = urllib.request.Request(url, method="GET")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------- Telegram sendMessage (bot -> self, valid Bot API use) -----------

def send_message(token: str, chat_id: str, text: str) -> dict:
    """Bot API sendMessage. Returns the parsed Telegram envelope (ok/result).

    sendMessage from a bot token sends AS the bot. We use this to push a
    correlation token into the bot's own chat so the gateway picks it up
    via the same path a real user message would (the bot is also a chat
    member). This does NOT prove a user→bot round-trip — that's Gate C.
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    return _post(url, {"chat_id": chat_id, "text": text}, timeout=15)


# ---------- Tiny JSONPath subset ($.a.b, $.a[0].b) --------------------------

def _jsonpath_simple(obj, path: str):
    """Resolve a $.a.b[0].c path against a Python dict/list tree.

    Sufficient for `$.choices[0].message.content` — the OpenAI-compatible
    response shape declared in recipes' direct_interface.spec.response_jsonpath.
    Not a general JSONPath; intentionally minimal.
    """
    cur = obj
    tokens = re.split(r"\.|\[(\d+)\]", path.lstrip("$").lstrip("."))
    tokens = [t for t in tokens if t]
    for t in tokens:
        if t.isdigit():
            cur = cur[int(t)]
        else:
            cur = cur[t]
    return cur


# ---------- Recipe loader ---------------------------------------------------

def _load_recipe(recipe_name: str) -> dict:
    """Load recipes/<name>.yaml from the repo root. Errors are FAIL envelopes."""
    try:
        import yaml
    except ImportError as e:
        print(json.dumps({
            "verdict": "ERROR",
            "error": f"PyYAML not installed: {e}",
        }))
        sys.exit(3)
    root = Path(__file__).resolve().parents[2]
    path = root / "recipes" / f"{recipe_name}.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


# ---------- Gate A: send-direct-and-read ------------------------------------

def cmd_send_direct_and_read(args) -> int:
    """Gate A — invoke recipe.direct_interface, read reply, assert correlation.

    JSON output schema:
      {"gate":"A","recipe":...,"correlation_id":...,
       "sent_text":...,"reply_text":<truncated 400 chars>|null,
       "wall_s":...,"verdict":"PASS"|"FAIL","error":null|<short str>}
    """
    recipe = _load_recipe(args.recipe)
    di = recipe.get("direct_interface")
    if not di:
        print(json.dumps({
            "gate": "A", "recipe": args.recipe,
            "correlation_id": None, "sent_text": None,
            "reply_text": None, "wall_s": 0,
            "verdict": "FAIL",
            "error": "no direct_interface block in recipe YAML",
        }))
        return 1

    corr = uuid.uuid4().hex[:4]
    prompt = (
        f"Please reply with exactly this text and nothing else: "
        f"ok-{args.recipe}-{corr}"
    )
    t0 = time.time()
    reply_text: str | None = None
    error: str | None = None
    kind = di.get("kind")

    try:
        if kind == "docker_exec_cli":
            spec = di["spec"]
            try:
                argv = [
                    a.format(prompt=prompt, model=args.model)
                    for a in spec["argv_template"]
                ]
            except KeyError as e:
                # Recipe declared a template variable we don't support.
                # Surface as FAIL (not a crash) so the e2e script can
                # capture which recipe needs a fix.
                error = (
                    f"recipe {args.recipe!r} direct_interface.spec.argv_template "
                    f"references unsupported template var: {e}"
                )
                print(json.dumps({
                    "gate": "A", "recipe": args.recipe, "correlation_id": corr,
                    "sent_text": prompt, "reply_text": None,
                    "wall_s": round(time.time() - t0, 2),
                    "verdict": "FAIL", "error": error,
                }))
                return 1
            out = subprocess.run(
                ["docker", "exec", args.container_id, *argv],
                capture_output=True, text=True,
                timeout=spec.get("timeout_s", 60),
                check=False,
            )
            if out.returncode != spec.get("exit_code_success", 0):
                # Truncate stderr — it can include token fragments from
                # noisy agent logging (T-22b-06-05).
                error = f"exit_code={out.returncode} stderr={out.stderr[:200]!r}"
            reply_text = out.stdout
            extract = spec.get("reply_extract_regex")
            if extract and reply_text:
                m = re.search(extract, reply_text)
                if m:
                    reply_text = (
                        m.group("reply")
                        if "reply" in m.groupdict()
                        else m.group(0)
                    )

        elif kind == "http_chat_completions":
            spec = di["spec"]
            url = f"http://127.0.0.1:{spec['port']}{spec['path']}"
            body = dict(spec["request_template"])
            # Always overwrite messages with our correlation prompt;
            # recipe's request_template.messages is a placeholder shape.
            body["messages"] = [{"role": "user", "content": prompt}]
            headers: dict[str, str] = {}
            auth = spec.get("auth") or {}
            if auth:
                headers[auth["header"]] = auth["value_template"].format(
                    api_key=args.api_key
                )
            resp = _post(
                url, body,
                timeout=spec.get("timeout_s", 60),
                headers=headers,
            )
            try:
                reply_text = str(_jsonpath_simple(resp, spec["response_jsonpath"]))
            except (KeyError, IndexError, TypeError) as e:
                error = (
                    f"response_jsonpath {spec['response_jsonpath']!r} "
                    f"failed against response keys={list(resp.keys()) if isinstance(resp, dict) else type(resp).__name__}: {e}"
                )

        else:
            error = f"unknown direct_interface.kind: {kind!r}"

    except subprocess.TimeoutExpired:
        error = "subprocess timeout"
    except Exception as e:
        error = f"{type(e).__name__}: {e}"

    wall_s = round(time.time() - t0, 2)
    expected = f"ok-{args.recipe}-{corr}"
    verdict = "PASS" if (error is None and expected in (reply_text or "")) else "FAIL"

    print(json.dumps({
        "gate": "A",
        "recipe": args.recipe,
        "correlation_id": corr,
        "sent_text": prompt,
        "reply_text": reply_text[:400] if reply_text else None,
        "wall_s": wall_s,
        "verdict": verdict,
        "error": error,
    }))
    return 0 if verdict == "PASS" else 1


# ---------- Gate B: send-telegram-and-watch-events --------------------------

def cmd_send_telegram_and_watch_events(args) -> int:
    """Gate B — bot->self sendMessage + long-poll /v1/agents/:id/events.

    JSON output schema:
      {"gate":"B","recipe":...,"correlation_id":...,
       "sent_text":...,"reply_sent_event":<event-row>|null,
       "wall_s":...,"verdict":"PASS"|"FAIL","error":null|<short str>}
    """
    corr = uuid.uuid4().hex[:4]
    text = f"ping-22b-test-{corr}"
    t0 = time.time()

    # Establish the since_seq cursor BEFORE sending — only events newer
    # than this count toward the verdict (D-11 + D-16 semantics: seq
    # is per-agent, gap-free; future events have strictly larger seq).
    try:
        resp = _get(
            f"{args.api_base}/v1/agents/{args.agent_id}/events"
            f"?since_seq=0&timeout_s=1",
            headers={"Authorization": f"Bearer {args.bearer}"},
            timeout=5,
        )
        since_seq = resp.get("next_since_seq", 0)
    except Exception as e:
        print(json.dumps({
            "gate": "B", "recipe": args.recipe,
            "correlation_id": corr, "sent_text": text,
            "reply_sent_event": None,
            "wall_s": round(time.time() - t0, 2),
            "verdict": "FAIL",
            "error": f"pre-query failed: {type(e).__name__}: {e}",
        }))
        return 2

    # Bot->self sendMessage. Bot API rejects ill-formed requests with
    # ok:false + description; we surface that as a send error (exit 2).
    try:
        sent = send_message(args.token, args.chat_id, text)
    except Exception as e:
        print(json.dumps({
            "gate": "B", "recipe": args.recipe,
            "correlation_id": corr, "sent_text": text,
            "reply_sent_event": None,
            "wall_s": round(time.time() - t0, 2),
            "verdict": "FAIL",
            "error": f"sendMessage failed: {type(e).__name__}: {e}",
        }))
        return 2
    if not sent.get("ok"):
        print(json.dumps({
            "gate": "B", "recipe": args.recipe,
            "correlation_id": corr, "sent_text": text,
            "reply_sent_event": None,
            "wall_s": round(time.time() - t0, 2),
            "verdict": "FAIL",
            "error": sent.get("description") or "sendMessage not ok",
        }))
        return 2

    # Long-poll the event-stream endpoint for any reply_sent in the
    # window. D-13 caps concurrent polls; D-09 timeout_s drives the
    # server-side asyncio.Event hold. We add a 5s grace to our own
    # urllib timeout so the server's idle-return doesn't race.
    try:
        url = (
            f"{args.api_base}/v1/agents/{args.agent_id}/events"
            f"?since_seq={since_seq}&kinds=reply_sent&timeout_s={args.timeout_s}"
        )
        resp = _get(
            url,
            headers={"Authorization": f"Bearer {args.bearer}"},
            timeout=args.timeout_s + 5,
        )
    except Exception as e:
        print(json.dumps({
            "gate": "B", "recipe": args.recipe,
            "correlation_id": corr, "sent_text": text,
            "reply_sent_event": None,
            "wall_s": round(time.time() - t0, 2),
            "verdict": "FAIL",
            "error": f"long-poll failed: {type(e).__name__}: {e}",
        }))
        return 1

    events = resp.get("events", []) or []
    # D-07 fallback: any reply_sent event for our chat after send time
    # is a PASS. Correlation_id echo is best-effort (not all recipes
    # echo the prompt verbatim); chat_id + ts-after-send is the floor.
    match = next(
        (
            e for e in events
            if e.get("kind") == "reply_sent"
            and (e.get("payload") or {}).get("chat_id") == str(args.chat_id)
        ),
        None,
    )
    verdict = "PASS" if match else "FAIL"

    print(json.dumps({
        "gate": "B",
        "recipe": args.recipe,
        "correlation_id": corr,
        "sent_text": text,
        "reply_sent_event": match,
        "wall_s": round(time.time() - t0, 2),
        "verdict": verdict,
        "error": None if match else "no matching reply_sent event in window",
    }))
    return 0 if verdict == "PASS" else 1


# ---------- argparse --------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent_harness",
        description="Phase 22b SC-03 harness — Gate A (direct_interface) + "
                    "Gate B (event-stream long-poll) subcommands.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser(
        "send-direct-and-read",
        help="Gate A: invoke recipe.direct_interface and read the reply.",
    )
    a.add_argument("--recipe", required=True,
                   help="Recipe name (file recipes/<name>.yaml)")
    a.add_argument("--container-id", required=True,
                   help="Running container id (for docker_exec_cli kinds)")
    a.add_argument("--model", required=True,
                   help="Model id substituted into argv_template / request body")
    a.add_argument("--api-key", required=True,
                   help="Bearer for http_chat_completions auth (BYOK provider key)")
    a.add_argument("--timeout-s", type=int, default=60,
                   help="Override the recipe's timeout_s (default 60)")
    a.set_defaults(func=cmd_send_direct_and_read)

    b = sub.add_parser(
        "send-telegram-and-watch-events",
        help="Gate B: bot->self sendMessage + long-poll the events endpoint.",
    )
    b.add_argument("--api-base", required=True,
                   help="Base URL of the API server (e.g. http://localhost:8000)")
    b.add_argument("--agent-id", required=True,
                   help="agent_instance_id — long-poll target")
    b.add_argument("--bearer", required=True,
                   help="AP_SYSADMIN_TOKEN value (D-15 sysadmin bypass)")
    b.add_argument("--recipe", required=True,
                   help="Recipe name (cosmetic — appears in JSON envelope)")
    b.add_argument("--token", required=True,
                   help="TELEGRAM_BOT_TOKEN")
    b.add_argument("--chat-id", required=True,
                   help="TELEGRAM_CHAT_ID — bot sends to itself in this chat")
    b.add_argument("--timeout-s", type=int, default=10,
                   help="Long-poll window in seconds (default 10)")
    b.set_defaults(func=cmd_send_telegram_and_watch_events)

    return p


def main(argv: list[str] | None = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

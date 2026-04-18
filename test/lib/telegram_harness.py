#!/usr/bin/env python3
"""Telegram test harness — send a DM and wait for the bot's reply.

Usage:
  # Drain any pending updates so the next send-and-wait sees a clean window.
  python3 test/lib/telegram_harness.py drain --token "$TELEGRAM_BOT_TOKEN"

  # Send a DM and wait up to 30s for a reply from the bot.  Any message from
  # the bot that arrives in the target chat after send_time is considered the
  # reply (agents rewrite wording and often don't echo, so strict content
  # correlation is brittle).
  python3 test/lib/telegram_harness.py send-and-wait \\
      --token "$TELEGRAM_BOT_TOKEN" \\
      --chat-id "$TELEGRAM_CHAT_ID" \\
      --text "ping-22a-test-$(uuidgen)" \\
      --timeout-s 30 \\
      --emit json

Outputs JSON to stdout (one line):
  {"send_ok": true, "sent_text": "...", "reply_text": "...",
   "reply_wall_s": 2.1, "error": null}
  OR
  {"send_ok": true, "sent_text": "...", "reply_text": null,
   "reply_wall_s": null, "error": "timeout"}
  OR
  {"send_ok": false, "error": "sendMessage failed: ..."}

Exit codes:
  0  round-trip PASS (reply received)
  1  timeout (no reply in window) OR getUpdates failure
  2  send failed (bot token bad, chat unreachable, HTTP error)
  3  usage error (caught by argparse before we reach here)

Design notes:
- Uses Bot API getUpdates with a moving offset.  `drain` consumes any backlog
  and ACKs it so the next caller sees a clean window.
- `--drain-backlog` inside send-and-wait does the same thing inline.  Required
  on FIRST use of a bot per session.
- We take an offset BASELINE *after* the successful sendMessage by calling
  getUpdates with offset=-1 (returns just the last update).  Any update_id
  greater than that baseline is "new" — this sidesteps the small race where
  the reply could arrive between send and first poll.
- Bot API getUpdates is mutually exclusive with webhook mode.  If the bot is
  on a webhook, this harness will see zero updates forever.  Caller must
  confirm `getWebhookInfo` returns an empty url (or call deleteWebhook).
- Stdlib-only (urllib).  No requests dependency — keeps the harness trivial
  to run inside CI or a bare container.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request


def _post(url: str, body: dict, timeout: int = 10) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode())
        except Exception:
            payload = {}
        payload.setdefault("ok", False)
        payload.setdefault(
            "description", f"HTTP {e.code} {e.reason}"
        )
        return payload
    except Exception as e:
        return {"ok": False, "description": f"{type(e).__name__}: {e}"}


def _get(url: str, timeout: int = 40) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode())
        except Exception:
            payload = {}
        payload.setdefault("ok", False)
        payload.setdefault(
            "description", f"HTTP {e.code} {e.reason}"
        )
        return payload
    except Exception as e:
        return {"ok": False, "description": f"{type(e).__name__}: {e}"}


def drain_backlog(token: str) -> int:
    """Consume all pending updates; return the highest seen update_id.

    Subsequent getUpdates calls use offset=highest_id+1 so only new updates
    land in the caller's window.
    """
    url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=0"
    payload = _get(url, timeout=20)
    if not payload.get("ok"):
        return 0
    max_id = 0
    for u in payload.get("result", []):
        if u.get("update_id", 0) > max_id:
            max_id = u["update_id"]
    if max_id:
        # ACK by calling once more with offset=max_id+1
        _get(
            f"https://api.telegram.org/bot{token}/getUpdates?offset={max_id + 1}&timeout=0",
            timeout=10,
        )
    return max_id


def send_message(token: str, chat_id: str, text: str) -> dict:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    return _post(url, {"chat_id": chat_id, "text": text})


def baseline_update_id(token: str) -> int:
    """Return the update_id of the most recent known update, or 0 if none.

    offset=-1 tells the Bot API to return only the last update.  We use its
    update_id as the baseline — any update with a larger id is a new message
    that arrived AFTER our send, i.e. a candidate reply.
    """
    url = f"https://api.telegram.org/bot{token}/getUpdates?offset=-1&timeout=0"
    payload = _get(url, timeout=10)
    if payload.get("ok") and payload.get("result"):
        return int(payload["result"][-1].get("update_id") or 0)
    return 0


def wait_for_reply(
    token: str,
    chat_id: str,
    after_update_id: int,
    timeout_s: int,
    self_sent_text: str | None = None,
) -> dict:
    """Poll getUpdates until a bot message arrives in chat_id, or timeout.

    A message is considered the reply if:
      * chat.id matches chat_id
      * AND the message text is not exactly self_sent_text (avoid catching our
        own outbound send if Telegram echoes it into the same user's update
        stream — shouldn't happen for sendMessage-from-bot, but cheap belt).
      * AND the author is NOT the test user (chat_id in DMs == user id), i.e.
        the author is the bot or any non-tester.  Bot messages typically have
        `from.is_bot == true`; we treat either signal as "this is a reply".
    """
    deadline = time.time() + timeout_s
    offset = after_update_id + 1
    while time.time() < deadline:
        remaining = int(max(1, min(30, deadline - time.time())))
        url = (
            f"https://api.telegram.org/bot{token}/getUpdates"
            f"?offset={offset}&timeout={remaining}"
        )
        payload = _get(url, timeout=remaining + 10)
        if not payload.get("ok"):
            return {
                "reply_text": None,
                "error": payload.get("description", "getUpdates !ok"),
            }
        for u in payload.get("result", []):
            offset = u["update_id"] + 1
            msg = u.get("message") or u.get("edited_message") or {}
            if not msg:
                continue
            msg_chat_id = str((msg.get("chat") or {}).get("id", ""))
            if msg_chat_id != str(chat_id):
                continue
            frm = msg.get("from") or {}
            text = msg.get("text") or msg.get("caption") or ""
            # Skip our own outbound echo if it ever shows up.
            if self_sent_text is not None and text == self_sent_text and str(
                frm.get("id")
            ) == str(chat_id):
                continue
            # Skip messages from the tester themselves (DM chat_id == user id).
            is_bot_reply = bool(frm.get("is_bot"))
            if not is_bot_reply and str(frm.get("id")) == str(chat_id):
                continue
            return {
                "reply_text": text or "<no text>",
                "update_id": u["update_id"],
                "from": frm,
                "error": None,
            }
    return {"reply_text": None, "error": "timeout"}


def cmd_drain(args) -> int:
    n = drain_backlog(args.token)
    print(json.dumps({"drained_up_to": n}))
    return 0


def cmd_send_and_wait(args) -> int:
    if args.drain_backlog:
        drain_backlog(args.token)

    text = args.text or f"ping-22a-test-{uuid.uuid4().hex[:8]}"
    t0 = time.time()

    sent = send_message(args.token, args.chat_id, text)
    if not sent.get("ok"):
        print(
            json.dumps(
                {
                    "send_ok": False,
                    "sent_text": text,
                    "reply_text": None,
                    "reply_wall_s": None,
                    "error": sent.get("description", "sendMessage failed"),
                }
            )
        )
        return 2

    # Baseline the reply window AFTER the send — any update_id > this is a new
    # message that arrived after we sent.  The sendMessage call itself does
    # not produce a getUpdates entry for the outbound (bots don't receive
    # their own sends), so this is safe.
    last_update_id = baseline_update_id(args.token)

    rep = wait_for_reply(
        args.token,
        args.chat_id,
        last_update_id,
        args.timeout_s,
        self_sent_text=text,
    )
    reply_wall = round(time.time() - t0, 2) if rep.get("reply_text") else None
    out = {
        "send_ok": True,
        "sent_text": text,
        "reply_text": rep.get("reply_text"),
        "reply_wall_s": reply_wall,
        "error": rep.get("error"),
    }
    print(json.dumps(out))
    return 0 if rep.get("reply_text") else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="telegram_harness.py",
        description="Send a Telegram DM via Bot API and wait for the bot's reply.",
    )
    sp = ap.add_subparsers(dest="cmd", required=True)

    drain = sp.add_parser(
        "drain",
        help="Consume and ACK any backlog of pending updates.",
    )
    drain.add_argument("--token", required=True, help="Telegram bot token.")
    drain.set_defaults(func=cmd_drain)

    send = sp.add_parser(
        "send-and-wait",
        help="Send a DM and block until a bot reply arrives or timeout expires.",
    )
    send.add_argument("--token", required=True, help="Telegram bot token.")
    send.add_argument(
        "--chat-id",
        required=True,
        help="Target chat id (for DMs, equals the user id).",
    )
    send.add_argument(
        "--text",
        default=None,
        help="Message to send; defaults to a unique ping-22a-test-<uuid8>.",
    )
    send.add_argument(
        "--timeout-s",
        type=int,
        default=30,
        help="Seconds to wait for the bot's reply before timing out.",
    )
    send.add_argument(
        "--drain-backlog",
        action="store_true",
        help="Drain pending updates before sending (recommended on first use).",
    )
    send.add_argument(
        "--emit",
        choices=["json", "text"],
        default="json",
        help="Output format (only json currently implemented).",
    )
    send.set_defaults(func=cmd_send_and_wait)

    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

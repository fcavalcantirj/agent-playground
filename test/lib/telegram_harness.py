#!/usr/bin/env python3
"""DEPRECATED — renamed to agent_harness.py in Phase 22b (D-18).

The legacy `send-and-wait` and `drain` subcommands are REMOVED. They
used the Telegram Bot API update-polling endpoint, which is
single-consumer and mutually exclusive with a running gateway (see
memory/feedback_telegram_getupdates_is_single_consumer.md and
.planning/phases/22-channels-v0.2/22-SC03-DESIGN-FLAW.md). Spike-01a
(2026-04-18) further proved the Bot API cannot impersonate a user, so
the entire send-and-wait round-trip story was the design flaw, not a
fixable bug.

Replacement subcommands now live in `agent_harness.py`:

  Gate A — send-direct-and-read (primary, fully automatable)
    Invokes the recipe's direct_interface (docker_exec_cli OR
    http_chat_completions). No Telegram involved.

  Gate B — send-telegram-and-watch-events (secondary)
    Bot->self sendMessage with embedded UUID, then long-poll
    GET /v1/agents/:id/events?kinds=reply_sent.

This shim exists so out-of-tree callers that still reference
test/lib/telegram_harness.py (e.g. an old shell script in a developer's
home dir) get a graceful, actionable error instead of a Python import
crash. Callers using non-removed argv will be forwarded to
agent_harness.main(), but no current subcommand of agent_harness has the
same shape as the legacy harness — so in practice this shim only ever
prints the deprecation error.
"""
from __future__ import annotations

import sys

_REMOVED = {"send-and-wait", "drain"}


def _has_removed_cmd(argv: list[str]) -> bool:
    for tok in argv:
        if tok in _REMOVED:
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if _has_removed_cmd(argv):
        print(
            "ERROR: test/lib/telegram_harness.py `send-and-wait` and `drain` "
            "subcommands were REMOVED in Phase 22b per D-18.\n"
            "  - Use `python3 test/lib/agent_harness.py send-direct-and-read` "
            "for SC-03 Gate A (direct_interface).\n"
            "  - Use `python3 test/lib/agent_harness.py send-telegram-and-watch-events` "
            "for SC-03 Gate B (event-stream long-poll).\n"
            "See .planning/phases/22b-agent-event-stream/22b-CONTEXT.md §D-18.",
            file=sys.stderr,
        )
        return 3
    # No removed subcommand on argv — forward to agent_harness for any
    # future-compatible caller that may have appeared between commits.
    from agent_harness import main as agent_main  # noqa: WPS433
    return agent_main(argv)


if __name__ == "__main__":
    sys.exit(main())

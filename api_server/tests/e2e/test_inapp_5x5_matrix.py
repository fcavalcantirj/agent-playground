"""Phase 22c.3 Plan 15 — SC-03 5×1 e2e matrix gate.

Real Docker recipe containers + real Postgres + real OpenRouter HTTP +
the production dispatcher's ``_handle_row`` — proving the 3-way contract
adapter switch (openai_compat ×3, a2a_jsonrpc ×1, zeroclaw_native ×1)
ends-to-ends correctly per the Plan 15 must_haves.truths.

Per the executor context Route B:
    The e2e ``recipe_container_factory`` does its own docker run from the
    recipe YAML (the plan explicitly allows this in key_links line 60).
    The runner-side gap flagged in Plans 22c.3-10/11/12/13/14 stays as
    explicit follow-up work — documented in this plan's SUMMARY. The
    gate still passes IF the dispatcher reaches the recipe containers
    and gets responses; this proves the contract adapters are correct
    end-to-end without coupling the gate to a runner-side refactor.

The dispatcher is invoked via the production ``_handle_row`` directly —
NO respx, NO mocks. The bot HTTP client is a real ``httpx.AsyncClient``
which posts to the recipe container's port over the test docker bridge
network; the recipe container makes real OpenRouter calls upstream.

Output: ``e2e-report.json`` is emitted on every run with the canonical
SC-03 acceptance shape:

    {
      "passed": true,
      "recipes": [
        {"recipe":"hermes",   "contract":"openai_compat",   "status":"PASS",
         "latency_ms": ...,   "bot_response_excerpt":"..."},
        {"recipe":"nanobot",  "contract":"openai_compat",   ...},
        {"recipe":"openclaw", "contract":"openai_compat",   ...},
        {"recipe":"nullclaw", "contract":"a2a_jsonrpc",     ...},
        {"recipe":"zeroclaw", "contract":"zeroclaw_native", ...}
      ],
      "failures": []
    }

picoclaw is DEFERRED per user direction 2026-04-30 (RESEARCH §Revision
Notice Round 3) and is NOT in this matrix.
"""
from __future__ import annotations

import json
import pathlib
import time

import pytest

from . import _helpers as h


pytestmark = pytest.mark.api_integration


# ---------------------------------------------------------------------------
# 5-cell matrix — recipe / contract / port / endpoint per Plan 15 recipe_matrix.
# ---------------------------------------------------------------------------


RECIPE_MATRIX = [
    ("hermes",   "openai_compat",   8642,  "/v1/chat/completions"),
    ("nanobot",  "openai_compat",   8900,  "/v1/chat/completions"),
    ("openclaw", "openai_compat",   18789, "/v1/chat/completions"),
    ("nullclaw", "a2a_jsonrpc",     3000,  "/a2a"),
    ("zeroclaw", "zeroclaw_native", 42617, "/webhook"),
]


REPORT_PATH = pathlib.Path(__file__).parent / "e2e-report.json"


# ---------------------------------------------------------------------------
# Report accumulator — written on session teardown via emit_report.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def report_accumulator() -> dict:
    """Shared report dict across the 5 parametrized cells."""
    return {"passed": True, "recipes": [], "failures": []}


@pytest.fixture(scope="session", autouse=True)
def emit_report(report_accumulator):
    """On session teardown, write the canonical e2e-report.json artifact."""
    yield
    REPORT_PATH.write_text(json.dumps(report_accumulator, indent=2))


# ---------------------------------------------------------------------------
# 5×1 parametrized matrix — one cell per recipe.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "recipe,contract,port,endpoint",
    RECIPE_MATRIX,
    ids=[r[0] for r in RECIPE_MATRIX],
)
async def test_recipe_inapp_round_trip(
    recipe: str,
    contract: str,
    port: int,
    endpoint: str,
    db_pool,
    oauth_user_with_openrouter_key,
    recipe_container_factory,
    recipe_index,
    report_accumulator,
):
    """One cell of the SC-03 matrix.

    Steps:

      1. Spawn the real recipe container on the e2e bridge network with
         the recipe's persistent_argv_override + activation_env rendered.
      2. Seed users + agent_instances + agent_containers + inapp_messages
         rows mirroring what start_persistent + POST /messages would do.
      3. Drive the production dispatcher's _handle_row once via a real
         httpx.AsyncClient — this is the same code path the live
         dispatcher loop runs.
      4. Assert: status='done', non-empty bot_response, agent_events
         row with kind='inapp_outbound', latency under D-40 600s.
      5. Append PASS/FAIL to the report accumulator (e2e-report.json).
    """
    t0 = time.monotonic()
    cell_record: dict = {"recipe": recipe, "contract": contract}

    # Per-recipe model id format. openclaw's anthropic plugin only
    # recognizes "anthropic/claude-haiku-4-5" (dash, not dot) — verified
    # in the spike artifact. Other recipes accept the OpenRouter-canonical
    # "anthropic/claude-haiku-4.5" form.
    model = (
        "anthropic/claude-haiku-4-5"
        if recipe == "openclaw"
        else "anthropic/claude-haiku-4.5"
    )

    try:
        # --- Step 1: real recipe container ---
        spawned = recipe_container_factory(recipe, model=model)
        container_id = spawned["container_id"]
        container_ip = spawned["container_ip"]
        inapp_auth_token = spawned["inapp_auth_token"]
        # Sanity: the recipe declares the matrix contract + endpoint we expect.
        inapp = spawned["inapp"]
        assert inapp["port"] == port, (
            f"recipe {recipe} declares port={inapp['port']}, expected {port}"
        )
        assert inapp["contract"] == contract, (
            f"recipe {recipe} declares contract={inapp['contract']}, "
            f"expected {contract}"
        )
        assert inapp["endpoint"] == endpoint, (
            f"recipe {recipe} declares endpoint={inapp['endpoint']}, "
            f"expected {endpoint}"
        )

        # --- Step 2: seed DB rows ---
        seeded = await h.seed_inapp_message(
            db_pool,
            recipe_name=recipe,
            docker_container_id=container_id,
            inapp_auth_token=inapp_auth_token if inapp.get("auth_mode") == "bearer" else None,
            content="who are you in 1 short sentence?",
            model=spawned["model"],
        )

        # --- Step 3: drive dispatcher (real bot HTTP client, real OpenRouter) ---
        # The dispatcher will resolve container_ip via recipe_index.get_container_ip,
        # build the URL http://{ip}:{port}{endpoint}, and POST per the contract.
        # The recipe container will then call OpenRouter upstream.
        await h.drive_dispatcher_once(
            pool=db_pool,
            recipe_index=recipe_index,
            message_id=seeded.message_id,
            bot_timeout_seconds=600.0,  # D-40
        )

        # --- Step 4: assertions ---
        latency_ms = int((time.monotonic() - t0) * 1000)
        final = await h.assert_status_transitions(
            db_pool, seeded.message_id, expected_terminal="done",
        )
        bot_response = str(final["bot_response"] or "")
        assert len(bot_response) > 0, "empty bot_response"

        outbound = await h.fetch_outbound_event(db_pool, seeded.container_row_id)
        assert outbound is not None, (
            f"no inapp_outbound agent_events row for container_row_id="
            f"{seeded.container_row_id}"
        )
        assert outbound["payload"]["content"] == bot_response
        assert outbound["payload"]["source"] == "agent"

        # D-40 600s budget per cell
        assert latency_ms < 600_000, (
            f"latency {latency_ms}ms exceeds D-40 600s budget"
        )

        cell_record.update({
            "status": "PASS",
            "latency_ms": latency_ms,
            "bot_response_excerpt": bot_response[:200],
            "container_ip": container_ip,
            "endpoint": endpoint,
            "port": port,
        })
        report_accumulator["recipes"].append(cell_record)

    except Exception as exc:
        report_accumulator["passed"] = False
        cell_record.update({
            "status": "FAIL",
            "error": repr(exc),
            "latency_ms": int((time.monotonic() - t0) * 1000),
        })
        report_accumulator["recipes"].append(cell_record)
        report_accumulator["failures"].append({
            "recipe": recipe,
            "contract": contract,
            "error": repr(exc),
        })
        raise

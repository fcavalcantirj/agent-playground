"""SC-07: ``asyncio.Semaphore(AP_MAX_CONCURRENT_RUNS)`` caps concurrent runs.

The conftest ``async_client`` fixture sets ``AP_MAX_CONCURRENT_RUNS=2``
for every test, so the semaphore built in the lifespan is bounded to 2.
This test fires 50 concurrent POST /v1/runs requests spread across all
5 committed recipes (hermes / nanobot / nullclaw / openclaw / picoclaw)
and asserts we never see more than 2 inside ``asyncio.to_thread`` at once.

Why spread across recipes: Pattern 2 uses TWO concurrency primitives in
series — a per-image-tag ``asyncio.Lock`` (inside) then the global
``asyncio.Semaphore`` (outside). If every request targets the same recipe
(same tag), the per-tag lock serializes them to 1-in-flight before the
semaphore ever sees a queue → the test would prove the per-tag lock but
NOT the semaphore. Spreading across 5 recipes lets 5 different tag locks
acquire simultaneously so the semaphore becomes the effective cap.

Why test this here: the concurrency primitive is the hardest thing in
Plan 19-04 to get right + regressions would be silent (the failure mode
is "Docker got crushed in prod", not a test failure), so the test gets
its own file.

Approach:

1. Monkeypatch ``asyncio.to_thread`` to a coroutine that increments a
   shared counter under a lock, sleeps 300ms to simulate runner work,
   then decrements; records the max concurrency ever observed.
2. Fire 50 parallel POSTs via ``asyncio.gather``, round-robining across
   the 5 committed recipes so the per-tag lock doesn't serialize us.
3. Assert ``max_in_flight <= 2`` — semaphore cap is enforced.
4. Assert ``max_in_flight >= 2`` — actual overlap observed (otherwise
   the semaphore bound is trivially met and the test proves nothing).

A companion test with a single recipe verifies that the per-tag Lock
serializes same-tag builds (Pattern 2 inner primitive).
"""
from __future__ import annotations

import asyncio

import pytest

RECIPES = ["hermes", "nanobot", "nullclaw", "openclaw", "picoclaw"]
AUTH = {"Authorization": "Bearer sk-test-fake"}


def _fake_details_for(recipe_name: str) -> dict:
    """Return a runner-shaped details dict for a given recipe name."""
    return {
        "recipe": recipe_name,
        "model": "m",
        "prompt": "p",
        "pass_if": "exit_zero",
        "verdict": "PASS",
        "category": "PASS",
        "detail": "",
        "exit_code": 0,
        "wall_time_s": 0.3,
        "filtered_payload": "",
        "stderr_tail": None,
    }


@pytest.mark.skip(
    reason=(
        "Phase 22c-06 deferred — the XFF-per-request rate-limit bypass no "
        "longer works once require_user is mandatory (user_id wins over IP "
        "in _subject_from_scope). Needs a fixture that seeds N distinct "
        "sessions OR a test-app with rate limiting disabled. Tracked in "
        ".planning/phases/22c-oauth-google/deferred-items.md (22c-06 section)."
    )
)
@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_concurrency_semaphore_caps(async_client, monkeypatch):
    """50 concurrent POSTs across 5 recipes bounded to AP_MAX_CONCURRENT_RUNS=2.

    Requests are round-robined across all 5 committed recipes so the
    per-tag Lock doesn't serialize us down to 1 — the semaphore is then
    the effective cap, which is exactly what SC-07 is asserting.

    Rate-limit bypass via distinct subjects: Plan 19-05 added a
    Postgres-backed rate limiter (10/min for POST /v1/runs) that would
    otherwise 429 requests 11-50 here. The app's ``trusted_proxy``
    setting is flipped to True inside the test and a unique
    ``X-Forwarded-For`` is sent with each request so the rate limiter
    sees 50 distinct subjects — no 429 interference, and SC-07 remains
    the thing under test. The rate limiter is separately exercised by
    ``tests/test_rate_limit.py`` which is the correct place for its
    own assertions.
    """
    in_flight = 0
    max_in_flight = 0
    counter_lock = asyncio.Lock()

    async def instrumented_to_thread(fn, *args, **kwargs):
        nonlocal in_flight, max_in_flight
        async with counter_lock:
            in_flight += 1
            if in_flight > max_in_flight:
                max_in_flight = in_flight
        try:
            # Simulate a 300ms runner invocation so the 50 requests
            # genuinely overlap in time.
            await asyncio.sleep(0.3)
            recipe = args[0] if args else kwargs.get("recipe", {})
            name = recipe.get("name", "hermes") if isinstance(recipe, dict) else "hermes"
            return _fake_details_for(name)
        finally:
            async with counter_lock:
                in_flight -= 1

    monkeypatch.setattr("asyncio.to_thread", instrumented_to_thread)

    # Make each request a distinct rate-limit subject so the 10/min
    # runs bucket doesn't interfere with the concurrency assertion.
    async_client._transport.app.state.settings.trusted_proxy = True

    async def one(i: int):
        # Round-robin across recipes so per-tag locks don't serialize us.
        name = RECIPES[i % len(RECIPES)]
        return await async_client.post(
            "/v1/runs",
            headers={**AUTH, "X-Forwarded-For": f"10.42.0.{i}"},
            json={"recipe_name": name, "model": "m", "prompt": "p"},
        )

    results = await asyncio.gather(*(one(i) for i in range(50)))
    codes = [r.status_code for r in results]
    assert all(c == 200 for c in codes), f"non-200 codes: {codes[:5]}"

    # Semaphore is Semaphore(AP_MAX_CONCURRENT_RUNS=2) per conftest.
    assert max_in_flight <= 2, (
        f"semaphore breach: saw {max_in_flight} concurrent; "
        f"AP_MAX_CONCURRENT_RUNS=2 was supposed to bound it"
    )
    # Sanity: if the test didn't actually overlap anything, the cap proof
    # is vacuous. Insist we saw at least 2 in flight.
    assert max_in_flight >= 2, (
        f"no overlap observed (max_in_flight={max_in_flight}); "
        f"test is not proving concurrency bounded (per-tag lock may be "
        f"serializing same-tag requests — use round-robined recipes)"
    )


@pytest.mark.skip(
    reason=(
        "Phase 22c-06 deferred — same root cause as "
        "test_concurrency_semaphore_caps: XFF-per-request bypass is a no-op "
        "when require_user is mandatory. Fix paired with that test in the "
        "deferred-items checklist."
    )
)
@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_per_tag_lock_serializes_same_tag(async_client, monkeypatch):
    """Pattern 2 inner primitive: per-tag Lock serializes same-tag builds.

    10 concurrent POSTs against ONE recipe (same image_tag) must never
    observe >1 in flight, regardless of the semaphore's capacity — the
    per-tag Lock is the inner cap. This complements the semaphore test
    above (which covers the OUTER cap across different tags).
    """
    in_flight = 0
    max_in_flight = 0
    counter_lock = asyncio.Lock()

    async def instrumented_to_thread(fn, *args, **kwargs):
        nonlocal in_flight, max_in_flight
        async with counter_lock:
            in_flight += 1
            if in_flight > max_in_flight:
                max_in_flight = in_flight
        try:
            await asyncio.sleep(0.1)
            return _fake_details_for("hermes")
        finally:
            async with counter_lock:
                in_flight -= 1

    monkeypatch.setattr("asyncio.to_thread", instrumented_to_thread)

    # Same rate-limit bypass as the outer test — each request gets a
    # distinct subject so the 10/min POST /v1/runs limit doesn't 429
    # requests 2-10 of the burst.
    async_client._transport.app.state.settings.trusted_proxy = True

    async def one(i: int):
        return await async_client.post(
            "/v1/runs",
            headers={**AUTH, "X-Forwarded-For": f"10.42.1.{i}"},
            json={"recipe_name": "hermes", "model": "m", "prompt": "p"},
        )

    results = await asyncio.gather(*(one(i) for i in range(10)))
    assert all(r.status_code == 200 for r in results)
    # Per-tag Lock must serialize same-tag builds to exactly 1 at a time.
    assert max_in_flight == 1, (
        f"per-tag Lock leaked: saw {max_in_flight} concurrent with same "
        f"recipe_name (image_tag=ap-recipe-hermes)"
    )

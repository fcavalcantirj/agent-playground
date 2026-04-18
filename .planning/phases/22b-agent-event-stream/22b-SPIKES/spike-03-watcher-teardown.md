---
spike: 03
name: watcher-teardown-on-docker-rm-f
validates: "Given a watcher task running against a container, when that container is docker rm -f'd from outside, then the SDK iterator ends cleanly, the watcher coroutine returns, and no dangling asyncio tasks remain — without needing explicit Task.cancel()"
verdict: PASS
related: [spike-02]
tags: [docker-sdk, teardown, asyncio, lifecycle]
---

# Spike 03 — Graceful watcher teardown on docker rm -f

## How I ran it

Same harness as Spike 02. After 8s of observing backpressure, run `docker rm -f <container_id>` and await the watcher task with a 5s timeout.

## Results

```
[main] === SPIKE 03: docker rm -f while watcher running ===
[main] rm -f completed in 0.27s
[main] waiting ≤5s for watcher to return...
[watcher] WARN: drops=17300  (iterator still emitting residual stream chunks)
[watcher] WARN: drops=17400
[main] watcher exited cleanly: iterator_ended    ← within the 5s window
[main] dangling tasks after teardown: 0
```

### Interpretation

- **`docker rm -f` is ~270ms** — fast enough that the watcher sees a normal iterator completion rather than a connection-reset exception.
- **Iterator ends cleanly.** The docker-py SDK's `logs(follow=True)` generator returns normally when the underlying HTTP stream closes (container removed = stream closed). Our `asyncio.to_thread(next, it, None)` returns None; our watcher loop breaks; `finally` block runs; stats recorded; task transitions to done.
- **No `Task.cancel()` needed.** The natural iterator end is sufficient. This simplifies D-10 (task registry) — the `/stop` handler can signal the watcher but doesn't need to cancel the task; the watcher will self-exit as soon as the container is reaped.
- **Zero dangling tasks** after teardown — `asyncio.all_tasks()` returns empty (minus `current_task()`).

## Verdict: PASS

D-10 (`app.state.log_watchers` registry) + D-11 (lifespan re-attach / shutdown) can rely on iterator-end semantics. No aggressive cancellation needed.

## Planner notes

1. **`/stop` handler should NOT `Task.cancel()` the watcher first.** The right order: (1) signal watcher that stop is imminent (or just skip — it'll notice), (2) call `execute_persistent_stop` which does `docker stop` + `docker rm`, (3) the watcher's `docker logs -f` iterator ends cleanly a few hundred ms later, (4) `await watcher_task` with a short timeout completes. Cancellation is only the fallback.
2. **Lifespan shutdown should use `await` with timeout, not blanket cancel.** For N watcher tasks: `await asyncio.gather(*tasks, return_exceptions=True)` with per-task 2s timeout. Watchers that don't exit get cancelled as a fallback.
3. **Edge case not tested: `docker stop` (SIGTERM) without rm.** If a container receives SIGTERM and its process goes away but the container object lingers (in `exited` state), does the SDK iterator end or hang? The test used `docker rm -f` which removes the container entirely. **Planner: add a sub-probe — stop without rm, verify iterator behavior.** Likely fine because the stream closes on stdout/stderr close, not container removal. But test empirically.

## Reproducer

Same as Spike 02. The verdict section in the combined run covered both spikes' exit criteria simultaneously.

## Related spikes

- Spike 02 (backpressure) — same harness, shared reproducer
- D-10, D-11 in CONTEXT.md — the watcher-registry + lifespan-reattach design this validates

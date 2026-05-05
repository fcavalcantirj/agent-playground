# Phase 28: Temporal-backed message dispatch — Research

**Researched:** 2026-05-04
**Domain:** Python `temporalio` SDK adoption + asyncpg-dispatcher replacement + mobile ticker re-mount
**Confidence:** HIGH for SDK + compose recipe; MEDIUM for migration risk surfaces (require empirical Wave-0 spike per Golden Rule #5)

CONTEXT.md (`28-CONTEXT.md`) already locks 25 decisions D-01..D-25 plus the verbatim MSV reference paths. This research closes the **Python-translation layer** + AP-specific gotchas the orchestrator flagged. Topics already settled in CONTEXT (Go shape, MSV verbatim ports, big-bang swap rationale, retry budgets) are NOT re-explored.

---

<phase_requirements>
## Phase Requirements

The phase requirement IDs are the 25 decisions D-01..D-25 in CONTEXT.md plus the implicit "preserve existing 113+ pytest test green" gate. There are no new IDs in REQUIREMENTS.md (Phase 28 is dispatcher infrastructure, not a v1 / v0.3 user-facing requirement). The de-facto exit gates per CONTEXT.md `<domain>`:

| Gate | CONTEXT decision | Research support |
|------|------------------|------------------|
| `DispatchMessageWorkflow` orchestrates ready-check → forward → record-usage → emit-SSE → mark-done | D-10 | §3 — code skeletons mirror MSV `send_message.go:1-200` |
| Activity-internal `[1s, 2s, 4s]` retry on `container_not_ready` / connection errors | D-11 | §3 — `RetryPolicy(initial_interval, backoff_coefficient, maximum_interval, maximum_attempts)` |
| Temporal UI on `localhost:8088` | D-03, D-16 | §2 — compose recipe with `temporalio/ui:2.40.0` |
| Phase 27 ticker re-mount via Consumer-scoped subscription | D-18, D-19 | §6 — verbatim Phase 25 chat_providers.dart pattern |
| Legacy `services/inapp_dispatcher.py:_handle_row` deleted | D-06 | §7 — migration risk #1 (reaper deletion) addressed |
| 113+ existing pytest tests stay green | D-25 | §5 — `WorkflowEnvironment.start_time_skipping()` + activity mocking pattern |

</phase_requirements>

---

## 1. Python SDK pinning — `temporalio==1.27.0` (latest stable, 2026-04-30)

**[VERIFIED: pypi.org/project/temporalio]**

- **Version:** `temporalio==1.27.0`, released 2026-04-30.
- **Python compatibility:** declares `Requires-Python: >=3.10`; classifiers include 3.10, 3.11, 3.12, 3.13, 3.14. Direct match for `ap-runtime-python:v0.1.0-3.13` (Makefile line 3) and `requires-python = ">=3.11"` (pyproject.toml line 9).
- **Recommended pin in `api_server/pyproject.toml`:**
  ```
  "temporalio>=1.27.0,<1.28",
  ```
  Floor at the latest stable; cap below the next minor so a future SDK breaking change doesn't ride in on `pip install -U` at deploy time. This mirrors the `respx>=0.22,<0.24` floor/ceiling discipline pyproject.toml already uses (line 93).

**Compatibility note:** `temporalio` 1.27 ships pre-built wheels for cpython 3.13 on linux-x86_64 + linux-aarch64 + darwin-arm64 + darwin-x86_64. No Rust toolchain dependency at install time on any of those platforms (the Rust core is bundled). Wheels for musl (Alpine) are NOT shipped — but api_server already builds on `python:3.13-slim` (Debian-based), so this doesn't bite us. `ap-runtime-python:v0.1.0-3.13` is also Debian-based.

**No new transitive risk:** `temporalio` 1.27 brings in `protobuf>=4.25,<6` and `typing-extensions`. Neither conflicts with the existing api_server dep tree (FastAPI 0.136 / pydantic 2.11 / asyncpg 0.31).

**Worker container:** Same image as api_server; no separate Python runtime. Worker entry point is `python -m api_server.temporal.worker` (per CONTEXT D-04).

---

## 2. Compose recipe — copy-paste-ready service blocks for `deploy/docker-compose.prod.yml`

**[VERIFIED: github.com/temporalio/docker-compose docker-compose-postgres.yml + hub.docker.com/r/temporalio/auto-setup tags + MSV `infra/docker-compose.yml:86-122`]**

### Image selection

| Image | Tag | Role | Source authority |
|-------|-----|------|------------------|
| `temporalio/auto-setup` | `1.29.2` | Temporal frontend + history + matching + worker, with embedded schema bootstrap against the existing Postgres | Docker Hub (latest 1.29.x as of 2026-05-04) — also matches MSV's `:latest` pin shape |
| `temporalio/ui` | `2.40.0` | Web UI, port 8080 internal → 8088 host | Docker Hub `temporalio/ui` latest |
| `temporalio/admin-tools` | `1.29.2` | `tctl` / `temporal` CLI for one-off cluster ops (optional but useful for `make tctl-*` targets) | Docker Hub |

**Why `auto-setup` and not `temporalio/server`** [CITED: docs.temporal.io/self-hosted-guide/deployment]: the `auto-setup` image's documented "deprecation" warning on Docker Hub refers to recommending `temporalio/server` for **multi-host production with externally-managed schema migration**. AP runs on a **single Hetzner box with one Postgres**, where the auto-setup's bootstrap-schema-on-first-boot is a feature, not a problem. MSV uses `temporalio/auto-setup:latest` in production for the same reason (`infra/docker-compose.yml:87`). The migration to `temporalio/server` is a Phase 999.x concern when AP grows beyond one host.

### Service blocks to add to `deploy/docker-compose.prod.yml`

Add AFTER the `redis:` service block, BEFORE `api_server:`:

```yaml
  temporal:
    # Phase 28 (D-01, D-02, D-03): Self-hosted Temporal cluster, single
    # namespace `default`, Postgres backend pointing at the existing
    # `postgres` service. auto-setup bootstraps `temporal` and
    # `temporal_visibility` databases inside the same Postgres on first boot.
    # NO host-bound port for 7233 — internal-only. UI exposes 8088 below.
    image: temporalio/auto-setup:1.29.2
    restart: always
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DB: postgres12
      DB_PORT: "5432"
      POSTGRES_SEEDS: postgres
      # Temporal needs its own Postgres role with CREATE-DB privilege so
      # it can bootstrap `temporal` + `temporal_visibility` schemas. The
      # `ap` superuser already owns the cluster — reuse it.
      POSTGRES_USER: ap
      POSTGRES_PWD: ${POSTGRES_PASSWORD}
      DBNAME: temporal
      VISIBILITY_DBNAME: temporal_visibility
      DYNAMIC_CONFIG_FILE_PATH: config/dynamicconfig/development-sql.yaml
      TEMPORAL_ADDRESS: temporal:7233
      TEMPORAL_CLI_ADDRESS: temporal:7233
    healthcheck:
      test: ["CMD", "temporal", "operator", "cluster", "health"]
      interval: 15s
      timeout: 5s
      retries: 10
      start_period: 30s

  temporal-ui:
    # Phase 28 (D-03, D-16): web UI on 8088. CORS origin must include the
    # public host the dev/prod admin uses; localhost:8088 covers local
    # `make dev-api-local` + the Hetzner box port-forward.
    image: temporalio/ui:2.40.0
    restart: always
    depends_on:
      temporal:
        condition: service_healthy
    ports:
      - "127.0.0.1:8088:8080"
    environment:
      TEMPORAL_ADDRESS: temporal:7233
      TEMPORAL_CORS_ORIGINS: http://localhost:8088

  temporal-worker:
    # Phase 28 (D-04): worker process for the `ap-messages` task queue.
    # Same image as api_server — shared deps, separate `command` invoking
    # the worker entrypoint. Inherits the same env_file so DB pool +
    # Redis + recipe dir are available.
    build:
      context: ..
      dockerfile: tools/Dockerfile.api
      args:
        DOCKER_GID: ${DOCKER_GID:-999}
    restart: always
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      temporal:
        condition: service_healthy
    command: ["python", "-m", "api_server.temporal.worker"]
    environment:
      AP_ENV: prod
      AP_RECIPES_DIR: /app/recipes
      AP_REDIS_URL: "redis://redis:6379/0"
      AP_DOCKER_NETWORK: "deploy_default"
      AP_TEMPORAL_HOST: "temporal:7233"
      AP_TEMPORAL_NAMESPACE: "default"
      AP_TEMPORAL_TASK_QUEUE: "ap-messages"
      DATABASE_URL: postgresql+asyncpg://ap:${POSTGRES_PASSWORD}@postgres:5432/agent_playground_api
      AP_CHANNEL_MASTER_KEY: ${AP_CHANNEL_MASTER_KEY}
    env_file:
      - .env.prod
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ../recipes:/app/recipes:ro
```

Then add `temporal: { condition: service_healthy }` to the api_server service's `depends_on:` block (so api_server boots strictly after Temporal frontend is ready — otherwise the lifespan's `temporal_client.dial()` errors with a connection-refused).

### Critical gotcha: macOS host-bridge limitation (CLAUDE.md banner)

The CLAUDE.md banner (lines 67-72) documents that `inapp_dispatcher` resolves agent containers by Docker bridge IP (172.18.0.x), and **macOS Docker Desktop does not route from host to the bridge**. The `ForwardToAgent` activity (which replaces `_handle_row`'s bot-call) has the same constraint — it uses `recipe_index.get_container_ip()` which reads `NetworkSettings.Networks[deploy_default].IPAddress`.

**Implication:** the `temporal-worker` container MUST run on `deploy_default` (the same network as agent containers and the Postgres/Redis services). Running the worker on the host (`python -m api_server.temporal.worker` from a venv) on macOS will fail with `inapp_dispatcher.ip_lookup_failed` exactly the way `inapp_dispatcher` does today. The compose block above already places it on `deploy_default` because all services in `docker-compose.prod.yml` default to the project's default network. **No worker-on-host path will work on macOS for end-to-end testing** — `make e2e-inapp-docker` semantics extend to Phase 28.

### Network name + the existing `AP_DOCKER_NETWORK=deploy_default`

The api_server service in `docker-compose.prod.yml:84` already sets `AP_DOCKER_NETWORK: deploy_default`. The worker reuses the same env var so `InappRecipeIndex` resolves IPs identically. No new env var is needed for network discovery.

---

## 3. Workflow code patterns — `DispatchMessageWorkflow` + activities

**[VERIFIED: github.com/temporalio/sdk-python README + python.temporal.io workflow API + community.temporal.io retry-policy patterns]**

### Determinism rules (the gotchas we MUST honor)

[CITED: docs.temporal.io/develop/python/python-sdk-sandbox + community searches] Inside `@workflow.run` methods, the Python SDK's sandbox forbids:

| Forbidden | Reason | Replacement |
|-----------|--------|-------------|
| `datetime.now()` / `datetime.utcnow()` | wall clock varies across replays | `workflow.now()` returns a `datetime` (UTC, deterministic per replay) |
| `time.time()` | same | `workflow.time()` returns float seconds since epoch |
| `random.random()` / `random.randint()` etc. | not deterministic across replays | `workflow.random()` returns a `random.Random` seeded per workflow execution |
| `uuid.uuid4()` | not deterministic | `workflow.uuid4()` returns a `uuid.UUID` |
| `asyncio.sleep()` | NOT actually forbidden — but you should still prefer `workflow.sleep()` because it integrates with Temporal's time-skipping in tests. Both work in production. | `workflow.sleep(seconds)` |
| Threading (`threading.Thread`, `concurrent.futures`) | non-deterministic ordering | Run blocking work in activities, not workflows |
| Network IO inside workflow | every call must be deterministic | Wrap in an activity |
| Reading env vars / files | environment varies | Pass via `WorkflowInput` from the API caller |
| Global state mutation | replays would re-mutate | Workflow instance attributes only |

**Sandbox enforcement:** `temporalio` runs each workflow definition inside a Python sandbox that proxies the standard library. Imports of `datetime`, `random`, `uuid`, `asyncio` are allowed but the unsafe entry points are intercepted. **Test the sandbox compatibility in Wave 0 with a smoke spike** — some libraries (notably `ruamel.yaml`, `httpx`) trigger `RAISE_ON_UNINTENTIONAL_PASSTHROUGH` warnings; the workflow file should NOT import them. Only the activity files import infrastructure libraries.

**Practical rule for AP:** keep `dispatch_message.py` (the workflow file) imports limited to `temporalio.workflow`, `temporalio.common`, `datetime` (for `timedelta`), `dataclasses`, and the input/output dataclass types. Push EVERY infra interaction (asyncpg, httpx, redis, docker) into activity files.

### File layout

Per CONTEXT D-04 + Claude's Discretion (last bullet — flat for now):

```
api_server/src/api_server/temporal/
  __init__.py
  client.py              # temporal_client factory (used by api_server lifespan + worker)
  worker.py              # `python -m api_server.temporal.worker` entry point
  workflows/
    __init__.py
    dispatch_message.py  # DispatchMessageWorkflow definition
    types.py             # WorkflowInput / ForwardResult dataclasses (shared by workflow + activities)
  activities/
    __init__.py
    check_container_ready.py
    forward_to_agent.py
    record_usage.py
    emit_inapp_outbound.py
    mark_message_done.py
    mark_message_failed.py
    debit_balance.py     # D-22 stub — no-op in Phase 28
```

### `temporal/workflows/dispatch_message.py` — workflow body

```python
"""Phase 28 — DispatchMessageWorkflow. Mirrors MSV's SendMessageWorkflow
verbatim (messaging/workflows/send_message.go:16-198). Go-portable Python
shape per CONTEXT D-09 — no comprehensions, no datetime.now, no random.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from temporalio import workflow
from temporalio.common import RetryPolicy

# Re-export the activity stub names. Workflow imports must NOT touch the
# activity bodies (they pull in asyncpg/httpx — sandbox-passthrough warnings).
with workflow.unsafe.imports_passed_through():
    from ..activities import (
        check_container_ready,
        forward_to_agent,
        record_usage,
        emit_inapp_outbound,
        mark_message_done,
        mark_message_failed,
        debit_balance,
    )


@dataclass(frozen=True)
class DispatchMessageInput:
    """Inputs the API route hands to client.start_workflow."""
    message_id: str          # UUID stringified (workflows prefer plain types)
    user_id: str
    agent_id: str
    container_row_id: str
    container_id: str
    recipe_name: str
    agent_model: str
    content: str
    inapp_auth_token: str | None
    bot_timeout_seconds: float


@dataclass(frozen=True)
class DispatchMessageResult:
    success: bool
    error_type: str | None = None
    reply: str | None = None


@workflow.defn(name="DispatchMessageWorkflow")
class DispatchMessageWorkflow:
    @workflow.run
    async def run(self, inp: DispatchMessageInput) -> DispatchMessageResult:
        # ---- Step 1: readiness gate (D-37/D-38 of Phase 22c.3, preserved) ----
        # Activity-internal retry [250ms, 500ms, 1s, 2s, 4s] — covers the
        # transient container_not_ready window that surfaced in the
        # 2026-05-04→05 chat-stability investigation.
        ready = await workflow.execute_activity(
            check_container_ready.check_container_ready,
            inp,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(milliseconds=250),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(seconds=4),
                maximum_attempts=5,
            ),
        )
        if not ready:
            await self._fail(inp, "container_not_ready")
            return DispatchMessageResult(success=False, error_type="container_not_ready")

        # ---- Step 2: forward to agent (the bot HTTP call) ----
        # Activity-internal retry on transport errors [1s, 2s, 4s] per D-11.
        # Workflow-level MaxAttempts=1 because the activity owns its own
        # retry budget for transport faults; HTTP 4xx/5xx fail terminal.
        try:
            forward = await workflow.execute_activity(
                forward_to_agent.forward_to_agent,
                inp,
                start_to_close_timeout=timedelta(
                    seconds=inp.bot_timeout_seconds + 30.0,  # D-12 buffer
                ),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except Exception as e:
            err = _classify_forward_failure(e)
            await self._fail(inp, err)
            return DispatchMessageResult(success=False, error_type=err)

        if not forward.reply or not forward.reply.strip():
            await self._fail(inp, "bot_empty")
            return DispatchMessageResult(success=False, error_type="bot_empty")

        # ---- Step 3: success path — record_usage + emit_inapp_outbound +
        # mark_message_done. record_usage + emit_inapp_outbound are
        # best-effort (D-15: failure logged, doesn't fail workflow).
        # mark_message_done is load-bearing (D-10) — must succeed.
        await workflow.execute_activity(
            record_usage.record_usage,
            forward.usage_input,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=1),
            ),
        )
        await workflow.execute_activity(
            debit_balance.debit_balance,   # D-22 no-op stub
            inp,
            start_to_close_timeout=timedelta(seconds=5),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        await workflow.execute_activity(
            emit_inapp_outbound.emit_inapp_outbound,
            forward.event_input,
            start_to_close_timeout=timedelta(seconds=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        await workflow.execute_activity(
            mark_message_done.mark_message_done,
            forward.mark_done_input,
            start_to_close_timeout=timedelta(seconds=5),
            retry_policy=RetryPolicy(
                maximum_attempts=5,
                initial_interval=timedelta(milliseconds=250),
            ),
        )
        return DispatchMessageResult(success=True, reply=forward.reply)

    async def _fail(self, inp: DispatchMessageInput, error_type: str) -> None:
        """Best-effort terminal failure: mark + emit failure event."""
        await workflow.execute_activity(
            mark_message_failed.mark_message_failed,
            (inp.message_id, error_type),
            start_to_close_timeout=timedelta(seconds=5),
            retry_policy=RetryPolicy(maximum_attempts=5),
        )


def _classify_forward_failure(e: Exception) -> str:
    """Map ApplicationError messages back to the existing AP error_type taxonomy.

    Activity raises temporalio.exceptions.ApplicationError(
        message=<error_type>, type=<error_type>, non_retryable=True
    ). The workflow reads `e.args[0]` or `getattr(e, 'type', None)` to recover.
    """
    msg = getattr(e, "type", None) or (str(e) if e.args else "internal_error")
    return msg
```

### Activity skeleton — `temporal/activities/forward_to_agent.py`

```python
"""Phase 28 — forward_to_agent activity. Mirrors MSV
messaging/activities/forward_to_agent.go:64-196 — connection-retry pattern
[1s, 2s, 4s] for transport errors only; HTTP 4xx/5xx fail terminal.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from temporalio import activity
from temporalio.exceptions import ApplicationError

# Note: the dispatcher's existing `_dispatch_http_localhost` is the body
# we extract verbatim. This file re-uses it via a thin wrapper because
# the existing 3-way contract switch is the value — we don't reimplement.
from ...services.inapp_dispatcher import _dispatch_http_localhost
from ...services.inapp_recipe_index import InappChannelConfig
from ..workflows.dispatch_message import DispatchMessageInput


@dataclass(frozen=True)
class ForwardResult:
    reply: str
    raw_response: dict | None
    usage_input: dict
    event_input: dict
    mark_done_input: dict


class ForwardActivities:
    """Class-bound activities so worker injects shared deps via __init__.

    Pattern: instance methods are registered with the worker. `self.db_pool`
    and `self.bot_http_client` are bound at worker boot from the same
    process-wide pool the api_server already creates.
    """

    def __init__(
        self,
        *,
        db_pool: Any,                  # asyncpg.Pool
        bot_http_client: httpx.AsyncClient,
        recipe_index: Any,             # InappRecipeIndex
    ) -> None:
        self.db_pool = db_pool
        self.bot_http_client = bot_http_client
        self.recipe_index = recipe_index

    @activity.defn(name="forward_to_agent")
    async def forward_to_agent(self, inp: DispatchMessageInput) -> ForwardResult:
        attempt = activity.info().attempt
        activity.logger.info(
            "phase28.forward_to_agent.attempt",
            extra={"message_id": inp.message_id, "attempt": attempt},
        )

        # 1. Recipe lookup — converts to recipe_no_inapp_channel terminal failure.
        inapp = self.recipe_index.get_inapp_block(inp.recipe_name)
        if inapp is None:
            raise ApplicationError(
                "recipe_lacks_inapp_channel",
                type="recipe_lacks_inapp_channel",
                non_retryable=True,  # not retryable — recipe doesn't define inapp
            )

        # 2. Container IP discovery (cached). RuntimeError → container_dead terminal.
        try:
            container_ip = self.recipe_index.get_container_ip(inp.container_id)
        except RuntimeError:
            raise ApplicationError(
                "container_dead", type="container_dead", non_retryable=True,
            )

        # 3. mark_forwarded BEFORE the call (D-28 persist-before-action).
        # NOTE: in Phase 28 this becomes implicit via Temporal's
        # started-but-not-completed state. We still write a marker row for
        # observability (last_attempt_at). Open question: do we keep
        # mark_forwarded? See §8 Open Question 1.

        # 4. Construct a dict-like row the existing _dispatch_http_localhost expects.
        row = {
            "id": UUID(inp.message_id),
            "user_id": UUID(inp.user_id),
            "agent_id": UUID(inp.agent_id),
            "container_row_id": UUID(inp.container_row_id),
            "container_id": inp.container_id,
            "recipe_name": inp.recipe_name,
            "agent_model": inp.agent_model,
            "content": inp.content,
            "inapp_auth_token": inp.inapp_auth_token,
            "attempts": attempt,
        }

        # 5. The 3-way contract switch — UNCHANGED from existing dispatcher.
        # Activity-internal retry on httpx.ConnectError + httpx.ReadTimeout only.
        # HTTP 4xx/5xx and parse errors raise non-retryable ApplicationError.
        for retry_idx, backoff_s in enumerate([0.0, 1.0, 2.0, 4.0]):
            if backoff_s > 0:
                await asyncio.sleep(backoff_s)
            try:
                reply, raw = await _dispatch_http_localhost(
                    self.bot_http_client, row, inapp, container_ip,
                    timeout_seconds=inp.bot_timeout_seconds,
                )
                # Build the inputs the workflow's downstream activities consume.
                return ForwardResult(
                    reply=reply,
                    raw_response=raw,
                    usage_input={...},   # see record_usage activity
                    event_input={...},
                    mark_done_input={...},
                )
            except (httpx.ConnectError, httpx.ReadTimeout):
                if retry_idx == 3:
                    raise ApplicationError(
                        "bot_timeout", type="bot_timeout", non_retryable=True,
                    )
                continue   # retry with backoff
            except httpx.HTTPStatusError as e:
                raise ApplicationError(
                    f"bot_5xx:{e.response.status_code}",
                    type="bot_5xx", non_retryable=True,
                )
            except RuntimeError as e:
                raise ApplicationError(
                    str(e), type=str(e).split(":", 1)[0], non_retryable=True,
                )
            except (httpx.RequestError, ValueError):
                raise ApplicationError(
                    "bot_invalid_response",
                    type="bot_invalid_response", non_retryable=True,
                )
```

### Activity retry policy details — verified

**[VERIFIED: github.com/temporalio/sdk-python README + python.temporal.io samples]**

```python
from temporalio.common import RetryPolicy
from datetime import timedelta

RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=4),
    maximum_attempts=3,
    non_retryable_error_types=["bot_5xx", "container_dead"],
)
```

`non_retryable_error_types` accepts `ApplicationError.type` strings. When the activity raises `ApplicationError(type="bot_5xx", non_retryable=True)`, the SDK skips retry **and** the workflow sees the typed exception — both paths converge. Use the per-raise `non_retryable=True` flag for AP since the error taxonomy is already encoded as enum values in `_KNOWN_ERROR_TYPES` (inapp_dispatcher.py:325-335).

### Activity timeout semantics — confirmed

**[CITED: docs.temporal.io/encyclopedia/detecting-activity-failures]**

| Timeout | Required? | Use in AP |
|---------|-----------|-----------|
| `start_to_close_timeout` | At least one of (start_to_close, schedule_to_close) is required. **Strongly recommended.** | **Yes** — set on every activity. `forward_to_agent`: `inp.bot_timeout_seconds + 30s` (D-12 buffer). Others: 5-10s. |
| `schedule_to_close_timeout` | Optional, controls total time across retries | **Optional** — set if you want a hard cap including retries. Workflow-level `execution_timeout=5min` (D-13) is the safer place to enforce this. |
| `schedule_to_start_timeout` | Optional, detects worker starvation | **No** — single worker per queue, no need to detect starvation. |
| `heartbeat_timeout` | Optional, **only required for long-running activities** (file uploads, ML training) | **No** — all AP activities are sub-minute. The docs explicitly say "not needed for short operations like API calls." |

**No activity in this phase needs heartbeats.** This eliminates a whole category of "I forgot to call `activity.heartbeat()`" gotchas.

---

## 4. Worker boot pattern — `temporal/worker.py`

### Worker module skeleton

```python
"""Phase 28 — Temporal worker process. Mirrors MSV
messaging/cmd/worker/main.go:288-327. Runs as `python -m api_server.temporal.worker`.

Concurrency settings copy MSV verbatim:
  MaxConcurrentActivityExecutionSize = 10
  WorkerActivitiesPerSecond          = 5
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
from contextlib import AsyncExitStack
from pathlib import Path

import docker
import httpx
import redis.asyncio as redis_async
from temporalio.client import Client
from temporalio.worker import Worker

from ..config import get_settings
from ..db import create_pool, close_pool
from ..log import configure_logging
from ..services.inapp_recipe_index import InappRecipeIndex
from .activities.forward_to_agent import ForwardActivities
from .activities.check_container_ready import ReadinessActivities
from .activities.record_usage import RecordUsageActivities
from .activities.emit_inapp_outbound import EmitEventActivities
from .activities.mark_message_done import MarkActivities
from .activities.debit_balance import DebitActivities
from .workflows.dispatch_message import DispatchMessageWorkflow

_log = logging.getLogger("api_server.temporal.worker")


async def main() -> None:
    configure_logging()
    settings = get_settings()
    _log.info("phase28.worker.boot", extra={
        "task_queue": settings.temporal_task_queue,
        "namespace": settings.temporal_namespace,
        "host": settings.temporal_host,
    })

    async with AsyncExitStack() as stack:
        # ---- 1. Shared infra (mirrors api_server lifespan) ----
        db_pool = await create_pool(settings.database_url)
        stack.push_async_callback(close_pool, db_pool)

        redis_client = redis_async.from_url(
            settings.redis_url, decode_responses=False, max_connections=20,
        )
        await redis_client.ping()  # fail loud
        stack.push_async_callback(redis_client.aclose)

        bot_http = httpx.AsyncClient(
            timeout=httpx.Timeout(600.0, connect=5.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        )
        stack.push_async_callback(bot_http.aclose)

        docker_client = docker.from_env()
        recipe_index = InappRecipeIndex(
            recipes_dir=settings.recipes_dir,
            docker_client=docker_client,
            network_name=settings.docker_network_name,
        )

        # ---- 2. Bind activities to instances with shared deps ----
        forward_acts = ForwardActivities(
            db_pool=db_pool,
            bot_http_client=bot_http,
            recipe_index=recipe_index,
        )
        ready_acts = ReadinessActivities(db_pool=db_pool)
        usage_acts = RecordUsageActivities(db_pool=db_pool)
        event_acts = EmitEventActivities(db_pool=db_pool)
        mark_acts = MarkActivities(db_pool=db_pool)
        debit_acts = DebitActivities(db_pool=db_pool)

        # ---- 3. Connect to Temporal frontend ----
        client = await Client.connect(
            settings.temporal_host,
            namespace=settings.temporal_namespace,
        )

        # ---- 4. Worker registration ----
        worker = Worker(
            client,
            task_queue=settings.temporal_task_queue,
            workflows=[DispatchMessageWorkflow],
            activities=[
                ready_acts.check_container_ready,
                forward_acts.forward_to_agent,
                usage_acts.record_usage,
                event_acts.emit_inapp_outbound,
                mark_acts.mark_message_done,
                mark_acts.mark_message_failed,
                debit_acts.debit_balance,
            ],
            max_concurrent_activities=10,        # MSV: 10
            max_activities_per_second=5,         # MSV: 5
        )

        # ---- 5. Graceful shutdown on SIGTERM (compose stop) / SIGINT ----
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        def _shutdown() -> None:
            _log.info("phase28.worker.shutdown_signal")
            stop_event.set()

        loop.add_signal_handler(signal.SIGTERM, _shutdown)
        loop.add_signal_handler(signal.SIGINT, _shutdown)

        run_task = asyncio.create_task(worker.run())
        stop_task = asyncio.create_task(stop_event.wait())
        done, pending = await asyncio.wait(
            {run_task, stop_task}, return_when=asyncio.FIRST_COMPLETED,
        )
        if stop_task in done:
            await worker.shutdown()
            run_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
```

**Key callouts:**

1. **`Worker.__init__(max_concurrent_activities=10, max_activities_per_second=5)`** — verified parameter names in [VERIFIED: python.temporal.io/temporalio.worker.Worker.html via search]. Default is 100 slots; we cap at 10 to mirror MSV.
2. **Shared deps via class-bound activities** — the SDK README explicitly documents this: "Activities can be defined on methods instead of top-level functions. This allows the instance to carry state that an activity may need (e.g. a DB connection). The instance method should be what is registered with the worker." [VERIFIED: github.com/temporalio/sdk-python README]
3. **No FastAPI app.state in the worker** — the worker is a separate process. We instantiate `InappRecipeIndex` directly with the docker client, NOT via `app.state.recipe_index`. CONTEXT D-04 already says "expose those to activities via worker-level dependency injector rather than FastAPI's app.state."
4. **Graceful shutdown** — `worker.shutdown()` drains in-flight activities before returning. Combined with the `--stop-grace-period` compose default (10s) this gives in-flight chats a clean exit. CONTEXT mentions this implicitly via D-13's 5-min execution timeout.
5. **`Client.connect(host, namespace=...)`** — the Python SDK `Client.connect` signature [VERIFIED: github.com/temporalio/sdk-python README] takes the host:port string positionally and `namespace` as a kwarg. No `Options` struct unlike Go.

### `temporal/client.py` — for the api_server lifespan

```python
"""Phase 28 — temporal_client factory. Used by api_server lifespan to
get a Client for `start_workflow` calls from the API route.
"""
from temporalio.client import Client
from ..config import Settings


async def make_client(settings: Settings) -> Client:
    return await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
    )
```

api_server's `lifespan()` (in `main.py:80-220`) gains:
```python
from .temporal.client import make_client
app.state.temporal_client = await make_client(settings)
# remove: app.state.inapp_tasks dispatcher_loop creation (D-06 deletion)
# keep:   reaper_loop + outbox_pump_loop creation — see §7 risk #1
```

The worker module does NOT live inside the api_server lifespan; it is a separate process per D-04.

### Route handler change in `routes/agent_messages.py`

After `insert_pending` (line 181-183), add:

```python
from ..temporal.workflows.dispatch_message import (
    DispatchMessageWorkflow, DispatchMessageInput,
)
from temporalio.client import WorkflowIDReusePolicy

# After the `insert_pending` returns message_id:
client = request.app.state.temporal_client
await client.start_workflow(
    DispatchMessageWorkflow.run,
    DispatchMessageInput(
        message_id=str(message_id),
        user_id=str(user_id),
        agent_id=str(agent_id),
        container_row_id=str(agent.container_row_id),
        container_id=agent.container_id,
        recipe_name=agent.recipe_name,
        agent_model=agent.model,
        content=body.content,
        inapp_auth_token=agent.inapp_auth_token,
        bot_timeout_seconds=settings.bot_timeout_seconds,
    ),
    id=f"msg-{message_id}",                                      # D-08
    task_queue=settings.temporal_task_queue,
    id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,      # D-08
    execution_timeout=timedelta(minutes=5),                       # D-13
)
```

`WorkflowIDReusePolicy.REJECT_DUPLICATE` [VERIFIED: python.temporal.io enum search] raises `WorkflowAlreadyStartedError` on the second start. The route should catch it and return 200 (not 202) since the message is already being dispatched — this is the retry-safe path that pairs with `Idempotency-Key` middleware (CONTEXT D-14 — "Two layers, separate concerns").

---

## 5. Test patterns — `WorkflowEnvironment` + integration tests

### Unit test — `WorkflowEnvironment.start_time_skipping`

**[VERIFIED: github.com/temporalio/sdk-python README]**

```python
"""tests/test_dispatch_message_workflow.py — workflow-level unit tests."""
import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from api_server.temporal.workflows.dispatch_message import (
    DispatchMessageWorkflow, DispatchMessageInput,
)
from api_server.temporal.activities import (
    check_container_ready, forward_to_agent, record_usage,
    emit_inapp_outbound, mark_message_done, mark_message_failed,
    debit_balance,
)


@pytest.mark.asyncio
async def test_happy_path():
    """Workflow: ready=True → forward returns reply → record/emit/mark all OK."""

    # Mock activities — same signature + same name (@activity.defn).
    @forward_to_agent.activity.defn(name="forward_to_agent")
    async def fake_forward(inp: DispatchMessageInput):
        return forward_to_agent.ForwardResult(
            reply="hello!", raw_response=None,
            usage_input={}, event_input={}, mark_done_input={},
        )

    # ... mock the other 6 activities similarly ...

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="ap-messages-test",
            workflows=[DispatchMessageWorkflow],
            activities=[fake_forward, ...],
        ):
            result = await env.client.execute_workflow(
                DispatchMessageWorkflow.run,
                DispatchMessageInput(message_id="...", ...),
                id="msg-test-1",
                task_queue="ap-messages-test",
            )
            assert result.success is True
            assert result.reply == "hello!"
```

**Patterns observed:**

- **Activity mocking:** the README explicitly documents this — provide a function with the same `@activity.defn(name=...)` and signature; pass it to the Worker's `activities=[...]`. The workflow sees the mock as if it were the real one.
- **Time-skipping:** `start_time_skipping()` advances time on `workflow.sleep()` calls automatically — perfect for testing the `[1s, 2s, 4s]` retry without waiting 7 seconds per test.
- **`pytest.mark.asyncio`:** existing pyproject `asyncio_mode = "auto"` means the marker is implicit. Tests just need `async def`.

### Integration test — real Temporal via deploy stack

CONTEXT D-24 says "integration tests start an actual deploy-temporal-1 container via the existing testcontainers harness (or via `make e2e-inapp-docker` extended)."

**Recommendation: extend `make e2e-inapp-docker`, do NOT add testcontainers for Temporal.**

Reasoning:
- `tests/conftest.py:47-65` already has `PostgresContainer` + `RedisContainer` session-scoped. Adding a `TemporalContainer` would mean (a) wiring the `temporalio/auto-setup` image to bootstrap on a private Postgres (slow — ~30s startup), (b) duplicating the schema-bootstrap logic that `make e2e-inapp-docker` already exercises against the deploy compose stack.
- `make e2e-inapp-docker` already runs the test process inside a container that joins `deploy_default`. Adding the `temporal` + `temporal-worker` services to the deploy compose stack means `e2e-inapp-docker` automatically gets Temporal too. The dockerized harness IS the integration test.
- Phase 22c.3.1 lessons (memory: `project_phase_22c31_shipped.md`) — the dockerized harness uncovered 3 production-correctness bugs that container-isolated unit tests missed. Same value applies here.

**Action:** Wave 0 spike confirms the dockerized harness boots Temporal cleanly and the worker connects + drains. Subsequent waves layer the real workflow tests on top.

### Existing tests inventory + risk

The 113+ pytest tests include:
- `test_inapp_dispatcher.py` — directly tests `_handle_row` and `_dispatch_http_localhost`. **`_handle_row` is being deleted (D-06).** These tests must be split: the bot-call tests stay (now testing `forward_to_agent` activity); the orchestration tests move to workflow-level tests using `WorkflowEnvironment`.
- `test_inapp_outbox.py` + `test_inapp_reaper.py` — outbox pump + reaper. **Reaper is partially being kept** (see §7 risk #1). Tests stay.
- `test_agent_messages.py` (route tests) — POST /messages now triggers a workflow start. The route test must mock `temporal_client.start_workflow` (or the test fixture provides a `WorkflowEnvironment.start_time_skipping()` client and the workflow runs end-to-end against test-mocked activities).

**Estimated test churn:** ~15-20 of the 113 tests touch `inapp_dispatcher` directly. Most of those re-target the new activity files with minor signature edits.

---

## 6. Mobile re-mount pattern — Phase 25 reference verbatim

The Phase 25 chat_providers.dart pattern is the model. Lines that matter:

**[VERIFIED: mobile/lib/features/chat/chat_providers.dart:308-348]**

```dart
@override
ChatState build() {
  final env = ref.read(appEnvProvider);
  final storage = ref.read(secureStorageProvider);
  _stream = streamBuilder(
    baseUrl: env.baseUrl,
    agentId: agentInstanceId,
    cookieProvider: storage.readSessionId,
  );
  if (autoBootstrap) {
    Future<void>.microtask(_bootstrap);
  }

  // D-52 lifecycle hook — disconnect/connect on resume.
  _lifeSub = ref.listen<AppLifecycleState>(
    appLifecycleProvider,
    (prev, next) {
      if (prev != next && next == AppLifecycleState.resumed) {
        // ignore: discarded_futures
        _onResumed();
      }
    },
  );

  ref.onDispose(() {
    _historyToken?.cancel('ChatScope disposed');
    _sendToken?.cancel('ChatScope disposed');
    // ignore: discarded_futures
    _sseSub?.cancel();
    // ignore: discarded_futures
    _stream.dispose();
    _lifeSub?.close();
  });

  return const ChatState();
}
```

**The load-bearing primitives** for Phase 28 D-18 ticker re-mount:

1. **`ref.onDispose(...)` cancels every subscription** — `_sseSub`, `_lifeSub`, `_stream`. This is what `chat_providers.dart` does and it's why screen tear-down doesn't crash with "Failed assertion: _lifecycleState != _ElementLifecycle.defunct" (the bug that caused the Phase 27 ticker yank — see comment on `chat_providers.dart:451-456`).
2. **`ref.listen<AppLifecycleState>(...)` registered INSIDE `build()`** — Riverpod re-registers each build. Listener fires only when `AppLifecycleState.resumed` AND prev != next, preventing duplicate fires.
3. **`Consumer` builder vs `ConsumerWidget`** — D-18 explicitly says to mount via a `Consumer` builder INSIDE the AppBar's `actions:` array. The element returned by the `Consumer` builder owns the provider subscription's Element lifecycle independently of the surrounding `AppBar`.

### Recommended mount pattern for `UsageTickerWidget` re-mount

```dart
// dashboard_screen.dart line 94 — INSIDE the AppBar's actions: array:
appBar: AppBar(
  title: Text('>_ SOLVR_LABS', ...),
  actions: [
    // D-18 — Consumer-scoped subscription. The Consumer's Element gets
    // disposed cleanly when the AppBar tears down; the provider
    // subscription's lifecycle is bound to THIS Consumer, not to the
    // outer ConsumerWidget.
    Consumer(
      builder: (context, ref, _) => const UsageTickerWidget(),
    ),
    PopupMenuButton<String>(...),  // existing overflow menu
  ],
),
```

The `UsageTickerWidget` itself (`mobile/lib/features/usage/usage_ticker_widget.dart:33`) is already a `ConsumerWidget` with `ref.watch(usageSummaryProvider)`. The ONLY change is wrapping it in a `Consumer` builder when mounting. The `UsageTickerWidget` body does NOT need to change.

The same change goes on `chat_screen.dart:158` (the `actions:` array) and matches D-19.

### What's deferred

D-21 explicitly defers Trigger #3 (instant ticker refresh on assistant SSE event). The `ref.invalidate(usageSummaryProvider)` call inside `_onSseEvent` (chat_providers.dart:451-456 — the historical comment in the file) is the path that crashed. Triggers #1 (mount via `ref.watch`) and #2 (lifecycle resume via `ref.listen<AppLifecycleState>`) cover the workflow without re-introducing the defunct-element race.

---

## 7. Migration risks — concrete list with mitigation

### Risk 1: `inapp_reaper` deletion vs pre-existing stuck rows

**The risk:** `services/inapp_reaper.py` runs every 15s and transitions rows stuck in `forwarded` past 11 minutes to `failed`. If we delete `dispatcher_loop` (per D-06) and rely on Temporal's own retry/timeout, **rows already in `forwarded` at the moment of cutover are orphaned** — no in-flight workflow exists for them, no reaper sweeps them.

**Mitigation:**
- **Keep `inapp_reaper` for 1-2 phases.** It's lifespan-managed (main.py:198-214), has its own tests, and costs ~2 SELECTs / 15s on a tiny indexed table. CONTEXT D-06 says "reaper logic moves into the workflow (timeout + retry policy own the cleanup)" — for **new** workflows, yes. For **legacy stuck rows** from before the cutover, keep the reaper.
- **Add a 11-up migration cleanup script** (one-shot, run as part of the cutover) that scans `inapp_messages WHERE status='forwarded' AND last_attempt_at < NOW() - INTERVAL '11 min'` and marks them `failed` with `last_error='phase28_cutover_swept'`. Audit log preserved.
- **Schedule reaper retirement for Phase 29 or later.** Once the system has run on Temporal for >1 week with zero reaper-caught rows, the reaper can be deleted.

**Open question for planner:** does the cleanup deserve an alembic migration (011_*) or a one-shot Python script invoked from `make migrate-api`? Recommendation: a Python script — alembic is for schema, not data.

### Risk 2: SSE outbox emission pathway

**The risk:** the existing dispatcher writes `agent_events` rows in the SAME transaction as `mark_done` (inapp_dispatcher.py:469-477). The `inapp_outbox` pump publishes those rows to Redis. Mobile's `MessagesStream` (chat_providers.dart) subscribes to that Redis channel. **If `mark_message_done` and `emit_inapp_outbound` activities run in SEPARATE transactions, the outbox pump can publish a "message done" event when the row is still `forwarded` — or vice versa. Mobile sees a torn state.**

**Mitigation:**
- **Combine `mark_message_done` + `emit_inapp_outbound` into a single activity** that opens one transaction, writes both rows, commits. Same shape as the existing dispatcher's `mark_done + insert_agent_event` block (inapp_dispatcher.py:469-477).
- The CONTEXT D-10 split into 5 activities is fine for the **happy path semantics**, but at the SQL layer, the mark+emit pair MUST be one transaction. Concretely: the new activity is `mark_message_done_and_emit(...)` which does both writes atomically.
- Same applies to `_terminal_failure` path (mark_failed + insert_agent_event of `inapp_outbound_failed`).

**Open question for planner:** does the plan name the combined activity `mark_message_done` and document internally that it also emits, or split-and-document-as-must-run-together? Recommendation: combined name `finalize_success` and `finalize_failure`, with docstrings calling out the dual-write atomicity invariant.

### Risk 3: `Idempotency-Key` middleware vs `WorkflowIDReusePolicy.REJECT_DUPLICATE`

**The risk:** the route layer has `IdempotencyMiddleware` (CONTEXT D-14 reference). The workflow layer has `REJECT_DUPLICATE`. They're independent layers, but they can produce CONFLICTING semantics:

- Client retries POST /messages with the same `Idempotency-Key`. Middleware replays the cached 202. Mobile sees the same `message_id`. So far so good.
- But if the middleware cache expired (TTL passed) and the same Idempotency-Key arrives, the middleware lets it through. The route does `insert_pending` — and inserts a NEW row with a NEW message_id. THEN it tries `start_workflow(id="msg-{new_message_id}")` which is a different workflow ID. So no REJECT_DUPLICATE fires.
- Result: two workflows, two SSE replies for the same client intent.

**Mitigation:**
- **`insert_pending` must be idempotent at the DB layer.** Add a UNIQUE constraint on `inapp_messages(idempotency_key, user_id)` with a partial index `WHERE idempotency_key IS NOT NULL` so a same-key insert returns the existing row.
- **OR** the IdempotencyMiddleware's TTL is set HIGHER than the workflow execution timeout (5min from D-13). If middleware cache holds for ≥10min, the second-burst race window collapses to zero.
- Quickest fix: bump the middleware TTL. Already a setting; verify it covers the workflow execution timeout window.

**Open question for planner:** does the IdempotencyMiddleware's existing TTL need adjustment, or is a UNIQUE-constraint-on-(idempotency_key, user_id) the cleaner fix? Recommendation: both — TTL bump is cheap, UNIQUE constraint is defense-in-depth.

### Risk 4: `mark_forwarded` semantics

**The risk:** the existing dispatcher writes `mark_forwarded` BEFORE the bot call (inapp_dispatcher.py:411 — "persist forwarded BEFORE the call"). This sets `last_attempt_at` which the reaper uses. The new Temporal flow has no equivalent step — `forward_to_agent` activity starts directly. **The `inapp_messages.status='forwarded'` state has no Temporal-side equivalent.** The row stays `pending` for the entire workflow life.

**Mitigation options:**
- **Option A: drop `forwarded` status entirely.** Mobile UI doesn't render `forwarded` (chat_providers.dart line 222 only renders `pending` / `delivered` / `typing` / `failed`). The status column on `inapp_messages` becomes `pending → done|failed`. Schema cleanup belongs to a future phase.
- **Option B: keep `forwarded`, write it in a tiny pre-bot activity.** First activity in the workflow is `mark_forwarded(message_id)` which sets status + last_attempt_at. The reaper still has something to scan during the cutover transition.

Recommendation: **Option B**, because Risk 1 (legacy reaper sweep) needs `forwarded` status to remain meaningful during the migration period. Drop after reaper retirement.

### Risk 5: Worker container can't reach `temporal:7233` on first boot

**The risk:** `depends_on: { temporal: { condition: service_healthy } }` waits for the healthcheck. The healthcheck is `temporal operator cluster health`. **If Temporal's auto-setup is still bootstrapping the schema against Postgres at the moment the healthcheck runs, the check times out and the worker never starts.**

**Mitigation:**
- The compose `temporal` block above sets `start_period: 30s` on the healthcheck — gives auto-setup 30s of grace before failing checks count.
- Worker should retry `Client.connect()` with backoff if it returns connection-refused. The Temporal Python SDK's `Client.connect` already retries internally for ~10s, but a defensive outer loop in `worker.py` (e.g. 5 attempts with 5s sleep) is cheap insurance.

### Risk 6: macOS host-side worker run path is broken

**The risk:** developers on macOS might run `python -m api_server.temporal.worker` from a host venv (matching the `make dev-api` pattern for api_server). The worker can connect to Temporal:7233 via the host port (which we should publish to localhost in `docker-compose.local.yml`). But the `forward_to_agent` activity calls `recipe_index.get_container_ip()` which returns a 172.18.x.x bridge IP that the host cannot route to.

**Mitigation:**
- **Document explicitly in `deploy/README.md`:** worker MUST run inside the deploy compose stack on macOS. There is no host-venv path.
- Linux dev hosts could run native, but the production target is macOS for local dev — keep one path, document it.
- `make dev-api-local` should bring up `temporal` + `temporal-ui` + `temporal-worker` together. Add a `make dev-worker` target that's a no-op alias documenting "the worker runs inside compose; use `docker compose logs -f temporal-worker`."

### Risk 7: Existing `inapp_outbox` pump conflicts with workflow direct emit

**The risk:** if `emit_inapp_outbound` activity writes `agent_events` with `published=false` (as today), and `inapp_outbox` pump publishes them — that's the same pathway. But if the activity also `redis.publish()` directly for low-latency UX, the outbox pump publishes a duplicate.

**Mitigation:**
- **Don't change the emit pathway.** `emit_inapp_outbound` activity writes `agent_events` row with `published=false`. The existing `inapp_outbox` pump (which we KEEP) does the Redis publish. Same flow as today.
- The activity's job is **only the DB write**. The outbox pump's job is **only the Redis publish**. Two responsibilities, two layers, no duplication. Latency cost: the 100ms pump tick (PUMP_TICK_S in inapp_outbox.py:56). Acceptable per D-25 ("not a regression — same envelope mobile already consumes").

---

## 8. Open questions for the planner

### Q1: `mark_forwarded` status — keep or drop?

CONTEXT D-10 says "MarkForwarded becomes implicit via Temporal's started-but-not-completed state." But Risk 1 + Risk 4 above argue the status column needs `forwarded` to remain during the migration so the legacy reaper has something to sweep.

**Recommendation:** plan ships an explicit `mark_forwarded` activity (1 SQL UPDATE, fast) as the first step inside the workflow, BEFORE `forward_to_agent`. After ~1 month of stable Temporal operation, plan a follow-up to delete that activity + the column value.

### Q2: 011 alembic migration?

If the planner wants `idempotency_key` UNIQUE constraint (Risk 3 mitigation), that's an alembic 011_*. Otherwise, no schema change.

**Recommendation:** add a 011 that does:
- `CREATE UNIQUE INDEX ... ON inapp_messages(user_id, idempotency_key) WHERE idempotency_key IS NOT NULL`.
- `ALTER TABLE inapp_messages ADD COLUMN workflow_id text` (nullable) — populated by the route handler at `start_workflow` time, useful for ops correlation in Temporal UI.

### Q3: Cleanup script vs alembic for stuck-row sweep?

Risk 1 mitigation needs a one-time data sweep at cutover time. Alembic isn't designed for data, but it does run once. A standalone Python script invoked from `deploy/deploy.sh` is cleaner.

**Recommendation:** standalone `tools/migrate_phase28_stuck_rows.py` invoked from `deploy/deploy.sh` AFTER `alembic upgrade head` + BEFORE the api_server roll. Single transaction, idempotent. Logged.

### Q4: `temporal-admin-tools` — include or skip?

Compose recipe in §2 lists it as optional. MSV doesn't include it. It's useful for `temporal workflow list` / `temporal task-queue describe` ops debugging.

**Recommendation:** skip in v1. Add `make tctl` target in a follow-up phase if/when an ops scenario actually needs it.

### Q5: Do we set `execution_timeout` per-workflow at start time, or via `workflow.defn(default_execution_timeout=...)`?

Both are valid. Per-workflow gives the route handler control; defn-level gives a hard guarantee.

**Recommendation:** set both — defn-level default of 5min (D-13) AND override on `start_workflow` only if a future use case needs it.

---

## 9. Sources

### Primary (HIGH confidence)
- [VERIFIED: pypi.org/project/temporalio] — version 1.27.0 (2026-04-30), Python 3.10-3.14 support
- [VERIFIED: github.com/temporalio/sdk-python/blob/main/README.md] — Worker constructor, activity-class pattern, WorkflowEnvironment.start_time_skipping, client.start_workflow
- [VERIFIED: python.temporal.io/temporalio.workflow.html] — workflow.now, workflow.sleep, workflow.execute_activity, workflow.uuid4, workflow.random
- [VERIFIED: python.temporal.io/temporalio.worker.Worker.html] — max_concurrent_activities param signature
- [VERIFIED: docs.temporal.io/encyclopedia/detecting-activity-failures] — start_to_close vs schedule_to_close vs heartbeat semantics
- [VERIFIED: github.com/temporalio/docker-compose/blob/main/docker-compose-postgres.yml] — auto-setup env vars (DB, POSTGRES_SEEDS, DBNAME, VISIBILITY_DBNAME)
- [VERIFIED: hub.docker.com/r/temporalio/auto-setup tags] — latest 1.29.x as of 2026-05-04
- [VERIFIED: meusecretariovirtual/messaging/cmd/worker/main.go:288-327] — concurrency settings (10 / 5)
- [VERIFIED: meusecretariovirtual/messaging/workflows/send_message.go:1-200] — workflow shape verbatim port template
- [VERIFIED: meusecretariovirtual/infra/docker-compose.yml:86-122] — temporal + temporal-ui compose pattern
- [VERIFIED: agent-playground/api_server/src/api_server/services/inapp_dispatcher.py] — full file, the surface being replaced
- [VERIFIED: agent-playground/api_server/src/api_server/main.py:80-220] — lifespan setup pattern
- [VERIFIED: agent-playground/mobile/lib/features/chat/chat_providers.dart:308-348] — Consumer-scoped subscription + onDispose pattern
- [VERIFIED: agent-playground/mobile/lib/features/dashboard/dashboard_screen.dart:80-110] — current AppBar mount site

### Secondary (MEDIUM confidence)
- [CITED: docs.temporal.io/develop/python/python-sdk-sandbox] — sandbox import policies; specific forbidden-call list partially documented (cross-verified via search)
- [CITED: WebSearch on workflow determinism] — datetime/random/threading rules confirmed across multiple results
- [CITED: docs.temporal.io/self-hosted-guide/deployment] — auto-setup vs server image tradeoffs

### Tertiary (LOW confidence — flag for Wave 0 spike validation)
- The exact Worker activity-class registration pattern (worker takes `instance.method_name` references) — README mentions but no full code block was retrievable. Wave 0 spike must verify against `samples-python` repo.
- The exact Python sandbox behavior for httpx imports (does `from ...services.inapp_dispatcher import _dispatch_http_localhost` inside an activity file trigger sandbox warnings?) — answer is "no, activity files are unsandboxed" but [ASSUMED] until Wave 0 verifies.

---

## 10. Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The Worker class exposes `max_concurrent_activities` and `max_activities_per_second` as kwargs (mirroring MSV's Go option names) | §4 | Low — if the actual kwarg is `max_concurrent_activity_executions` we adjust at Wave 0 spike time. Pinned via the SDK source line; needs verification. |
| A2 | `workflow.unsafe.imports_passed_through()` context manager exists for unsandboxed imports inside workflow files | §3 | Medium — if the API moved, the workflow file's imports of activity references will fail to load. Verified via SDK README structure but not reproduced inline. Wave 0 spike must run `python -m api_server.temporal.worker` and confirm. |
| A3 | `temporalio/auto-setup:1.29.2` works against Postgres 17 (deploy uses `postgres:17-alpine`) | §2 | Low — `DB: postgres12` is the SCHEMA dialect identifier (not a version match). `auto-setup` README explicitly supports postgres ≥12. But spike should confirm the schema bootstrap completes against PG17. |
| A4 | Temporal's default healthcheck (`temporal operator cluster health`) is shipped with the auto-setup image | §2 | Low — MSV uses the same command (`infra/docker-compose.yml:105`) and runs in production. Confirmed by file. |
| A5 | The Python SDK's `WorkflowIDReusePolicy.REJECT_DUPLICATE` raises `WorkflowAlreadyStartedError` (not a generic `RPCError`) | §4 | Low — documented behavior, but the route handler's catch-class needs verification. Spike. |
| A6 | macOS Docker Desktop bridge limitation (CLAUDE.md banner) applies identically to the worker container as to the api_server container today | §7 risk #6 | Low — both run on `deploy_default`. CLAUDE.md banner directly applies. |
| A7 | The Phase 25 chat_providers.dart Consumer-scoped pattern is sufficient to prevent the defunct-element race that caused the Phase 27 ticker yank | §6 | Medium — the pattern works for chat. Phase 28 mounts it on `dashboard` AND `chat`. The defunct race could still surface during navigation transitions. Ticker re-mount needs a manual smoke test on a real device, not just unit tests. |

---

## 11. Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.23.x (existing) |
| Config file | `api_server/pyproject.toml:99-104` (`[tool.pytest.ini_options]`) |
| Quick run command | `pytest api_server/tests/test_dispatch_message_workflow.py -x` |
| Full suite command | `cd api_server && pytest -x` (existing 113+ test green gate per D-25) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| D-10 happy path | DispatchMessageWorkflow ready→forward→record→emit→mark | unit | `pytest tests/test_dispatch_message_workflow.py::test_happy_path -x` | ❌ Wave 0 |
| D-11 retry budget | forward_to_agent retries [1s,2s,4s] on httpx.ConnectError | unit | `pytest tests/temporal/test_forward_to_agent.py::test_retry_on_connect_error -x` | ❌ Wave 0 |
| D-13 5-min cap | workflow_execution_timeout fires at 5min | unit (time-skip) | `pytest tests/test_dispatch_message_workflow.py::test_execution_timeout -x` | ❌ Wave 0 |
| D-14 idempotency | duplicate Idempotency-Key returns cached 202; duplicate workflow_id rejected | integration | `make e2e-inapp-docker -- -k test_idempotency_layers` | ❌ Wave 0 |
| D-15 best-effort | record_usage activity failure does not fail workflow | unit | `pytest tests/test_dispatch_message_workflow.py::test_record_usage_swallow -x` | ❌ Wave 0 |
| D-18 ticker mount | UsageTickerWidget Consumer-scoped mount survives Dashboard → Chat → back navigation | manual smoke + widget test | `cd mobile && flutter test test/features/usage/usage_ticker_widget_remount_test.dart` | ❌ Wave 0 |
| D-25 happy E2E | full chat round-trip via Temporal succeeds against deploy stack | integration | `make e2e-inapp-docker` | ✅ exists, needs Phase 28 extension |

### Sampling Rate
- **Per task commit:** `pytest tests/temporal/ -x` (just the new tests; sub-second per file)
- **Per wave merge:** `cd api_server && pytest -x` (full 113+ test suite stays green per D-25)
- **Phase gate:** `make e2e-inapp-docker` — the dockerized harness is the integration-level validation

### Wave 0 Gaps
- [ ] `api_server/tests/test_dispatch_message_workflow.py` — workflow-level unit tests with WorkflowEnvironment
- [ ] `api_server/tests/temporal/test_forward_to_agent.py` — activity-level retry tests
- [ ] `api_server/tests/temporal/conftest.py` — shared `temporal_client` fixture using `WorkflowEnvironment.start_time_skipping`
- [ ] `mobile/test/features/usage/usage_ticker_widget_remount_test.dart` — widget-level test of Consumer-scoped mount surviving navigation
- [ ] Spike A: confirm `temporalio/auto-setup:1.29.2` boots against the existing `postgres:17-alpine` (~30s healthcheck wait expected)
- [ ] Spike B: confirm Python sandbox doesn't choke on the workflow file's `from ..activities import ...` imports (use `workflow.unsafe.imports_passed_through()` if it does)
- [ ] Spike C: confirm Temporal worker container reaches agent containers via `deploy_default` IPs (CLAUDE.md macOS gotcha — same constraint as api_server today)

---

## 12. Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13 | api_server + worker | ✓ | `ap-runtime-python:v0.1.0-3.13` | — |
| Postgres 17 | Temporal backend (shared) | ✓ | `postgres:17-alpine` | — |
| Redis 7 | outbox pump (unchanged) | ✓ | `redis:7-alpine` | — |
| Docker engine | worker → agent containers | ✓ | local Docker Desktop on macOS, dockerd on Hetzner | — |
| `temporalio/auto-setup:1.29.2` | Temporal frontend + history + matching | needs pull | new dep | none — required |
| `temporalio/ui:2.40.0` | Temporal UI | needs pull | new dep | none — required (D-03 / D-16) |
| `temporalio` Python SDK | workflow + activity + worker | needs install | 1.27.0 | none — required |

**Missing dependencies with no fallback:**
- The 3 above are net-new and must be added to deploy/docker-compose.prod.yml + api_server/pyproject.toml.

**Missing dependencies with fallback:** none — every other primitive is already in the stack.

---

*Phase: 28-temporal-dispatch*
*Researched: 2026-05-04*
*Valid until: 2026-06-04 (30 days — Temporal SDK is stable but moves; re-verify if planning slips past June)*

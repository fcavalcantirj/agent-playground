---
phase: 22b
plan: 02
type: execute
wave: 1
depends_on: ["22b-01"]
files_modified:
  - api_server/alembic/versions/004_agent_events.py
  - api_server/src/api_server/models/events.py
  - api_server/src/api_server/services/event_store.py
  - api_server/tests/test_events_migration.py
  - api_server/tests/test_events_store.py
  - api_server/tests/test_events_seq_concurrency.py
  - api_server/tests/test_events_batching_perf.py
autonomous: true
requirements:
  - SC-03-GATE-B

must_haves:
  truths:
    - "Alembic 004_agent_events upgrades cleanly on fresh PG17 and creates the agent_events table with CHECK + UNIQUE + CASCADE FK"
    - "CHECK constraint rejects kind NOT IN ('reply_sent','reply_failed','agent_ready','agent_error')"
    - "insert_agent_event allocates gap-free per-agent seqs under 4 concurrent writers on SAME agent_container_id (spike-05 reproducer)"
    - "insert_agent_events_batch achieves >=5x speedup vs per-row INSERT (spike-04 reproducer)"
    - "Pydantic ConfigDict(extra='forbid') rejects payloads with reply_text/body field (D-06 privacy enforcement)"
    - "fetch_events_after_seq filters kinds via kind = ANY($3::text[]) — never interpolates (V13 defense)"
  artifacts:
    - path: "api_server/alembic/versions/004_agent_events.py"
      provides: "agent_events schema DDL"
      contains: "agent_events"
    - path: "api_server/src/api_server/models/events.py"
      provides: "Per-kind Pydantic payloads + AgentEventsResponse"
      exports: ["VALID_KINDS","KIND_TO_PAYLOAD","ReplySentPayload","ReplyFailedPayload","AgentReadyPayload","AgentErrorPayload","AgentEvent","AgentEventsResponse"]
    - path: "api_server/src/api_server/services/event_store.py"
      provides: "insert_agent_event, insert_agent_events_batch, fetch_events_after_seq"
      exports: ["insert_agent_event","insert_agent_events_batch","fetch_events_after_seq"]
  key_links:
    - from: "api_server/src/api_server/services/event_store.py"
      to: "api_server/alembic/versions/004_agent_events.py"
      via: "INSERT matches DDL column order"
      pattern: "INSERT INTO agent_events"
    - from: "api_server/src/api_server/models/events.py"
      to: "api_server/src/api_server/services/event_store.py"
      via: "KIND_TO_PAYLOAD validation before INSERT"
      pattern: "KIND_TO_PAYLOAD"
---

<objective>
Build the durable persistence tier for Phase 22b.

1. **Migration 004_agent_events** — BIGSERIAL id, UUID agent_container_id CASCADE FK → agent_containers.id, BIGINT seq, TEXT kind with CHECK (4 kinds), JSONB payload, TEXT correlation_id, TIMESTAMPTZ ts. Composite UNIQUE(agent_container_id, seq) + descending-seq index.
2. **Pydantic models** — ReplySentPayload / ReplyFailedPayload / AgentReadyPayload / AgentErrorPayload, all ConfigDict(extra="forbid") — NO reply_text/body fields anywhere (D-06). Plus AgentEvent + AgentEventsResponse for API projection.
3. **event_store** — insert_agent_event (per-row with advisory-lock seq per D-16/spike-05), insert_agent_events_batch (100-row executemany, single advisory lock per batch per D-12/spike-04), fetch_events_after_seq (parameterized kind = ANY($3::text[])).

All tests hit real PG17 via testcontainers (Golden Rule 1). Tests port spike-04 and spike-05 reproducers verbatim.

Parallelizable with Plan 22b-03 (no shared files).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/22b-agent-event-stream/22b-CONTEXT.md
@.planning/phases/22b-agent-event-stream/22b-RESEARCH.md
@.planning/phases/22b-agent-event-stream/22b-PATTERNS.md
@.planning/phases/22b-agent-event-stream/22b-VALIDATION.md
@.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-04-postgres-batching.md
@.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-05-seq-ordering.md
@.planning/phases/22b-agent-event-stream/22b-01-SUMMARY.md
@api_server/alembic/versions/003_agent_containers.py
@api_server/src/api_server/models/agents.py
@api_server/src/api_server/services/run_store.py
@api_server/tests/test_run_concurrency.py
@api_server/tests/test_migration.py

<interfaces>
<!-- New exports this plan creates for Wave 2 to consume. -->

From api_server/src/api_server/models/events.py (NEW):
```python
VALID_KINDS: set[str] = {"reply_sent","reply_failed","agent_ready","agent_error"}
KIND_TO_PAYLOAD: dict[str, type[BaseModel]]  # kind → payload class

class ReplySentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat_id: str = Field(..., min_length=1, max_length=64)
    length_chars: int = Field(..., ge=0)
    captured_at: datetime

class ReplyFailedPayload(BaseModel):       # chat_id optional, reason(<=256) classification only
class AgentReadyPayload(BaseModel):        # ready_log_line truncated <=512
class AgentErrorPayload(BaseModel):        # severity pattern ^(ERROR|FATAL)$, detail <=512

class AgentEvent(BaseModel):
    seq: int; kind: str; payload: dict; correlation_id: str | None = None; ts: datetime

class AgentEventsResponse(BaseModel):
    agent_id: UUID
    events: list[AgentEvent]
    next_since_seq: int
    timed_out: bool = False
```

From api_server/src/api_server/services/event_store.py (NEW):
```python
async def insert_agent_event(conn, agent_container_id: UUID, kind: str,
                              payload: dict, correlation_id: str | None = None) -> int
async def insert_agent_events_batch(conn, agent_container_id: UUID,
                                     rows: list[tuple[str, dict, str | None]]) -> list[int]
async def fetch_events_after_seq(conn, agent_container_id: UUID, since_seq: int,
                                  kinds: set[str] | None = None) -> list[dict]
```

From api_server/alembic/versions/003_agent_containers.py (existing — 004 mirrors ondelete=CASCADE pattern).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Migration 004_agent_events + schema test</name>
  <files>api_server/alembic/versions/004_agent_events.py, api_server/tests/test_events_migration.py</files>
  <read_first>
    - api_server/alembic/versions/003_agent_containers.py (style to mirror — imports, revision header, upgrade/downgrade ordering)
    - api_server/tests/test_migration.py (schema-DDL-assertion fixture pattern)
    - 22b-PATTERNS.md §"api_server/alembic/versions/004_agent_events.py" (authoritative shape)
    - 22b-RESEARCH.md §"Example 5: Migration 004 shape"
    - 22b-CONTEXT.md D-05, D-17
    - 22b-RESEARCH.md §"Open Questions" Q4 (composite UNIQUE, no partial filter)
  </read_first>
  <behavior>
    - alembic upgrade head on empty PG17 creates agent_events with exact DDL
    - Inserting kind='bogus' raises asyncpg.CheckViolationError
    - Inserting (agent_container_id=X, seq=1) twice raises UniqueViolationError
    - DELETE FROM agent_containers CASCADEs to agent_events
    - alembic downgrade -1 drops cleanly
  </behavior>
  <action>
Create `api_server/alembic/versions/004_agent_events.py` following 003's exact style. Content per 22b-PATTERNS.md lines 37-96:

```python
"""Phase 22b-02 — agent_events table (durable event stream).

Columns: id BIGSERIAL PK, agent_container_id UUID CASCADE FK, seq BIGINT,
kind TEXT (CHECK 4 kinds), payload JSONB default '{}', correlation_id TEXT null,
ts TIMESTAMPTZ default NOW().
Indexes: UNIQUE(agent_container_id, seq); (agent_container_id, seq DESC).

Revision ID: 004_agent_events
Revises: 003_agent_containers
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004_agent_events"
down_revision = "003_agent_containers"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "agent_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("agent_container_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("agent_containers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.BigInteger, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("correlation_id", sa.Text, nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_check_constraint("ck_agent_events_kind", "agent_events",
        "kind IN ('reply_sent', 'reply_failed', 'agent_ready', 'agent_error')")
    op.create_unique_constraint("uq_agent_events_container_seq", "agent_events",
        ["agent_container_id", "seq"])
    op.create_index("ix_agent_events_container_seq_desc", "agent_events",
        ["agent_container_id", sa.text("seq DESC")])

def downgrade() -> None:
    op.drop_index("ix_agent_events_container_seq_desc", table_name="agent_events")
    op.drop_constraint("uq_agent_events_container_seq", "agent_events", type_="unique")
    op.drop_constraint("ck_agent_events_kind", "agent_events", type_="check")
    op.drop_table("agent_events")
```

Create `api_server/tests/test_events_migration.py` mirroring test_migration.py. Required tests:
- test_agent_events_table_exists (query information_schema.tables)
- test_kind_check_constraint_rejects_bogus (pytest.raises asyncpg.CheckViolationError on kind='bogus')
- test_unique_agent_seq (pytest.raises asyncpg.UniqueViolationError on duplicate (agent_container_id, seq=1))
- test_cascade_delete (DELETE FROM agent_containers → agent_events row count drops to 0)

If test_run_concurrency.py already has a `seed_agent_container` fixture, reuse it. Otherwise, define inline — create agent_instances + agent_containers rows to satisfy FK (use UUIDs).
  </action>
  <verify>
    <automated>cd api_server && pytest -x tests/test_events_migration.py -v 2>&1 | grep -qE "4 passed|passed"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "agent_events" api_server/alembic/versions/004_agent_events.py` returns >=3
    - `grep -c "ck_agent_events_kind" api_server/alembic/versions/004_agent_events.py` returns >=2 (create+drop)
    - `grep -c "ondelete=.CASCADE." api_server/alembic/versions/004_agent_events.py` returns >=1
    - `cd api_server && pytest -x tests/test_events_migration.py -v 2>&1 | grep -cE "PASSED"` returns 4
  </acceptance_criteria>
  <done>Migration file committed with CHECK + UNIQUE + CASCADE + descending index; 4 schema tests pass on real PG17 via testcontainers.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Pydantic per-kind event payloads + AgentEvent response models</name>
  <files>api_server/src/api_server/models/events.py, api_server/tests/test_events_store.py</files>
  <read_first>
    - api_server/src/api_server/models/agents.py (analog — ConfigDict(extra='forbid') + per-variant class pattern at lines 55-192)
    - api_server/src/api_server/models/runs.py (datetime+UUID response-model pattern)
    - 22b-PATTERNS.md §"api_server/src/api_server/models/events.py"
    - 22b-CONTEXT.md D-05 (4 kinds), D-06 (metadata only — NO reply_text/body), D-08 (typed-per-kind)
    - 22b-RESEARCH.md §"Known Threat Patterns" row "Reply body leakage" (D-06 is load-bearing)
  </read_first>
  <behavior>
    - `from api_server.models.events import VALID_KINDS, KIND_TO_PAYLOAD, ReplySentPayload, ReplyFailedPayload, AgentReadyPayload, AgentErrorPayload, AgentEvent, AgentEventsResponse` succeeds
    - `ReplySentPayload(chat_id="1", length_chars=42, captured_at=dt, reply_text="body")` raises ValidationError (extra='forbid' — D-06)
    - `ReplySentPayload(chat_id="", length_chars=42, captured_at=dt)` raises ValidationError (min_length=1)
    - `AgentErrorPayload(severity="WARN", ...)` raises ValidationError (pattern ^(ERROR|FATAL)$)
    - `VALID_KINDS == {"reply_sent","reply_failed","agent_ready","agent_error"}`
  </behavior>
  <action>
Create `api_server/src/api_server/models/events.py`:

```python
"""Phase 22b-02 — Pydantic models for agent_events (D-05, D-06, D-08).

Per-kind typed payloads with ConfigDict(extra="forbid") enforce D-06
metadata-only at parse time — a payload with reply_text/body is rejected
BEFORE event_store.insert_agent_event is reached.
"""
from __future__ import annotations
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

VALID_KINDS: set[str] = {"reply_sent", "reply_failed", "agent_ready", "agent_error"}

class ReplySentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat_id: str = Field(..., min_length=1, max_length=64)
    length_chars: int = Field(..., ge=0)
    captured_at: datetime

class ReplyFailedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat_id: str | None = Field(default=None, max_length=64)
    reason: str = Field(..., min_length=1, max_length=256)     # classification — never body
    captured_at: datetime

class AgentReadyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ready_log_line: str | None = Field(default=None, max_length=512)
    captured_at: datetime

class AgentErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    severity: str = Field(..., pattern=r"^(ERROR|FATAL)$")
    detail: str = Field(..., min_length=1, max_length=512)     # cred-redacted upstream
    captured_at: datetime

KIND_TO_PAYLOAD: dict[str, type[BaseModel]] = {
    "reply_sent": ReplySentPayload,
    "reply_failed": ReplyFailedPayload,
    "agent_ready": AgentReadyPayload,
    "agent_error": AgentErrorPayload,
}

class AgentEvent(BaseModel):
    seq: int; kind: str; payload: dict
    correlation_id: str | None = None
    ts: datetime

class AgentEventsResponse(BaseModel):
    agent_id: UUID
    events: list[AgentEvent] = Field(default_factory=list)
    next_since_seq: int
    timed_out: bool = False

__all__ = ["VALID_KINDS","KIND_TO_PAYLOAD","ReplySentPayload","ReplyFailedPayload",
           "AgentReadyPayload","AgentErrorPayload","AgentEvent","AgentEventsResponse"]
```

Start `api_server/tests/test_events_store.py` with payload-only tests (store tests land in Task 3):

```python
"""Phase 22b-02 — event store + payload validation."""
from datetime import datetime
import pytest
from pydantic import ValidationError
from api_server.models.events import (
    VALID_KINDS, KIND_TO_PAYLOAD,
    ReplySentPayload, ReplyFailedPayload, AgentReadyPayload, AgentErrorPayload,
)

def test_valid_kinds_exact():
    assert VALID_KINDS == {"reply_sent","reply_failed","agent_ready","agent_error"}

def test_kind_to_payload_coverage():
    assert set(KIND_TO_PAYLOAD.keys()) == VALID_KINDS

def test_reply_sent_happy_path():
    p = ReplySentPayload(chat_id="152099202", length_chars=42, captured_at=datetime.utcnow())
    assert p.chat_id == "152099202" and p.length_chars == 42

def test_reply_sent_rejects_reply_text():     # D-06 enforcement
    with pytest.raises(ValidationError):
        ReplySentPayload(chat_id="1", length_chars=42, captured_at=datetime.utcnow(),
                         reply_text="body content")

def test_reply_sent_rejects_body():
    with pytest.raises(ValidationError):
        ReplySentPayload(chat_id="1", length_chars=42, captured_at=datetime.utcnow(), body="x")

def test_reply_sent_rejects_empty_chat_id():
    with pytest.raises(ValidationError):
        ReplySentPayload(chat_id="", length_chars=42, captured_at=datetime.utcnow())

def test_reply_sent_rejects_negative_length():
    with pytest.raises(ValidationError):
        ReplySentPayload(chat_id="1", length_chars=-1, captured_at=datetime.utcnow())

def test_agent_error_severity_enum():
    AgentErrorPayload(severity="ERROR", detail="x", captured_at=datetime.utcnow())
    AgentErrorPayload(severity="FATAL", detail="x", captured_at=datetime.utcnow())
    with pytest.raises(ValidationError):
        AgentErrorPayload(severity="WARN", detail="x", captured_at=datetime.utcnow())
```
  </action>
  <verify>
    <automated>cd api_server && python3 -c "from api_server.models.events import VALID_KINDS, KIND_TO_PAYLOAD, ReplySentPayload, AgentEventsResponse; assert VALID_KINDS=={'reply_sent','reply_failed','agent_ready','agent_error'}" && pytest -x tests/test_events_store.py -v 2>&1 | grep -qE "8 passed|passed"</automated>
  </verify>
  <acceptance_criteria>
    - `python3 -c "from api_server.models.events import *; assert 'reply_text' not in ReplySentPayload.model_fields"` exits 0
    - `grep -c "ConfigDict(extra=.forbid.)" api_server/src/api_server/models/events.py` returns >=4 (one per payload class)
    - `grep -c "reply_text\|body" api_server/src/api_server/models/events.py` returns 0 (no such fields anywhere in the module)
    - `cd api_server && pytest -x tests/test_events_store.py -v 2>&1 | grep -c PASSED` returns >=8
  </acceptance_criteria>
  <done>Models module exports 4 payload classes + AgentEvent + AgentEventsResponse; 8+ payload tests pass; D-06 (no reply_text/body) programmatically enforced.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: event_store module + seq concurrency + batching perf tests</name>
  <files>api_server/src/api_server/services/event_store.py, api_server/tests/test_events_store.py, api_server/tests/test_events_seq_concurrency.py, api_server/tests/test_events_batching_perf.py</files>
  <read_first>
    - api_server/src/api_server/services/run_store.py (analog — module docstring, $N placeholders, one-function-per-transition, connection-per-scope, __all__)
    - api_server/tests/test_run_concurrency.py (analog — session-scoped PG fixture, asyncio gather concurrency pattern)
    - 22b-PATTERNS.md §"api_server/src/api_server/services/event_store.py" (authoritative function shapes)
    - 22b-RESEARCH.md §"Pattern 3: Advisory-lock seq allocation (spike 05)" (verbatim code)
    - 22b-SPIKES/spike-04-postgres-batching.md (reproducer — 5 agents × 200 rows, batched vs per-row)
    - 22b-SPIKES/spike-05-seq-ordering.md (reproducer — 4 writers × 50 rows on SAME agent_id)
    - 22b-CONTEXT.md D-16 (revised), D-12 (batching), D-06 (metadata only)
  </read_first>
  <behavior>
    - `insert_agent_event` allocates seq=1 on empty table, seq=N+1 on next call, all within advisory-locked transaction
    - 4 concurrent writers × 50 rows on SAME agent_container_id produces 200 gap-free rows, 0 UniqueViolation, 0 deadlock (spike-05 exactly)
    - `insert_agent_events_batch` with 100 rows is >=5x faster than 100 per-row calls (spike-04 measured 12.4x; floor is 5x)
    - `fetch_events_after_seq(since_seq=10, kinds={"reply_sent"})` returns only rows seq>10 AND kind='reply_sent', ordered ASC by seq
    - Passing `kinds={"bogus"}` returns [] without error (asyncpg ANY($3::text[]) handles empty match)
    - Zero SQL injection surface: query string NEVER contains CSV-interpolated `kinds` value
  </behavior>
  <action>
Create `api_server/src/api_server/services/event_store.py`:

```python
"""Phase 22b-02 — asyncpg repository for agent_events (D-16).

Every query uses $1, $2, ... placeholders. Per-agent advisory locks serialize
concurrent seq allocation (spike-05 proved gap-free + 0 UV + 0 deadlock for
4-way race). Batched INSERT uses a single advisory lock per batch
(spike-04 measured 12.4x vs per-row).
"""
from __future__ import annotations
import json
from uuid import UUID
import asyncpg


async def insert_agent_event(conn: asyncpg.Connection, agent_container_id: UUID,
                              kind: str, payload: dict,
                              correlation_id: str | None = None) -> int:
    """Allocate next per-agent seq via pg_advisory_xact_lock and INSERT.
    Returns the allocated seq. Caller validates kind against VALID_KINDS and
    payload against KIND_TO_PAYLOAD BEFORE calling.
    """
    async with conn.transaction():
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1::text))", str(agent_container_id))
        row = await conn.fetchrow(
            "SELECT COALESCE(MAX(seq),0)+1 AS next_seq FROM agent_events "
            "WHERE agent_container_id=$1", agent_container_id)
        next_seq = row["next_seq"]
        await conn.execute(
            "INSERT INTO agent_events "
            "(agent_container_id, seq, kind, payload, correlation_id) "
            "VALUES ($1, $2, $3, $4::jsonb, $5)",
            agent_container_id, next_seq, kind, json.dumps(payload), correlation_id)
    return next_seq


async def insert_agent_events_batch(conn: asyncpg.Connection, agent_container_id: UUID,
                                     rows: list[tuple[str, dict, str | None]]) -> list[int]:
    """executemany-batched INSERT with ONE advisory lock per batch.
    rows = [(kind, payload_dict, correlation_id), ...]. Returns allocated seqs.
    """
    if not rows:
        return []
    async with conn.transaction():
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1::text))", str(agent_container_id))
        base = await conn.fetchval(
            "SELECT COALESCE(MAX(seq),0) FROM agent_events WHERE agent_container_id=$1",
            agent_container_id)
        values = [(agent_container_id, base + i + 1, kind, json.dumps(payload), cid)
                  for i, (kind, payload, cid) in enumerate(rows)]
        await conn.executemany(
            "INSERT INTO agent_events "
            "(agent_container_id, seq, kind, payload, correlation_id) "
            "VALUES ($1, $2, $3, $4::jsonb, $5)", values)
    return [base + i + 1 for i in range(len(rows))]


async def fetch_events_after_seq(conn: asyncpg.Connection, agent_container_id: UUID,
                                  since_seq: int,
                                  kinds: set[str] | None = None) -> list[dict]:
    """Return rows with seq > since_seq, optionally filtered by kinds set.

    V13 defense: kinds is bound via $3::text[] ANY clause — NEVER interpolated.
    """
    if kinds:
        query = ("SELECT seq, kind, payload, correlation_id, ts "
                 "FROM agent_events WHERE agent_container_id=$1 AND seq > $2 "
                 "AND kind = ANY($3::text[]) ORDER BY seq ASC")
        rows = await conn.fetch(query, agent_container_id, since_seq, list(kinds))
    else:
        query = ("SELECT seq, kind, payload, correlation_id, ts "
                 "FROM agent_events WHERE agent_container_id=$1 AND seq > $2 "
                 "ORDER BY seq ASC")
        rows = await conn.fetch(query, agent_container_id, since_seq)
    # asyncpg returns Record; convert to dict. payload is returned as jsonb-decoded dict.
    return [dict(r) for r in rows]


__all__ = ["insert_agent_event", "insert_agent_events_batch", "fetch_events_after_seq"]
```

Append to `api_server/tests/test_events_store.py` (after Task 2 payload tests):

```python
# ----------- Store tests (live PG17 via testcontainers) -----------

from uuid import uuid4
from api_server.services.event_store import (
    insert_agent_event, insert_agent_events_batch, fetch_events_after_seq,
)

@pytest.mark.asyncio
async def test_insert_single_happy_path(real_db_pool, seed_agent_container):
    async with real_db_pool.acquire() as conn:
        seq1 = await insert_agent_event(conn, seed_agent_container, "reply_sent",
            {"chat_id":"1","length_chars":3,"captured_at":"2026-04-18T00:00:00Z"},
            correlation_id="abc1")
        seq2 = await insert_agent_event(conn, seed_agent_container, "reply_sent",
            {"chat_id":"1","length_chars":4,"captured_at":"2026-04-18T00:00:01Z"},
            correlation_id="abc2")
    assert seq1 == 1 and seq2 == 2

@pytest.mark.asyncio
async def test_kind_check_constraint_at_store_layer(real_db_pool, seed_agent_container):
    async with real_db_pool.acquire() as conn:
        with pytest.raises(asyncpg.CheckViolationError):
            await insert_agent_event(conn, seed_agent_container, "bogus", {})

@pytest.mark.asyncio
async def test_fetch_events_after_seq_kinds_filter(real_db_pool, seed_agent_container):
    async with real_db_pool.acquire() as conn:
        await insert_agent_event(conn, seed_agent_container, "reply_sent",
            {"chat_id":"1","length_chars":1,"captured_at":"2026-04-18T00:00:00Z"})
        await insert_agent_event(conn, seed_agent_container, "agent_error",
            {"severity":"ERROR","detail":"x","captured_at":"2026-04-18T00:00:01Z"})
        rows = await fetch_events_after_seq(conn, seed_agent_container, 0,
                                             kinds={"reply_sent"})
    assert len(rows) == 1 and rows[0]["kind"] == "reply_sent"

@pytest.mark.asyncio
async def test_fetch_events_unknown_kind_returns_empty(real_db_pool, seed_agent_container):
    async with real_db_pool.acquire() as conn:
        await insert_agent_event(conn, seed_agent_container, "reply_sent",
            {"chat_id":"1","length_chars":1,"captured_at":"2026-04-18T00:00:00Z"})
        rows = await fetch_events_after_seq(conn, seed_agent_container, 0,
                                             kinds={"bogus"})
    assert rows == []
```

Create `api_server/tests/test_events_seq_concurrency.py` — port spike-05 reproducer:

```python
"""Phase 22b-02 — spike-05 port: 4 writers × 50 rows on SAME agent_container_id.
Asserts gap-free 1..200, 0 UV, 0 deadlock (spike-05 measured 130ms for 200 serialized).
"""
import asyncio, asyncpg, pytest
from api_server.services.event_store import insert_agent_event

@pytest.mark.asyncio
async def test_seq_concurrent_4_writers_gap_free(real_db_pool, seed_agent_container):
    async def writer(wid: int):
        counts = {"successes": 0, "uv": 0, "dl": 0}
        for i in range(50):
            async with real_db_pool.acquire() as conn:
                try:
                    await insert_agent_event(conn, seed_agent_container, "reply_sent",
                        {"chat_id":"1","length_chars":1,
                         "captured_at":"2026-04-18T00:00:00Z"},
                        correlation_id=f"w{wid}-{i}")
                    counts["successes"] += 1
                except asyncpg.UniqueViolationError:
                    counts["uv"] += 1
                except asyncpg.DeadlockDetectedError:
                    counts["dl"] += 1
        return counts

    results = await asyncio.gather(*[writer(w) for w in range(4)])

    async with real_db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT seq FROM agent_events WHERE agent_container_id=$1 ORDER BY seq",
            seed_agent_container)
    seqs = [r["seq"] for r in rows]
    assert seqs == list(range(1, 201)), f"gaps detected: {seqs[:5]}..{seqs[-5:]}"
    assert sum(r["successes"] for r in results) == 200
    assert all(r["uv"] == 0 and r["dl"] == 0 for r in results)
```

Create `api_server/tests/test_events_batching_perf.py` — port spike-04 reproducer with 5x floor:

```python
"""Phase 22b-02 — spike-04 port: 100-row batch >= 5x speedup vs per-row
(spike measured 12.4x; 5x floor guards against regression).
"""
import time, pytest
from uuid import uuid4
from api_server.services.event_store import insert_agent_event, insert_agent_events_batch

@pytest.mark.asyncio
async def test_batch_speedup_vs_per_row(real_db_pool, seed_agent_container, seed_agent_container_factory):
    # Two separate agents so state doesn't cross-contaminate.
    agent_a = seed_agent_container
    agent_b = seed_agent_container_factory()   # second agent — Wave 0 conftest may need to expose this helper

    payload = {"chat_id":"1","length_chars":1,"captured_at":"2026-04-18T00:00:00Z"}

    # Per-row: 100 separate transactions
    t0 = time.perf_counter()
    for _ in range(100):
        async with real_db_pool.acquire() as conn:
            await insert_agent_event(conn, agent_a, "reply_sent", payload)
    per_row_s = time.perf_counter() - t0

    # Batched: 1 transaction, 100 rows
    t0 = time.perf_counter()
    async with real_db_pool.acquire() as conn:
        await insert_agent_events_batch(conn, agent_b,
            [("reply_sent", payload, None) for _ in range(100)])
    batch_s = time.perf_counter() - t0

    speedup = per_row_s / batch_s if batch_s > 0 else float("inf")
    assert speedup >= 5.0, f"batch speedup {speedup:.1f}x < 5x floor (per_row={per_row_s:.3f}s, batch={batch_s:.3f}s)"
```

If `seed_agent_container_factory` doesn't exist in conftest yet, add a simple factory fixture inline in the test file OR inline-create a second agent_container row.

Run:
```bash
cd api_server && pytest -x tests/test_events_store.py tests/test_events_seq_concurrency.py tests/test_events_batching_perf.py -v
```
All green. Note: seq_concurrency should complete in ≤2s (spike-05 measured 0.13s serialized); batch perf should show >=5x.
  </action>
  <verify>
    <automated>cd api_server && pytest -x tests/test_events_store.py tests/test_events_seq_concurrency.py tests/test_events_batching_perf.py -v 2>&1 | tail -10 | grep -qE "passed"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "pg_advisory_xact_lock(hashtext" api_server/src/api_server/services/event_store.py` returns >=2 (per-row + batch)
    - `grep -c "kind = ANY(.3::text\[\])" api_server/src/api_server/services/event_store.py` returns >=1
    - `grep -cE "f\".*\{kinds\}|%s.*kinds" api_server/src/api_server/services/event_store.py` returns 0 (no string interpolation of kinds)
    - `cd api_server && pytest -x tests/test_events_seq_concurrency.py -v 2>&1 | grep -q "1 passed"` (4-way race → gap-free)
    - `cd api_server && pytest -x tests/test_events_batching_perf.py -v 2>&1 | grep -q "1 passed"` (speedup >=5x)
    - `cd api_server && pytest -x tests/test_events_store.py -v 2>&1 | grep -c PASSED` returns >=12 (8 payload + 4 store)
  </acceptance_criteria>
  <done>event_store module exports 3 CRUD functions with advisory-lock seq allocation; spike-04 batching + spike-05 concurrency reproduced as passing tests; kinds filter uses $N binding (V13).</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| watcher → event_store | Untrusted log content crosses here — payload dicts from regex captures must be validated by KIND_TO_PAYLOAD BEFORE INSERT (D-08) |
| caller (long-poll) → fetch_events_after_seq | `kinds` CSV from query string reaches this function as a set — MUST be bound via $3::text[] ANY (V13) |
| Postgres → app | CHECK constraint rejects unknown kind at DB layer — defense-in-depth behind Pydantic |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-22b-02-01 | Information Disclosure | ReplySentPayload / other payloads | mitigate | ConfigDict(extra="forbid") rejects any field not explicitly declared (no reply_text, no body, no message, no content). Programmatically enforced by `test_reply_sent_rejects_reply_text` + `test_reply_sent_rejects_body` (D-06) |
| T-22b-02-02 | Injection | fetch_events_after_seq | mitigate | kinds bound as `$3::text[]` with `kind = ANY($3::text[])` — `set[str]` → `list[str]` → asyncpg parameter binding. NEVER builds the IN clause via string format. Unit test ensures `kinds={"bogus"}` returns `[]` with no error (asyncpg handles unknown values gracefully) |
| T-22b-02-03 | Tampering | insert_agent_event | mitigate | Advisory lock `pg_advisory_xact_lock(hashtext($1::text))` serializes per-agent writers; UNIQUE(agent_container_id, seq) is the DB-layer backstop (spike-05: 4-way race, 0 UV). Two independent defenses |
| T-22b-02-04 | Denial of Service | insert_agent_events_batch | accept | Batch size is bounded by caller (watcher_service passes <=100 — Wave 1); no per-call limit enforced here. Unbounded batches could OOM via JSON encoding; acceptable because watcher is trusted (same process) |
| T-22b-02-05 | Information Disclosure | AgentErrorPayload.detail | transfer | Module docstring + field comment says "cred-redacted upstream"; redaction is the WATCHER's responsibility via `_redact_creds` import (Wave 1 Plan 22b-03). Threat is transferred to Plan 22b-03 test coverage |
| T-22b-02-06 | Elevation of Privilege | fetch_events_after_seq | mitigate | Function takes agent_container_id as parameter; no route-level lookup here. Caller (long-poll handler in Plan 22b-05) is responsible for ownership check BEFORE calling. Comment in module docstring makes this explicit |
</threat_model>

<verification>
- `cd api_server && pytest -x tests/test_events_migration.py tests/test_events_store.py tests/test_events_seq_concurrency.py tests/test_events_batching_perf.py -v 2>&1 | tail -5` shows all PASSED
- `python3 -c "from api_server.services.event_store import insert_agent_event, insert_agent_events_batch, fetch_events_after_seq"` exits 0
- `python3 -c "from api_server.models.events import VALID_KINDS, KIND_TO_PAYLOAD, AgentEventsResponse"` exits 0
- `grep -r "pg_advisory_xact_lock" api_server/src/` returns >=2 matches (per-row + batch)
- No existing test regresses: `cd api_server && pytest -x tests/ -q 2>&1 | tail -3` shows no red
</verification>

<success_criteria>
1. Migration 004_agent_events upgrades + downgrades cleanly; CHECK + UNIQUE + CASCADE + descending index verified
2. 4 Pydantic payload classes + KIND_TO_PAYLOAD + AgentEvent + AgentEventsResponse exported; D-06 (no reply_text/body) programmatically enforced
3. event_store exposes insert_agent_event (advisory-lock seq), insert_agent_events_batch (executemany, single lock), fetch_events_after_seq (parameterized kinds)
4. Spike-05 reproducer (4×50 gap-free) passes
5. Spike-04 reproducer (100-row batch >=5x speedup) passes
6. 12+ payload + store tests green on real PG17 via testcontainers
</success_criteria>

<output>
After completion, create `.planning/phases/22b-agent-event-stream/22b-02-SUMMARY.md` with:
- Migration revision id + columns/indexes/constraints created
- The 4 Pydantic payload classes + their D-06 forbid-extra discipline
- event_store function signatures + advisory-lock + batching evidence
- Spike-05 wall time + gap-free verdict
- Spike-04 speedup ratio observed
- Any deviation from PATTERNS.md §"event_store" shape
</output>

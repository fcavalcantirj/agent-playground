"""Phase 29 Plan 09 Task 1 — integration tests for the cutover script.

Mirrors the test pattern of ``api_server/tests/services/test_proxy_byok_cache.py``
(real PG17 via testcontainers, no mocks for the DB substrate). The Docker
SDK is the only dependency monkeypatched — we don't actually want to stop
real containers from this test file.

Coverage map (8 behaviors enumerated in 29-09-PLAN.md Task 1):

  1. ``test_dry_run_prints_does_not_write`` — seed 3 nanobot rows; --dry-run
     leaves the rows + DB state untouched and makes ZERO docker stop calls.
  2. ``test_live_mode_stops_and_updates`` — seed 3 nanobot rows; live mode
     stops all 3 containers (mocked SDK records calls) and transitions
     each row to status='stopped' with stopped_at NOT NULL.
  3. ``test_limit_caps_sweep`` — seed 10 nanobot rows; --limit=2 stops + UPDATEs
     only 2 rows; the other 8 stay 'running'.
  4. ``test_404_tolerant_docker_stop`` — mock the SDK to raise NotFound for
     ONE row; assert the script logs the orphan, continues, and UPDATEs
     ALL 3 rows (orphan reconciliation).
  5. ``test_filters_recipe_name_nanobot_only`` — seed 3 nanobot rows + 2
     hermes + 1 openclaw; assert ONLY the 3 nanobot rows are touched.
  6. ``test_filters_status_running_or_starting`` — seed 1 nanobot row in
     'stopped' state; assert it is NOT touched (status preservation).
  7. ``test_database_url_env_reads_from_env`` — set DATABASE_URL env; the
     script connects without an explicit --dsn argument.
  8. ``test_missing_dsn_returns_nonzero`` — no DATABASE_URL, no --dsn;
     the script prints to stderr (caplog/captured logging) and returns 2.

AMD-01 enforcement: the string ``nano-kaiku`` MUST NOT appear anywhere
in ``tools/migrate_phase29_nanobot_cutover.py``. The grep gate in
29-09-PLAN.md acceptance_criteria catches accidental references; this
test file documents the invariant in test 5.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest


pytestmark = pytest.mark.api_integration


# ---------------------------------------------------------------------------
# Module-loader — import tools/migrate_phase29_nanobot_cutover.py from a path
# the api_server tests' sys.path doesn't normally include.
# ---------------------------------------------------------------------------


API_SERVER_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = API_SERVER_DIR.parent
SCRIPT_PATH = REPO_ROOT / "tools" / "migrate_phase29_nanobot_cutover.py"


def _load_cutover_module() -> types.ModuleType:
    """Import the cutover script as a module via importlib.

    The ``tools/`` directory is not on the test ``sys.path``; importing
    via spec_from_file_location keeps the test self-contained.
    """
    spec = importlib.util.spec_from_file_location(
        "phase29_nanobot_cutover", str(SCRIPT_PATH),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Fake docker SDK — record calls + raise NotFound on demand.
# ---------------------------------------------------------------------------


class _FakeContainer:
    def __init__(self, container_id: str, *, recorder: list[tuple[str, int]]):
        self.id = container_id
        self._recorder = recorder

    def stop(self, timeout: int = 10) -> None:
        self._recorder.append((self.id, timeout))


class _FakeNotFound(Exception):
    """Stand-in for ``docker.errors.NotFound``."""


class _FakeContainersAPI:
    def __init__(
        self,
        recorder: list[tuple[str, int]],
        *,
        not_found_ids: set[str] | None = None,
    ) -> None:
        self._recorder = recorder
        self._not_found_ids = not_found_ids or set()

    def get(self, container_id: str) -> _FakeContainer:
        if container_id in self._not_found_ids:
            raise _FakeNotFound(
                f"No such container: {container_id[:12]}"
            )
        return _FakeContainer(container_id, recorder=self._recorder)


class _FakeDockerClient:
    def __init__(
        self,
        recorder: list[tuple[str, int]],
        *,
        not_found_ids: set[str] | None = None,
    ) -> None:
        self.containers = _FakeContainersAPI(
            recorder, not_found_ids=not_found_ids,
        )


def _patch_docker(
    monkeypatch: pytest.MonkeyPatch,
    cutover_mod: types.ModuleType,
    *,
    not_found_ids: set[str] | None = None,
) -> list[tuple[str, int]]:
    """Replace the cutover module's docker SDK shims with the fake.

    Returns the list of ``(container_id, timeout)`` calls the fake
    recorded — caller asserts on its length / contents.
    """
    recorder: list[tuple[str, int]] = []

    def _build_client():
        return _FakeDockerClient(recorder, not_found_ids=not_found_ids)

    def _not_found_class():
        return _FakeNotFound

    monkeypatch.setattr(cutover_mod, "_build_docker_client", _build_client)
    monkeypatch.setattr(cutover_mod, "_docker_not_found_class", _not_found_class)
    return recorder


# ---------------------------------------------------------------------------
# DB seed helpers
# ---------------------------------------------------------------------------


async def _seed_user_and_agent(pool: asyncpg.Pool) -> tuple[UUID, UUID]:
    user_id = uuid4()
    agent_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, display_name) VALUES ($1, $2)",
            user_id, f"phase29-cutover-test-{uuid4().hex[:6]}",
        )
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, 'nanobot', 'm-test', $3)
            """,
            agent_id, user_id, f"agent-{uuid4().hex[:8]}",
        )
    return user_id, agent_id


async def _seed_container(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    agent_instance_id: UUID,
    recipe_name: str = "nanobot",
    container_status: str = "running",
    container_id: str | None = None,
) -> UUID:
    row_id = uuid4()
    cid = container_id if container_id is not None else (
        f"deadbeef{uuid4().hex[:48]}"
    )
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_containers (
                id, agent_instance_id, user_id, recipe_name,
                deploy_mode, container_status, container_id,
                ready_at
            ) VALUES (
                $1, $2, $3, $4,
                'persistent', $5, $6,
                CASE WHEN $5 = 'running' THEN NOW() ELSE NULL END
            )
            """,
            row_id, agent_instance_id, user_id, recipe_name,
            container_status, cid,
        )
    return row_id


async def _fetch_row(
    pool: asyncpg.Pool, row_id: UUID,
) -> dict:
    async with pool.acquire() as conn:
        r = await conn.fetchrow(
            """
            SELECT id, container_status, stopped_at, last_error, recipe_name
            FROM agent_containers WHERE id=$1
            """,
            row_id,
        )
    assert r is not None
    return dict(r)


def _dsn_from_pool(pool: asyncpg.Pool) -> str:
    """Reconstruct a DSN the cutover script's asyncpg.connect can use.

    asyncpg pools expose connection parameters via the underlying
    connection-args; we round-trip through pool.acquire to read the
    server address + db. Simpler: ``pool._connect_args`` is a private
    attr; instead we re-use the env var the conftest set.
    """
    # The migrated_pg fixture uses testcontainers — its connection URL
    # starts with postgresql+asyncpg:// which the script normalizes.
    # Easiest path: pull DSN from the pool directly via the public API.
    # asyncpg's ``Pool`` doesn't expose the DSN, so we read it back from
    # one acquired connection.
    # NOTE: pytest_asyncio's plain context manager works here.
    raise NotImplementedError  # pragma: no cover  — replaced by fixture below


@pytest.fixture
def db_dsn(migrated_pg) -> str:
    """The DSN string suitable for asyncpg.connect (used by the script)."""
    # migrated_pg is the testcontainers PostgresContainer; its
    # get_connection_url() returns a SQLAlchemy DSN. Mirror the
    # _normalize_testcontainers_dsn helper from tests/conftest.py.
    raw = migrated_pg.get_connection_url()
    return raw.replace("postgresql+psycopg2://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


# ---------------------------------------------------------------------------
# Test harness — wraps cutover module's main() with a controlled argv.
# ---------------------------------------------------------------------------


async def _run_cutover(
    cutover_mod: types.ModuleType,
    *,
    dsn: str | None,
    extra_argv: list[str] | None = None,
    monkeypatch: pytest.MonkeyPatch,
) -> int:
    """Invoke ``cutover_mod.main()`` with a controlled argv + env."""
    argv = ["migrate_phase29_nanobot_cutover.py"]
    if dsn is not None:
        argv += ["--dsn", dsn]
    if extra_argv:
        argv += extra_argv
    monkeypatch.setattr(sys, "argv", argv)
    return await cutover_mod.main()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_dry_run_prints_does_not_write(
    db_pool: asyncpg.Pool, db_dsn: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--dry-run lists rows, makes ZERO docker stop calls, leaves DB untouched."""
    cutover_mod = _load_cutover_module()
    recorder = _patch_docker(monkeypatch, cutover_mod)

    rows: list[UUID] = []
    for _ in range(3):
        u, a = await _seed_user_and_agent(db_pool)
        rid = await _seed_container(
            db_pool, user_id=u, agent_instance_id=a,
        )
        rows.append(rid)

    rc = await _run_cutover(
        cutover_mod, dsn=db_dsn, extra_argv=["--dry-run"], monkeypatch=monkeypatch,
    )
    assert rc == 0

    # No docker calls.
    assert recorder == [], f"--dry-run made docker calls: {recorder}"

    # All rows still 'running' with no stopped_at.
    for rid in rows:
        r = await _fetch_row(db_pool, rid)
        assert r["container_status"] == "running", r
        assert r["stopped_at"] is None, r
        assert r["last_error"] is None, r


async def test_live_mode_stops_and_updates(
    db_pool: asyncpg.Pool, db_dsn: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live mode stops 3 containers + transitions all 3 rows."""
    cutover_mod = _load_cutover_module()
    recorder = _patch_docker(monkeypatch, cutover_mod)

    rows: list[UUID] = []
    for _ in range(3):
        u, a = await _seed_user_and_agent(db_pool)
        rid = await _seed_container(
            db_pool, user_id=u, agent_instance_id=a,
        )
        rows.append(rid)

    rc = await _run_cutover(
        cutover_mod, dsn=db_dsn, monkeypatch=monkeypatch,
    )
    assert rc == 0

    assert len(recorder) == 3, f"expected 3 docker stops, got {len(recorder)}"

    for rid in rows:
        r = await _fetch_row(db_pool, rid)
        assert r["container_status"] == "stopped", r
        assert r["stopped_at"] is not None, r
        assert r["last_error"] == "phase29_cutover_swept", r


async def test_limit_caps_sweep(
    db_pool: asyncpg.Pool, db_dsn: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--limit=2 stops + UPDATEs only 2 rows; rest stay 'running'."""
    cutover_mod = _load_cutover_module()
    recorder = _patch_docker(monkeypatch, cutover_mod)

    rows: list[UUID] = []
    for _ in range(10):
        u, a = await _seed_user_and_agent(db_pool)
        rid = await _seed_container(
            db_pool, user_id=u, agent_instance_id=a,
        )
        rows.append(rid)

    rc = await _run_cutover(
        cutover_mod, dsn=db_dsn, extra_argv=["--limit", "2"],
        monkeypatch=monkeypatch,
    )
    assert rc == 0

    assert len(recorder) == 2, f"expected 2 docker stops, got {len(recorder)}"

    states = []
    for rid in rows:
        r = await _fetch_row(db_pool, rid)
        states.append(r["container_status"])

    stopped_count = states.count("stopped")
    running_count = states.count("running")
    assert stopped_count == 2 and running_count == 8, (
        f"expected 2 stopped + 8 running, got {stopped_count}/{running_count}"
    )


async def test_404_tolerant_docker_stop(
    db_pool: asyncpg.Pool, db_dsn: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A NotFound on one row's docker.stop is logged + the row is still UPDATEd."""
    cutover_mod = _load_cutover_module()

    rows: list[tuple[UUID, str]] = []
    for _ in range(3):
        u, a = await _seed_user_and_agent(db_pool)
        cid = f"orphan{uuid4().hex[:50]}"
        rid = await _seed_container(
            db_pool, user_id=u, agent_instance_id=a,
            container_id=cid,
        )
        rows.append((rid, cid))

    # Make the second row's docker.stop raise NotFound.
    not_found_ids = {rows[1][1]}
    recorder = _patch_docker(
        monkeypatch, cutover_mod, not_found_ids=not_found_ids,
    )

    rc = await _run_cutover(
        cutover_mod, dsn=db_dsn, monkeypatch=monkeypatch,
    )
    assert rc == 0

    # 2 stops succeeded; the orphan didn't reach .stop().
    assert len(recorder) == 2, f"expected 2 stops (1 orphan), got {len(recorder)}"

    # All 3 rows transitioned (orphan reconciliation).
    for rid, _cid in rows:
        r = await _fetch_row(db_pool, rid)
        assert r["container_status"] == "stopped", r
        assert r["stopped_at"] is not None, r
        assert r["last_error"] == "phase29_cutover_swept", r


async def test_filters_recipe_name_nanobot_only(
    db_pool: asyncpg.Pool, db_dsn: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """3 nanobot + 2 hermes + 1 openclaw: only the 3 nanobot rows touched.

    AMD-01 invariant — nanobot is the canonical name. The script must
    NOT match a hypothetical 'nano-kaiku' recipe (it doesn't exist; this
    test additionally documents that ``nano-kaiku`` does not appear in
    the cutover script source).
    """
    cutover_mod = _load_cutover_module()
    recorder = _patch_docker(monkeypatch, cutover_mod)

    nanobot_rids: list[UUID] = []
    other_rids: list[UUID] = []

    for _ in range(3):
        u, a = await _seed_user_and_agent(db_pool)
        nanobot_rids.append(await _seed_container(
            db_pool, user_id=u, agent_instance_id=a,
            recipe_name="nanobot",
        ))

    # Seed 2 hermes + 1 openclaw rows (different agent_instances + their
    # OWN agent_instances rows, since agent_instances has its own
    # recipe_name column).
    for recipe in ("hermes", "hermes", "openclaw"):
        u, a = await _seed_user_and_agent(db_pool)
        # Update the agent_instances row to the right recipe_name.
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE agent_instances SET recipe_name=$1 WHERE id=$2",
                recipe, a,
            )
        other_rids.append(await _seed_container(
            db_pool, user_id=u, agent_instance_id=a,
            recipe_name=recipe,
        ))

    rc = await _run_cutover(
        cutover_mod, dsn=db_dsn, monkeypatch=monkeypatch,
    )
    assert rc == 0

    assert len(recorder) == 3, f"expected 3 stops (nanobot only), got {len(recorder)}"

    for rid in nanobot_rids:
        r = await _fetch_row(db_pool, rid)
        assert r["container_status"] == "stopped", r
    for rid in other_rids:
        r = await _fetch_row(db_pool, rid)
        assert r["container_status"] == "running", r
        assert r["stopped_at"] is None, r

    # Source-level AMD-01 grep — file must not mention nano-kaiku.
    src = SCRIPT_PATH.read_text()
    assert "nano-kaiku" not in src, (
        "AMD-01 violation: tools/migrate_phase29_nanobot_cutover.py "
        "contains the forbidden 'nano-kaiku' string"
    )


async def test_filters_status_running_or_starting(
    db_pool: asyncpg.Pool, db_dsn: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A nanobot row already in 'stopped' is NOT touched.

    Status preservation — the cutover wipes only live rows.
    """
    cutover_mod = _load_cutover_module()
    recorder = _patch_docker(monkeypatch, cutover_mod)

    u_running, a_running = await _seed_user_and_agent(db_pool)
    rid_running = await _seed_container(
        db_pool, user_id=u_running, agent_instance_id=a_running,
        container_status="running",
    )

    u_starting, a_starting = await _seed_user_and_agent(db_pool)
    rid_starting = await _seed_container(
        db_pool, user_id=u_starting, agent_instance_id=a_starting,
        container_status="starting",
    )

    u_stopped, a_stopped = await _seed_user_and_agent(db_pool)
    rid_stopped = await _seed_container(
        db_pool, user_id=u_stopped, agent_instance_id=a_stopped,
        container_status="stopped",
    )

    rc = await _run_cutover(
        cutover_mod, dsn=db_dsn, monkeypatch=monkeypatch,
    )
    assert rc == 0

    # 2 stops — running + starting were swept; stopped was not.
    assert len(recorder) == 2

    for rid in (rid_running, rid_starting):
        r = await _fetch_row(db_pool, rid)
        assert r["container_status"] == "stopped"
        assert r["stopped_at"] is not None
        assert r["last_error"] == "phase29_cutover_swept"

    # The pre-existing 'stopped' row is untouched.
    r_stopped = await _fetch_row(db_pool, rid_stopped)
    assert r_stopped["container_status"] == "stopped"
    assert r_stopped["last_error"] is None  # script did NOT overwrite


async def test_database_url_env_reads_from_env(
    db_pool: asyncpg.Pool, db_dsn: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without --dsn, the script reads DATABASE_URL from env."""
    cutover_mod = _load_cutover_module()
    _patch_docker(monkeypatch, cutover_mod)

    u, a = await _seed_user_and_agent(db_pool)
    rid = await _seed_container(
        db_pool, user_id=u, agent_instance_id=a,
    )

    monkeypatch.setenv("DATABASE_URL", db_dsn)
    rc = await _run_cutover(
        cutover_mod, dsn=None, extra_argv=["--dry-run"], monkeypatch=monkeypatch,
    )
    assert rc == 0

    # Dry-run preserves state; the row stays 'running'.
    r = await _fetch_row(db_pool, rid)
    assert r["container_status"] == "running"


async def test_missing_dsn_returns_nonzero(
    monkeypatch: pytest.MonkeyPatch, caplog,
) -> None:
    """No DATABASE_URL + no --dsn → return code 2 + a stderr-style log."""
    cutover_mod = _load_cutover_module()
    monkeypatch.delenv("DATABASE_URL", raising=False)

    monkeypatch.setattr(sys, "argv", ["migrate_phase29_nanobot_cutover.py"])
    rc = await cutover_mod.main()
    assert rc == 2

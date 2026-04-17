"""Test fixtures for api_server.

Plan 19-01 leaves this as a placeholder. Wave 2 (Plan 19-02) populates it with
the full fixture set described in 19-PATTERNS.md lines 393-430:

    - postgres_container   (session-scoped testcontainers Postgres)
    - db_pool              (asyncpg pool wired to the container; TRUNCATE per test)
    - async_client         (httpx AsyncClient + ASGITransport → FastAPI app)
    - mock_run_cell        (factory fixture mirroring tools/tests/conftest.py style)

Until then, each test that needs Postgres spins its own container inline
(see tests/test_migration.py).
"""

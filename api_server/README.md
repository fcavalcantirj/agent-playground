# api_server

FastAPI service wrapping `tools/run_recipe.py`. See `.planning/phases/19-api-foundation/19-CONTEXT.md` for the full design.

## Running locally

```bash
make dev-api          # added in Plan 19-07
```

Until then (Plan 19-02+ ships the FastAPI app):

```bash
pip install -e 'api_server/[dev]'
cd api_server && uvicorn api_server.main:app --reload --port 8000
```

`DATABASE_URL` is required (see `.env.example`).

## Tests

Install once:

```bash
pip install -e 'api_server/[dev]'
```

Fast unit-only run (CI default):

```bash
cd api_server && pytest -q -m 'not api_integration'
```

Full suite including real-Postgres integration tests (requires Docker):

```bash
cd api_server && pytest -q
```

The `api_integration` marker opts into the slower tests that spawn a real
Postgres 17 container via `testcontainers[postgres]`.

## Migrations

```bash
cd api_server && DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db alembic upgrade head
```

The migration env (`alembic/env.py`) is async. `postgres://` / `postgresql://`
DSN shapes are auto-normalized to `postgresql+asyncpg://`.

To roll back to an empty schema:

```bash
cd api_server && DATABASE_URL=... alembic downgrade base
```

"""Async Alembic env.

Synthesized from `.planning/phases/19-api-foundation/19-RESEARCH.md` lines 562-593:
- `sqlalchemy.ext.asyncio.async_engine_from_config` + `pool.NullPool`
- Bare `MetaData()` (DDL is authored via `op.create_table`, no ORM models)
- Offline mode rejected explicitly — migrations require a live DB connection.

DSN sourcing: `DATABASE_URL` env var, normalized to `postgresql+asyncpg://...`
so callers can pass the shorter `postgres://...` or `postgresql://...` shapes
that testcontainers + most ops tooling emit.
"""
import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import MetaData, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Normalize DSN: accept postgres://, postgresql://, or postgresql+asyncpg://
raw_url = os.environ.get("DATABASE_URL")
if not raw_url:
    raise RuntimeError("DATABASE_URL is required for migrations")
if raw_url.startswith("postgres://"):
    raw_url = "postgresql+asyncpg://" + raw_url[len("postgres://"):]
elif raw_url.startswith("postgresql://") and "+asyncpg" not in raw_url:
    raw_url = "postgresql+asyncpg://" + raw_url[len("postgresql://"):]
config.set_main_option("sqlalchemy.url", raw_url)

target_metadata = MetaData()  # bare metadata — DDL is authored via op.create_table


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    raise RuntimeError("offline migrations not supported")
asyncio.run(run_async_migrations())

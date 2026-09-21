"""Async SQLAlchemy engine/session management."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings
from app.database.models import Base

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class UnmanagedDatabaseError(RuntimeError):
    """Raised by init_db() when the target database already has application
    tables but Alembic has no record of migrating it — see
    docs/development.md#reconciling-a-pre-alembic-database. Calling
    init_db() again would be a no-op on the existing tables (SQLAlchemy's
    create_all() never alters an existing table), silently leaving any
    migration since applied — e.g. new evidence columns — missing forever."""


def get_engine(database_url: str | None = None):
    global _engine
    if _engine is None:
        url = database_url or get_settings().database_url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_async_engine(url, echo=False, connect_args=connect_args)
    return _engine


def get_session_factory(database_url: str | None = None) -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(database_url), expire_on_commit=False
        )
    return _session_factory


async def init_db(database_url: str | None = None) -> None:
    """Creates tables for a genuinely brand-new database, then stamps it at
    the current Alembic head so a later `alembic upgrade head` correctly
    sees "already up to date" instead of trying to replay migrations against
    tables that already exist (see migrations/versions/2974c89766cf — the
    exact failure this prevents).

    Refuses to touch a database that already has application tables but that
    Alembic has no completed record of (no alembic_version table, or an
    empty one) — that state means the schema was bootstrapped by an earlier
    call to this function before Alembic migrations existed for it, and
    create_all() cannot safely reconcile it: SQLAlchemy's create_all() only
    creates missing tables, it never alters an existing one, so silently
    continuing would leave any column added by a later migration missing
    forever. Run `alembic upgrade head` to manage schema changes on an
    existing database; this function is only for a database that doesn't
    exist yet (fresh dev setup) or an isolated per-test database.
    """
    engine = get_engine(database_url)

    async with engine.connect() as conn:
        existing_tables = set(await conn.run_sync(lambda c: sa.inspect(c).get_table_names()))
        has_stamped_revision = await _has_stamped_revision(conn, existing_tables)

    has_app_tables = bool(existing_tables - {"alembic_version"})
    if has_app_tables and has_stamped_revision:
        return  # already Alembic-managed; do not mask un-applied migrations
    if has_app_tables and not has_stamped_revision:
        raise UnmanagedDatabaseError(
            f"Database at {engine.url!r} already has application tables "
            f"({sorted(existing_tables - {'alembic_version'})}) but no stamped "
            "Alembic revision. Reconcile it manually with Alembic instead of "
            "calling init_db()/create_all() again — see "
            "docs/development.md#reconciling-a-pre-alembic-database."
        )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _stamp_head(conn)


async def _has_stamped_revision(conn: AsyncConnection, existing_tables: set[str]) -> bool:
    if "alembic_version" not in existing_tables:
        return False
    result = await conn.execute(sa.text("SELECT COUNT(*) FROM alembic_version"))
    return (result.scalar() or 0) > 0


async def _stamp_head(conn: AsyncConnection) -> None:
    """Writes the current migration head into alembic_version directly
    (matching Alembic's own single-row table shape) rather than invoking
    Alembic's command API — that API runs migrations/env.py, which calls
    asyncio.run() and would fail here since init_db() already runs inside an
    active event loop (FastAPI lifespan, the CLI, or a test fixture)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(_PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_PROJECT_ROOT / "migrations"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    if head is None:
        return  # no migrations exist yet; nothing to stamp

    await conn.execute(
        sa.text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "version_num VARCHAR(32) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        )
    )
    await conn.execute(sa.text("DELETE FROM alembic_version"))
    await conn.execute(sa.text("INSERT INTO alembic_version (version_num) VALUES (:v)"), {"v": head})


async def reset_engine() -> None:
    """Used by tests to force a fresh engine/session factory per test database."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session

"""app.database.connection.init_db() safety behavior: a fresh database gets
created and stamped at the current Alembic head; a database that already has
application tables but no stamped Alembic revision (the exact real-world
drift diagnosed — tables bootstrapped by create_all() before Alembic ever
ran) is refused rather than silently left half-migrated. Every test uses its
own tmp_path database file — never the developer's real jarvis.db."""
from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.database import connection as db_connection
from app.database.models import Base


@pytest.fixture(autouse=True)
async def _reset_engine_singleton():
    """db_connection keeps a module-level engine singleton — every test here
    constructs its own database, so the singleton must not leak across tests
    (or point at the real default database_url from a prior test)."""
    await db_connection.reset_engine()
    yield
    await db_connection.reset_engine()


async def test_init_db_stamps_fresh_database_at_current_head(tmp_path):
    db_path = tmp_path / "fresh_app.db"
    url = f"sqlite+aiosqlite:///{db_path}"

    await db_connection.init_db(url)

    con = sqlite3.connect(str(db_path))
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        version = con.execute("SELECT version_num FROM alembic_version").fetchone()
    finally:
        con.close()

    assert "users" in tables
    assert "evidence" in tables
    assert version is not None and version[0]


async def test_init_db_is_idempotent_once_it_has_stamped_a_database(tmp_path):
    db_path = tmp_path / "idempotent.db"
    url = f"sqlite+aiosqlite:///{db_path}"

    await db_connection.init_db(url)
    await db_connection.reset_engine()
    await db_connection.init_db(url)  # must not raise, must not re-run create_all


async def test_init_db_refuses_database_with_untracked_existing_tables(tmp_path):
    """Simulates the pre-fix bootstrap path exactly: tables created directly
    via create_all with zero Alembic awareness — no alembic_version table at
    all. This is what init_db() used to do unconditionally."""
    db_path = tmp_path / "drifted_no_table.db"
    url = f"sqlite+aiosqlite:///{db_path}"

    raw_engine = create_async_engine(url)
    async with raw_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await raw_engine.dispose()

    with pytest.raises(db_connection.UnmanagedDatabaseError, match="no stamped"):
        await db_connection.init_db(url)


async def test_init_db_refuses_database_with_empty_alembic_version_table(tmp_path):
    """The exact state the real development database was found in: tables
    present, an alembic_version table present (created by the failed manual
    `alembic upgrade head` attempt), but zero rows in it — a migration never
    completed successfully, so no revision was ever stamped."""
    db_path = tmp_path / "drifted_empty_version.db"
    url = f"sqlite+aiosqlite:///{db_path}"

    raw_engine = create_async_engine(url)
    async with raw_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await raw_engine.dispose()

    con = sqlite3.connect(str(db_path))
    con.execute(
        "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL, "
        "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
    )
    con.commit()
    con.close()

    with pytest.raises(db_connection.UnmanagedDatabaseError):
        await db_connection.init_db(url)


def test_init_db_does_not_touch_a_properly_alembic_managed_database(tmp_path, monkeypatch):
    """A database already correctly stamped (by a real `alembic upgrade`,
    not init_db()) at an earlier revision must be left alone by init_db() —
    reconciling it forward is Alembic's job (`alembic upgrade head`), not
    create_all()'s.

    A plain (non-async) test: it drives both the sync Alembic command and
    init_db() (an async function) via asyncio.run() itself, sequentially —
    never inside an already-running event loop. See test_migrations.py's
    module docstring for why DATABASE_URL must be set via monkeypatch, not
    just Config.set_main_option().
    """
    import asyncio
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    from app.config.settings import get_settings

    project_root = Path(__file__).resolve().parents[1]
    db_path = tmp_path / "properly_managed.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()

    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "352f47664add")  # older revision, deliberately behind head

    cols_before = _columns(db_path, "evidence")
    assert "evidence_depth" not in cols_before

    async def _run() -> None:
        await db_connection.reset_engine()
        await db_connection.init_db(url)  # must be a silent no-op
        await db_connection.reset_engine()

    asyncio.run(_run())
    get_settings.cache_clear()

    cols_after = _columns(db_path, "evidence")
    assert cols_after == cols_before  # untouched — init_db() does not upgrade an existing DB


def _columns(db_path, table: str) -> set[str]:
    con = sqlite3.connect(str(db_path))
    try:
        return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    finally:
        con.close()


# --- Tests remain isolated from the real development database ----------------


async def test_session_factory_fixture_never_uses_the_real_database_url(session_factory):
    from app.config.settings import get_settings

    url = get_settings().database_url
    assert url != "sqlite+aiosqlite:///./jarvis.db"
    assert "jarvis.db" not in url

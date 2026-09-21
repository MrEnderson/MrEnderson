"""Migration regression tests. Every test here runs real Alembic commands,
but only ever against an isolated temp-file SQLite database created inside
`tmp_path` — never the developer's real jarvis.db, and never seed_demo.py or
a live API call. This is the regression suite for the exact failure diagnosed
in docs/development.md#reconciling-a-pre-alembic-database: a database whose
tables were bootstrapped by init_db()/create_all() before Alembic managed it,
so `alembic upgrade head` tried to replay the initial migration against
tables that already existed.

IMPORTANT: migrations/env.py re-derives `sqlalchemy.url` from
`get_settings().database_url` at the top of the script, UNCONDITIONALLY
overwriting whatever URL was set via `Config.set_main_option()` — that's by
design for the normal CLI flow (always honor .env's DATABASE_URL), but it
means a test cannot safely point Alembic at an isolated database just by
building a custom `Config` object. Every test below sets the `DATABASE_URL`
environment variable (via monkeypatch) to the tmp_path file and clears
get_settings()'s cache before calling into Alembic — skipping that step was
tried once while writing this suite and it silently ran against the real
development jarvis.db instead (caught before any write succeeded, since
SQLite DDL is atomic per-statement — the real db was verified unchanged
afterward, but the mistake is exactly why this warning exists here).

Tests that call `alembic.command.upgrade()` / `command.stamp()` (a sync API
that internally does its own `asyncio.run()` via migrations/env.py) are
plain `def` tests, not `async def` — calling it from inside a running event
loop (as an async test would have) raises "asyncio.run() cannot be called
from a running event loop".
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.config.settings import get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_OLD_SCHEMA_REVISION = "352f47664add"  # the "evidence and usage records" migration —
# exactly the revision the real development database was found to physically
# match (tables present, but no columns from any later migration).


def _alembic_config(monkeypatch, db_path: Path) -> Config:
    """Points BOTH the Config object and (critically) the DATABASE_URL env
    var that migrations/env.py actually reads at the tmp_path database."""
    url = f"sqlite+aiosqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _tables(db_path: Path) -> set[str]:
    con = sqlite3.connect(str(db_path))
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()


def _columns(db_path: Path, table: str) -> set[str]:
    con = sqlite3.connect(str(db_path))
    try:
        return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    finally:
        con.close()


# --- 1. Fresh database migrates base -> head ---------------------------------


def test_fresh_database_migrates_base_to_head(tmp_path, monkeypatch):
    db_path = tmp_path / "fresh.db"
    command.upgrade(_alembic_config(monkeypatch, db_path), "head")

    tables = _tables(db_path)
    assert {"users", "workspaces", "projects", "tasks", "evidence", "usage_records", "alembic_version"} <= tables

    con = sqlite3.connect(str(db_path))
    try:
        version = con.execute("SELECT version_num FROM alembic_version").fetchone()
    finally:
        con.close()
    assert version is not None
    get_settings.cache_clear()


# --- 2. Migration head contains evidence_depth --------------------------------


def test_migration_head_contains_evidence_depth_and_source_quality(tmp_path, monkeypatch):
    db_path = tmp_path / "head.db"
    command.upgrade(_alembic_config(monkeypatch, db_path), "head")

    cols = _columns(db_path, "evidence")
    assert "evidence_depth" in cols
    assert "source_quality" in cols
    get_settings.cache_clear()


# --- 3. + 7. Existing migration-managed DB upgrades to head, preserving data -


def test_existing_migration_managed_database_upgrades_to_head_preserving_data(tmp_path, monkeypatch):
    """Reproduces the diagnosed real-world state: a database already
    correctly stamped at an EARLIER revision (not the drifted/unstamped
    case — that's covered separately in test_database_connection.py),
    upgrading cleanly to head without losing existing rows."""
    db_path = tmp_path / "existing.db"
    cfg = _alembic_config(monkeypatch, db_path)
    command.upgrade(cfg, _OLD_SCHEMA_REVISION)

    con = sqlite3.connect(str(db_path))
    con.execute(
        "INSERT INTO users (id, email, created_at, updated_at) VALUES "
        "('u1', 'x@example.com', '2026-01-01T00:00:00', '2026-01-01T00:00:00')"
    )
    con.execute(
        "INSERT INTO workspaces (id, user_id, name, created_at, updated_at) VALUES "
        "('w1', 'u1', 'WS', '2026-01-01T00:00:00', '2026-01-01T00:00:00')"
    )
    con.execute(
        "INSERT INTO projects (id, workspace_id, name, status, created_at, updated_at) VALUES "
        "('p1', 'w1', 'Proj', 'ACTIVE', '2026-01-01T00:00:00', '2026-01-01T00:00:00')"
    )
    con.execute(
        "INSERT INTO tasks (id, project_id, agent_type, title, status, priority, "
        "requires_approval, retry_count, created_at, updated_at) VALUES "
        "('t1', 'p1', 'research', 'Task', 'PENDING', 'NORMAL', 0, 0, "
        "'2026-01-01T00:00:00', '2026-01-01T00:00:00')"
    )
    con.execute(
        "INSERT INTO evidence (id, workspace_id, project_id, task_id, claim, retrieved_at, "
        "evidence_type, confidence, verification_status, created_at) VALUES "
        "('e1', 'w1', 'p1', 't1', 'a real claim', '2026-01-01T00:00:00', 'OTHER', 0.5, "
        "'RETRIEVED', '2026-01-01T00:00:00')"
    )
    con.commit()
    con.close()

    command.upgrade(cfg, "head")

    cols = _columns(db_path, "evidence")
    assert "source_quality" in cols
    assert "evidence_depth" in cols

    con = sqlite3.connect(str(db_path))
    try:
        row = con.execute(
            "SELECT id, claim, source_quality, evidence_depth FROM evidence WHERE id = 'e1'"
        ).fetchone()
    finally:
        con.close()

    assert row == ("e1", "a real claim", "UNKNOWN", "SEARCH_SNIPPET")  # preserved + backfilled
    get_settings.cache_clear()


# --- 6. Migration chain has exactly one head ----------------------------------
# (Pure ScriptDirectory graph inspection — no database URL involved at all,
# so no DATABASE_URL override is needed for these two.)


def test_migration_chain_has_exactly_one_head():
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1


def test_migration_chain_is_fully_linked_to_base():
    """Every revision must be reachable by walking down_revision back to
    base — guards against an orphaned/disconnected migration file."""
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    revisions = list(script.walk_revisions(base="base", head=head))
    assert len(revisions) == len(list(script.walk_revisions()))

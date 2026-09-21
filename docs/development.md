# Development Guide

## Prerequisites

- Windows with PowerShell.
- Python. The build spec requested 3.13; this environment only had **3.14**
  installed (no 3.13 available via `py -0p`), so the project was built and
  verified against 3.14. It should also work on 3.11–3.13; nothing in the
  codebase is 3.14-specific.

## Setup

```powershell
cd jarvis-os
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# edit .env: set OPENAI_API_KEY to use the live provider, or leave it blank
# to run entirely on the deterministic MockProvider (no network, no cost).
```

## Database

SQLite by default (`DATABASE_URL=sqlite+aiosqlite:///./jarvis.db`), Postgres in
production by changing `DATABASE_URL` to a `postgresql+psycopg://...` URL —
nothing else in the code changes (SQLAlchemy async engine + Alembic both work
against either).

```powershell
python scripts/init_db.py       # create tables directly, only for a brand-new database
alembic upgrade head             # apply versioned migrations (preferred; required for an existing database)
alembic revision --autogenerate -m "describe your change"   # after editing models.py
```

`scripts/init_db.py` (and the API/CLI's own startup) call
`app.database.connection.init_db()`, which creates tables via
`Base.metadata.create_all()` **only for a database that doesn't exist yet**,
and stamps it at the current Alembic head immediately afterward so a later
`alembic upgrade head` correctly sees "already up to date." If the database
already has application tables, `init_db()` checks whether Alembic has a
stamped revision for it:

- Stamped → it's already Alembic-managed; `init_db()` does nothing (schema
  changes from here are `alembic upgrade head`'s job).
- Not stamped (no `alembic_version` table, or an empty one) → `init_db()`
  raises `UnmanagedDatabaseError` instead of silently doing nothing. This is
  deliberate: `create_all()` never alters an existing table, so silently
  continuing would leave any column added by a later migration permanently
  missing with no indication anything was wrong.

### Reconciling a pre-Alembic database

If you hit `UnmanagedDatabaseError`, or `alembic upgrade head` itself fails
with `table ... already exists`, your database's tables were created by
`init_db()`/`create_all()` before Alembic ever tracked it (this was possible
before the check above existed). Do **not** run `alembic stamp head` — that
only works if the schema already matches head exactly, which is not
guaranteed. Instead:

1. Inspect the physical schema (`PRAGMA table_info(<table>)` for each table)
   and compare it against `migrations/versions/*.py` to find which
   revision's cumulative effect it actually matches.
2. Stamp exactly that revision — not head:
   ```powershell
   alembic stamp <revision-that-schema-actually-matches>
   ```
3. Then apply the rest normally:
   ```powershell
   alembic upgrade head
   ```

This lets Alembic apply only the migrations genuinely missing from the
physical schema, preserving all existing data. See `tests/test_migrations.py`
and `tests/test_database_connection.py` for the regression coverage (both
run only against isolated `tmp_path` databases, never your real one).

## Running

```powershell
# API
uvicorn app.main:app --reload
# then: curl http://127.0.0.1:8000/health

# CLI
python -m app.main

# Non-interactive end-to-end demo
python scripts/seed_demo.py
python scripts/seed_demo.py "Research the children's colouring-book market and identify three possible product opportunities."
```

## Testing

```powershell
pytest -q
```

44 tests, all runnable offline against the `MockProvider` and a fresh
temp-file SQLite database per test (see `tests/conftest.py`) — no
`OPENAI_API_KEY` required, and tests never touch your local `jarvis.db`.
`pyproject.toml` sets `asyncio_mode = "auto"` so async test functions need no
extra markers.

Covered: agent registry, individual agent I/O schemas, task creation, the
state machine (valid/invalid transitions), dependency enforcement, parallel
independent-task execution, the QA retry loop (success and max-retry-exhausted
paths), permission enforcement, approval request/approve/reject, memory
create/retrieve/workspace-isolation, audit events, and the FastAPI endpoints
(health, workspace/project creation, validation errors, the full `/chat`
pipeline, and the approval endpoints).

## Adding a migration after a model change

```powershell
# edit app/database/models.py, then:
alembic revision --autogenerate -m "add X column to Y"
alembic upgrade head
```

## Configuration reference

All settings live in `app/config/settings.py` and are read from environment
variables / `.env` — see `.env.example` for the full list, including
`MAX_AGENT_RETRIES`, `MAX_CONCURRENT_AGENTS`, `MAX_TASKS_PER_RUN`, and
per-agent model overrides (`JARVIS_MODEL`, `RESEARCH_MODEL`, etc.).

## Known deviations from a from-scratch ideal

- **Python 3.14, not 3.13** — see Prerequisites above.
- **`pydantic`/`fastapi`/`sqlalchemy`/etc. pinned to the newest versions that
  ship a prebuilt Windows wheel for Python 3.14** at build time, not the
  versions originally listed in the spec — the spec's exact pins (e.g.
  `pydantic==2.10.4`) do not have a `cp314` wheel and fail to build from
  source in this environment (PyO3 doesn't yet support 3.14 at the pin's
  release). See `requirements.txt` for the resolved, verified-working set.

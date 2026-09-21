"""Create all database tables for the configured DATABASE_URL.

Usage: python scripts/init_db.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.connection import init_db  # noqa: E402
from app.utils.logging import configure_logging, get_logger  # noqa: E402


async def main() -> None:
    configure_logging("INFO")
    logger = get_logger(__name__)
    await init_db()
    logger.info("database_initialized")
    print("Database initialized.")


if __name__ == "__main__":
    asyncio.run(main())

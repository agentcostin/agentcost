"""
Database Connection Factory — Single entry point for the AgentCost data layer.

Configuration via environment variables:

  SQLite (default):
    AGENTCOST_DB=/path/to/benchmarks.db
    (or just leave unset — defaults to ~/.agentcost/benchmarks.db)

  PostgreSQL:
    AGENTCOST_DATABASE_URL=postgresql://user:pass@host:5432/agentcost

Logic:
  - If AGENTCOST_DATABASE_URL is set → PostgresAdapter
  - Otherwise → SQLiteAdapter using AGENTCOST_DB path

Usage:
    from agentcost.data.connection import get_db
    db = get_db()
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .adapter import DatabaseAdapter

# Module-level singleton
_db: DatabaseAdapter | None = None


def _default_sqlite_path() -> str:
    return os.environ.get(
        "AGENTCOST_DB",
        os.path.join(os.path.expanduser("~"), ".agentcost", "benchmarks.db"),
    )


def get_db() -> DatabaseAdapter:
    """Get or create the database adapter singleton.

    Thread-safe for SQLite (each call in SQLiteAdapter creates its own connection).
    Thread-safe for Postgres (uses ThreadedConnectionPool).
    """
    global _db
    if _db is not None:
        return _db

    pg_url = os.environ.get("AGENTCOST_DATABASE_URL")

    if pg_url:
        from .postgres_adapter import PostgresAdapter

        _db = PostgresAdapter(
            dsn=pg_url,
            min_connections=int(os.environ.get("AGENTCOST_PG_MIN_CONN", "2")),
            max_connections=int(os.environ.get("AGENTCOST_PG_MAX_CONN", "10")),
        )
    else:
        from .sqlite_adapter import SQLiteAdapter

        _db = SQLiteAdapter(db_path=_default_sqlite_path())

    return _db


def reset_db() -> None:
    """Close and discard the current adapter. Used in tests or reconfiguration."""
    global _db
    if _db:
        _db.close()
    _db = None


def set_db(adapter: DatabaseAdapter) -> None:
    """Inject a specific adapter. Useful for tests with in-memory SQLite."""
    global _db
    if _db:
        _db.close()
    _db = adapter

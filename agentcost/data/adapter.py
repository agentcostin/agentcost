"""
Database Adapter — Abstract interface for AgentCost data layer.

Both SQLiteAdapter and PostgresAdapter implement this contract.
All SQL is written with `?` placeholders (SQLite style).
The Postgres adapter auto-translates to `%s` at execution time.

Usage:
    from agentcost.data.connection import get_db
    db = get_db()
    rows = db.fetch_all("SELECT * FROM trace_events WHERE project=?", ("my-app",))
"""
from __future__ import annotations

import abc
from contextlib import contextmanager
from typing import Any, Iterator, Sequence


class Row(dict):
    """Dict subclass that also supports attribute-style access (row.column_name).
    Mirrors sqlite3.Row behaviour so existing code using dict(row) still works."""
    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"Row has no column '{key}'")


class DatabaseAdapter(abc.ABC):
    """Abstract base class for database backends."""

    # ── Query methods ────────────────────────────────────────────

    @abc.abstractmethod
    def execute(self, sql: str, params: Sequence = ()) -> None:
        """Execute a write query (INSERT, UPDATE, DELETE). Auto-commits."""

    @abc.abstractmethod
    def fetch_one(self, sql: str, params: Sequence = ()) -> Row | None:
        """Execute a query and return the first row as a Row dict, or None."""

    @abc.abstractmethod
    def fetch_all(self, sql: str, params: Sequence = ()) -> list[Row]:
        """Execute a query and return all rows as a list of Row dicts."""

    @abc.abstractmethod
    def executescript(self, sql: str) -> None:
        """Execute multiple SQL statements (DDL). Used for schema init."""

    # ── Transaction support ──────────────────────────────────────

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Context manager for explicit transactions.
        Default implementation is a no-op (each execute auto-commits).
        Override in adapters that support real transactions."""
        yield

    # ── Lifecycle ────────────────────────────────────────────────

    def close(self) -> None:
        """Release connections. Override if adapter holds a pool."""
        pass

    @abc.abstractmethod
    def is_postgres(self) -> bool:
        """Returns True if this is a PostgreSQL backend."""

    # ── SQL portability helpers ───────────────────────────────────

    @staticmethod
    def translate_placeholders(sql: str) -> str:
        """Convert `?` placeholders to `%s` for psycopg2.
        Naive but sufficient — AgentCost SQL never uses `?` in string literals."""
        return sql.replace("?", "%s")

    @staticmethod
    def translate_upsert(sql: str) -> str:
        """Convert `INSERT OR REPLACE INTO table (...)` to Postgres-compatible
        `INSERT INTO table (...) ... ON CONFLICT DO UPDATE`.
        Only needed for BenchmarkStore.save_run_summary — handled there explicitly."""
        return sql.replace("INSERT OR REPLACE INTO", "INSERT INTO")

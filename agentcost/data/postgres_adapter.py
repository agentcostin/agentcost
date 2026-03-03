"""
PostgreSQL Adapter — Enterprise backend for AgentCost.

Used for: Cloud SaaS, enterprise deployments, multi-tenant.
Requires: psycopg2-binary (pip install psycopg2-binary)

Key differences from SQLite handled automatically:
  - `?` placeholders → `%s`
  - `INSERT OR REPLACE` → `INSERT ... ON CONFLICT DO UPDATE` (handled in store layer)
  - Connection pooling with ThreadedConnectionPool
  - SERIALIZABLE isolation for budget enforcement transactions

Config via env:
  AGENTCOST_DATABASE_URL=postgresql://user:pass@host:5432/agentcost
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Iterator, Sequence

from .adapter import DatabaseAdapter, Row


def _translate_sql(sql: str) -> str:
    """Translate SQLite SQL to PostgreSQL dialect.

    Handles:
      - `?` → `%s` (parameter placeholders)
      - `AUTOINCREMENT` → (removed, SERIAL handles it)
      - `INTEGER PRIMARY KEY AUTOINCREMENT` → `SERIAL PRIMARY KEY`

    Does NOT handle INSERT OR REPLACE — that's dealt with explicitly
    in the store layer since it needs table-specific ON CONFLICT clauses.
    """
    # Placeholder swap: ? → %s
    # Only swap ? that aren't inside quotes. Since AgentCost SQL never
    # puts ? inside string literals, a simple replace is safe.
    out = sql.replace("?", "%s")

    # DDL translations for executescript()
    out = re.sub(
        r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
        "SERIAL PRIMARY KEY",
        out,
        flags=re.IGNORECASE,
    )
    # SQLite's REAL → PostgreSQL DOUBLE PRECISION (optional, REAL also works in PG)
    # We keep REAL since Postgres supports it natively.
    return out


def _translate_executescript(sql: str) -> list[str]:
    """Split a multi-statement SQL script into individual statements.

    SQLite's executescript() runs everything in one call.
    psycopg2 needs separate execute() calls, or one execute with all statements.
    We just run the full translated script via execute().
    """
    translated = _translate_sql(sql)
    return [translated]


class PostgresAdapter(DatabaseAdapter):
    """PostgreSQL backend with connection pooling."""

    def __init__(self, dsn: str, min_connections: int = 2, max_connections: int = 10):
        try:
            import psycopg2
            import psycopg2.pool
            import psycopg2.extras
        except ImportError:
            raise ImportError(
                "PostgreSQL support requires psycopg2.\n"
                "Install with: pip install psycopg2-binary"
            )

        self._dsn = dsn
        self._psycopg2 = psycopg2
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            min_connections, max_connections, dsn
        )

    def _get_conn(self):
        conn = self._pool.getconn()
        conn.autocommit = True
        return conn

    def _put_conn(self, conn):
        self._pool.putconn(conn)

    # ── Query methods ────────────────────────────────────────────

    def execute(self, sql: str, params: Sequence = ()) -> None:
        translated = _translate_sql(sql)
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(translated, params)
        finally:
            self._put_conn(conn)

    def fetch_one(self, sql: str, params: Sequence = ()) -> Row | None:
        translated = _translate_sql(sql)
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(translated, params)
                cols = [desc[0] for desc in cur.description] if cur.description else []
                row = cur.fetchone()
                if row is None:
                    return None
                return Row(zip(cols, row))
        finally:
            self._put_conn(conn)

    def fetch_all(self, sql: str, params: Sequence = ()) -> list[Row]:
        translated = _translate_sql(sql)
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(translated, params)
                cols = [desc[0] for desc in cur.description] if cur.description else []
                return [Row(zip(cols, r)) for r in cur.fetchall()]
        finally:
            self._put_conn(conn)

    def executescript(self, sql: str) -> None:
        """Execute a multi-statement DDL script."""
        translated = _translate_sql(sql)
        conn = self._get_conn()
        try:
            # Temporarily disable autocommit for DDL script
            conn.autocommit = False
            try:
                with conn.cursor() as cur:
                    cur.execute(translated)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.autocommit = True
        finally:
            self._put_conn(conn)

    # ── Transactions ─────────────────────────────────────────────

    @contextmanager
    def transaction(self, isolation_level: str = "READ COMMITTED") -> Iterator[None]:
        """Context manager for explicit transactions.

        For budget enforcement, use isolation_level='SERIALIZABLE' to prevent
        race conditions where two agents both pass budget check before
        either records its cost.
        """
        conn = self._get_conn()
        conn.autocommit = False
        try:
            with conn.cursor() as cur:
                cur.execute(f"SET TRANSACTION ISOLATION LEVEL {isolation_level}")
            yield
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.autocommit = True
            self._put_conn(conn)

    # ── Lifecycle ────────────────────────────────────────────────

    def close(self) -> None:
        if self._pool:
            self._pool.closeall()

    def is_postgres(self) -> bool:
        return True

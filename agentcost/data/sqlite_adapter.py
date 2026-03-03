"""
SQLite Adapter — Default backend for AgentCost.

Used for: CLI benchmarks, self-hosted deployments, development.
Zero external dependencies (uses Python's built-in sqlite3).

All SQL uses `?` placeholders natively — no translation needed.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator, Sequence

from .adapter import DatabaseAdapter, Row


class SQLiteAdapter(DatabaseAdapter):
    """SQLite backend using a single file database."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ── Query methods ────────────────────────────────────────────

    def execute(self, sql: str, params: Sequence = ()) -> None:
        with self._conn() as conn:
            conn.execute(sql, params)

    def fetch_one(self, sql: str, params: Sequence = ()) -> Row | None:
        with self._conn() as conn:
            r = conn.execute(sql, params).fetchone()
            return Row(r) if r else None

    def fetch_all(self, sql: str, params: Sequence = ()) -> list[Row]:
        with self._conn() as conn:
            return [Row(r) for r in conn.execute(sql, params).fetchall()]

    def executescript(self, sql: str) -> None:
        with self._conn() as conn:
            conn.executescript(sql)

    # ── Transaction ──────────────────────────────────────────────

    @contextmanager
    def transaction(self) -> Iterator[None]:
        conn = self._conn()
        try:
            yield
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Meta ─────────────────────────────────────────────────────

    def is_postgres(self) -> bool:
        return False

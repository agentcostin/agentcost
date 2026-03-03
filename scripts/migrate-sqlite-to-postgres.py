#!/usr/bin/env python3
"""
Migrate data from SQLite to PostgreSQL.

Reads all rows from the SQLite database and batch-inserts into Postgres.
Assumes Postgres tables already exist (run schema migrations first).

Usage:
    # 1. Ensure Postgres schema is ready
    python -m agentcost.data.migrations.migrate

    # 2. Run data migration
    python scripts/migrate-sqlite-to-postgres.py

    # Or with explicit paths:
    python scripts/migrate-sqlite-to-postgres.py \
        --sqlite ~/.agentcost/benchmarks.db \
        --pg postgresql://user:pass@localhost:5432/agentcost

Environment variables (alternative to CLI args):
    AGENTCOST_DB              = SQLite path
    AGENTCOST_DATABASE_URL    = PostgreSQL connection string
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time


BATCH_SIZE = 500  # Rows per INSERT


# ── Tables and their columns (excluding auto-increment id) ───────────────────

TABLES = {
    "trace_events": [
        "trace_id", "project", "agent_id", "session_id", "model", "provider",
        "input_tokens", "output_tokens", "cost", "latency_ms", "status",
        "error", "metadata", "timestamp",
    ],
    "budgets": [
        "project", "daily_limit", "monthly_limit", "total_limit",
        "alert_threshold", "created_at", "updated_at",
    ],
    "task_results": [
        "run_id", "task_id", "model", "sector", "occupation",
        "quality_score", "max_payment", "actual_payment",
        "input_tokens", "output_tokens", "llm_cost", "eval_cost", "total_cost",
        "duration_seconds", "roi", "work_output", "timestamp",
    ],
    "run_summaries": [
        "run_id", "model", "total_tasks", "completed_tasks",
        "avg_quality", "total_income", "total_cost", "net_profit", "profit_margin",
        "avg_roi", "total_input_tokens", "total_output_tokens",
        "total_duration", "started_at", "finished_at",
    ],
}


def migrate_table(sqlite_conn, pg_conn, table: str, columns: list[str], verbose: bool):
    """Copy all rows from SQLite table to PostgreSQL table."""
    # Check if SQLite table exists
    exists = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not exists:
        if verbose:
            print(f"   ⏭  {table}: table not found in SQLite, skipping")
        return 0

    # Count rows
    count = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    if count == 0:
        if verbose:
            print(f"   ⏭  {table}: 0 rows, skipping")
        return 0

    # Read all rows
    col_list = ", ".join(columns)
    rows = sqlite_conn.execute(f"SELECT {col_list} FROM {table}").fetchall()

    # Build INSERT statement
    placeholders = ", ".join(["%s"] * len(columns))
    insert_sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"

    # Batch insert
    pg_cursor = pg_conn.cursor()
    migrated = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        values = [tuple(row) for row in batch]
        pg_cursor.executemany(insert_sql, values)
        pg_conn.commit()
        migrated += len(batch)

    if verbose:
        print(f"   ✓  {table}: {migrated} rows migrated")
    return migrated


def main():
    parser = argparse.ArgumentParser(description="Migrate AgentCost data from SQLite to PostgreSQL")
    parser.add_argument(
        "--sqlite",
        default=os.environ.get("AGENTCOST_DB",
                               os.path.join(os.path.expanduser("~"), ".agentcost", "benchmarks.db")),
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--pg",
        default=os.environ.get("AGENTCOST_DATABASE_URL"),
        help="PostgreSQL connection string",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated")
    args = parser.parse_args()

    if not args.pg:
        print("ERROR: No PostgreSQL URL. Set AGENTCOST_DATABASE_URL or pass --pg.")
        sys.exit(1)

    if not os.path.exists(args.sqlite):
        print(f"ERROR: SQLite database not found: {args.sqlite}")
        sys.exit(1)

    # Connect
    sqlite_conn = sqlite3.connect(args.sqlite)
    sqlite_conn.row_factory = sqlite3.Row

    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)

    pg_conn = psycopg2.connect(args.pg)

    print("\n🔄 AgentCost Data Migration: SQLite → PostgreSQL")
    print(f"   Source: {args.sqlite}")
    print(f"   Target: {args.pg.split('@')[-1] if '@' in args.pg else args.pg}\n")

    if args.dry_run:
        print("   [DRY RUN — no data will be written]\n")
        for table in TABLES:
            exists = sqlite_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if exists:
                count = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"   {table}: {count} rows")
            else:
                print(f"   {table}: not found")
        print()
        sqlite_conn.close()
        pg_conn.close()
        return

    start = time.time()
    total_rows = 0

    for table, columns in TABLES.items():
        total_rows += migrate_table(sqlite_conn, pg_conn, table, columns, verbose=True)

    elapsed = time.time() - start
    print(f"\n   ✓ Migration complete: {total_rows} total rows in {elapsed:.1f}s\n")

    # Reset Postgres sequences to max(id) + 1
    pg_cursor = pg_conn.cursor()
    for table in TABLES:
        try:
            pg_cursor.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE(MAX(id), 1)) FROM {table}"
            )
            pg_conn.commit()
        except Exception:
            pg_conn.rollback()  # Table might not have rows yet

    sqlite_conn.close()
    pg_conn.close()


if __name__ == "__main__":
    main()

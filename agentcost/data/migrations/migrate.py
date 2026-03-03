"""
Database Migration Runner — Applies numbered SQL migrations to PostgreSQL.

Usage:
    # Apply all pending migrations
    python -m agentcost.data.migrations.migrate

    # Or run directly (no package dependency needed):
    python agentcost/data/migrations/migrate.py

    # Check current version
    python -m agentcost.data.migrations.migrate --status

    # Apply up to a specific version
    python -m agentcost.data.migrations.migrate --target 1

Migrations are SQL files in this directory named NNN_description.sql.
Each migration must INSERT into schema_version with its version number.
The runner skips migrations whose version is already in schema_version.
"""
from __future__ import annotations

import glob
import os
import re
import sys

# Load .env from project root (agentcost-phase2/.env)
try:
    from dotenv import load_dotenv
    _migrate_dir = os.path.dirname(os.path.abspath(__file__))
    _root = os.path.normpath(os.path.join(_migrate_dir, "..", "..", ".."))
    load_dotenv(os.path.join(_root, ".env"))
except ImportError:
    pass

MIGRATIONS_DIR = os.path.dirname(os.path.abspath(__file__))


def _get_migration_files() -> list[tuple[int, str, str]]:
    """Return sorted list of (version, filename, full_path) tuples."""
    files = glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql"))
    result = []
    for f in files:
        basename = os.path.basename(f)
        m = re.match(r"^(\d+)_(.+)\.sql$", basename)
        if m:
            result.append((int(m.group(1)), basename, f))
    return sorted(result, key=lambda x: x[0])


def _get_applied_versions(conn) -> set[int]:
    """Get the set of already-applied migration versions."""
    try:
        cur = conn.cursor()
        cur.execute("SELECT version FROM schema_version ORDER BY version")
        return {row[0] for row in cur.fetchall()}
    except Exception:
        conn.rollback()
        # schema_version table doesn't exist yet — no migrations applied
        return set()


def migrate(dsn: str, target: int | None = None, verbose: bool = True):
    """Apply pending migrations to the given PostgreSQL database.

    Args:
        dsn: PostgreSQL connection string
        target: Apply up to this version (None = apply all)
        verbose: Print progress
    """
    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)

    conn = psycopg2.connect(dsn)
    conn.autocommit = False

    applied = _get_applied_versions(conn)
    migrations = _get_migration_files()

    if verbose:
        print("\n🗄️  AgentCost Database Migration")
        print(f"   Database: {dsn.split('@')[-1] if '@' in dsn else dsn}")
        print(f"   Applied versions: {sorted(applied) or 'none'}")
        print(f"   Available migrations: {len(migrations)}\n")

    pending = [
        (ver, name, path) for ver, name, path in migrations
        if ver not in applied and (target is None or ver <= target)
    ]

    if not pending:
        if verbose:
            print("   ✓ Database is up to date.\n")
        conn.close()
        return

    for ver, name, path in pending:
        if verbose:
            print(f"   Applying {name} ... ", end="", flush=True)
        try:
            with open(path, "r") as f:
                sql = f.read()
            cur = conn.cursor()
            cur.execute(sql)
            conn.commit()
            if verbose:
                print("✓")
        except Exception as e:
            conn.rollback()
            if verbose:
                print(f"✗\n   ERROR: {e}")
            conn.close()
            sys.exit(1)

    if verbose:
        print(f"\n   ✓ Applied {len(pending)} migration(s).\n")

    conn.close()


def status(dsn: str):
    """Print the current migration status."""
    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 not installed.")
        sys.exit(1)

    conn = psycopg2.connect(dsn)
    applied = _get_applied_versions(conn)
    migrations = _get_migration_files()

    print("\n🗄️  Migration Status\n")
    for ver, name, _ in migrations:
        status_str = "✓ applied" if ver in applied else "○ pending"
        print(f"   {status_str}  {name}")
    print()

    conn.close()


# ── CLI entry point ──────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="AgentCost Database Migrations")
    parser.add_argument(
        "--dsn",
        default=os.environ.get("AGENTCOST_DATABASE_URL"),
        help="PostgreSQL connection string (or set AGENTCOST_DATABASE_URL)",
    )
    parser.add_argument("--status", action="store_true", help="Show migration status")
    parser.add_argument("--target", type=int, help="Apply up to this version")

    args = parser.parse_args()

    if not args.dsn:
        print("ERROR: No database URL. Set AGENTCOST_DATABASE_URL or pass --dsn.")
        sys.exit(1)

    if args.status:
        status(args.dsn)
    else:
        migrate(args.dsn, target=args.target)


if __name__ == "__main__":
    main()

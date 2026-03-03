"""
Benchmark Store — Persistence for benchmark results.

Stores per-task results, per-run summaries, and model leaderboard data.
Refactored to use DatabaseAdapter (supports both SQLite and PostgreSQL).
"""
from __future__ import annotations

from dataclasses import dataclass

from .adapter import DatabaseAdapter
from .connection import get_db


@dataclass
class TaskResult:
    run_id: str
    task_id: str
    model: str
    sector: str
    occupation: str
    quality_score: float
    max_payment: float
    actual_payment: float
    input_tokens: int
    output_tokens: int
    llm_cost: float
    eval_cost: float
    total_cost: float
    duration_seconds: float
    roi: float  # actual_payment / total_cost
    work_output: str = ""
    timestamp: str = ""


@dataclass
class RunSummary:
    run_id: str
    model: str
    total_tasks: int
    completed_tasks: int
    avg_quality: float
    total_income: float
    total_cost: float
    net_profit: float
    profit_margin: float
    avg_roi: float
    total_input_tokens: int
    total_output_tokens: int
    total_duration: float
    started_at: str
    finished_at: str


# ── Schema DDL ───────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS task_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    model TEXT NOT NULL,
    sector TEXT,
    occupation TEXT,
    quality_score REAL,
    max_payment REAL,
    actual_payment REAL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    llm_cost REAL,
    eval_cost REAL,
    total_cost REAL,
    duration_seconds REAL,
    roi REAL,
    work_output TEXT,
    timestamp TEXT,
    org_id TEXT
);

CREATE TABLE IF NOT EXISTS run_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT UNIQUE NOT NULL,
    model TEXT NOT NULL,
    total_tasks INTEGER,
    completed_tasks INTEGER,
    avg_quality REAL,
    total_income REAL,
    total_cost REAL,
    net_profit REAL,
    profit_margin REAL,
    avg_roi REAL,
    total_input_tokens INTEGER,
    total_output_tokens INTEGER,
    total_duration REAL,
    started_at TEXT,
    finished_at TEXT,
    org_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_task_results_run ON task_results(run_id);
CREATE INDEX IF NOT EXISTS idx_task_results_model ON task_results(model);
CREATE INDEX IF NOT EXISTS idx_run_summaries_model ON run_summaries(model);
"""


class BenchmarkStore:
    """Benchmark data persistence.

    Works with any DatabaseAdapter backend (SQLite or PostgreSQL).
    """

    def __init__(self, db: DatabaseAdapter | None = None):
        self.db = db or get_db()
        self._init_db()

    def _init_db(self):
        self.db.executescript(_SCHEMA)

    # ── Write ────────────────────────────────────────────────────

    def save_task_result(self, result: TaskResult):
        self.db.execute(
            """INSERT INTO task_results (
                run_id, task_id, model, sector, occupation,
                quality_score, max_payment, actual_payment,
                input_tokens, output_tokens, llm_cost, eval_cost, total_cost,
                duration_seconds, roi, work_output, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.run_id, result.task_id, result.model, result.sector,
                result.occupation, result.quality_score, result.max_payment,
                result.actual_payment, result.input_tokens, result.output_tokens,
                result.llm_cost, result.eval_cost, result.total_cost,
                result.duration_seconds, result.roi, result.work_output,
                result.timestamp,
            ),
        )

    def save_run_summary(self, summary: RunSummary):
        """Save or update a run summary. Handles SQLite and Postgres upsert styles."""
        if self.db.is_postgres():
            self.db.execute(
                """INSERT INTO run_summaries (
                    run_id, model, total_tasks, completed_tasks,
                    avg_quality, total_income, total_cost, net_profit, profit_margin,
                    avg_roi, total_input_tokens, total_output_tokens,
                    total_duration, started_at, finished_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(run_id) DO UPDATE SET
                    model=EXCLUDED.model, total_tasks=EXCLUDED.total_tasks,
                    completed_tasks=EXCLUDED.completed_tasks, avg_quality=EXCLUDED.avg_quality,
                    total_income=EXCLUDED.total_income, total_cost=EXCLUDED.total_cost,
                    net_profit=EXCLUDED.net_profit, profit_margin=EXCLUDED.profit_margin,
                    avg_roi=EXCLUDED.avg_roi, total_input_tokens=EXCLUDED.total_input_tokens,
                    total_output_tokens=EXCLUDED.total_output_tokens,
                    total_duration=EXCLUDED.total_duration, started_at=EXCLUDED.started_at,
                    finished_at=EXCLUDED.finished_at""",
                (
                    summary.run_id, summary.model, summary.total_tasks,
                    summary.completed_tasks, summary.avg_quality, summary.total_income,
                    summary.total_cost, summary.net_profit, summary.profit_margin,
                    summary.avg_roi, summary.total_input_tokens,
                    summary.total_output_tokens, summary.total_duration,
                    summary.started_at, summary.finished_at,
                ),
            )
        else:
            # SQLite: INSERT OR REPLACE works natively
            self.db.execute(
                """INSERT OR REPLACE INTO run_summaries (
                    run_id, model, total_tasks, completed_tasks,
                    avg_quality, total_income, total_cost, net_profit, profit_margin,
                    avg_roi, total_input_tokens, total_output_tokens,
                    total_duration, started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    summary.run_id, summary.model, summary.total_tasks,
                    summary.completed_tasks, summary.avg_quality, summary.total_income,
                    summary.total_cost, summary.net_profit, summary.profit_margin,
                    summary.avg_roi, summary.total_input_tokens,
                    summary.total_output_tokens, summary.total_duration,
                    summary.started_at, summary.finished_at,
                ),
            )

    # ── Read ─────────────────────────────────────────────────────

    def get_run_results(self, run_id: str) -> list[dict]:
        return [
            dict(r) for r in self.db.fetch_all(
                "SELECT * FROM task_results WHERE run_id = ? ORDER BY timestamp",
                (run_id,),
            )
        ]

    def get_all_summaries(self, limit: int = 50) -> list[dict]:
        return [
            dict(r) for r in self.db.fetch_all(
                "SELECT * FROM run_summaries ORDER BY finished_at DESC LIMIT ?",
                (limit,),
            )
        ]

    def get_model_leaderboard(self) -> list[dict]:
        """Aggregate stats per model across all runs."""
        return [
            dict(r) for r in self.db.fetch_all("""
                SELECT
                    model,
                    COUNT(*) as total_runs,
                    ROUND(CAST(AVG(avg_quality) AS NUMERIC), 3) as avg_quality,
                    ROUND(CAST(AVG(avg_roi) AS NUMERIC), 2) as avg_roi,
                    ROUND(CAST(AVG(profit_margin) AS NUMERIC), 1) as avg_margin,
                    ROUND(CAST(SUM(total_income) AS NUMERIC), 2) as total_income,
                    ROUND(CAST(SUM(total_cost) AS NUMERIC), 4) as total_cost,
                    SUM(total_input_tokens) as total_input_tokens,
                    SUM(total_output_tokens) as total_output_tokens
                FROM run_summaries
                GROUP BY model
                ORDER BY avg_roi DESC
            """)
        ]

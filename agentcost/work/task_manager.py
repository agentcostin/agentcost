"""
Task Manager — loads GDPVal tasks and assigns them for benchmarking.
"""

from __future__ import annotations
import json
import os
import random
from dataclasses import dataclass

SAMPLE_TASKS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "sample-data", "tasks.jsonl"
)


@dataclass
class Task:
    task_id: str
    sector: str
    occupation: str
    prompt: str
    estimated_hours: float
    hourly_wage: float
    max_payment: float
    deliverable_type: str

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


class TaskManager:
    """Loads and manages the benchmark task dataset."""

    def __init__(self, tasks_path: str | None = None):
        self.tasks_path = tasks_path or os.environ.get(
            "AGENTCOST_TASKS", SAMPLE_TASKS_PATH
        )
        self.tasks: list[Task] = []
        self._load()

    def _load(self):
        path = self.tasks_path
        if not os.path.exists(path):
            # Try relative to cwd
            alt = os.path.join(os.getcwd(), "sample-data", "tasks.jsonl")
            if os.path.exists(alt):
                path = alt
            else:
                print(f"[TaskManager] Warning: Task file not found at {path}")
                return

        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    self.tasks.append(Task.from_dict(json.loads(line)))

        print(f"[TaskManager] Loaded {len(self.tasks)} tasks from {path}")

    def get_tasks(
        self,
        count: int | None = None,
        sector: str | None = None,
        shuffle: bool = True,
    ) -> list[Task]:
        """Get tasks, optionally filtered by sector."""
        pool = self.tasks
        if sector:
            pool = [t for t in pool if t.sector.lower() == sector.lower()]
        if shuffle:
            pool = list(pool)
            random.shuffle(pool)
        if count:
            pool = pool[:count]
        return pool

    def get_sectors(self) -> list[str]:
        return sorted(set(t.sector for t in self.tasks))

    def get_task_by_id(self, task_id: str) -> Task | None:
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        return None

    @property
    def total_value(self) -> float:
        return sum(t.max_payment for t in self.tasks)

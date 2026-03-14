"""
AgentCost Feedback — User feedback on LLM traces.

Attach thumbs-up/down, scores (1-5), and text comments to any trace.
Connects cost data to quality data — the missing link for optimization.

When you know which traces produce good results and which don't, you can:
- Measure quality per model: "GPT-4.1 gets 92% positive, Haiku gets 78%"
- Measure quality per prompt version: "V3 of support-bot gets better ratings"
- Find cost-quality sweet spots: "GPT-4.1-mini is 80% cheaper with only 5% lower quality"
- Feed into optimizer recommendations with real quality signals

Usage:
    from agentcost.feedback import get_feedback_service

    svc = get_feedback_service()

    # Simple thumbs up/down
    svc.submit("trace-abc-123", score=1, source="user")

    # Detailed feedback
    svc.submit("trace-abc-123", score=1, comment="Accurate and helpful",
               source="user", user_id="u-456", tags=["accurate", "complete"])

    # Get quality stats
    stats = svc.get_model_quality("gpt-4.1", project="support")
    # → {"positive_pct": 92.3, "avg_score": 0.87, "total_feedback": 240}
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("agentcost.feedback")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS trace_feedback (
    id              TEXT PRIMARY KEY,
    trace_id        TEXT NOT NULL,
    score           INTEGER NOT NULL,
    comment         TEXT DEFAULT '',
    source          TEXT DEFAULT 'user',
    user_id         TEXT DEFAULT '',
    tags            TEXT DEFAULT '[]',
    metadata        TEXT DEFAULT '{}',
    org_id          TEXT DEFAULT 'default',
    created_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fb_trace ON trace_feedback(trace_id);
CREATE INDEX IF NOT EXISTS idx_fb_org ON trace_feedback(org_id);
CREATE INDEX IF NOT EXISTS idx_fb_created ON trace_feedback(created_at);
CREATE INDEX IF NOT EXISTS idx_fb_score ON trace_feedback(score);
"""


@dataclass
class Feedback:
    """A single feedback record on a trace."""

    id: str
    trace_id: str
    score: int  # 1 = positive (thumbs up), 0 = neutral, -1 = negative (thumbs down)
    comment: str = ""
    source: str = "user"  # user, automated, eval, human-review
    user_id: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    org_id: str = "default"
    created_at: float = 0.0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "trace_id": self.trace_id,
            "score": self.score,
            "comment": self.comment,
            "source": self.source,
            "user_id": self.user_id,
            "tags": self.tags,
            "metadata": self.metadata,
            "org_id": self.org_id,
            "created_at": self.created_at,
        }


class FeedbackService:
    """Manages user feedback on LLM traces. Persisted to database."""

    def __init__(self, db=None):
        from ..data.connection import get_db

        self.db = db or get_db()
        self._init()

    def _init(self):
        self.db.executescript(_SCHEMA)

    # ── Submit ────────────────────────────────────────────────────

    def submit(
        self,
        trace_id: str,
        *,
        score: int,
        comment: str = "",
        source: str = "user",
        user_id: str = "",
        tags: list[str] | None = None,
        metadata: dict | None = None,
        org_id: str = "default",
    ) -> dict:
        """Submit feedback for a trace.

        Args:
            trace_id: The trace to attach feedback to.
            score: 1 (positive/thumbs-up), 0 (neutral), -1 (negative/thumbs-down).
            comment: Optional text comment.
            source: Who submitted — 'user', 'automated', 'eval', 'human-review'.
            user_id: Optional user identifier.
            tags: Optional tags like ['accurate', 'slow', 'hallucination'].
            metadata: Optional key-value metadata.
        """
        if score not in (-1, 0, 1):
            raise ValueError("Score must be -1, 0, or 1")

        fb = Feedback(
            id=uuid.uuid4().hex[:12],
            trace_id=trace_id,
            score=score,
            comment=comment,
            source=source,
            user_id=user_id,
            tags=tags or [],
            metadata=metadata or {},
            org_id=org_id,
        )

        self.db.execute(
            """INSERT INTO trace_feedback
               (id, trace_id, score, comment, source, user_id, tags,
                metadata, org_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fb.id,
                fb.trace_id,
                fb.score,
                fb.comment,
                fb.source,
                fb.user_id,
                json.dumps(fb.tags),
                json.dumps(fb.metadata),
                fb.org_id,
                fb.created_at,
            ),
        )
        logger.info(
            "Feedback submitted: trace=%s score=%d source=%s",
            trace_id,
            score,
            source,
        )
        return fb.to_dict()

    # ── Read ──────────────────────────────────────────────────────

    def get_feedback(self, feedback_id: str) -> dict | None:
        row = self.db.fetch_one(
            "SELECT * FROM trace_feedback WHERE id=?", (feedback_id,)
        )
        return self._row_to_dict(row) if row else None

    def get_trace_feedback(self, trace_id: str) -> list[dict]:
        """Get all feedback for a specific trace."""
        rows = self.db.fetch_all(
            "SELECT * FROM trace_feedback WHERE trace_id=? ORDER BY created_at DESC",
            (trace_id,),
        )
        return [self._row_to_dict(r) for r in rows]

    def list_feedback(
        self,
        *,
        project: str | None = None,
        model: str | None = None,
        score: int | None = None,
        source: str | None = None,
        since: str | None = None,
        limit: int = 100,
        org_id: str = "default",
    ) -> list[dict]:
        """List feedback with optional filters.

        Joins with trace_events to filter by project/model.
        """
        if project or model:
            sql = """SELECT f.* FROM trace_feedback f
                     JOIN trace_events t ON f.trace_id = t.trace_id
                     WHERE f.org_id=?"""
            params: list = [org_id]
            if project:
                sql += " AND t.project=?"
                params.append(project)
            if model:
                sql += " AND t.model=?"
                params.append(model)
        else:
            sql = "SELECT * FROM trace_feedback f WHERE f.org_id=?"
            params = [org_id]

        if score is not None:
            sql += " AND f.score=?"
            params.append(score)
        if source:
            sql += " AND f.source=?"
            params.append(source)
        if since:
            sql += " AND f.created_at>=?"
            params.append(float(since))

        sql += " ORDER BY f.created_at DESC LIMIT ?"
        params.append(limit)

        rows = self.db.fetch_all(sql, params)
        return [self._row_to_dict(r) for r in rows]

    def delete_feedback(self, feedback_id: str) -> bool:
        existing = self.db.fetch_one(
            "SELECT id FROM trace_feedback WHERE id=?", (feedback_id,)
        )
        if not existing:
            return False
        self.db.execute("DELETE FROM trace_feedback WHERE id=?", (feedback_id,))
        return True

    # ── Analytics ─────────────────────────────────────────────────

    def get_trace_score(self, trace_id: str) -> dict:
        """Get aggregated score for a trace."""
        row = self.db.fetch_one(
            """SELECT COUNT(*) as total,
                      SUM(CASE WHEN score = 1 THEN 1 ELSE 0 END) as positive,
                      SUM(CASE WHEN score = -1 THEN 1 ELSE 0 END) as negative,
                      SUM(CASE WHEN score = 0 THEN 1 ELSE 0 END) as neutral
               FROM trace_feedback WHERE trace_id=?""",
            (trace_id,),
        )
        if not row or row["total"] == 0:
            return {
                "trace_id": trace_id,
                "total": 0,
                "positive": 0,
                "negative": 0,
                "neutral": 0,
                "score": None,
            }
        return {
            "trace_id": trace_id,
            "total": row["total"],
            "positive": row["positive"],
            "negative": row["negative"],
            "neutral": row["neutral"],
            "score": round((row["positive"] - row["negative"]) / row["total"], 2),
        }

    def get_model_quality(self, model: str, project: str | None = None) -> dict:
        """Get quality stats for a model based on feedback.

        Returns positive %, average score, total feedback count.
        """
        if project:
            sql = """SELECT COUNT(*) as total,
                            SUM(CASE WHEN f.score = 1 THEN 1 ELSE 0 END) as positive,
                            SUM(CASE WHEN f.score = -1 THEN 1 ELSE 0 END) as negative
                     FROM trace_feedback f
                     JOIN trace_events t ON f.trace_id = t.trace_id
                     WHERE t.model=? AND t.project=?"""
            params = [model, project]
        else:
            sql = """SELECT COUNT(*) as total,
                            SUM(CASE WHEN f.score = 1 THEN 1 ELSE 0 END) as positive,
                            SUM(CASE WHEN f.score = -1 THEN 1 ELSE 0 END) as negative
                     FROM trace_feedback f
                     JOIN trace_events t ON f.trace_id = t.trace_id
                     WHERE t.model=?"""
            params = [model]

        row = self.db.fetch_one(sql, params)
        if not row or row["total"] == 0:
            return {
                "model": model,
                "total_feedback": 0,
                "positive_pct": 0,
                "negative_pct": 0,
                "avg_score": 0,
            }

        total = row["total"]
        positive = row["positive"]
        negative = row["negative"]
        return {
            "model": model,
            "total_feedback": total,
            "positive_pct": round(positive / total * 100, 1),
            "negative_pct": round(negative / total * 100, 1),
            "avg_score": round((positive - negative) / total, 3),
        }

    def get_quality_by_model(self, project: str | None = None) -> list[dict]:
        """Get quality breakdown across all models."""
        if project:
            sql = """SELECT t.model,
                            COUNT(*) as total,
                            SUM(CASE WHEN f.score = 1 THEN 1 ELSE 0 END) as positive,
                            SUM(CASE WHEN f.score = -1 THEN 1 ELSE 0 END) as negative,
                            ROUND(CAST(AVG(t.cost) AS NUMERIC), 6) as avg_cost
                     FROM trace_feedback f
                     JOIN trace_events t ON f.trace_id = t.trace_id
                     WHERE t.project=?
                     GROUP BY t.model ORDER BY positive DESC"""
            params = [project]
        else:
            sql = """SELECT t.model,
                            COUNT(*) as total,
                            SUM(CASE WHEN f.score = 1 THEN 1 ELSE 0 END) as positive,
                            SUM(CASE WHEN f.score = -1 THEN 1 ELSE 0 END) as negative,
                            ROUND(CAST(AVG(t.cost) AS NUMERIC), 6) as avg_cost
                     FROM trace_feedback f
                     JOIN trace_events t ON f.trace_id = t.trace_id
                     GROUP BY t.model ORDER BY positive DESC"""
            params = []

        rows = self.db.fetch_all(sql, params)
        results = []
        for r in rows:
            total = r["total"]
            positive = r["positive"]
            negative = r["negative"]
            results.append(
                {
                    "model": r["model"],
                    "total_feedback": total,
                    "positive_pct": round(positive / total * 100, 1)
                    if total > 0
                    else 0,
                    "negative_pct": round(negative / total * 100, 1)
                    if total > 0
                    else 0,
                    "avg_score": round((positive - negative) / total, 3)
                    if total > 0
                    else 0,
                    "avg_cost": r.get("avg_cost", 0),
                    "cost_per_positive": round(
                        r.get("avg_cost", 0) * total / positive, 6
                    )
                    if positive > 0
                    else 0,
                }
            )
        return results

    def get_quality_by_prompt_version(self, prompt_id: str) -> list[dict]:
        """Get quality breakdown per prompt version.

        Requires traces to have metadata.prompt_id and metadata.prompt_version.
        """
        rows = self.db.fetch_all(
            """SELECT t.metadata, f.score
               FROM trace_feedback f
               JOIN trace_events t ON f.trace_id = t.trace_id
               WHERE t.metadata LIKE ?""",
            (f'%"prompt_id": "{prompt_id}"%',),
        )

        version_stats: dict = {}
        for r in rows:
            meta_str = r.get("metadata", "{}")
            try:
                meta = json.loads(meta_str) if isinstance(meta_str, str) else {}
            except (json.JSONDecodeError, TypeError):
                meta = {}

            version = meta.get("prompt_version", "unknown")
            vs = version_stats.setdefault(
                version, {"total": 0, "positive": 0, "negative": 0}
            )
            vs["total"] += 1
            if r["score"] == 1:
                vs["positive"] += 1
            elif r["score"] == -1:
                vs["negative"] += 1

        results = []
        for version, vs in sorted(version_stats.items()):
            total = vs["total"]
            results.append(
                {
                    "prompt_id": prompt_id,
                    "version": version,
                    "total_feedback": total,
                    "positive_pct": round(vs["positive"] / total * 100, 1)
                    if total > 0
                    else 0,
                    "avg_score": round((vs["positive"] - vs["negative"]) / total, 3)
                    if total > 0
                    else 0,
                }
            )
        return results

    def get_summary(self) -> dict:
        """Overall feedback stats."""
        row = self.db.fetch_one(
            """SELECT COUNT(*) as total,
                      SUM(CASE WHEN score = 1 THEN 1 ELSE 0 END) as positive,
                      SUM(CASE WHEN score = -1 THEN 1 ELSE 0 END) as negative,
                      SUM(CASE WHEN score = 0 THEN 1 ELSE 0 END) as neutral
               FROM trace_feedback"""
        )
        if not row or row["total"] == 0:
            return {
                "total": 0,
                "positive": 0,
                "negative": 0,
                "neutral": 0,
                "positive_pct": 0,
            }
        return {
            "total": row["total"],
            "positive": row["positive"],
            "negative": row["negative"],
            "neutral": row["neutral"],
            "positive_pct": round(row["positive"] / row["total"] * 100, 1),
        }

    # ── Internal ──────────────────────────────────────────────────

    def _row_to_dict(self, row) -> dict:
        tags = row.get("tags", "[]")
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = []
        metadata = row.get("metadata", "{}")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = {}
        return {
            "id": row["id"],
            "trace_id": row["trace_id"],
            "score": row["score"],
            "comment": row.get("comment", ""),
            "source": row.get("source", "user"),
            "user_id": row.get("user_id", ""),
            "tags": tags,
            "metadata": metadata,
            "org_id": row.get("org_id", "default"),
            "created_at": row.get("created_at", 0),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

_service: FeedbackService | None = None


def get_feedback_service(db=None) -> FeedbackService:
    global _service
    if _service is None:
        _service = FeedbackService(db=db)
    return _service


def reset_feedback_service() -> None:
    global _service
    _service = None

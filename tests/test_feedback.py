"""Tests for AgentCost Feedback module."""

import json
import time

import pytest

from agentcost.feedback import get_feedback_service


@pytest.fixture
def svc():
    return get_feedback_service()


@pytest.fixture
def events_db():
    """Create trace_events table and insert sample traces for join queries."""
    from agentcost.data.connection import get_db

    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS trace_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id TEXT NOT NULL,
            project TEXT DEFAULT 'default',
            agent_id TEXT, session_id TEXT,
            model TEXT NOT NULL, provider TEXT,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cost REAL DEFAULT 0,
            latency_ms REAL DEFAULT 0,
            status TEXT DEFAULT 'success',
            error TEXT, metadata TEXT,
            timestamp TEXT NOT NULL
        );
    """
    )
    # Insert sample traces
    traces = [
        ("t-1", "support", "gpt-4.1", 0.003, "{}"),
        ("t-2", "support", "gpt-4.1", 0.004, "{}"),
        ("t-3", "support", "gpt-4.1-mini", 0.0005, "{}"),
        ("t-4", "sales", "claude-sonnet-4-6", 0.006, "{}"),
        (
            "t-5",
            "support",
            "gpt-4.1",
            0.003,
            '{"prompt_id": "support-bot", "prompt_version": 1}',
        ),
        (
            "t-6",
            "support",
            "gpt-4.1",
            0.003,
            '{"prompt_id": "support-bot", "prompt_version": 2}',
        ),
        (
            "t-7",
            "support",
            "gpt-4.1",
            0.003,
            '{"prompt_id": "support-bot", "prompt_version": 2}',
        ),
    ]
    for tid, proj, model, cost, meta in traces:
        db.execute(
            """INSERT INTO trace_events
               (trace_id, project, model, provider, cost, metadata, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tid, proj, model, "openai", cost, meta, "2026-03-14T10:00:00"),
        )
    return db


# ── Submit ────────────────────────────────────────────────────────────────────


class TestSubmitFeedback:
    def test_submit_positive(self, svc):
        result = svc.submit("t-1", score=1)
        assert result["trace_id"] == "t-1"
        assert result["score"] == 1
        assert result["id"]

    def test_submit_negative(self, svc):
        result = svc.submit("t-2", score=-1, comment="Wrong answer")
        assert result["score"] == -1
        assert result["comment"] == "Wrong answer"

    def test_submit_neutral(self, svc):
        result = svc.submit("t-3", score=0)
        assert result["score"] == 0

    def test_submit_with_all_fields(self, svc):
        result = svc.submit(
            "t-1",
            score=1,
            comment="Great response",
            source="human-review",
            user_id="u-123",
            tags=["accurate", "concise"],
            metadata={"review_round": 2},
        )
        assert result["source"] == "human-review"
        assert result["user_id"] == "u-123"
        assert result["tags"] == ["accurate", "concise"]
        assert result["metadata"]["review_round"] == 2

    def test_submit_invalid_score_raises(self, svc):
        with pytest.raises(ValueError):
            svc.submit("t-1", score=5)

    def test_submit_invalid_score_negative_raises(self, svc):
        with pytest.raises(ValueError):
            svc.submit("t-1", score=-2)

    def test_multiple_feedback_per_trace(self, svc):
        svc.submit("t-1", score=1, user_id="u-1")
        svc.submit("t-1", score=-1, user_id="u-2")
        svc.submit("t-1", score=1, user_id="u-3")
        feedback = svc.get_trace_feedback("t-1")
        assert len(feedback) == 3


# ── Read ──────────────────────────────────────────────────────────────────────


class TestReadFeedback:
    def test_get_feedback(self, svc):
        fb = svc.submit("t-1", score=1)
        result = svc.get_feedback(fb["id"])
        assert result is not None
        assert result["trace_id"] == "t-1"

    def test_get_nonexistent(self, svc):
        assert svc.get_feedback("nonexistent") is None

    def test_get_trace_feedback(self, svc):
        svc.submit("t-1", score=1)
        svc.submit("t-1", score=-1)
        feedback = svc.get_trace_feedback("t-1")
        assert len(feedback) == 2

    def test_get_trace_feedback_empty(self, svc):
        assert svc.get_trace_feedback("nonexistent") == []

    def test_list_feedback(self, svc):
        svc.submit("t-1", score=1)
        svc.submit("t-2", score=-1)
        svc.submit("t-3", score=1)
        result = svc.list_feedback()
        assert len(result) == 3

    def test_list_by_score(self, svc):
        svc.submit("t-1", score=1)
        svc.submit("t-2", score=-1)
        svc.submit("t-3", score=1)
        positive = svc.list_feedback(score=1)
        assert len(positive) == 2

    def test_list_by_source(self, svc):
        svc.submit("t-1", score=1, source="user")
        svc.submit("t-2", score=1, source="automated")
        svc.submit("t-3", score=-1, source="user")
        user_fb = svc.list_feedback(source="user")
        assert len(user_fb) == 2

    def test_delete_feedback(self, svc):
        fb = svc.submit("t-1", score=1)
        assert svc.delete_feedback(fb["id"])
        assert svc.get_feedback(fb["id"]) is None

    def test_delete_nonexistent(self, svc):
        assert not svc.delete_feedback("nonexistent")


# ── Analytics ─────────────────────────────────────────────────────────────────


class TestTraceScore:
    def test_single_positive(self, svc):
        svc.submit("t-1", score=1)
        result = svc.get_trace_score("t-1")
        assert result["total"] == 1
        assert result["positive"] == 1
        assert result["score"] == 1.0

    def test_mixed_feedback(self, svc):
        svc.submit("t-1", score=1)
        svc.submit("t-1", score=1)
        svc.submit("t-1", score=-1)
        result = svc.get_trace_score("t-1")
        assert result["total"] == 3
        assert result["positive"] == 2
        assert result["negative"] == 1
        assert result["score"] == pytest.approx(0.33, abs=0.01)

    def test_no_feedback(self, svc):
        result = svc.get_trace_score("nonexistent")
        assert result["total"] == 0
        assert result["score"] is None


class TestModelQuality:
    def test_model_quality(self, svc, events_db):
        svc.submit("t-1", score=1)
        svc.submit("t-2", score=1)
        svc.submit("t-3", score=-1)
        result = svc.get_model_quality("gpt-4.1")
        assert result["total_feedback"] == 2
        assert result["positive_pct"] == 100.0

    def test_model_quality_no_feedback(self, svc, events_db):
        result = svc.get_model_quality("gpt-4.1")
        assert result["total_feedback"] == 0

    def test_quality_by_model(self, svc, events_db):
        svc.submit("t-1", score=1)  # gpt-4.1
        svc.submit("t-2", score=-1)  # gpt-4.1
        svc.submit("t-4", score=1)  # claude-sonnet-4-6
        result = svc.get_quality_by_model()
        assert len(result) == 2
        models = {r["model"] for r in result}
        assert "gpt-4.1" in models
        assert "claude-sonnet-4-6" in models

    def test_quality_by_model_filtered(self, svc, events_db):
        svc.submit("t-1", score=1)  # support, gpt-4.1
        svc.submit("t-4", score=1)  # sales, claude
        result = svc.get_quality_by_model(project="support")
        assert len(result) == 1
        assert result[0]["model"] == "gpt-4.1"


class TestPromptQuality:
    def test_quality_by_prompt_version(self, svc, events_db):
        svc.submit("t-5", score=1)  # prompt v1
        svc.submit("t-6", score=1)  # prompt v2
        svc.submit("t-7", score=-1)  # prompt v2
        result = svc.get_quality_by_prompt_version("support-bot")
        assert len(result) == 2
        v1 = [r for r in result if r["version"] == 1][0]
        v2 = [r for r in result if r["version"] == 2][0]
        assert v1["positive_pct"] == 100.0
        assert v2["positive_pct"] == 50.0


class TestSummary:
    def test_summary(self, svc):
        svc.submit("t-1", score=1)
        svc.submit("t-2", score=1)
        svc.submit("t-3", score=-1)
        svc.submit("t-4", score=0)
        result = svc.get_summary()
        assert result["total"] == 4
        assert result["positive"] == 2
        assert result["negative"] == 1
        assert result["neutral"] == 1
        assert result["positive_pct"] == 50.0

    def test_empty_summary(self, svc):
        result = svc.get_summary()
        assert result["total"] == 0

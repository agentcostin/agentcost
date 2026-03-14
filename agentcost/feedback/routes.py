"""
AgentCost Feedback Routes — FastAPI endpoints for trace feedback.

Mounts under /api/feedback/* on the main app.
Available in all editions (community + enterprise).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from . import get_feedback_service

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class SubmitFeedbackRequest(BaseModel):
    trace_id: str
    score: int  # 1, 0, or -1
    comment: str = ""
    source: str = "user"
    user_id: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


@router.post("")
async def submit_feedback(req: SubmitFeedbackRequest):
    """Submit feedback (thumbs up/down) on a trace."""
    svc = get_feedback_service()
    try:
        return svc.submit(
            req.trace_id,
            score=req.score,
            comment=req.comment,
            source=req.source,
            user_id=req.user_id,
            tags=req.tags,
            metadata=req.metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_feedback(
    project: str | None = Query(None),
    model: str | None = Query(None),
    score: int | None = Query(None),
    source: str | None = Query(None),
    limit: int = Query(100, le=1000),
):
    """List feedback with optional filters."""
    svc = get_feedback_service()
    return svc.list_feedback(
        project=project, model=model, score=score, source=source, limit=limit
    )


@router.get("/summary")
async def feedback_summary():
    """Get overall feedback statistics."""
    svc = get_feedback_service()
    return svc.get_summary()


@router.get("/quality/models")
async def quality_by_model(project: str | None = Query(None)):
    """Get quality breakdown by model (with cost-per-positive)."""
    svc = get_feedback_service()
    return svc.get_quality_by_model(project=project)


@router.get("/quality/model/{model}")
async def model_quality(model: str, project: str | None = Query(None)):
    """Get quality stats for a specific model."""
    svc = get_feedback_service()
    return svc.get_model_quality(model, project=project)


@router.get("/quality/prompt/{prompt_id}")
async def prompt_quality(prompt_id: str):
    """Get quality breakdown per prompt version."""
    svc = get_feedback_service()
    return svc.get_quality_by_prompt_version(prompt_id)


@router.get("/trace/{trace_id}")
async def trace_feedback(trace_id: str):
    """Get all feedback for a specific trace."""
    svc = get_feedback_service()
    return svc.get_trace_feedback(trace_id)


@router.get("/trace/{trace_id}/score")
async def trace_score(trace_id: str):
    """Get aggregated score for a trace."""
    svc = get_feedback_service()
    return svc.get_trace_score(trace_id)


@router.delete("/{feedback_id}")
async def delete_feedback(feedback_id: str):
    """Delete a feedback entry."""
    svc = get_feedback_service()
    if svc.delete_feedback(feedback_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Feedback not found")

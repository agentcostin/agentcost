"""
AgentCost Prompt Routes — FastAPI endpoints for prompt management.

Mounts under /api/prompts/* on the main app.
Available in all editions (community + enterprise).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from . import get_prompt_service

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


# ── Request models ───────────────────────────────────────────────────────────


class CreatePromptRequest(BaseModel):
    name: str
    project: str = "default"
    content: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    model: str = ""
    config: dict = Field(default_factory=dict)
    author: str = ""
    commit_message: str = "Initial version"


class CreateVersionRequest(BaseModel):
    content: str
    model: str = ""
    config: dict = Field(default_factory=dict)
    author: str = ""
    commit_message: str = ""


class DeployRequest(BaseModel):
    version: int
    environment: str = "production"
    deployed_by: str = ""


class ResolveRequest(BaseModel):
    environment: str = "production"
    variables: dict = Field(default_factory=dict)
    version: Optional[int] = None


# ── Prompt CRUD ──────────────────────────────────────────────────────────────


@router.post("")
async def create_prompt(req: CreatePromptRequest):
    """Create a new prompt with its first version."""
    svc = get_prompt_service()
    try:
        result = svc.create_prompt(
            req.name,
            project=req.project,
            content=req.content,
            description=req.description,
            tags=req.tags,
            model=req.model,
            config=req.config,
            author=req.author,
            commit_message=req.commit_message,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_prompts(
    project: str | None = Query(None),
    tag: str | None = Query(None),
):
    """List all prompts, optionally filtered by project or tag."""
    svc = get_prompt_service()
    return svc.list_prompts(project=project, tag=tag)


@router.get("/summary")
async def prompt_summary():
    """Get prompt management statistics."""
    svc = get_prompt_service()
    return svc.get_summary()


@router.get("/{prompt_id}")
async def get_prompt(prompt_id: str):
    """Get a prompt with its latest version and deployments."""
    svc = get_prompt_service()
    result = svc.get_prompt(prompt_id)
    if not result:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return result


@router.delete("/{prompt_id}")
async def delete_prompt(prompt_id: str):
    """Delete a prompt and all its versions/deployments."""
    svc = get_prompt_service()
    if svc.delete_prompt(prompt_id):
        return {"status": "deleted", "prompt_id": prompt_id}
    raise HTTPException(status_code=404, detail="Prompt not found")


# ── Versions ─────────────────────────────────────────────────────────────────


@router.post("/{prompt_id}/versions")
async def create_version(prompt_id: str, req: CreateVersionRequest):
    """Create a new version of a prompt."""
    svc = get_prompt_service()
    try:
        return svc.create_version(
            prompt_id,
            content=req.content,
            model=req.model,
            config=req.config,
            author=req.author,
            commit_message=req.commit_message,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{prompt_id}/versions")
async def list_versions(prompt_id: str):
    """List all versions of a prompt."""
    svc = get_prompt_service()
    versions = svc.list_versions(prompt_id)
    if not versions:
        raise HTTPException(status_code=404, detail="Prompt not found or no versions")
    return versions


@router.get("/{prompt_id}/versions/{version}")
async def get_version(prompt_id: str, version: int):
    """Get a specific version of a prompt."""
    svc = get_prompt_service()
    v = svc.get_version(prompt_id, version)
    if not v:
        raise HTTPException(status_code=404, detail="Version not found")
    return v


@router.get("/{prompt_id}/diff")
async def diff_versions(
    prompt_id: str,
    v1: int = Query(..., description="First version"),
    v2: int = Query(..., description="Second version"),
):
    """Get a unified diff between two versions."""
    svc = get_prompt_service()
    try:
        return svc.diff_versions(prompt_id, v1, v2)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Deployments ──────────────────────────────────────────────────────────────


@router.post("/{prompt_id}/deploy")
async def deploy_version(prompt_id: str, req: DeployRequest):
    """Deploy a version to an environment."""
    svc = get_prompt_service()
    try:
        return svc.deploy(
            prompt_id,
            version=req.version,
            environment=req.environment,
            deployed_by=req.deployed_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{prompt_id}/deployments")
async def list_deployments(prompt_id: str):
    """List all deployments for a prompt."""
    svc = get_prompt_service()
    return svc.list_deployments(prompt_id)


# ── Resolve (SDK usage) ─────────────────────────────────────────────────────


@router.post("/{prompt_id}/resolve")
async def resolve_prompt(prompt_id: str, req: ResolveRequest):
    """Resolve a prompt for use — fills variables, returns deployed content."""
    svc = get_prompt_service()
    try:
        return svc.resolve(
            prompt_id,
            environment=req.environment,
            variables=req.variables,
            version=req.version,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Cost analytics ───────────────────────────────────────────────────────────


@router.get("/{prompt_id}/versions/{version}/cost")
async def version_cost_stats(prompt_id: str, version: int):
    """Get cost stats for traces using this prompt version."""
    svc = get_prompt_service()
    return svc.get_version_cost_stats(prompt_id, version)


@router.get("/{prompt_id}/cost/compare")
async def compare_version_costs(
    prompt_id: str,
    v1: int = Query(..., description="First version"),
    v2: int = Query(..., description="Second version"),
):
    """Compare cost stats between two prompt versions."""
    svc = get_prompt_service()
    return svc.compare_version_costs(prompt_id, v1, v2)

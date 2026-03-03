"""
Policy Routes — FastAPI router for policies & approvals (Block 4).

Endpoints:
  Policies:
    POST   /policy/policies              → Create policy
    GET    /policy/policies              → List policies
    GET    /policy/policies/{id}         → Get policy
    PUT    /policy/policies/{id}         → Update policy
    PUT    /policy/policies/{id}/toggle  → Enable/disable policy
    DELETE /policy/policies/{id}         → Delete policy

  Templates:
    GET    /policy/templates             → List available templates
    POST   /policy/templates/{name}      → Create policy from template

  Evaluation:
    POST   /policy/evaluate              → Evaluate request against policies
    POST   /policy/dry-run               → Dry-run evaluation (show all matches)

  Approvals:
    POST   /policy/approvals             → Create approval request
    GET    /policy/approvals             → List approval requests
    GET    /policy/approvals/{id}        → Get approval request
    POST   /policy/approvals/{id}/approve → Approve request
    POST   /policy/approvals/{id}/deny    → Deny request
    GET    /policy/approvals/stats       → Approval stats
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth.dependencies import get_current_user, require_role
from ..auth.models import AuthContext, Role

logger = logging.getLogger("agentcost.policy.routes")

policy_router = APIRouter(prefix="/policy", tags=["policy"])


# ── Request Models ───────────────────────────────────────────────────────────


class PolicyCreate(BaseModel):
    name: str
    conditions: list[dict]
    action: str = "deny"
    description: str = ""
    message: str = ""
    priority: int = 100
    enabled: bool = True


class PolicyUpdate(BaseModel):
    name: Optional[str] = None
    conditions: Optional[list[dict]] = None
    action: Optional[str] = None
    description: Optional[str] = None
    message: Optional[str] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None


class PolicyToggle(BaseModel):
    enabled: bool


class EvaluateRequest(BaseModel):
    model: Optional[str] = None
    provider: Optional[str] = None
    project: Optional[str] = None
    agent_id: Optional[str] = None
    estimated_cost: Optional[float] = None
    estimated_tokens: Optional[int] = None


class ApprovalCreate(BaseModel):
    requester_id: str
    requester_type: str = "agent"
    request_type: str = "policy_override"
    context: Optional[dict] = None
    estimated_cost: Optional[float] = None
    expires_hours: int = 24


class ApprovalDecision(BaseModel):
    unlock_amount: Optional[float] = None


class ApprovalDeny(BaseModel):
    reason: str = ""


# ── Service factories ────────────────────────────────────────────────────────


def _policy_svc():
    from .policy_service import PolicyService

    return PolicyService()


def _engine():
    from .engine import PolicyEngine

    return PolicyEngine()


def _approval_svc():
    from .approval_service import ApprovalService

    return ApprovalService()


def _audit_svc():
    from ..org.audit_service import AuditService

    return AuditService()


def _resolve_user_id(user: AuthContext) -> str:
    """Resolve the DB user ID from the auth context (same pattern as org routes)."""
    from ..data.connection import get_db
    from datetime import datetime
    import uuid as _uuid

    db = get_db()
    row = db.fetch_one(
        "SELECT id FROM users WHERE email = ? AND org_id = ?",
        (user.email, user.org_id),
    )
    if row:
        return row["id"]

    # Auto-provision
    if user.email:
        user_id = str(_uuid.uuid4())
        now = datetime.utcnow().isoformat()
        org_id = user.org_id or "default"
        role = user.role.value if user.role else "org_member"
        try:
            db.execute(
                "INSERT INTO users (id, email, name, org_id, role, sso_provider_id, "
                "last_login_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    user.email,
                    user.claims.name,
                    org_id,
                    role,
                    user.claims.sub,
                    now,
                    now,
                    now,
                ),
            )
            return user_id
        except Exception:
            pass
    return user.user_id


# ─────────────────────────────────────────────────────────────────────────────
# POLICY ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────


@policy_router.post("/policies")
async def create_policy(
    body: PolicyCreate,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Create a new policy. Requires org_admin."""
    svc = _policy_svc()
    audit = _audit_svc()
    actor_id = _resolve_user_id(user)

    result = svc.create(
        org_id=user.org_id,
        name=body.name,
        conditions=body.conditions,
        action=body.action,
        description=body.description,
        message=body.message,
        priority=body.priority,
        enabled=body.enabled,
        created_by=actor_id,
    )
    if "error" in result:
        raise HTTPException(400, result["error"])

    audit.log(
        event_type="policy.create",
        org_id=user.org_id,
        actor_id=actor_id,
        resource_type="policy",
        resource_id=result.get("id", ""),
        action="create",
        details={"name": body.name, "action": body.action, "priority": body.priority},
    )
    return result


@policy_router.get("/policies")
async def list_policies(
    enabled_only: bool = False,
    user: AuthContext = Depends(get_current_user),
):
    """List all policies for the org."""
    svc = _policy_svc()
    return svc.list(user.org_id, enabled_only=enabled_only)


@policy_router.get("/policies/{policy_id}")
async def get_policy(
    policy_id: str,
    user: AuthContext = Depends(get_current_user),
):
    """Get a specific policy."""
    svc = _policy_svc()
    policy = svc.get(policy_id, user.org_id)
    if not policy:
        raise HTTPException(404, "Policy not found")
    return policy


@policy_router.put("/policies/{policy_id}")
async def update_policy(
    policy_id: str,
    body: PolicyUpdate,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Update a policy. Requires org_admin."""
    svc = _policy_svc()
    audit = _audit_svc()

    result = svc.update(policy_id, user.org_id, **body.model_dump(exclude_none=True))
    if not result:
        raise HTTPException(404, "Policy not found")
    if "error" in result:
        raise HTTPException(400, result["error"])

    audit.log(
        event_type="policy.update",
        org_id=user.org_id,
        actor_id=_resolve_user_id(user),
        resource_type="policy",
        resource_id=policy_id,
        action="update",
        details=body.model_dump(exclude_none=True),
    )
    return result


@policy_router.put("/policies/{policy_id}/toggle")
async def toggle_policy(
    policy_id: str,
    body: PolicyToggle,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Enable or disable a policy. Requires org_admin."""
    svc = _policy_svc()
    result = svc.toggle(policy_id, user.org_id, body.enabled)
    if not result:
        raise HTTPException(404, "Policy not found")
    return result


@policy_router.delete("/policies/{policy_id}")
async def delete_policy(
    policy_id: str,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Delete a policy. Requires org_admin."""
    svc = _policy_svc()
    audit = _audit_svc()
    result = svc.delete(policy_id, user.org_id)
    audit.log(
        event_type="policy.delete",
        org_id=user.org_id,
        actor_id=_resolve_user_id(user),
        resource_type="policy",
        resource_id=policy_id,
        action="delete",
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────


@policy_router.get("/templates")
async def list_templates(user: AuthContext = Depends(get_current_user)):
    """List available policy templates."""
    svc = _policy_svc()
    return svc.get_templates()


@policy_router.post("/templates/{template_name}")
async def create_from_template(
    template_name: str,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Create a policy from a pre-built template. Requires org_admin."""
    svc = _policy_svc()
    audit = _audit_svc()
    actor_id = _resolve_user_id(user)

    result = svc.create_from_template(user.org_id, template_name, created_by=actor_id)
    if "error" in result:
        raise HTTPException(400, result["error"])

    audit.log(
        event_type="policy.create",
        org_id=user.org_id,
        actor_id=actor_id,
        resource_type="policy",
        resource_id=result.get("id", ""),
        action="create",
        details={"template": template_name, "name": result.get("name")},
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# EVALUATION ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────


@policy_router.post("/evaluate")
async def evaluate_request(
    body: EvaluateRequest,
    user: AuthContext = Depends(get_current_user),
):
    """Evaluate a request against org policies.

    Returns the decision (allow/deny/require_approval/log_only) and
    the matched policy if any. Used by the SDK before making an LLM call.
    """
    engine = _engine()
    ctx = body.model_dump(exclude_none=True)
    return engine.evaluate(user.org_id, ctx)


@policy_router.post("/dry-run")
async def dry_run(
    body: EvaluateRequest,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Dry-run evaluation — shows ALL matching policies, not just first.

    Useful for testing policy configurations. Requires org_admin.
    """
    engine = _engine()
    ctx = body.model_dump(exclude_none=True)
    return engine.dry_run(user.org_id, ctx)


# ─────────────────────────────────────────────────────────────────────────────
# APPROVAL ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────


@policy_router.post("/approvals")
async def create_approval(
    body: ApprovalCreate,
    user: AuthContext = Depends(get_current_user),
):
    """Create an approval request (typically triggered by policy engine)."""
    svc = _approval_svc()
    return svc.create(
        org_id=user.org_id,
        requester_id=body.requester_id,
        requester_type=body.requester_type,
        request_type=body.request_type,
        context=body.context,
        estimated_cost=body.estimated_cost,
        expires_hours=body.expires_hours,
    )


@policy_router.get("/approvals")
async def list_approvals(
    status: Optional[str] = None,
    request_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """List approval requests. Requires org_admin."""
    svc = _approval_svc()
    return svc.list(
        user.org_id,
        status=status,
        request_type=request_type,
        limit=limit,
        offset=offset,
    )


@policy_router.get("/approvals/stats")
async def approval_stats(
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Get approval request stats."""
    svc = _approval_svc()
    return svc.stats(user.org_id)


@policy_router.get("/approvals/{req_id}")
async def get_approval(
    req_id: str,
    user: AuthContext = Depends(get_current_user),
):
    """Get a specific approval request."""
    svc = _approval_svc()
    req = svc.get(req_id, user.org_id)
    if not req:
        raise HTTPException(404, "Approval request not found")
    return req


@policy_router.post("/approvals/{req_id}/approve")
async def approve_request(
    req_id: str,
    body: ApprovalDecision = ApprovalDecision(),
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Approve a pending request. Requires org_admin."""
    svc = _approval_svc()
    audit = _audit_svc()
    actor_id = _resolve_user_id(user)

    result = svc.approve(
        req_id, user.org_id, decided_by=actor_id, unlock_amount=body.unlock_amount
    )
    if "error" in result:
        raise HTTPException(400, result["error"])

    audit.log(
        event_type="approval.decide",
        org_id=user.org_id,
        actor_id=actor_id,
        resource_type="approval",
        resource_id=req_id,
        action="approve",
        details={"unlock_amount": body.unlock_amount},
    )
    return result


@policy_router.post("/approvals/{req_id}/deny")
async def deny_request(
    req_id: str,
    body: ApprovalDeny = ApprovalDeny(),
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Deny a pending request. Requires org_admin."""
    svc = _approval_svc()
    audit = _audit_svc()
    actor_id = _resolve_user_id(user)

    result = svc.deny(req_id, user.org_id, decided_by=actor_id, reason=body.reason)
    if "error" in result:
        raise HTTPException(400, result["error"])

    audit.log(
        event_type="approval.decide",
        org_id=user.org_id,
        actor_id=actor_id,
        resource_type="approval",
        resource_id=req_id,
        action="deny",
        details={"reason": body.reason},
    )
    return result

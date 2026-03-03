"""
Cost Routes — FastAPI router for budget enforcement & cost allocation (Block 3).

Endpoints:
  Cost Centers:
    POST   /cost/centers              → Create cost center
    GET    /cost/centers              → List cost centers
    GET    /cost/centers/{id}         → Get cost center details
    PUT    /cost/centers/{id}         → Update cost center
    DELETE /cost/centers/{id}         → Delete cost center

  Allocations:
    POST   /cost/allocations          → Create allocation rule
    GET    /cost/allocations          → List allocation rules
    GET    /cost/allocations/summary/{project} → Get allocation summary for project
    PUT    /cost/allocations/{id}     → Update allocation rule
    DELETE /cost/allocations/{id}     → Delete allocation rule

  Budgets:
    POST   /cost/budgets              → Set/update budget
    GET    /cost/budgets              → List all budgets with spend
    GET    /cost/budgets/{project}    → Get budget for project
    DELETE /cost/budgets/{project}    → Delete budget
    POST   /cost/budgets/check        → Pre-call budget check

  Reports:
    GET    /cost/chargeback           → Chargeback report
    GET    /cost/utilization          → Budget utilization report
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth.dependencies import get_current_user, require_role
from ..auth.models import AuthContext, Role

logger = logging.getLogger("agentcost.cost.routes")

cost_router = APIRouter(prefix="/cost", tags=["cost"])


# ── Request Models ───────────────────────────────────────────────────────────


class CostCenterCreate(BaseModel):
    name: str
    code: str = ""
    manager_email: str = ""
    monthly_budget: Optional[float] = None


class CostCenterUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    manager_email: Optional[str] = None
    monthly_budget: Optional[float] = None


class AllocationCreate(BaseModel):
    cost_center_id: str
    project: Optional[str] = None
    agent_id: Optional[str] = None
    allocation_pct: float = 100.0


class AllocationUpdate(BaseModel):
    cost_center_id: Optional[str] = None
    project: Optional[str] = None
    agent_id: Optional[str] = None
    allocation_pct: Optional[float] = None


class BudgetSet(BaseModel):
    project: str
    daily_limit: Optional[float] = None
    monthly_limit: Optional[float] = None
    total_limit: Optional[float] = None
    alert_threshold: float = 0.8


class BudgetCheck(BaseModel):
    project: str
    estimated_cost: float = 0.0


# ── Service factories ────────────────────────────────────────────────────────


def _cc_svc():
    from .cost_center_service import CostCenterService

    return CostCenterService()


def _alloc_svc():
    from .allocation_service import AllocationService

    return AllocationService()


def _budget_svc():
    from .budget_service import BudgetService

    return BudgetService()


def _audit_svc():
    from ..org.audit_service import AuditService

    return AuditService()


# ─────────────────────────────────────────────────────────────────────────────
# COST CENTER ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────


@cost_router.post("/centers")
async def create_cost_center(
    body: CostCenterCreate,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Create a new cost center. Requires org_admin."""
    svc = _cc_svc()
    audit = _audit_svc()
    result = svc.create(
        org_id=user.org_id,
        name=body.name,
        code=body.code,
        manager_email=body.manager_email,
        monthly_budget=body.monthly_budget,
    )
    audit.log(
        event_type="cost_center.create",
        org_id=user.org_id,
        actor_id=user.user_id,
        resource_type="cost_center",
        resource_id=result.get("id", ""),
        action="create",
        details={"name": body.name, "code": body.code},
    )
    return result


@cost_router.get("/centers")
async def list_cost_centers(
    limit: int = 100,
    offset: int = 0,
    user: AuthContext = Depends(get_current_user),
):
    """List cost centers for the org."""
    svc = _cc_svc()
    centers = svc.list(user.org_id, limit=limit, offset=offset)
    total = svc.get_count(user.org_id)
    return {"centers": centers, "total": total}


@cost_router.get("/centers/{cc_id}")
async def get_cost_center(
    cc_id: str,
    user: AuthContext = Depends(get_current_user),
):
    """Get a specific cost center."""
    svc = _cc_svc()
    cc = svc.get(cc_id, user.org_id)
    if not cc:
        raise HTTPException(404, "Cost center not found")
    return cc


@cost_router.put("/centers/{cc_id}")
async def update_cost_center(
    cc_id: str,
    body: CostCenterUpdate,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Update a cost center. Requires org_admin."""
    svc = _cc_svc()
    audit = _audit_svc()
    updated = svc.update(cc_id, user.org_id, **body.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(404, "Cost center not found")
    audit.log(
        event_type="cost_center.update",
        org_id=user.org_id,
        actor_id=user.user_id,
        resource_type="cost_center",
        resource_id=cc_id,
        action="update",
        details=body.model_dump(exclude_none=True),
    )
    return updated


@cost_router.delete("/centers/{cc_id}")
async def delete_cost_center(
    cc_id: str,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Delete a cost center and its allocation rules. Requires org_admin."""
    svc = _cc_svc()
    audit = _audit_svc()
    result = svc.delete(cc_id, user.org_id)
    audit.log(
        event_type="cost_center.delete",
        org_id=user.org_id,
        actor_id=user.user_id,
        resource_type="cost_center",
        resource_id=cc_id,
        action="delete",
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# ALLOCATION ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────


@cost_router.post("/allocations")
async def create_allocation(
    body: AllocationCreate,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Create an allocation rule. Requires org_admin."""
    svc = _alloc_svc()
    result = svc.create(
        org_id=user.org_id,
        cost_center_id=body.cost_center_id,
        project=body.project,
        agent_id=body.agent_id,
        allocation_pct=body.allocation_pct,
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@cost_router.get("/allocations")
async def list_allocations(
    cost_center_id: Optional[str] = None,
    project: Optional[str] = None,
    user: AuthContext = Depends(get_current_user),
):
    """List allocation rules, optionally filtered."""
    svc = _alloc_svc()
    return svc.list(user.org_id, cost_center_id=cost_center_id, project=project)


@cost_router.get("/allocations/summary/{project}")
async def allocation_summary(
    project: str,
    user: AuthContext = Depends(get_current_user),
):
    """Get allocation summary for a project (shows if fully allocated)."""
    svc = _alloc_svc()
    return svc.get_allocation_summary(user.org_id, project)


@cost_router.put("/allocations/{alloc_id}")
async def update_allocation(
    alloc_id: int,
    body: AllocationUpdate,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Update an allocation rule. Requires org_admin."""
    svc = _alloc_svc()
    result = svc.update(alloc_id, user.org_id, **body.model_dump(exclude_none=True))
    if not result:
        raise HTTPException(404, "Allocation rule not found")
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@cost_router.delete("/allocations/{alloc_id}")
async def delete_allocation(
    alloc_id: int,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Delete an allocation rule. Requires org_admin."""
    svc = _alloc_svc()
    return svc.delete(alloc_id, user.org_id)


# ─────────────────────────────────────────────────────────────────────────────
# BUDGET ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────


@cost_router.post("/budgets")
async def set_budget(
    body: BudgetSet,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Set or update a project budget. Requires org_admin."""
    svc = _budget_svc()
    audit = _audit_svc()
    result = svc.set_budget(
        org_id=user.org_id,
        project=body.project,
        daily_limit=body.daily_limit,
        monthly_limit=body.monthly_limit,
        total_limit=body.total_limit,
        alert_threshold=body.alert_threshold,
    )
    audit.log(
        event_type="budget.set",
        org_id=user.org_id,
        actor_id=user.user_id,
        resource_type="budget",
        resource_id=body.project,
        action="create",
        details=body.model_dump(),
    )
    return result


@cost_router.get("/budgets")
async def list_budgets(user: AuthContext = Depends(get_current_user)):
    """List all budgets for the org with current spend."""
    svc = _budget_svc()
    return svc.list_budgets(user.org_id)


@cost_router.get("/budgets/{project}")
async def get_budget(
    project: str,
    user: AuthContext = Depends(get_current_user),
):
    """Get budget and current spend for a project."""
    svc = _budget_svc()
    budget = svc.get_budget(user.org_id, project)
    if not budget:
        return {"has_budget": False, "project": project}
    return budget


@cost_router.delete("/budgets/{project}")
async def delete_budget(
    project: str,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Delete a project budget. Requires org_admin."""
    svc = _budget_svc()
    audit = _audit_svc()
    result = svc.delete_budget(user.org_id, project)
    audit.log(
        event_type="budget.delete",
        org_id=user.org_id,
        actor_id=user.user_id,
        resource_type="budget",
        resource_id=project,
        action="delete",
    )
    return result


@cost_router.post("/budgets/check")
async def check_budget(
    body: BudgetCheck,
    user: AuthContext = Depends(get_current_user),
):
    """Pre-call budget check — can this LLM call proceed?

    Returns {allowed: true/false, reason: str, budget: dict}.
    Used by the SDK before making an LLM call.
    """
    svc = _budget_svc()
    return svc.check_can_proceed(user.org_id, body.project, body.estimated_cost)


# ─────────────────────────────────────────────────────────────────────────────
# REPORT ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────


@cost_router.get("/chargeback")
async def chargeback_report(
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Generate a chargeback report — spend per cost center.

    Optional date filters: ?period_start=2026-02-01&period_end=2026-03-01
    """
    svc = _cc_svc()
    return svc.chargeback_report(user.org_id, period_start, period_end)


@cost_router.get("/utilization")
async def utilization_report(
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Budget utilization report across all projects."""
    svc = _budget_svc()
    return svc.utilization_report(user.org_id)

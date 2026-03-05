"""
AgentCost Cost — Cost Calculation, Budget Enforcement, Cost Centers & Allocation

Provides:
  - Native cost calculator with 2,600+ model pricing (vendored from LiteLLM)
  - Custom model pricing overrides (overrides.json + runtime registration)
  - Cache-aware cost calculation (Anthropic prompt caching, etc.)
  - Cost center CRUD with ERP codes and monthly budgets
  - Cost allocation rules (project/agent → cost center mapping, split %)
  - Enterprise budget enforcement with SERIALIZABLE isolation
  - Chargeback reports (spend per cost center per period)
  - Budget alerts and overage detection

Usage:
    from agentcost.cost import CostCenterService, AllocationService, BudgetService

    # Cost calculation (no external dependencies required)
    from agentcost.cost.calculator import (
        cost_per_token,
        completion_cost,
        calculate_cost,
        get_model_info,
        register_model,
        register_model_per_1m,
        list_providers,
        list_models,
    )
"""

from .cost_center_service import CostCenterService
from .allocation_service import AllocationService
from .budget_service import BudgetService
from .calculator import (
    cost_per_token,
    completion_cost,
    calculate_cost,
    get_model_info,
    register_model,
    register_model_per_1m,
    list_providers,
    list_models,
    model_count,
)

__all__ = [
    "CostCenterService",
    "AllocationService",
    "BudgetService",
    # Calculator
    "cost_per_token",
    "completion_cost",
    "calculate_cost",
    "get_model_info",
    "register_model",
    "register_model_per_1m",
    "list_providers",
    "list_models",
    "model_count",
]

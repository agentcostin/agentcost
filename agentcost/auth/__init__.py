"""
AgentCost Auth — SSO/SAML Authentication Module (Block 1, Phase 3)

Provides Keycloak-backed authentication with:
  - OIDC JWT validation for API requests
  - SAML 2.0 SP endpoints for enterprise SSO
  - Multi-tenant org isolation via JWT claims
  - Role-based access control (RBAC)
  - API key authentication for SDK/agent traffic

Usage:
    from agentcost.auth import get_current_user, require_role
    from agentcost.auth.dependencies import AuthContext
"""

from .dependencies import get_current_user, require_role, get_optional_user
from .models import AuthContext, TokenClaims

__all__ = [
    "get_current_user",
    "get_optional_user",
    "require_role",
    "AuthContext",
    "TokenClaims",
]

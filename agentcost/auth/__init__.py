"""
AgentCost Auth — SSO/SAML Authentication Module

Provides provider-agnostic authentication with:
  - OIDC JWT validation for API requests (any compliant IdP)
  - SAML 2.0 SP endpoints for enterprise SSO
  - Multi-tenant org isolation via JWT claims
  - Role-based access control (RBAC)
  - API key authentication for SDK/agent traffic

Supported providers: Okta, Auth0, Azure AD, Google, Keycloak, Authentik, etc.

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

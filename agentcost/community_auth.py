"""
AgentCost Community Auth Stubs

Provides lightweight auth replacements for community edition.
No SSO, no Keycloak, no JWT — just passthrough auth with a
default anonymous user context.

Enterprise edition replaces these with real auth from agentcost.auth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from fastapi import Request, Depends
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


# ── Models (compatible with enterprise AuthContext) ──────────────────────────


class Role(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    AGENT_DEV = "agent_dev"
    VIEWER = "viewer"


@dataclass
class AuthContext:
    """Minimal auth context for community edition."""

    sub: str = "anonymous"
    email: str = "open@agentcost.in"
    name: str = "Local User"
    org_id: str = "default"
    org_slug: str = "default"
    roles: list[str] = field(default_factory=lambda: ["admin"])
    role: Role = Role.ADMIN

    def has_role(self, role: Role) -> bool:
        return True  # Community mode: all access

    def is_admin(self) -> bool:
        return True


@dataclass(frozen=True)
class AuthConfig:
    """Minimal auth config for community edition."""

    enabled: bool = False
    session_cookie_name: str = "agentcost_session"
    session_secret: str = "community-mode"
    api_key_header: str = "X-AgentCost-Key"
    api_key_prefix: str = "ac_"
    session_max_age: int = 86400


_default_user = AuthContext()
_config = AuthConfig()


def get_auth_config() -> AuthConfig:
    return _config


async def get_current_user(request: Request) -> AuthContext:
    """Always returns the default community user."""
    return _default_user


async def get_optional_user(request: Request) -> AuthContext:
    """Always returns the default community user."""
    return _default_user


def require_role(*roles: Role):
    """No-op in community mode — always grants access."""

    async def _dep(request: Request) -> AuthContext:
        return _default_user

    return Depends(_dep)


def org_filter_sql(user: AuthContext, table_alias: str = "") -> str:
    """Returns empty filter in community mode."""
    return ""


class AuthMiddleware(BaseHTTPMiddleware):
    """Passthrough middleware for community edition."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request.state.user = _default_user
        return await call_next(request)

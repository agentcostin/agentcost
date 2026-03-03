"""
FastAPI Auth Dependencies — Injected into route handlers via Depends().

Three authentication strategies, tried in order:
  1. Bearer JWT (Authorization: Bearer <token>) — OIDC from Keycloak
  2. API Key (X-AgentCost-Key: ac_live_xxx) — SDK / agent traffic
  3. Session cookie (agentcost_session) — post-SAML browser sessions

If AGENTCOST_AUTH_ENABLED=false, all endpoints get an anonymous context.

Usage in routes:
    from agentcost.auth import get_current_user, require_role
    from agentcost.auth.models import AuthContext, Role

    @app.get("/api/protected")
    async def protected(user: AuthContext = Depends(get_current_user)):
        return {"org": user.org_id, "email": user.email}

    @app.get("/api/admin-only")
    async def admin_only(user: AuthContext = Depends(require_role(Role.ORG_ADMIN))):
        return {"admin": user.email}
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_auth_config
from .models import AuthContext, AuthMethod, Role, TokenClaims

logger = logging.getLogger("agentcost.auth.deps")

# ── Security schemes ────────────────────────────────────────────────────────

# auto_error=False so missing Bearer header doesn't 401 immediately —
# we fall through to API key and session checks.
_bearer_scheme = HTTPBearer(auto_error=False)


# ── Org isolation filter ────────────────────────────────────────────────────

def org_filter_sql(auth: AuthContext, alias: str = "") -> tuple[str, list]:
    """Generate SQL WHERE clause for multi-tenant org isolation.

    Platform admins see everything. Other users only see their org's data.

    Args:
        auth: Current auth context
        alias: Table alias prefix (e.g., "t." for "t.org_id")

    Returns:
        (where_clause, params) — e.g., ("AND t.org_id = ?", ["org-123"])
    """
    col = f"{alias}org_id" if alias else "org_id"

    if auth.is_platform_admin:
        return "", []
    return f"AND {col} = ?", [auth.org_id]


# ── Core dependency: resolve auth context ───────────────────────────────────

async def get_current_user(
    request: Request,
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> AuthContext:
    """Resolve the authenticated user from the request.

    Tries in order: Bearer JWT → API key → Session cookie → reject (401).
    If auth is disabled, returns anonymous context.
    """
    config = get_auth_config()

    # ── Auth disabled? Return anonymous ─────────────────────────
    if not config.enabled:
        return AuthContext.anonymous()

    # ── Strategy 1: Bearer JWT ──────────────────────────────────
    if bearer and bearer.credentials:
        try:
            from .jwt_provider import validate_jwt
            claims = validate_jwt(bearer.credentials, config)
            return AuthContext(claims=claims, method=AuthMethod.OIDC)
        except Exception as e:
            logger.warning("JWT validation failed: %s", e)
            # Don't return 401 yet — maybe they also sent an API key
            pass

    # ── Strategy 2: API Key header ──────────────────────────────
    api_key = request.headers.get(config.api_key_header)
    if api_key:
        from .api_key import validate_api_key
        ctx = validate_api_key(api_key)
        if ctx:
            return ctx
        raise HTTPException(status_code=401, detail="Invalid or expired API key")

    # ── Strategy 3: Session cookie ──────────────────────────────
    session_token = request.cookies.get(config.session_cookie_name)
    if session_token:
        ctx = _validate_session(session_token, config)
        if ctx:
            return ctx
        # Session invalid/expired — fall through to 401

    # ── Nothing worked ──────────────────────────────────────────
    raise HTTPException(
        status_code=401,
        detail="Authentication required. Provide Bearer token, API key, or session cookie.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_optional_user(
    request: Request,
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> AuthContext:
    """Like get_current_user but returns anonymous instead of 401.

    Use for endpoints that work both authenticated and unauthenticated
    (e.g., public dashboard with optional org filtering).
    """
    try:
        return await get_current_user(request, bearer)
    except HTTPException:
        return AuthContext.anonymous()


# ── Role-based access control ───────────────────────────────────────────────

def require_role(minimum_role: Role) -> Callable:
    """Dependency factory: require the user to have at least the given role.

    Usage:
        @app.get("/admin")
        async def admin(user: AuthContext = Depends(require_role(Role.ORG_ADMIN))):
            ...
    """
    async def _check(
        user: AuthContext = Depends(get_current_user),
    ) -> AuthContext:
        if not user.has_role(minimum_role):
            raise HTTPException(
                status_code=403,
                detail=f"Requires role '{minimum_role.value}' or higher. Your role: '{user.role.value}'",
            )
        return user
    return _check


def require_org_match(target_org_id: str) -> Callable:
    """Dependency factory: require the user belongs to the specified org.

    Platform admins bypass this check.
    """
    async def _check(
        user: AuthContext = Depends(get_current_user),
    ) -> AuthContext:
        if user.is_platform_admin:
            return user
        if user.org_id != target_org_id:
            raise HTTPException(
                status_code=403,
                detail="You don't have access to this organization's resources.",
            )
        return user
    return _check


# ── Session validation (simple signed cookie) ──────────────────────────────

def _validate_session(token: str, config) -> Optional[AuthContext]:
    """Validate a session cookie.

    Sessions are created after SAML auth and stored as signed JWTs
    (using the session_secret as HMAC key). This avoids needing a
    server-side session store for the initial implementation.
    """
    try:
        import jwt as pyjwt
        payload = pyjwt.decode(
            token,
            key=config.session_secret,
            algorithms=["HS256"],
            options={"verify_exp": True},
        )
        claims = TokenClaims.from_jwt(payload)
        return AuthContext(
            claims=claims,
            method=AuthMethod.SESSION,
            session_id=payload.get("session_id"),
        )
    except Exception as e:
        logger.debug("Session validation failed: %s", e)
        return None


def create_session_token(claims: TokenClaims, config=None) -> str:
    """Create a signed session cookie JWT from SAML/OIDC claims.

    Used after successful SAML ACS to set a browser cookie.
    """
    import jwt as pyjwt
    import time
    import uuid

    cfg = config or get_auth_config()

    payload = {
        "sub": claims.sub,
        "email": claims.email,
        "name": claims.name,
        "org_id": claims.org_id,
        "org_slug": claims.org_slug,
        "roles": claims.roles,
        "session_id": str(uuid.uuid4()),
        "iat": int(time.time()),
        "exp": int(time.time()) + cfg.session_max_age,
    }

    return pyjwt.encode(payload, cfg.session_secret, algorithm="HS256")

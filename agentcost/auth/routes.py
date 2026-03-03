"""
Auth Routes — FastAPI router for all authentication endpoints.

Endpoints:
  OIDC:
    GET  /auth/login            → Redirect to Keycloak login page
    GET  /auth/callback         → Handle OIDC auth code callback
    POST /auth/token            → Exchange auth code for tokens
    POST /auth/refresh          → Refresh an access token
    POST /auth/logout           → Logout (revoke session)

  SAML:
    GET  /auth/saml/metadata    → SP metadata XML
    GET  /auth/saml/login       → Initiate SAML SSO redirect
    POST /auth/saml/acs         → Assertion Consumer Service
    GET  /auth/saml/slo         → Single Logout

  User/Org:
    GET  /auth/me               → Current user info
    POST /auth/org/provision    → Auto-provision org + user on first login

Mount in the main app:
    from agentcost.auth.routes import auth_router
    app.include_router(auth_router)
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
import ssl
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .config import get_auth_config, AuthConfig
from .dependencies import get_current_user, create_session_token
from .models import AuthContext, TokenClaims

logger = logging.getLogger("agentcost.auth.routes")

auth_router = APIRouter(prefix="/auth", tags=["authentication"])


# ─────────────────────────────────────────────────────────────────────────────
# OIDC ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────


@auth_router.get("/login")
async def oidc_login(
    request: Request,
    redirect_uri: str = "",
    state: str = "/",
):
    """Redirect the browser to Keycloak's OIDC login page.

    After login, Keycloak redirects back to /auth/callback with an auth code.
    """
    config = get_auth_config()
    # Build callback URL dynamically from the current request
    if not redirect_uri:
        redirect_uri = str(request.url_for("oidc_callback"))
        # Fix 0.0.0.0 → localhost for Keycloak redirect URI matching
        redirect_uri = redirect_uri.replace("://0.0.0.0:", "://localhost:")
    params = urllib.parse.urlencode(
        {
            "client_id": config.oidc_client_id,
            "response_type": "code",
            "scope": "openid email profile",
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )
    return RedirectResponse(f"{config.auth_url}?{params}")


@auth_router.get("/callback")
async def oidc_callback(
    request: Request,
    code: str = "",
    state: str = "/",
    error: str = "",
    error_description: str = "",
):
    """Handle the OIDC auth code callback from Keycloak.

    Exchanges the auth code for tokens and sets a session cookie.
    """
    if error:
        return JSONResponse(
            status_code=400,
            content={"error": error, "description": error_description},
        )

    if not code:
        raise HTTPException(400, "Missing authorization code")

    config = get_auth_config()

    # Exchange auth code for tokens
    callback_uri = str(request.url_for("oidc_callback")).replace(
        "://0.0.0.0:", "://localhost:"
    )
    print(f"[AUTH DEBUG] token_url={config.token_url}")
    print(f"[AUTH DEBUG] redirect_uri={callback_uri}")
    print(f"[AUTH DEBUG] code={code[:20]}...")
    token_data = _exchange_code(
        code=code,
        redirect_uri=callback_uri,
        config=config,
    )

    if "error" in token_data:
        print(f"[AUTH DEBUG] Token exchange error: {token_data}")
        logger.error("Token exchange error: %s", token_data)
        raise HTTPException(
            400,
            f"Token validation failed: {token_data.get('error_description', token_data['error'])}",
        )

    access_token = token_data["access_token"]
    token_data.get("refresh_token", "")
    print("[AUTH DEBUG] Token exchange OK, validating JWT...")

    # Validate the access token to get claims
    from .jwt_provider import validate_jwt

    try:
        claims = validate_jwt(access_token, config)
        print(f"[AUTH DEBUG] JWT validated: sub={claims.sub} org={claims.org_id}")
    except Exception as e:
        print(f"[AUTH DEBUG] JWT validation failed: {e}")
        raise HTTPException(400, f"Token validation failed: {e}")

    # Auto-provision org + user if first login
    await _auto_provision(claims)

    # Set session cookie and redirect
    session_token = create_session_token(claims, config)

    response = RedirectResponse(url=state or "/", status_code=302)
    response.set_cookie(
        key=config.session_cookie_name,
        value=session_token,
        max_age=config.session_max_age,
        httponly=True,
        samesite="lax",
        secure=False,  # True in production with HTTPS
    )

    return response


@auth_router.post("/token")
async def token_exchange(
    request: Request,
    grant_type: str = "authorization_code",
    code: str = "",
    redirect_uri: str = "",
    refresh_token: str = "",
):
    """Exchange auth code or refresh token for access/refresh tokens.

    This endpoint is used by SPA clients that handle tokens directly
    (instead of cookie-based sessions).
    """
    config = get_auth_config()

    if grant_type == "authorization_code":
        if not code:
            raise HTTPException(400, "Missing 'code' parameter")
        result = _exchange_code(code, redirect_uri, config)
    elif grant_type == "refresh_token":
        if not refresh_token:
            raise HTTPException(400, "Missing 'refresh_token' parameter")
        result = _refresh_token(refresh_token, config)
    else:
        raise HTTPException(400, f"Unsupported grant_type: {grant_type}")

    if "error" in result:
        raise HTTPException(400, result)

    return result


@auth_router.post("/refresh")
async def refresh(refresh_token: str):
    """Refresh an access token using a refresh token."""
    config = get_auth_config()
    result = _refresh_token(refresh_token, config)
    if "error" in result:
        raise HTTPException(401, result)
    return result


@auth_router.post("/logout")
async def logout(request: Request, response: Response):
    """Logout: clear session cookie and optionally revoke tokens at Keycloak."""
    config = get_auth_config()

    # Clear session cookie
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie(config.session_cookie_name)

    return response


# ─────────────────────────────────────────────────────────────────────────────
# SAML ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────


@auth_router.get("/saml/metadata", response_class=HTMLResponse)
async def saml_metadata():
    """Return SAML SP metadata XML.

    Enterprise customers download this and upload it to their IdP
    (Okta, Azure AD, Ping, etc.) to configure the SAML trust.
    """
    from .saml_provider import get_sp_metadata

    metadata = get_sp_metadata()
    return Response(content=metadata, media_type="application/xml")


@auth_router.get("/saml/login")
async def saml_login(
    request: Request,
    relay_state: str = "/",
):
    """Initiate SAML SSO — redirect to Keycloak (which may redirect to corporate IdP)."""
    from .saml_provider import create_authn_request

    request_data = _build_saml_request_data(request)
    redirect_url, info = create_authn_request(request_data, relay_state=relay_state)

    logger.info("SAML AuthnRequest initiated, redirecting to: %s", redirect_url)
    return RedirectResponse(redirect_url)


@auth_router.post("/saml/acs")
async def saml_acs(request: Request):
    """SAML Assertion Consumer Service — receives POST from IdP after auth.

    Validates the SAML response, extracts user attributes, provisions
    the user/org if needed, and sets a session cookie.
    """
    from .saml_provider import process_saml_response

    # Read form data
    form = await request.form()
    saml_response = form.get("SAMLResponse", "")
    relay_state = form.get("RelayState", "/")

    if not saml_response:
        raise HTTPException(400, "Missing SAMLResponse in POST body")

    # Build request data for python3-saml
    request_data = _build_saml_request_data(
        request, post_data={"SAMLResponse": saml_response}
    )

    claims, errors = process_saml_response(request_data)

    if errors:
        logger.error("SAML ACS errors: %s", errors)
        raise HTTPException(400, f"SAML authentication failed: {'; '.join(errors)}")

    if not claims:
        raise HTTPException(400, "SAML authentication failed: no claims returned")

    # Auto-provision org + user
    await _auto_provision(claims)

    # Set session cookie
    config = get_auth_config()
    session_token = create_session_token(claims, config)

    response = RedirectResponse(url=relay_state or "/", status_code=302)
    response.set_cookie(
        key=config.session_cookie_name,
        value=session_token,
        max_age=config.session_max_age,
        httponly=True,
        samesite="lax",
        secure=False,
    )

    logger.info("SAML ACS success: email=%s org=%s", claims.email, claims.org_id)
    return response


@auth_router.get("/saml/slo")
async def saml_slo(request: Request, response: Response):
    """SAML Single Logout endpoint."""
    from .saml_provider import process_slo

    request_data = _build_saml_request_data(request)
    redirect_url, errors = process_slo(request_data)

    config = get_auth_config()
    resp = RedirectResponse(url=redirect_url or "/", status_code=302)
    resp.delete_cookie(config.session_cookie_name)
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# USER / ORG ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────


@auth_router.get("/me")
async def me(user: AuthContext = Depends(get_current_user)):
    """Return the current authenticated user's info."""
    return {
        "user_id": user.user_id,
        "email": user.email,
        "name": user.claims.name,
        "org_id": user.org_id,
        "org_slug": user.org_slug,
        "role": user.role.value,
        "roles": user.claims.roles,
        "auth_method": user.method.value,
    }


@auth_router.get("/health")
async def auth_health():
    """Check if Keycloak is reachable and the realm exists."""
    config = get_auth_config()

    if not config.enabled:
        return {"status": "disabled", "message": "Auth is disabled"}

    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        url = f"{config.keycloak_url}/realms/{config.realm}/.well-known/openid-configuration"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            data = json.loads(resp.read())
            return {
                "status": "ok",
                "keycloak": config.keycloak_url,
                "realm": config.realm,
                "issuer": data.get("issuer"),
                "endpoints": {
                    "authorization": data.get("authorization_endpoint"),
                    "token": data.get("token_endpoint"),
                    "jwks": data.get("jwks_uri"),
                },
            }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "keycloak": config.keycloak_url,
        }


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _exchange_code(code: str, redirect_uri: str, config: AuthConfig) -> dict:
    """Exchange an OIDC auth code for tokens at Keycloak's token endpoint."""
    data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": config.oidc_client_id,
            "client_secret": config.oidc_client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }
    ).encode("utf-8")

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        config.token_url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error("Token exchange failed: %s %s", e.code, body)
        return {"error": "token_exchange_failed", "error_description": body}


def _refresh_token(refresh_token: str, config: AuthConfig) -> dict:
    """Refresh an access token using a refresh token."""
    data = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "client_id": config.oidc_client_id,
            "client_secret": config.oidc_client_secret,
            "refresh_token": refresh_token,
        }
    ).encode("utf-8")

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        config.token_url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"error": "refresh_failed", "error_description": body}


def _build_saml_request_data(
    request: Request, post_data: Optional[dict] = None
) -> dict:
    """Build the request dict that python3-saml expects."""
    return {
        "http_host": request.headers.get("host", "localhost:8100"),
        "server_port": request.url.port or 443,
        "script_name": request.url.path,
        "get_data": dict(request.query_params),
        "post_data": post_data or {},
    }


async def _auto_provision(claims: TokenClaims) -> None:
    """Auto-provision org and user in the AgentCost database on first login.

    Called after successful OIDC or SAML authentication. Uses the org_id
    and email from the token claims to create records if they don't exist.

    This is idempotent — safe to call on every login.
    """
    try:
        from ..data.connection import get_db
        import uuid
        from datetime import datetime

        db = get_db()
        now = datetime.utcnow().isoformat()

        # Default org_id if token doesn't have one
        org_id = claims.org_id or "default"
        org_slug = claims.org_slug or org_id

        # Ensure org exists — use separate check + insert to avoid
        # ON CONFLICT issues across SQLite/Postgres
        try:
            existing_org = db.fetch_one("SELECT id FROM orgs WHERE id = ?", (org_id,))
            if not existing_org:
                db.execute(
                    "INSERT INTO orgs (id, name, slug, plan, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (org_id, org_slug, org_slug, "free", now, now),
                )
                logger.info("Auto-provisioned org: %s (%s)", org_id, org_slug)
        except Exception as e:
            # Org might already exist (race condition) — that's fine
            logger.debug("Org provision note: %s", e)

        # Ensure user exists
        if claims.email:
            try:
                existing_user = db.fetch_one(
                    "SELECT id FROM users WHERE email = ?", (claims.email,)
                )
                if not existing_user:
                    user_id = str(uuid.uuid4())
                    role = claims.highest_role.value if claims.roles else "org_member"
                    db.execute(
                        "INSERT INTO users (id, email, name, org_id, role, sso_provider_id, "
                        "last_login_at, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            user_id,
                            claims.email,
                            claims.name,
                            org_id,
                            role,
                            claims.sub,
                            now,
                            now,
                            now,
                        ),
                    )
                    logger.info(
                        "Auto-provisioned user: %s (org=%s role=%s)",
                        claims.email,
                        org_id,
                        role,
                    )
                else:
                    # Update last login
                    db.execute(
                        "UPDATE users SET last_login_at = ?, name = ?, sso_provider_id = ? WHERE email = ?",
                        (now, claims.name, claims.sub, claims.email),
                    )
            except Exception as e:
                logger.error("User provision failed: %s", e)

    except Exception as e:
        # Don't fail auth if provisioning fails — log and continue
        logger.error("Auto-provision failed: %s", e, exc_info=True)

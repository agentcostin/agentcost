"""
Org Routes — FastAPI router for multi-tenant org management (Block 2).

Endpoints:
  Organization:
    GET    /org                    → Get current org details + stats
    PUT    /org                    → Update org settings
    GET    /org/all                → List all orgs (platform_admin only)

  Team:
    GET    /org/members            → List org members
    GET    /org/members/{user_id}  → Get member details
    PUT    /org/members/{user_id}/role → Update member role
    DELETE /org/members/{user_id}  → Remove member
    PUT    /org/profile            → Update own profile
    POST   /org/leave              → Leave current org

  Invites:
    POST   /org/invites            → Create invite
    GET    /org/invites            → List invites
    POST   /org/invites/{id}/accept  → Accept invite
    POST   /org/invites/{id}/revoke  → Revoke invite
    POST   /org/invites/{id}/resend  → Resend invite
    GET    /org/invites/pending    → Get my pending invites

  Audit:
    GET    /org/audit              → Query audit log
    GET    /org/audit/verify       → Verify hash chain integrity
    GET    /org/audit/stats        → Audit log stats

Mount in the main app:
    from agentcost.org.routes import org_router
    app.include_router(org_router)
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth.dependencies import get_current_user, require_role
from ..auth.models import AuthContext, Role

logger = logging.getLogger("agentcost.org.routes")

org_router = APIRouter(prefix="/org", tags=["organization"])


# ── Pydantic models for request bodies ───────────────────────────────────────

class OrgUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    plan: Optional[str] = None
    sso_provider: Optional[str] = None
    sso_config: Optional[dict] = None

class InviteCreate(BaseModel):
    email: str
    role: str = "org_member"

class RoleUpdate(BaseModel):
    role: str

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    avatar_url: Optional[str] = None


# ── Service factories ────────────────────────────────────────────────────────

def _org_svc():
    from .org_service import OrgService
    return OrgService()

def _team_svc():
    from .team_service import TeamService
    return TeamService()

def _invite_svc():
    from .invite_service import InviteService
    return InviteService()

def _audit_svc():
    from .audit_service import AuditService
    return AuditService()


# ─────────────────────────────────────────────────────────────────────────────
# ORGANIZATION ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@org_router.get("")
async def get_org(user: AuthContext = Depends(get_current_user)):
    """Get current user's organization details + stats."""
    svc = _org_svc()
    org = svc.get_org(user.org_id)
    if not org:
        raise HTTPException(404, "Organization not found")

    stats = svc.get_org_stats(user.org_id)
    return {**org, "stats": stats}


@org_router.put("")
async def update_org(
    body: OrgUpdate,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Update organization settings. Requires org_admin."""
    svc = _org_svc()
    audit = _audit_svc()

    updated = svc.update_org(user.org_id, **body.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(404, "Organization not found")

    audit.log_org_event(user.org_id, user.user_id, "update", body.model_dump(exclude_none=True))
    return updated


@org_router.get("/all")
async def list_orgs(
    limit: int = 50,
    offset: int = 0,
    user: AuthContext = Depends(require_role(Role.PLATFORM_ADMIN)),
):
    """List all organizations. Platform admin only."""
    svc = _org_svc()
    return svc.list_orgs(limit, offset)


@org_router.post("/create")
async def create_org(
    name: str,
    slug: str = "",
    user: AuthContext = Depends(require_role(Role.PLATFORM_ADMIN)),
):
    """Create a new organization. Platform admin only."""
    svc = _org_svc()
    audit = _audit_svc()

    org = svc.create_org(name=name, slug=slug, created_by_email=user.email)

    audit.log_org_event(org["id"], user.user_id, "create", {"name": name, "slug": org["slug"]})
    return org


# ─────────────────────────────────────────────────────────────────────────────
# TEAM ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@org_router.get("/members")
async def list_members(
    role: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    user: AuthContext = Depends(get_current_user),
):
    """List members in your organization."""
    svc = _team_svc()
    members = svc.list_members(user.org_id, role_filter=role, search=search, limit=limit, offset=offset)
    count = svc.get_member_count(user.org_id)
    return {"members": members, "total": count}


@org_router.get("/members/{user_id}")
async def get_member(
    user_id: str,
    user: AuthContext = Depends(get_current_user),
):
    """Get details of a specific team member."""
    svc = _team_svc()
    member = svc.get_member(user.org_id, user_id)
    if not member:
        raise HTTPException(404, "Member not found")
    return member


@org_router.put("/members/{user_id}/role")
async def update_member_role(
    user_id: str,
    body: RoleUpdate,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Change a member's role. Requires org_admin."""
    svc = _team_svc()
    audit = _audit_svc()

    # Get old role for audit
    member = svc.get_member(user.org_id, user_id)
    old_role = member["role"] if member else "unknown"

    result = svc.update_role(user.org_id, user_id, body.role, user)

    if "error" in result:
        raise HTTPException(400, result["error"])

    audit.log_role_change(user.org_id, user.user_id, user_id, old_role, body.role)
    return result


@org_router.delete("/members/{user_id}")
async def remove_member(
    user_id: str,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Remove a member from the organization. Requires org_admin."""
    svc = _team_svc()
    audit = _audit_svc()

    member = svc.get_member(user.org_id, user_id)
    result = svc.remove_member(user.org_id, user_id, user)

    if "error" in result:
        raise HTTPException(400, result["error"])

    if member:
        audit.log_member_remove(user.org_id, user.user_id, member["email"])
    return result


@org_router.put("/profile")
async def update_profile(
    body: ProfileUpdate,
    user: AuthContext = Depends(get_current_user),
):
    """Update your own profile (name, avatar)."""
    svc = _team_svc()
    updated = svc.update_profile(user.user_id, **body.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(400, "No fields to update")
    return updated


@org_router.post("/leave")
async def leave_org(user: AuthContext = Depends(get_current_user)):
    """Leave your current organization."""
    svc = _team_svc()
    audit = _audit_svc()

    result = svc.leave_org(user.org_id, user.user_id)

    if "error" in result:
        raise HTTPException(400, result["error"])

    audit.log(
        event_type="member.leave", org_id=user.org_id, actor_id=user.user_id,
        action="delete", details={"email": user.email},
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# INVITE ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@org_router.post("/invites")
async def create_invite(
    body: InviteCreate,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Send an invite to join the organization. Requires org_admin."""
    svc = _invite_svc()
    audit = _audit_svc()

    result = svc.create_invite(
        org_id=user.org_id,
        email=body.email,
        role=body.role,
        invited_by=_resolve_user_id(user),
    )

    if "error" in result:
        raise HTTPException(400, result["error"])

    audit.log_invite(user.org_id, _resolve_user_id(user), body.email, body.role)
    return result


@org_router.get("/invites")
async def list_invites(
    status: Optional[str] = None,
    limit: int = 50,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """List invites for the organization. Requires org_admin."""
    svc = _invite_svc()
    return svc.list_invites(user.org_id, status_filter=status, limit=limit)


@org_router.get("/invites/pending")
async def my_pending_invites(user: AuthContext = Depends(get_current_user)):
    """Get pending invites for the current user's email."""
    svc = _invite_svc()
    return svc.get_pending_invites_for_email(user.email)


@org_router.post("/invites/{invite_id}/accept")
async def accept_invite(
    invite_id: str,
    user: AuthContext = Depends(get_current_user),
):
    """Accept a pending invite."""
    svc = _invite_svc()
    audit = _audit_svc()

    result = svc.accept_invite(invite_id, user.email, user.claims.name)

    if "error" in result:
        raise HTTPException(400, result["error"])

    if result.get("org_id"):
        audit.log(
            event_type="member.invite_accepted", org_id=result["org_id"],
            actor_id=user.user_id, action="create",
            details={"email": user.email, "role": result.get("role")},
        )
    return result


@org_router.post("/invites/{invite_id}/revoke")
async def revoke_invite(
    invite_id: str,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Revoke a pending invite. Requires org_admin."""
    svc = _invite_svc()
    result = svc.revoke_invite(invite_id, user.org_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@org_router.post("/invites/{invite_id}/resend")
async def resend_invite(
    invite_id: str,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Resend (reset expiry) a pending invite. Requires org_admin."""
    svc = _invite_svc()
    result = svc.resend_invite(invite_id, user.org_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


# ─────────────────────────────────────────────────────────────────────────────
# AUDIT LOG ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@org_router.get("/audit")
async def query_audit_log(
    event_type: Optional[str] = None,
    actor_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Query the audit log. Requires org_admin."""
    svc = _audit_svc()
    entries = svc.get_log(
        org_id=user.org_id, event_type=event_type, actor_id=actor_id,
        resource_type=resource_type, since=since, limit=limit, offset=offset,
    )
    total = svc.get_entry_count(user.org_id)
    return {"entries": entries, "total": total, "limit": limit, "offset": offset}


@org_router.get("/audit/verify")
async def verify_audit_chain(
    limit: int = Query(1000, le=10000),
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Verify the hash chain integrity of the audit log."""
    svc = _audit_svc()
    return svc.verify_chain(user.org_id, limit=limit)


@org_router.get("/audit/stats")
async def audit_stats(
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Get audit log statistics."""
    svc = _audit_svc()
    total = svc.get_entry_count(user.org_id)

    # Event type breakdown
    from ..data.connection import get_db
    db = get_db()
    rows = db.fetch_all(
        "SELECT event_type, COUNT(*) as count FROM audit_log "
        "WHERE org_id = ? GROUP BY event_type ORDER BY count DESC",
        (user.org_id,),
    )

    return {
        "total_entries": total,
        "by_event_type": {r["event_type"]: r["count"] for r in rows},
    }


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_user_id(user: AuthContext) -> str:
    """Resolve the DB user ID from the auth context.

    The JWT 'sub' is the Keycloak UUID, which may differ from the
    auto-provisioned user ID in our users table. Look up by email,
    and auto-create the user if not found (handles direct-grant tokens
    that bypass the /auth/callback auto-provisioning).
    """
    from ..data.connection import get_db
    from datetime import datetime
    import uuid

    db = get_db()
    row = db.fetch_one(
        "SELECT id FROM users WHERE email = ? AND org_id = ?",
        (user.email, user.org_id),
    )
    if row:
        return row["id"]

    # User not in DB yet — auto-provision from JWT claims
    if user.email:
        user_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        org_id = user.org_id or "default"
        role = user.role.value if user.role else "org_member"
        try:
            # Ensure org exists
            org_exists = db.fetch_one("SELECT id FROM orgs WHERE id = ?", (org_id,))
            if not org_exists:
                db.execute(
                    "INSERT INTO orgs (id, name, slug, plan, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (org_id, org_id, org_id, "free", now, now),
                )
            db.execute(
                "INSERT INTO users (id, email, name, org_id, role, sso_provider_id, "
                "last_login_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, user.email, user.claims.name, org_id, role,
                 user.claims.sub, now, now, now),
            )
            logger.info("Auto-provisioned user via _resolve_user_id: %s (org=%s)", user.email, org_id)
            return user_id
        except Exception as e:
            logger.error("Failed to auto-provision user in _resolve_user_id: %s", e)

    return user.user_id
"""
TeamService — Team member management within an organization.

Handles listing members, updating roles, removing users, and user profiles.
All operations are scoped to the caller's org unless they're platform_admin.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from ..auth.models import AuthContext, Role
from ..data.connection import get_db


class TeamService:
    """Stateless service for team operations."""

    def __init__(self, db=None):
        self._db = db or get_db()

    # ── List Members ─────────────────────────────────────────────

    def list_members(
        self,
        org_id: str,
        role_filter: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """List org members with optional role/search filters."""
        sql = "SELECT id, email, name, role, avatar_url, last_login_at, created_at FROM users WHERE org_id = ?"
        params: list = [org_id]

        if role_filter:
            sql += " AND role = ?"
            params.append(role_filter)

        if search:
            sql += " AND (email LIKE ? OR name LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])

        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self._db.fetch_all(sql, params)
        return [dict(r) for r in rows]

    def get_member_count(self, org_id: str) -> int:
        """Get total member count for an org."""
        row = self._db.fetch_one(
            "SELECT COUNT(*) as count FROM users WHERE org_id = ?", (org_id,)
        )
        return row["count"] if row else 0

    # ── Get Member ───────────────────────────────────────────────

    def get_member(self, org_id: str, user_id: str) -> Optional[dict]:
        """Get a specific member by ID within an org."""
        row = self._db.fetch_one(
            "SELECT id, email, name, role, avatar_url, last_login_at, created_at "
            "FROM users WHERE id = ? AND org_id = ?",
            (user_id, org_id),
        )
        return dict(row) if row else None

    def get_member_by_email(self, org_id: str, email: str) -> Optional[dict]:
        """Get a member by email within an org."""
        row = self._db.fetch_one(
            "SELECT id, email, name, role, avatar_url, last_login_at, created_at "
            "FROM users WHERE email = ? AND org_id = ?",
            (email, org_id),
        )
        return dict(row) if row else None

    # ── Update Role ──────────────────────────────────────────────

    def update_role(
        self,
        org_id: str,
        target_user_id: str,
        new_role: str,
        actor: AuthContext,
    ) -> dict:
        """Update a member's role.

        Rules:
          - Can't change your own role
          - Can only set roles at or below your own level
          - Must be org_admin+ to change roles
          - Can't demote the last org_admin
        """
        # Validate the new role
        try:
            target_role = Role(new_role)
        except ValueError:
            return {"error": f"Invalid role: {new_role}"}

        # Can't change own role
        if target_user_id == actor.user_id:
            return {"error": "Cannot change your own role"}

        # Can only assign roles at or below your level
        if not actor.is_platform_admin and target_role > actor.role:
            return {"error": f"Cannot assign role '{new_role}' — exceeds your own role"}

        # Check target exists
        member = self.get_member(org_id, target_user_id)
        if not member:
            return {"error": "User not found in this organization"}

        # Prevent removing the last admin
        if member["role"] in ("org_admin", "platform_admin") and new_role not in (
            "org_admin",
            "platform_admin",
        ):
            admin_count = self._db.fetch_one(
                "SELECT COUNT(*) as count FROM users WHERE org_id = ? AND role IN ('org_admin', 'platform_admin')",
                (org_id,),
            )
            if admin_count and admin_count["count"] <= 1:
                return {
                    "error": "Cannot demote the last admin — org must have at least one admin"
                }

        # Do the update
        now = datetime.utcnow().isoformat()
        self._db.execute(
            "UPDATE users SET role = ?, updated_at = ? WHERE id = ? AND org_id = ?",
            (new_role, now, target_user_id, org_id),
        )

        return {
            "status": "updated",
            "user_id": target_user_id,
            "old_role": member["role"],
            "new_role": new_role,
        }

    # ── Update Profile ───────────────────────────────────────────

    def update_profile(self, user_id: str, **kwargs) -> Optional[dict]:
        """Update a user's own profile fields. Allowed: name, avatar_url."""
        allowed = {"name", "avatar_url"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}

        if not updates:
            return None

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = list(updates.values()) + [datetime.utcnow().isoformat(), user_id]

        self._db.execute(
            f"UPDATE users SET {set_clause}, updated_at = ? WHERE id = ?",
            params,
        )
        row = self._db.fetch_one(
            "SELECT id, email, name, role, avatar_url FROM users WHERE id = ?",
            (user_id,),
        )
        return dict(row) if row else None

    # ── Remove Member ────────────────────────────────────────────

    def remove_member(
        self,
        org_id: str,
        target_user_id: str,
        actor: AuthContext,
    ) -> dict:
        """Remove a member from the org.

        Rules:
          - Can't remove yourself (use leave_org instead)
          - Must be org_admin+
          - Can't remove the last admin
        """
        if target_user_id == actor.user_id:
            return {"error": "Cannot remove yourself — use leave_org instead"}

        member = self.get_member(org_id, target_user_id)
        if not member:
            return {"error": "User not found in this organization"}

        # Prevent removing the last admin
        if member["role"] in ("org_admin", "platform_admin"):
            admin_count = self._db.fetch_one(
                "SELECT COUNT(*) as count FROM users WHERE org_id = ? AND role IN ('org_admin', 'platform_admin')",
                (org_id,),
            )
            if admin_count and admin_count["count"] <= 1:
                return {"error": "Cannot remove the last admin"}

        self._db.execute(
            "DELETE FROM users WHERE id = ? AND org_id = ?", (target_user_id, org_id)
        )
        return {
            "status": "removed",
            "user_id": target_user_id,
            "email": member["email"],
        }

    # ── Leave Org ────────────────────────────────────────────────

    def leave_org(self, org_id: str, user_id: str) -> dict:
        """User voluntarily leaves an org.

        Can't leave if you're the last admin.
        """
        member = self.get_member(org_id, user_id)
        if not member:
            return {"error": "You are not a member of this organization"}

        if member["role"] in ("org_admin", "platform_admin"):
            admin_count = self._db.fetch_one(
                "SELECT COUNT(*) as count FROM users WHERE org_id = ? AND role IN ('org_admin', 'platform_admin')",
                (org_id,),
            )
            if admin_count and admin_count["count"] <= 1:
                return {
                    "error": "Cannot leave — you are the last admin. Transfer admin role first."
                }

        self._db.execute(
            "DELETE FROM users WHERE id = ? AND org_id = ?", (user_id, org_id)
        )
        return {"status": "left", "org_id": org_id}

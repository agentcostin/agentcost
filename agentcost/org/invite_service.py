"""
InviteService — Email-based team invitations.

Lifecycle: create → pending → accepted/expired/revoked
  - Invites are scoped to an org
  - Accepting an invite creates a user record in the org
  - Invites expire after a configurable period (default 7 days)
  - Duplicate invites to same email are rejected
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

from ..data.connection import get_db


INVITE_EXPIRY_DAYS = 7


class InviteService:
    """Stateless service for invite operations."""

    def __init__(self, db=None):
        self._db = db or get_db()

    # ── Create Invite ────────────────────────────────────────────

    def create_invite(
        self,
        org_id: str,
        email: str,
        role: str = "org_member",
        invited_by: str = "",
    ) -> dict:
        """Create a new invitation to join an org.

        Returns error if:
          - Email is already a member of the org
          - A pending invite already exists for this email + org
        """
        email = email.lower().strip()

        # Check if already a member
        existing_user = self._db.fetch_one(
            "SELECT id FROM users WHERE email = ? AND org_id = ?",
            (email, org_id),
        )
        if existing_user:
            return {"error": f"{email} is already a member of this organization"}

        # Check for existing pending invite
        existing_invite = self._db.fetch_one(
            "SELECT id FROM invites WHERE email = ? AND org_id = ? AND status = 'pending'",
            (email, org_id),
        )
        if existing_invite:
            return {"error": f"A pending invite already exists for {email}"}

        invite_id = str(uuid.uuid4())
        now = datetime.utcnow()
        expires_at = now + timedelta(days=INVITE_EXPIRY_DAYS)

        self._db.execute(
            "INSERT INTO invites (id, org_id, email, role, invited_by, status, expires_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
            (invite_id, org_id, email, role, invited_by, expires_at.isoformat(), now.isoformat()),
        )

        return {
            "id": invite_id,
            "org_id": org_id,
            "email": email,
            "role": role,
            "status": "pending",
            "expires_at": expires_at.isoformat(),
        }

    # ── List Invites ─────────────────────────────────────────────

    def list_invites(
        self,
        org_id: str,
        status_filter: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """List invites for an org, optionally filtered by status."""
        sql = "SELECT id, email, role, invited_by, status, expires_at, created_at FROM invites WHERE org_id = ?"
        params: list = [org_id]

        if status_filter:
            sql += " AND status = ?"
            params.append(status_filter)

        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._db.fetch_all(sql, params)
        result = []
        for r in rows:
            invite = dict(r)
            # Auto-expire if past expiry date
            if invite["status"] == "pending" and invite.get("expires_at"):
                try:
                    exp = datetime.fromisoformat(invite["expires_at"].replace("Z", "+00:00").replace("+00:00", ""))
                    if exp < datetime.utcnow():
                        self._expire_invite(invite["id"])
                        invite["status"] = "expired"
                except (ValueError, TypeError):
                    pass
            result.append(invite)
        return result

    # ── Get Invite ───────────────────────────────────────────────

    def get_invite(self, invite_id: str) -> Optional[dict]:
        """Get a specific invite by ID."""
        row = self._db.fetch_one(
            "SELECT * FROM invites WHERE id = ?", (invite_id,)
        )
        return dict(row) if row else None

    def get_pending_invites_for_email(self, email: str) -> list[dict]:
        """Get all pending invites for an email across all orgs."""
        rows = self._db.fetch_all(
            "SELECT i.id, i.org_id, o.name as org_name, i.role, i.expires_at, i.created_at "
            "FROM invites i JOIN orgs o ON i.org_id = o.id "
            "WHERE i.email = ? AND i.status = 'pending' "
            "ORDER BY i.created_at DESC",
            (email.lower().strip(),),
        )
        return [dict(r) for r in rows]

    # ── Accept Invite ────────────────────────────────────────────

    def accept_invite(self, invite_id: str, user_email: str, user_name: str = "") -> dict:
        """Accept an invite — creates a user record in the org.

        The accepting user's email must match the invite email.
        """
        invite = self.get_invite(invite_id)
        if not invite:
            return {"error": "Invite not found"}

        if invite["status"] != "pending":
            return {"error": f"Invite is {invite['status']}, cannot accept"}

        # Check expiry
        if invite.get("expires_at"):
            try:
                exp = datetime.fromisoformat(invite["expires_at"].replace("Z", "+00:00").replace("+00:00", ""))
                if exp < datetime.utcnow():
                    self._expire_invite(invite_id)
                    return {"error": "Invite has expired"}
            except (ValueError, TypeError):
                pass

        # Email must match
        if user_email.lower().strip() != invite["email"].lower().strip():
            return {"error": "Email does not match the invite"}

        # Check if already a member
        existing = self._db.fetch_one(
            "SELECT id FROM users WHERE email = ? AND org_id = ?",
            (user_email, invite["org_id"]),
        )
        if existing:
            # Already a member — just mark invite accepted
            self._db.execute(
                "UPDATE invites SET status = 'accepted' WHERE id = ?", (invite_id,)
            )
            return {"status": "accepted", "note": "User was already a member"}

        # Create user
        user_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        self._db.execute(
            "INSERT INTO users (id, email, name, org_id, role, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, user_email, user_name, invite["org_id"], invite["role"], now, now),
        )

        # Mark invite accepted
        self._db.execute(
            "UPDATE invites SET status = 'accepted' WHERE id = ?", (invite_id,)
        )

        return {
            "status": "accepted",
            "user_id": user_id,
            "org_id": invite["org_id"],
            "role": invite["role"],
        }

    # ── Revoke Invite ────────────────────────────────────────────

    def revoke_invite(self, invite_id: str, org_id: str) -> dict:
        """Revoke a pending invite."""
        invite = self.get_invite(invite_id)
        if not invite:
            return {"error": "Invite not found"}

        if invite["org_id"] != org_id:
            return {"error": "Invite does not belong to this organization"}

        if invite["status"] != "pending":
            return {"error": f"Cannot revoke — invite is {invite['status']}"}

        self._db.execute(
            "UPDATE invites SET status = 'revoked' WHERE id = ?", (invite_id,)
        )
        return {"status": "revoked", "id": invite_id}

    # ── Resend Invite ────────────────────────────────────────────

    def resend_invite(self, invite_id: str, org_id: str) -> dict:
        """Reset expiry on a pending invite (simulates resend)."""
        invite = self.get_invite(invite_id)
        if not invite:
            return {"error": "Invite not found"}
        if invite["org_id"] != org_id:
            return {"error": "Invite does not belong to this organization"}

        new_expiry = (datetime.utcnow() + timedelta(days=INVITE_EXPIRY_DAYS)).isoformat()

        # If expired, reset to pending
        self._db.execute(
            "UPDATE invites SET status = 'pending', expires_at = ? WHERE id = ?",
            (new_expiry, invite_id),
        )
        return {"status": "resent", "id": invite_id, "new_expires_at": new_expiry}

    # ── Internal ─────────────────────────────────────────────────

    def _expire_invite(self, invite_id: str) -> None:
        self._db.execute(
            "UPDATE invites SET status = 'expired' WHERE id = ?", (invite_id,)
        )

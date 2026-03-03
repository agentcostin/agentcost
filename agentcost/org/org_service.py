"""
OrgService — Organization lifecycle management.

Handles creation, updates, plan changes, and SSO configuration for orgs.
All methods are org-scoped and require an AuthContext for authorization.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Optional

from ..data.connection import get_db


class OrgService:
    """Stateless service — gets a DB handle per call."""

    def __init__(self, db=None):
        self._db = db or get_db()

    # ── Create ───────────────────────────────────────────────────

    def create_org(
        self,
        name: str,
        slug: str = "",
        plan: str = "free",
        created_by_email: str = "",
    ) -> dict:
        """Create a new organization and optionally its first admin user.

        Returns the created org dict.
        """
        org_id = str(uuid.uuid4())
        if not slug:
            slug = self._slugify(name)

        # Ensure slug uniqueness
        existing = self._db.fetch_one("SELECT id FROM orgs WHERE slug = ?", (slug,))
        if existing:
            slug = f"{slug}-{org_id[:8]}"

        now = datetime.utcnow().isoformat()
        self._db.execute(
            "INSERT INTO orgs (id, name, slug, plan, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (org_id, name, slug, plan, now, now),
        )

        # If a creator email is provided, make them org_admin
        if created_by_email:
            user_id = str(uuid.uuid4())
            self._db.execute(
                "INSERT INTO users (id, email, name, org_id, role, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'org_admin', ?, ?) "
                "ON CONFLICT (email) DO UPDATE SET org_id = ?, role = 'org_admin', updated_at = ?",
                (user_id, created_by_email, "", org_id, now, now, org_id, now),
            )

        return {"id": org_id, "name": name, "slug": slug, "plan": plan}

    # ── Read ─────────────────────────────────────────────────────

    def get_org(self, org_id: str) -> Optional[dict]:
        """Get org by ID."""
        row = self._db.fetch_one("SELECT * FROM orgs WHERE id = ?", (org_id,))
        return dict(row) if row else None

    def get_org_by_slug(self, slug: str) -> Optional[dict]:
        """Get org by slug."""
        row = self._db.fetch_one("SELECT * FROM orgs WHERE slug = ?", (slug,))
        return dict(row) if row else None

    def list_orgs(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """List all orgs (platform_admin only)."""
        rows = self._db.fetch_all(
            "SELECT id, name, slug, plan, created_at FROM orgs ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [dict(r) for r in rows]

    def get_org_stats(self, org_id: str) -> dict:
        """Get org statistics — member count, trace count, total cost."""
        user_count = self._db.fetch_one(
            "SELECT COUNT(*) as count FROM users WHERE org_id = ?", (org_id,)
        )
        trace_count = self._db.fetch_one(
            "SELECT COUNT(*) as count FROM trace_events WHERE org_id = ?", (org_id,)
        )
        total_cost = self._db.fetch_one(
            "SELECT COALESCE(SUM(cost), 0) as total FROM trace_events WHERE org_id = ?",
            (org_id,),
        )
        api_key_count = self._db.fetch_one(
            "SELECT COUNT(*) as count FROM api_keys WHERE org_id = ?", (org_id,)
        )
        return {
            "org_id": org_id,
            "members": user_count["count"] if user_count else 0,
            "traces": trace_count["count"] if trace_count else 0,
            "total_cost": round(total_cost["total"], 4) if total_cost else 0,
            "api_keys": api_key_count["count"] if api_key_count else 0,
        }

    # ── Update ───────────────────────────────────────────────────

    def update_org(self, org_id: str, **kwargs) -> Optional[dict]:
        """Update org fields. Allowed: name, slug, plan, sso_provider, sso_config."""
        allowed = {"name", "slug", "plan", "sso_provider", "sso_config"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}

        if not updates:
            return self.get_org(org_id)

        # Serialize sso_config if dict
        if "sso_config" in updates and isinstance(updates["sso_config"], dict):
            updates["sso_config"] = json.dumps(updates["sso_config"])

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = list(updates.values()) + [datetime.utcnow().isoformat(), org_id]

        self._db.execute(
            f"UPDATE orgs SET {set_clause}, updated_at = ? WHERE id = ?",
            params,
        )
        return self.get_org(org_id)

    # ── Delete ───────────────────────────────────────────────────

    def delete_org(self, org_id: str) -> bool:
        """Delete an org and all associated data. USE WITH CAUTION.

        In production, this should be a soft-delete with a grace period.
        """
        # Delete in dependency order
        for table in [
            "cost_allocations",
            "cost_centers",
            "approval_requests",
            "policies",
            "notification_channels",
            "agent_scorecards",
            "audit_log",
            "invites",
            "api_keys",
            "users",
        ]:
            self._db.execute(f"DELETE FROM {table} WHERE org_id = ?", (org_id,))

        self._db.execute("DELETE FROM orgs WHERE id = ?", (org_id,))
        return True

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _slugify(name: str) -> str:
        """Convert org name to URL-safe slug."""
        slug = name.lower().strip()
        slug = re.sub(r"[^a-z0-9\s-]", "", slug)
        slug = re.sub(r"[\s-]+", "-", slug)
        return slug[:50].strip("-")

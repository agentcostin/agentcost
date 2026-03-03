"""
AuditService — Hash-chained, immutable audit log.

Every significant action in AgentCost is recorded here:
  - Auth events: login, logout, failed_login
  - Org events: org.create, org.update, org.delete
  - Team events: member.invite, member.role_change, member.remove
  - Data events: budget.set, api_key.create, api_key.revoke
  - Agent events: llm_call, benchmark.run

Entries are hash-chained: each entry's hash includes the previous entry's hash,
creating a tamper-evident chain. This satisfies enterprise audit requirements
and supports the AI governance compliance features (AI6 framework).

The audit log is APPEND-ONLY — no updates or deletes.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional

from ..data.connection import get_db


class AuditService:
    """Stateless service for audit log operations."""

    def __init__(self, db=None):
        self._db = db or get_db()

    # ── Write ────────────────────────────────────────────────────

    def log(
        self,
        event_type: str,
        org_id: str = "",
        actor_id: str = "",
        actor_type: str = "user",
        resource_type: str = "",
        resource_id: str = "",
        action: str = "",
        details: Optional[dict] = None,
        retention_days: int = 365,
    ) -> dict:
        """Append an audit log entry with hash chaining.

        Args:
            event_type: Category of event (e.g., 'login', 'budget.set', 'llm_call')
            org_id: Organization context
            actor_id: Who performed the action (user_id, agent_id, or 'system')
            actor_type: 'user', 'agent', or 'system'
            resource_type: What was acted on ('project', 'budget', 'policy', etc.)
            resource_id: ID of the resource
            action: Verb ('create', 'update', 'delete', 'execute')
            details: JSON-serializable dict with additional context
            retention_days: How long to keep this entry

        Returns:
            The created audit entry dict.
        """
        now = datetime.utcnow()
        now_str = now.isoformat()
        details_json = json.dumps(details) if details else None
        retention_until = (now + timedelta(days=retention_days)).isoformat()

        # Get the previous entry's hash for chaining
        prev = self._db.fetch_one(
            "SELECT entry_hash FROM audit_log WHERE org_id = ? ORDER BY id DESC LIMIT 1",
            (org_id,),
        )
        prev_hash = prev["entry_hash"] if prev else "GENESIS"

        # Compute this entry's hash
        entry_data = f"{event_type}|{actor_id}|{actor_type}|{org_id}|{resource_type}|{resource_id}|{action}|{details_json}|{now_str}"
        entry_hash = hashlib.sha256(f"{prev_hash}|{entry_data}".encode()).hexdigest()

        self._db.execute(
            "INSERT INTO audit_log "
            "(event_type, actor_id, actor_type, org_id, resource_type, resource_id, "
            "action, details, prev_hash, entry_hash, timestamp, retention_until) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_type,
                actor_id,
                actor_type,
                org_id,
                resource_type,
                resource_id,
                action,
                details_json,
                prev_hash,
                entry_hash,
                now_str,
                retention_until,
            ),
        )

        return {
            "event_type": event_type,
            "actor_id": actor_id,
            "org_id": org_id,
            "action": action,
            "entry_hash": entry_hash,
            "timestamp": now.isoformat(),
        }

    # ── Convenience loggers ──────────────────────────────────────

    def log_login(self, user_id: str, org_id: str, method: str, ip: str = "") -> dict:
        return self.log(
            event_type="login",
            org_id=org_id,
            actor_id=user_id,
            action="login",
            details={"method": method, "ip": ip},
        )

    def log_role_change(
        self,
        org_id: str,
        actor_id: str,
        target_user_id: str,
        old_role: str,
        new_role: str,
    ) -> dict:
        return self.log(
            event_type="member.role_change",
            org_id=org_id,
            actor_id=actor_id,
            resource_type="user",
            resource_id=target_user_id,
            action="update",
            details={"old_role": old_role, "new_role": new_role},
        )

    def log_invite(self, org_id: str, actor_id: str, email: str, role: str) -> dict:
        return self.log(
            event_type="member.invite",
            org_id=org_id,
            actor_id=actor_id,
            resource_type="invite",
            action="create",
            details={"email": email, "role": role},
        )

    def log_member_remove(self, org_id: str, actor_id: str, removed_email: str) -> dict:
        return self.log(
            event_type="member.remove",
            org_id=org_id,
            actor_id=actor_id,
            resource_type="user",
            action="delete",
            details={"email": removed_email},
        )

    def log_api_key_event(
        self, org_id: str, actor_id: str, key_id: str, action: str
    ) -> dict:
        return self.log(
            event_type=f"api_key.{action}",
            org_id=org_id,
            actor_id=actor_id,
            resource_type="api_key",
            resource_id=key_id,
            action=action,
        )

    def log_org_event(
        self, org_id: str, actor_id: str, action: str, details: dict = None
    ) -> dict:
        return self.log(
            event_type=f"org.{action}",
            org_id=org_id,
            actor_id=actor_id,
            resource_type="org",
            resource_id=org_id,
            action=action,
            details=details,
        )

    # ── Query ────────────────────────────────────────────────────

    def get_log(
        self,
        org_id: str,
        event_type: Optional[str] = None,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Query audit log entries with filters."""
        sql = "SELECT id, event_type, actor_id, actor_type, resource_type, resource_id, action, details, entry_hash, timestamp FROM audit_log WHERE org_id = ?"
        params: list = [org_id]

        if event_type:
            sql += " AND event_type = ?"
            params.append(event_type)
        if actor_id:
            sql += " AND actor_id = ?"
            params.append(actor_id)
        if resource_type:
            sql += " AND resource_type = ?"
            params.append(resource_type)
        if since:
            sql += " AND timestamp >= ?"
            params.append(since)

        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self._db.fetch_all(sql, params)
        result = []
        for r in rows:
            entry = dict(r)
            # Parse details JSON
            if entry.get("details"):
                try:
                    entry["details"] = json.loads(entry["details"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append(entry)
        return result

    def get_entry_count(self, org_id: str) -> int:
        """Total audit entries for an org."""
        row = self._db.fetch_one(
            "SELECT COUNT(*) as count FROM audit_log WHERE org_id = ?", (org_id,)
        )
        return row["count"] if row else 0

    # ── Chain Verification ───────────────────────────────────────

    def verify_chain(self, org_id: str, limit: int = 1000) -> dict:
        """Verify the hash chain integrity of the audit log.

        Returns:
            {"valid": True/False, "entries_checked": N, "first_broken": id_or_None}
        """
        rows = self._db.fetch_all(
            "SELECT id, event_type, actor_id, actor_type, org_id, resource_type, "
            "resource_id, action, details, prev_hash, entry_hash, timestamp "
            "FROM audit_log WHERE org_id = ? ORDER BY id ASC LIMIT ?",
            (org_id, limit),
        )

        if not rows:
            return {"valid": True, "entries_checked": 0, "first_broken": None}

        expected_prev = "GENESIS"
        for row in rows:
            r = dict(row)
            # Verify prev_hash matches
            if r["prev_hash"] != expected_prev:
                return {
                    "valid": False,
                    "entries_checked": r["id"],
                    "first_broken": r["id"],
                }

            # Normalize timestamp — Postgres returns a datetime object or
            # a string with timezone. We need to match what was hashed:
            # datetime.utcnow().isoformat() which produces e.g. "2026-02-24T05:31:57.447613"
            ts = r["timestamp"]
            if hasattr(ts, "isoformat"):
                # It's a datetime object — convert to naive UTC isoformat
                ts = ts.replace(tzinfo=None).isoformat()
            else:
                ts = str(ts)
                # If string, normalize: replace space with T, strip tz suffix
                ts = ts.replace(" ", "T")
                for suffix in ["+00:00", "+00", "Z"]:
                    if ts.endswith(suffix):
                        ts = ts[: -len(suffix)]
                        break

            # Normalize details — re-serialize to match what was hashed
            details_raw = r["details"]
            if details_raw and isinstance(details_raw, str):
                try:
                    details_raw = json.dumps(json.loads(details_raw))
                except (json.JSONDecodeError, TypeError):
                    pass
            elif details_raw and isinstance(details_raw, dict):
                details_raw = json.dumps(details_raw)

            # Recompute hash
            entry_data = (
                f"{r['event_type']}|{r['actor_id']}|{r['actor_type']}|{r['org_id']}|"
                f"{r['resource_type']}|{r['resource_id']}|{r['action']}|{details_raw}|{ts}"
            )
            recomputed = hashlib.sha256(
                f"{expected_prev}|{entry_data}".encode()
            ).hexdigest()

            if recomputed != r["entry_hash"]:
                return {
                    "valid": False,
                    "entries_checked": r["id"],
                    "first_broken": r["id"],
                }

            expected_prev = r["entry_hash"]

        return {"valid": True, "entries_checked": len(rows), "first_broken": None}

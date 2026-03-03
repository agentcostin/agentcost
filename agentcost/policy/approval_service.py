"""
ApprovalService — Approval request lifecycle management.

When a policy returns 'require_approval', the system creates an approval
request that pauses the LLM call until a manager approves or denies it.

Lifecycle:
  pending → approved (manager approves, optionally unlocks budget)
  pending → denied   (manager denies with reason)
  pending → expired  (auto-expires after TTL, default 24h)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from ..data.connection import get_db


class ApprovalService:
    def __init__(self, db=None):
        self._db = db or get_db()

    # ── Create ───────────────────────────────────────────────────

    def create(
        self,
        org_id: str,
        requester_id: str,
        requester_type: str = "agent",
        request_type: str = "policy_override",
        context: Optional[dict] = None,
        estimated_cost: Optional[float] = None,
        expires_hours: int = 24,
    ) -> dict:
        """Create a new approval request.

        Args:
            org_id: Organization ID
            requester_id: Agent or user who triggered the request
            requester_type: 'agent' or 'user'
            request_type: 'budget_overage', 'policy_override', 'high_cost'
            context: JSON-serializable context about what triggered it
            estimated_cost: Estimated cost of the blocked action
            expires_hours: Auto-expire after N hours (default 24)
        """
        req_id = str(uuid.uuid4())
        now = datetime.utcnow()
        expires_at = (now + timedelta(hours=expires_hours)).isoformat()
        context_json = json.dumps(context) if context else None

        self._db.execute(
            "INSERT INTO approval_requests "
            "(id, org_id, requester_type, requester_id, request_type, context, "
            "estimated_cost, status, expires_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                req_id,
                org_id,
                requester_type,
                requester_id,
                request_type,
                context_json,
                estimated_cost,
                "pending",
                expires_at,
                now.isoformat(),
            ),
        )
        return {
            "id": req_id,
            "org_id": org_id,
            "requester_type": requester_type,
            "requester_id": requester_id,
            "request_type": request_type,
            "context": context,
            "estimated_cost": estimated_cost,
            "status": "pending",
            "expires_at": expires_at,
        }

    # ── Read ─────────────────────────────────────────────────────

    def get(self, req_id: str, org_id: str) -> Optional[dict]:
        row = self._db.fetch_one(
            "SELECT * FROM approval_requests WHERE id = ? AND org_id = ?",
            (req_id, org_id),
        )
        if not row:
            return None
        return self._parse_row(row)

    def list(
        self,
        org_id: str,
        status: Optional[str] = None,
        request_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """List approval requests with filters."""
        # Auto-expire stale requests first
        self._expire_stale(org_id)

        sql = "SELECT * FROM approval_requests WHERE org_id = ?"
        params: list = [org_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        if request_type:
            sql += " AND request_type = ?"
            params.append(request_type)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self._db.fetch_all(sql, params)

        # Count
        count_sql = "SELECT COUNT(*) as total FROM approval_requests WHERE org_id = ?"
        count_params: list = [org_id]
        if status:
            count_sql += " AND status = ?"
            count_params.append(status)
        if request_type:
            count_sql += " AND request_type = ?"
            count_params.append(request_type)
        count_row = self._db.fetch_one(count_sql, count_params)

        return {
            "requests": [self._parse_row(r) for r in rows],
            "total": count_row["total"] if count_row else 0,
            "limit": limit,
            "offset": offset,
        }

    def get_pending_count(self, org_id: str) -> int:
        """Count pending approval requests."""
        row = self._db.fetch_one(
            "SELECT COUNT(*) as count FROM approval_requests WHERE org_id = ? AND status = ?",
            (org_id, "pending"),
        )
        return row["count"] if row else 0

    # ── Decide ───────────────────────────────────────────────────

    def approve(
        self,
        req_id: str,
        org_id: str,
        decided_by: str,
        unlock_amount: Optional[float] = None,
    ) -> dict:
        """Approve a pending request."""
        req = self.get(req_id, org_id)
        if not req:
            return {"error": "Approval request not found"}
        if req["status"] != "pending":
            return {"error": f"Cannot approve — current status is '{req['status']}'"}

        now = datetime.utcnow().isoformat()
        self._db.execute(
            "UPDATE approval_requests SET status = ?, decided_by = ?, decided_at = ?, "
            "unlock_amount = ? WHERE id = ? AND org_id = ?",
            ("approved", decided_by, now, unlock_amount, req_id, org_id),
        )
        return self.get(req_id, org_id)

    def deny(
        self,
        req_id: str,
        org_id: str,
        decided_by: str,
        reason: str = "",
    ) -> dict:
        """Deny a pending request."""
        req = self.get(req_id, org_id)
        if not req:
            return {"error": "Approval request not found"}
        if req["status"] != "pending":
            return {"error": f"Cannot deny — current status is '{req['status']}'"}

        now = datetime.utcnow().isoformat()
        # Store denial reason in context
        existing_context = req.get("context") or {}
        if isinstance(existing_context, str):
            try:
                existing_context = json.loads(existing_context)
            except (json.JSONDecodeError, TypeError):
                existing_context = {}
        existing_context["denial_reason"] = reason
        context_json = json.dumps(existing_context)

        self._db.execute(
            "UPDATE approval_requests SET status = ?, decided_by = ?, decided_at = ?, "
            "context = ? WHERE id = ? AND org_id = ?",
            ("denied", decided_by, now, context_json, req_id, org_id),
        )
        return self.get(req_id, org_id)

    # ── Stats ────────────────────────────────────────────────────

    def stats(self, org_id: str) -> dict:
        """Summary stats for approval requests."""
        rows = self._db.fetch_all(
            "SELECT status, COUNT(*) as count FROM approval_requests "
            "WHERE org_id = ? GROUP BY status",
            (org_id,),
        )
        by_status = {r["status"]: r["count"] for r in rows}
        total = sum(by_status.values())

        # Average decision time for resolved requests
        # Use SQLite-compatible syntax (julianday diff), fallback for Postgres
        try:
            avg_row = self._db.fetch_one(
                "SELECT AVG((julianday(decided_at) - julianday(created_at)) * 86400) as avg_seconds "
                "FROM approval_requests WHERE org_id = ? AND decided_at IS NOT NULL",
                (org_id,),
            )
        except Exception:
            # Postgres fallback
            avg_row = self._db.fetch_one(
                "SELECT AVG(EXTRACT(EPOCH FROM (decided_at::timestamp - created_at::timestamp))) as avg_seconds "
                "FROM approval_requests WHERE org_id = ? AND decided_at IS NOT NULL",
                (org_id,),
            )
        # Fallback for SQLite where EXTRACT doesn't work
        avg_seconds = None
        if avg_row and avg_row.get("avg_seconds") is not None:
            avg_seconds = round(avg_row["avg_seconds"], 0)

        return {
            "total": total,
            "by_status": by_status,
            "pending": by_status.get("pending", 0),
            "approved": by_status.get("approved", 0),
            "denied": by_status.get("denied", 0),
            "expired": by_status.get("expired", 0),
            "avg_decision_seconds": avg_seconds,
        }

    # ── Internal ─────────────────────────────────────────────────

    def _expire_stale(self, org_id: str):
        """Auto-expire requests past their expiry time."""
        now = datetime.utcnow().isoformat()
        self._db.execute(
            "UPDATE approval_requests SET status = ? "
            "WHERE org_id = ? AND status = ? AND expires_at < ?",
            ("expired", org_id, "pending", now),
        )

    def _parse_row(self, row) -> dict:
        d = dict(row)
        if d.get("context") and isinstance(d["context"], str):
            try:
                d["context"] = json.loads(d["context"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d

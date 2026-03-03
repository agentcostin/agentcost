"""
PolicyService — Policy lifecycle management.

Policies define rules that govern LLM usage within an organization.
Each policy has:
  - conditions: JSON rules evaluated against incoming requests
  - action: what happens when conditions match (allow/deny/require_approval/log_only)
  - priority: lower number = evaluated first, first match wins
  - enabled: toggle without deleting

Condition format (JSON):
  {
    "field": "model",           // model, provider, project, agent_id, estimated_cost, time_of_day, day_of_week
    "operator": "in",           // eq, neq, gt, gte, lt, lte, in, not_in, contains, matches
    "value": ["gpt-4", "gpt-4o"]
  }

Multiple conditions use AND logic — all must match for the policy to trigger.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Optional

from ..data.connection import get_db


# ── Pre-built policy templates ───────────────────────────────────────────────

POLICY_TEMPLATES = {
    "block_expensive_models": {
        "name": "Block Expensive Models",
        "description": "Deny requests to high-cost models (GPT-4, Claude Opus) without approval",
        "conditions": [
            {"field": "model", "operator": "in", "value": ["gpt-4", "gpt-4o", "claude-3-opus", "claude-opus-4-20250514"]}
        ],
        "action": "require_approval",
        "message": "This model requires manager approval due to high cost.",
        "priority": 50,
    },
    "daily_cost_cap": {
        "name": "Daily Cost Cap per Agent",
        "description": "Deny requests when estimated cost exceeds $50/day per agent",
        "conditions": [
            {"field": "estimated_cost", "operator": "gt", "value": 50.0}
        ],
        "action": "deny",
        "message": "Daily cost cap of $50 exceeded for this agent.",
        "priority": 30,
    },
    "restrict_weekend": {
        "name": "Restrict Weekend Usage",
        "description": "Log all LLM calls made on weekends for review",
        "conditions": [
            {"field": "day_of_week", "operator": "in", "value": ["Saturday", "Sunday"]}
        ],
        "action": "log_only",
        "message": "Weekend usage logged for review.",
        "priority": 200,
    },
    "block_unknown_providers": {
        "name": "Block Unknown Providers",
        "description": "Only allow known/approved AI providers",
        "conditions": [
            {"field": "provider", "operator": "not_in", "value": ["openai", "anthropic", "google", "azure"]}
        ],
        "action": "deny",
        "message": "This AI provider is not approved for use in this organization.",
        "priority": 10,
    },
    "high_token_warning": {
        "name": "High Token Usage Warning",
        "description": "Flag requests with estimated token count over 100K for review",
        "conditions": [
            {"field": "estimated_tokens", "operator": "gt", "value": 100000}
        ],
        "action": "require_approval",
        "message": "High token usage request — requires approval.",
        "priority": 80,
    },
}


class PolicyService:

    def __init__(self, db=None):
        self._db = db or get_db()

    # ── Create ───────────────────────────────────────────────────

    def create(
        self,
        org_id: str,
        name: str,
        conditions: list[dict],
        action: str = "deny",
        description: str = "",
        message: str = "",
        priority: int = 100,
        enabled: bool = True,
        created_by: str = "",
    ) -> dict:
        if action not in ("allow", "deny", "require_approval", "log_only"):
            return {"error": f"Invalid action: {action}. Must be allow/deny/require_approval/log_only"}

        policy_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conditions_json = json.dumps(conditions)

        self._db.execute(
            "INSERT INTO policies (id, org_id, name, description, enabled, priority, "
            "conditions, action, message, created_by, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (policy_id, org_id, name, description, enabled, priority,
             conditions_json, action, message, created_by or None, now, now),
        )
        return {
            "id": policy_id, "org_id": org_id, "name": name, "description": description,
            "enabled": enabled, "priority": priority, "conditions": conditions,
            "action": action, "message": message,
        }

    def create_from_template(self, org_id: str, template_name: str, created_by: str = "") -> dict:
        """Create a policy from a pre-built template."""
        tmpl = POLICY_TEMPLATES.get(template_name)
        if not tmpl:
            return {"error": f"Unknown template: {template_name}. Available: {list(POLICY_TEMPLATES.keys())}"}
        return self.create(org_id=org_id, created_by=created_by, **tmpl)

    # ── Read ─────────────────────────────────────────────────────

    def get(self, policy_id: str, org_id: str) -> Optional[dict]:
        row = self._db.fetch_one(
            "SELECT * FROM policies WHERE id = ? AND org_id = ?", (policy_id, org_id)
        )
        if not row:
            return None
        return self._parse_row(row)

    def list(self, org_id: str, enabled_only: bool = False) -> list[dict]:
        sql = "SELECT * FROM policies WHERE org_id = ?"
        params: list = [org_id]
        if enabled_only:
            sql += " AND enabled = ?"
            params.append(True)
        sql += " ORDER BY priority ASC, created_at ASC"
        rows = self._db.fetch_all(sql, params)
        return [self._parse_row(r) for r in rows]

    def get_templates(self) -> dict:
        """Return available policy templates."""
        return POLICY_TEMPLATES

    # ── Update ───────────────────────────────────────────────────

    def update(self, policy_id: str, org_id: str, **kwargs) -> Optional[dict]:
        allowed = {"name", "description", "enabled", "priority", "conditions", "action", "message"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not updates:
            return self.get(policy_id, org_id)

        if "conditions" in updates and isinstance(updates["conditions"], list):
            updates["conditions"] = json.dumps(updates["conditions"])
        if "action" in updates and updates["action"] not in ("allow", "deny", "require_approval", "log_only"):
            return {"error": f"Invalid action: {updates['action']}"}

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = list(updates.values()) + [datetime.utcnow().isoformat(), policy_id, org_id]
        self._db.execute(
            f"UPDATE policies SET {set_clause}, updated_at = ? WHERE id = ? AND org_id = ?",
            params,
        )
        return self.get(policy_id, org_id)

    def toggle(self, policy_id: str, org_id: str, enabled: bool) -> Optional[dict]:
        """Enable or disable a policy."""
        return self.update(policy_id, org_id, enabled=enabled)

    # ── Delete ───────────────────────────────────────────────────

    def delete(self, policy_id: str, org_id: str) -> dict:
        self._db.execute(
            "DELETE FROM policies WHERE id = ? AND org_id = ?", (policy_id, org_id)
        )
        return {"status": "deleted", "id": policy_id}

    # ── Helpers ──────────────────────────────────────────────────

    def _parse_row(self, row) -> dict:
        d = dict(row)
        if d.get("conditions") and isinstance(d["conditions"], str):
            try:
                d["conditions"] = json.loads(d["conditions"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d

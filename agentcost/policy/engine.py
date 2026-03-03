"""
PolicyEngine — Evaluates incoming LLM requests against org policies.

The engine loads all enabled policies for an org (sorted by priority),
evaluates each policy's conditions against the request context, and
returns the first matching policy's action.

Evaluation order: policies sorted by priority ASC (lower = higher priority).
First match wins. If no policy matches, the request is allowed.

Supported condition fields:
  - model: model name (string match)
  - provider: provider name (string match)
  - project: project name (string match)
  - agent_id: agent identifier (string match)
  - estimated_cost: estimated cost of the call (numeric)
  - estimated_tokens: estimated token count (numeric)
  - time_of_day: current hour 0-23 (numeric)
  - day_of_week: current day name (Monday, Tuesday, etc.)

Supported operators:
  - eq, neq: equality / inequality
  - gt, gte, lt, lte: numeric comparisons
  - in, not_in: list membership
  - contains: substring match
  - matches: regex match
"""
from __future__ import annotations

import re
import logging
from datetime import datetime
from typing import Any

from .policy_service import PolicyService

logger = logging.getLogger("agentcost.policy.engine")


class PolicyEngine:
    """Evaluate LLM request context against org policies."""

    def __init__(self, db=None):
        self._policy_svc = PolicyService(db)

    def evaluate(self, org_id: str, request_context: dict) -> dict:
        """Evaluate a request against all enabled policies.

        Args:
            org_id: Organization ID
            request_context: Dict with fields like:
                {
                    "model": "gpt-4",
                    "provider": "openai",
                    "project": "chatbot-v2",
                    "agent_id": "agent-123",
                    "estimated_cost": 0.15,
                    "estimated_tokens": 5000,
                }

        Returns:
            {
                "decision": "allow" | "deny" | "require_approval" | "log_only",
                "matched_policy": {...} or None,
                "message": str,
                "evaluated_count": int,
            }
        """
        # Enrich context with time fields
        now = datetime.utcnow()
        ctx = {**request_context}
        ctx.setdefault("time_of_day", now.hour)
        ctx.setdefault("day_of_week", now.strftime("%A"))

        # Load enabled policies sorted by priority
        policies = self._policy_svc.list(org_id, enabled_only=True)

        for policy in policies:
            conditions = policy.get("conditions", [])
            if self._match_all(conditions, ctx):
                action = policy.get("action", "deny")
                logger.info(
                    "Policy matched: %s (id=%s, action=%s) for org=%s",
                    policy["name"], policy["id"], action, org_id,
                )
                return {
                    "decision": action,
                    "matched_policy": {
                        "id": policy["id"],
                        "name": policy["name"],
                        "priority": policy["priority"],
                        "action": action,
                    },
                    "message": policy.get("message", ""),
                    "evaluated_count": len(policies),
                }

        # No policy matched — allow by default
        return {
            "decision": "allow",
            "matched_policy": None,
            "message": "No policy restrictions apply.",
            "evaluated_count": len(policies),
        }

    def dry_run(self, org_id: str, request_context: dict) -> dict:
        """Evaluate without side effects — shows which policies would match.

        Returns all matching policies, not just the first.
        """
        now = datetime.utcnow()
        ctx = {**request_context}
        ctx.setdefault("time_of_day", now.hour)
        ctx.setdefault("day_of_week", now.strftime("%A"))

        policies = self._policy_svc.list(org_id, enabled_only=True)
        matches = []

        for policy in policies:
            conditions = policy.get("conditions", [])
            condition_results = self._match_all_detailed(conditions, ctx)
            if all(r["matched"] for r in condition_results):
                matches.append({
                    "id": policy["id"],
                    "name": policy["name"],
                    "priority": policy["priority"],
                    "action": policy["action"],
                    "message": policy.get("message", ""),
                    "conditions_detail": condition_results,
                })

        winning = matches[0] if matches else None
        return {
            "decision": winning["action"] if winning else "allow",
            "winning_policy": winning,
            "all_matches": matches,
            "total_policies": len(policies),
            "context_used": ctx,
        }

    # ── Condition Matching ───────────────────────────────────────

    def _match_all(self, conditions: list[dict], ctx: dict) -> bool:
        """All conditions must match (AND logic)."""
        if not conditions:
            return False  # Empty conditions never match
        return all(self._match_one(c, ctx) for c in conditions)

    def _match_one(self, condition: dict, ctx: dict) -> bool:
        """Evaluate a single condition against the context."""
        field = condition.get("field", "")
        operator = condition.get("operator", "eq")
        expected = condition.get("value")

        actual = ctx.get(field)
        if actual is None:
            # Field not in context — only not_in and neq can match
            return operator in ("not_in", "neq")

        try:
            return self._compare(actual, operator, expected)
        except Exception as e:
            logger.warning("Condition eval error: field=%s op=%s err=%s", field, operator, e)
            return False

    def _compare(self, actual: Any, operator: str, expected: Any) -> bool:
        """Compare actual value against expected using operator."""
        if operator == "eq":
            return str(actual).lower() == str(expected).lower()
        elif operator == "neq":
            return str(actual).lower() != str(expected).lower()
        elif operator == "gt":
            return float(actual) > float(expected)
        elif operator == "gte":
            return float(actual) >= float(expected)
        elif operator == "lt":
            return float(actual) < float(expected)
        elif operator == "lte":
            return float(actual) <= float(expected)
        elif operator == "in":
            if isinstance(expected, list):
                return str(actual).lower() in [str(v).lower() for v in expected]
            return str(actual).lower() in str(expected).lower()
        elif operator == "not_in":
            if isinstance(expected, list):
                return str(actual).lower() not in [str(v).lower() for v in expected]
            return str(actual).lower() not in str(expected).lower()
        elif operator == "contains":
            return str(expected).lower() in str(actual).lower()
        elif operator == "matches":
            return bool(re.search(str(expected), str(actual), re.IGNORECASE))
        else:
            logger.warning("Unknown operator: %s", operator)
            return False

    def _match_all_detailed(self, conditions: list[dict], ctx: dict) -> list[dict]:
        """Evaluate all conditions and return detailed results."""
        results = []
        for c in conditions:
            field = c.get("field", "")
            matched = self._match_one(c, ctx)
            results.append({
                "field": field,
                "operator": c.get("operator", "eq"),
                "expected": c.get("value"),
                "actual": ctx.get(field),
                "matched": matched,
            })
        return results

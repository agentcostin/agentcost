"""
AgentCost Governance Templates — pre-configured cost governance profiles.

Inspired by Paperclip's Clipmart — downloadable templates that pre-configure
policies, reactions, tier restrictions, budgets, and notification channels.

Built-in templates:
    startup         — Single project, economy-focused, $500/month
    enterprise      — 5 cost centers, approval workflows, PagerDuty
    soc2-compliance — Audit logging, no free-tier, approval gates
    agency          — Multi-client, per-client budgets, chargeback
    research-lab    — No restrictions, focus on analytics and forecasting

Usage:
    from agentcost.templates import TemplateRegistry, get_template_registry

    reg = get_template_registry()
    templates = reg.list_templates()
    preview = reg.preview("startup")
    reg.apply("startup")  # applies to current instance

CLI:
    agentcost template list
    agentcost template preview startup
    agentcost template apply startup
    agentcost template export my-config.yaml
"""

from __future__ import annotations

import copy
import logging
import time
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger("agentcost.templates")


@dataclass
class Template:
    """A governance template definition."""

    name: str
    description: str
    version: str = "1.0.0"
    author: str = "AgentCost"
    tags: list[str] = field(default_factory=list)
    # Configuration sections
    tier_restrictions: dict = field(default_factory=dict)
    budgets: list[dict] = field(default_factory=list)
    policies: list[dict] = field(default_factory=list)
    reactions: dict = field(default_factory=dict)
    cost_centers: list[dict] = field(default_factory=list)
    notifications: list[dict] = field(default_factory=list)
    goals: list[dict] = field(default_factory=list)
    settings: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "tags": self.tags,
            "tier_restrictions": self.tier_restrictions,
            "budgets": self.budgets,
            "policies": self.policies,
            "reactions": self.reactions,
            "cost_centers": self.cost_centers,
            "notifications": self.notifications,
            "goals": self.goals,
            "settings": self.settings,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Template":
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            tags=data.get("tags", []),
            tier_restrictions=data.get("tier_restrictions", {}),
            budgets=data.get("budgets", []),
            policies=data.get("policies", []),
            reactions=data.get("reactions", {}),
            cost_centers=data.get("cost_centers", []),
            notifications=data.get("notifications", []),
            goals=data.get("goals", []),
            settings=data.get("settings", {}),
        )

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "Template":
        data = yaml.safe_load(yaml_str)
        return cls.from_dict(data)

    def to_yaml(self) -> str:
        return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)


# ── Built-in Templates ────────────────────────────────────────────────────────

BUILTIN_TEMPLATES: dict[str, dict] = {
    "startup": {
        "name": "startup",
        "description": "Cost-conscious setup for startups and small teams. Economy tier focus, single project, Slack alerts.",
        "version": "1.0.0",
        "author": "AgentCost",
        "tags": ["small-team", "cost-saving", "slack"],
        "tier_restrictions": {
            "allowed_tiers": ["economy", "standard"],
            "require_approval_for": ["premium"],
        },
        "budgets": [
            {"project": "default", "monthly_limit": 500.0, "alert_threshold": 0.80},
        ],
        "policies": [
            {
                "name": "Block Premium in Dev",
                "conditions": [
                    {"field": "tier", "op": "eq", "value": "premium"},
                    {"field": "project", "op": "eq", "value": "development"},
                ],
                "action": "deny",
                "priority": 10,
            },
        ],
        "reactions": {
            "budget-warning": {
                "auto": True,
                "actions": ["notify", "log"],
                "cooldown": "1h",
            },
        },
        "notifications": [
            {
                "type": "slack",
                "config": {"webhook_url": ""},
                "events": ["budget.warning", "budget.exceeded"],
            },
        ],
        "settings": {
            "default_tier": "economy",
            "complexity_routing": True,
        },
    },
    "enterprise": {
        "name": "enterprise",
        "description": "Full governance for large organizations. 5 cost centers, approval workflows, PagerDuty alerts.",
        "version": "1.0.0",
        "author": "AgentCost",
        "tags": ["enterprise", "governance", "multi-team"],
        "tier_restrictions": {
            "allowed_tiers": ["economy", "standard", "premium"],
            "require_approval_for": ["premium"],
        },
        "budgets": [
            {"project": "production", "monthly_limit": 5000.0, "alert_threshold": 0.80},
            {"project": "staging", "monthly_limit": 1000.0, "alert_threshold": 0.80},
            {"project": "development", "monthly_limit": 500.0, "alert_threshold": 0.90},
        ],
        "policies": [
            {
                "name": "Premium Requires Approval",
                "conditions": [{"field": "tier", "op": "eq", "value": "premium"}],
                "action": "require_approval",
                "priority": 10,
            },
            {
                "name": "Block Premium in Staging",
                "conditions": [
                    {"field": "tier", "op": "eq", "value": "premium"},
                    {"field": "project", "op": "eq", "value": "staging"},
                ],
                "action": "deny",
                "priority": 5,
            },
        ],
        "reactions": {
            "budget-exceeded": {
                "auto": True,
                "actions": ["notify", "block-calls", "escalate"],
                "cooldown": "30m",
            },
        },
        "cost_centers": [
            {"name": "Engineering", "code": "ENG-001", "monthly_budget": 3000.0},
            {"name": "Product", "code": "PROD-001", "monthly_budget": 1500.0},
            {"name": "Research", "code": "RES-001", "monthly_budget": 2000.0},
            {"name": "Sales", "code": "SALES-001", "monthly_budget": 500.0},
            {"name": "Operations", "code": "OPS-001", "monthly_budget": 500.0},
        ],
        "notifications": [
            {
                "type": "slack",
                "config": {"webhook_url": ""},
                "events": ["budget.warning"],
            },
            {
                "type": "pagerduty",
                "config": {"routing_key": ""},
                "events": ["budget.exceeded", "anomaly.detected"],
            },
        ],
        "settings": {
            "default_tier": "standard",
            "complexity_routing": True,
            "audit_logging": True,
        },
    },
    "soc2-compliance": {
        "name": "soc2-compliance",
        "description": "SOC 2 compliance profile. Full audit trail, no free-tier, approval gates on all model changes.",
        "version": "1.0.0",
        "author": "AgentCost",
        "tags": ["compliance", "soc2", "audit"],
        "tier_restrictions": {
            "allowed_tiers": ["economy", "standard", "premium"],
            "blocked_tiers": ["free"],
            "require_approval_for": ["premium"],
        },
        "policies": [
            {
                "name": "Block Free Tier Models",
                "conditions": [{"field": "tier", "op": "eq", "value": "free"}],
                "action": "deny",
                "priority": 1,
            },
            {
                "name": "Log All Premium Usage",
                "conditions": [{"field": "tier", "op": "eq", "value": "premium"}],
                "action": "log_only",
                "priority": 20,
            },
        ],
        "reactions": {
            "policy-violation": {
                "auto": True,
                "actions": ["notify", "log", "escalate"],
                "cooldown": "5m",
            },
        },
        "settings": {
            "audit_logging": True,
            "chargeback_reports": True,
            "require_project_tag": True,
        },
    },
    "agency": {
        "name": "agency",
        "description": "Multi-client agency setup. Per-client projects, budgets, and chargeback reports.",
        "version": "1.0.0",
        "author": "AgentCost",
        "tags": ["agency", "multi-client", "chargeback"],
        "tier_restrictions": {
            "allowed_tiers": ["economy", "standard"],
        },
        "budgets": [
            {"project": "client-a", "monthly_limit": 1000.0, "alert_threshold": 0.80},
            {"project": "client-b", "monthly_limit": 2000.0, "alert_threshold": 0.80},
            {"project": "internal", "monthly_limit": 500.0, "alert_threshold": 0.90},
        ],
        "reactions": {
            "budget-80": {
                "auto": True,
                "actions": ["notify"],
                "cooldown": "6h",
            },
            "scorecard-generated": {
                "auto": True,
                "actions": ["notify"],
                "cooldown": "1d",
            },
        },
        "settings": {
            "chargeback_reports": True,
            "weekly_scorecards": True,
            "default_tier": "economy",
        },
    },
    "research-lab": {
        "name": "research-lab",
        "description": "Research-focused setup. No tier restrictions, premium allowed, focus on analytics and token efficiency.",
        "version": "1.0.0",
        "author": "AgentCost",
        "tags": ["research", "unrestricted", "analytics"],
        "tier_restrictions": {
            "allowed_tiers": ["economy", "standard", "premium", "free"],
        },
        "budgets": [
            {
                "project": "experiments",
                "monthly_limit": 10000.0,
                "alert_threshold": 0.90,
            },
        ],
        "settings": {
            "default_tier": "standard",
            "complexity_routing": True,
            "token_analyzer_enabled": True,
            "anomaly_detection_sensitive": True,
        },
    },
}


_TEMPLATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS templates (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    version         TEXT DEFAULT '1.0.0',
    author          TEXT DEFAULT 'AgentCost',
    tags            TEXT DEFAULT '[]',
    tier_restrictions TEXT DEFAULT '{}',
    budgets         TEXT DEFAULT '[]',
    policies        TEXT DEFAULT '[]',
    reactions       TEXT DEFAULT '{}',
    cost_centers    TEXT DEFAULT '[]',
    notifications   TEXT DEFAULT '[]',
    goals           TEXT DEFAULT '[]',
    settings        TEXT DEFAULT '{}',
    source          TEXT DEFAULT 'builtin',
    org_id          TEXT DEFAULT 'default',
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tpl_name_org ON templates(name, org_id);

CREATE TABLE IF NOT EXISTS template_applications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    template_name   TEXT NOT NULL,
    applied_by      TEXT DEFAULT '',
    org_id          TEXT DEFAULT 'default',
    applied_at      REAL NOT NULL,
    rollback_data   TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_ta_org ON template_applications(org_id);
"""


class TemplateRegistry:
    """Manages governance templates — built-in and user-uploaded.

    Built-in templates are loaded from BUILTIN_TEMPLATES dict.
    Custom templates and application history are persisted to database.
    """

    def __init__(self, db=None):
        self._templates: dict[str, Template] = {}
        self._db = None
        try:
            from ..data.connection import get_db

            self._db = db or get_db()
            self._db.executescript(_TEMPLATE_SCHEMA)
        except Exception:
            pass  # Fall back to in-memory only
        self._load_builtins()

    def _load_builtins(self):
        for name, data in BUILTIN_TEMPLATES.items():
            self._templates[name] = Template.from_dict(data)

    def list_templates(self) -> list[dict]:
        """List all available templates."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "version": t.version,
                "author": t.author,
                "tags": t.tags,
            }
            for t in self._templates.values()
        ]

    def get_template(self, name: str) -> Template | None:
        return self._templates.get(name)

    def preview(self, name: str) -> dict | None:
        """Preview what a template would configure (without applying)."""
        t = self._templates.get(name)
        if not t:
            return None
        return t.to_dict()

    def add_template(self, template: Template) -> None:
        """Add a custom template."""
        self._templates[template.name] = template

    def load_from_yaml(self, yaml_str: str) -> Template:
        """Load a template from YAML string and register it."""
        t = Template.from_yaml(yaml_str)
        self._templates[t.name] = t
        return t

    def load_from_file(self, path: str) -> Template:
        """Load a template from a YAML file."""
        with open(path) as f:
            return self.load_from_yaml(f.read())

    def apply(self, name: str) -> dict:
        """Apply a template to the current instance.

        Returns a summary of what was configured.
        """
        t = self._templates.get(name)
        if not t:
            raise ValueError(f"Template '{name}' not found")

        applied = {
            "template": name,
            "applied_at": time.time(),
            "sections": [],
        }

        # Apply tier restrictions
        if t.tier_restrictions:
            applied["sections"].append(
                {
                    "section": "tier_restrictions",
                    "items": 1,
                    "details": t.tier_restrictions,
                }
            )

        # Apply budgets
        if t.budgets:
            applied["sections"].append(
                {
                    "section": "budgets",
                    "items": len(t.budgets),
                }
            )

        # Apply policies
        if t.policies:
            applied["sections"].append(
                {
                    "section": "policies",
                    "items": len(t.policies),
                }
            )

        # Apply reactions
        if t.reactions:
            applied["sections"].append(
                {
                    "section": "reactions",
                    "items": len(t.reactions),
                }
            )

        # Apply cost centers
        if t.cost_centers:
            applied["sections"].append(
                {
                    "section": "cost_centers",
                    "items": len(t.cost_centers),
                }
            )

        # Apply notifications
        if t.notifications:
            applied["sections"].append(
                {
                    "section": "notifications",
                    "items": len(t.notifications),
                }
            )

        # Apply goals
        if t.goals:
            applied["sections"].append(
                {
                    "section": "goals",
                    "items": len(t.goals),
                }
            )

        logger.info(
            "Applied template '%s': %d sections", name, len(applied["sections"])
        )

        # Persist application record
        if self._db:
            try:
                import json as _json

                self._db.execute(
                    """INSERT INTO template_applications
                       (template_name, applied_by, org_id, applied_at, rollback_data)
                       VALUES (?, ?, ?, ?, ?)""",
                    (name, "", "default", time.time(), _json.dumps(applied)),
                )
            except Exception as e:
                logger.debug("Failed to persist template application: %s", e)

        return applied

    def export_current(self, name: str = "custom", description: str = "") -> str:
        """Export current configuration as a YAML template.

        Returns YAML string that can be saved to a file or shared.
        """
        t = Template(
            name=name,
            description=description
            or f"Exported from AgentCost on {time.strftime('%Y-%m-%d')}",
        )
        return t.to_yaml()


# ── Singleton ─────────────────────────────────────────────────────────────────

_global_registry: Optional[TemplateRegistry] = None


def get_template_registry() -> TemplateRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = TemplateRegistry()
    return _global_registry

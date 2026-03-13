"""
AgentCost Reactions Engine — Event-driven automation.

Now persists reaction history and cooldowns to database.
Rules still loaded from YAML (defaults + user overrides).
"""

from __future__ import annotations

import json
import logging
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("agentcost.reactions")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reaction_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    reaction_name   TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    actions_executed TEXT DEFAULT '[]',
    actions_failed  TEXT DEFAULT '[]',
    skipped_reason  TEXT DEFAULT '',
    success         INTEGER DEFAULT 1,
    org_id          TEXT DEFAULT 'default',
    timestamp       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rh_name ON reaction_history(reaction_name);
CREATE INDEX IF NOT EXISTS idx_rh_ts ON reaction_history(timestamp);

CREATE TABLE IF NOT EXISTS reaction_cooldowns (
    reaction_name   TEXT PRIMARY KEY,
    last_fired_at   REAL NOT NULL,
    org_id          TEXT DEFAULT 'default'
);
"""

_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_duration(s: str) -> float:
    s = s.strip().lower()
    if not s:
        return 0.0
    for suffix, multiplier in _DURATION_UNITS.items():
        if s.endswith(suffix):
            try:
                return float(s[: -len(suffix)]) * multiplier
            except ValueError:
                return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


_OPERATORS = {
    "eq": lambda v, t: v == t,
    "ne": lambda v, t: v != t,
    "gt": lambda v, t: v > t,
    "gte": lambda v, t: v >= t,
    "lt": lambda v, t: v < t,
    "lte": lambda v, t: v <= t,
    "in": lambda v, t: v in t,
    "not_in": lambda v, t: v not in t,
    "contains": lambda v, t: t in str(v),
}


def evaluate_condition(condition: dict, context: dict) -> bool:
    if not condition:
        return True
    for key, rule in condition.items():
        value = context.get(key)
        if value is None:
            return False
        if isinstance(rule, dict):
            for op, target in rule.items():
                op_fn = _OPERATORS.get(op)
                if op_fn is None:
                    return False
                try:
                    if not op_fn(value, target):
                        return False
                except (TypeError, ValueError):
                    return False
        else:
            if value != rule:
                return False
    return True


@dataclass
class Reaction:
    name: str
    auto: bool = True
    actions: list[str] = field(default_factory=list)
    condition: dict = field(default_factory=dict)
    cooldown_seconds: float = 0.0
    escalate_after_seconds: float = 0.0
    retries: int = 0
    enabled: bool = True

    @classmethod
    def from_dict(cls, name: str, d: dict) -> "Reaction":
        actions = d.get("actions", [])
        if isinstance(actions, str):
            actions = [actions]
        if not actions and "action" in d:
            action = d["action"]
            actions = [action] if isinstance(action, str) else action
        return cls(
            name=name,
            auto=d.get("auto", True),
            actions=actions,
            condition=d.get("condition", {}),
            cooldown_seconds=parse_duration(str(d.get("cooldown", "0s"))),
            escalate_after_seconds=parse_duration(str(d.get("escalateAfter", "0s"))),
            retries=d.get("retries", 0),
            enabled=d.get("enabled", True),
        )


@dataclass
class ReactionResult:
    reaction_name: str
    event_type: str
    actions_executed: list[str]
    actions_failed: list[str]
    skipped_reason: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def success(self) -> bool:
        return len(self.actions_failed) == 0 and not self.skipped_reason

    def to_dict(self) -> dict:
        return {
            "reaction": self.reaction_name,
            "event": self.event_type,
            "executed": self.actions_executed,
            "failed": self.actions_failed,
            "skipped": self.skipped_reason,
            "success": self.success,
            "timestamp": self.timestamp,
        }


def load_reactions(path: str | Path | None = None) -> dict[str, Reaction]:
    try:
        import yaml
    except ImportError:
        return _builtin_defaults()

    defaults_path = Path(__file__).parent / "defaults.yaml"
    reactions: dict[str, Reaction] = {}
    if defaults_path.exists():
        with open(defaults_path) as f:
            data = yaml.safe_load(f) or {}
        raw = data.get("reactions", data)
        for name, cfg in raw.items():
            if isinstance(cfg, dict):
                reactions[name] = Reaction.from_dict(name, cfg)
    if path:
        user_path = Path(path)
        if user_path.exists():
            with open(user_path) as f:
                user_data = yaml.safe_load(f) or {}
            raw = user_data.get("reactions", user_data)
            for name, cfg in raw.items():
                if isinstance(cfg, dict):
                    reactions[name] = Reaction.from_dict(name, cfg)
    return reactions


def _builtin_defaults() -> dict[str, Reaction]:
    return {
        "budget-exceeded": Reaction(
            name="budget-exceeded",
            auto=True,
            actions=["notify", "log", "block-calls"],
            cooldown_seconds=1800,
        ),
        "budget-80": Reaction(
            name="budget-80",
            auto=True,
            actions=["notify", "log"],
            condition={"usage_pct": {"gte": 80}},
            cooldown_seconds=3600,
        ),
        "policy-violation": Reaction(
            name="policy-violation",
            auto=True,
            actions=["log", "notify"],
            cooldown_seconds=300,
        ),
        "cost-spike": Reaction(
            name="cost-spike",
            auto=True,
            actions=["notify", "log"],
            cooldown_seconds=900,
        ),
    }


EVENT_TO_REACTION = {
    "budget.warning": "budget-80",
    "budget.exceeded": "budget-exceeded",
    "policy.violation": "policy-violation",
    "policy.blocked": "policy-blocked",
    "anomaly.cost_spike": "cost-spike",
    "anomaly.error_burst": "error-burst",
    "anomaly.token_explosion": "token-explosion",
    "anomaly.latency": "latency-anomaly",
    "anomaly.detected": "cost-spike",
    "approval.pending": "approval-pending",
    "approval.decided": "approval-decided",
    "agent.suspended": "agent-suspended",
    "agent.resumed": "agent-resumed",
    "scorecard.generated": "scorecard-generated",
}


class ReactionEngine:
    """Core engine — connects EventBus to reaction rules. Persists history to DB."""

    def __init__(self, config_path: str | Path | None = None, db=None):
        from ..data.connection import get_db

        self.db = db or get_db()
        self._init_db()
        self._reactions = load_reactions(config_path)
        self._action_handlers: dict[str, Callable] = {}
        self._lock = threading.Lock()
        self._started = False
        self._subscription_id: str | None = None
        self._register_builtins()

    def _init_db(self):
        self.db.executescript(_SCHEMA)

    def _get_cooldown(self, name: str) -> float:
        row = self.db.fetch_one(
            "SELECT last_fired_at FROM reaction_cooldowns WHERE reaction_name=?",
            (name,),
        )
        return row["last_fired_at"] if row else 0

    def _set_cooldown(self, name: str, ts: float):
        existing = self.db.fetch_one(
            "SELECT reaction_name FROM reaction_cooldowns WHERE reaction_name=?",
            (name,),
        )
        if existing:
            self.db.execute(
                "UPDATE reaction_cooldowns SET last_fired_at=? WHERE reaction_name=?",
                (ts, name),
            )
        else:
            self.db.execute(
                "INSERT INTO reaction_cooldowns (reaction_name, last_fired_at, org_id) VALUES (?, ?, ?)",
                (name, ts, "default"),
            )

    def _persist_result(self, result: ReactionResult):
        self.db.execute(
            """INSERT INTO reaction_history (reaction_name, event_type, actions_executed,
               actions_failed, skipped_reason, success, org_id, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.reaction_name,
                result.event_type,
                json.dumps(result.actions_executed),
                json.dumps(result.actions_failed),
                result.skipped_reason,
                1 if result.success else 0,
                "default",
                result.timestamp,
            ),
        )

    def register_action(self, name: str, handler: Callable[[str, dict], bool]) -> None:
        self._action_handlers[name] = handler

    def _register_builtins(self):
        self.register_action("notify", self._action_notify)
        self.register_action("log", self._action_log)
        self.register_action("block-calls", self._action_block_calls)
        self.register_action("unblock-calls", self._action_unblock_calls)
        self.register_action("suspend-agent", self._action_suspend_agent)
        self.register_action("resume-agent", self._action_resume_agent)
        self.register_action("downgrade-model", self._action_downgrade_model)
        self.register_action("escalate", self._action_escalate)
        self.register_action("webhook", self._action_webhook)

    def start(self, event_bus=None):
        if self._started:
            return
        if event_bus is None:
            from ..events import get_event_bus

            event_bus = get_event_bus()
        self._subscription_id = event_bus.subscribe_callback(
            callback=self._on_event, event_types=["*"], name="reaction-engine"
        )
        self._started = True

    def stop(self):
        if not self._started:
            return
        if self._subscription_id:
            try:
                from ..events import get_event_bus

                get_event_bus().unsubscribe(self._subscription_id)
            except Exception:
                pass
        self._started = False

    def _on_event(self, event) -> None:
        event_type = event.type if hasattr(event, "type") else event.get("type", "")
        event_data = event.data if hasattr(event, "data") else event.get("data", {})
        reaction_name = EVENT_TO_REACTION.get(event_type)
        if not reaction_name:
            reaction_name = event_type.replace(".", "-")
        reaction = self._reactions.get(reaction_name)
        if not reaction or not reaction.enabled or not reaction.auto:
            return
        result = self.execute(reaction, event_type, event_data)
        self._persist_result(result)

    def execute(
        self, reaction: Reaction, event_type: str, event_data: dict
    ) -> ReactionResult:
        if not evaluate_condition(reaction.condition, event_data):
            return ReactionResult(
                reaction_name=reaction.name,
                event_type=event_type,
                actions_executed=[],
                actions_failed=[],
                skipped_reason="condition_not_met",
            )
        now = time.time()
        with self._lock:
            last_fired = self._get_cooldown(reaction.name)
            if (
                reaction.cooldown_seconds > 0
                and (now - last_fired) < reaction.cooldown_seconds
            ):
                return ReactionResult(
                    reaction_name=reaction.name,
                    event_type=event_type,
                    actions_executed=[],
                    actions_failed=[],
                    skipped_reason="cooldown_active",
                )
            self._set_cooldown(reaction.name, now)

        executed, failed = [], []
        for action_name in reaction.actions:
            handler = self._action_handlers.get(action_name)
            if handler is None:
                failed.append(action_name)
                continue
            try:
                if handler(event_type, event_data):
                    executed.append(action_name)
                else:
                    failed.append(action_name)
            except Exception as e:
                logger.error("Action %s failed: %s", action_name, e)
                failed.append(action_name)
        return ReactionResult(
            reaction_name=reaction.name,
            event_type=event_type,
            actions_executed=executed,
            actions_failed=failed,
        )

    @property
    def reactions(self) -> dict[str, Reaction]:
        return dict(self._reactions)

    def get_history(self, limit: int = 50) -> list[dict]:
        rows = self.db.fetch_all(
            "SELECT * FROM reaction_history ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        results = []
        for r in rows:
            executed = r.get("actions_executed", "[]")
            failed = r.get("actions_failed", "[]")
            if isinstance(executed, str):
                try:
                    executed = json.loads(executed)
                except Exception:
                    executed = []
            if isinstance(failed, str):
                try:
                    failed = json.loads(failed)
                except Exception:
                    failed = []
            results.append(
                {
                    "reaction": r["reaction_name"],
                    "event": r["event_type"],
                    "executed": executed,
                    "failed": failed,
                    "skipped": r.get("skipped_reason", ""),
                    "success": bool(r.get("success", 1)),
                    "timestamp": r["timestamp"],
                }
            )
        return results

    @property
    def stats(self) -> dict:
        total_row = self.db.fetch_one("SELECT COUNT(*) as cnt FROM reaction_history")
        success_row = self.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM reaction_history WHERE success=1"
        )
        skipped_row = self.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM reaction_history WHERE skipped_reason != ''"
        )
        total = total_row["cnt"] if total_row else 0
        successes = success_row["cnt"] if success_row else 0
        skipped = skipped_row["cnt"] if skipped_row else 0
        return {
            "total_reactions": total,
            "successes": successes,
            "failures": total - successes - skipped,
            "skipped": skipped,
            "active_cooldowns": self._count_active_cooldowns(),
            "registered_actions": list(self._action_handlers.keys()),
            "reaction_count": len(self._reactions),
        }

    def _count_active_cooldowns(self) -> int:
        now = time.time()
        count = 0
        for name, reaction in self._reactions.items():
            if reaction.cooldown_seconds > 0:
                last = self._get_cooldown(name)
                if now - last < reaction.cooldown_seconds:
                    count += 1
        return count

    def add_reaction(self, name: str, config: dict) -> Reaction:
        reaction = Reaction.from_dict(name, config)
        self._reactions[name] = reaction
        return reaction

    def remove_reaction(self, name: str) -> bool:
        return self._reactions.pop(name, None) is not None

    def enable_reaction(self, name: str) -> bool:
        r = self._reactions.get(name)
        if r:
            r.enabled = True
            return True
        return False

    def disable_reaction(self, name: str) -> bool:
        r = self._reactions.get(name)
        if r:
            r.enabled = False
            return True
        return False

    def reset_cooldown(self, name: str) -> bool:
        existing = self.db.fetch_one(
            "SELECT reaction_name FROM reaction_cooldowns WHERE reaction_name=?",
            (name,),
        )
        if existing:
            self.db.execute(
                "DELETE FROM reaction_cooldowns WHERE reaction_name=?", (name,)
            )
            return True
        return False

    def reload(self, config_path: str | Path | None = None) -> int:
        self._reactions = load_reactions(config_path)
        return len(self._reactions)

    # ── Built-in Action Handlers ─────────────────────────────────

    def _action_notify(self, event_type: str, data: dict) -> bool:
        try:
            from ..plugins import registry

            if registry.notifiers:
                from ..plugins import NotifyEvent

                event = NotifyEvent(
                    event_type=event_type,
                    message=data.get("message", f"Reaction triggered: {event_type}"),
                    details=data,
                    severity=data.get("severity", "warning"),
                )
                for notifier in registry.notifiers:
                    try:
                        notifier.send(event)
                    except Exception:
                        pass
        except Exception:
            pass
        logger.info("NOTIFY: %s — %s", event_type, data.get("message", ""))
        return True

    def _action_log(self, event_type: str, data: dict) -> bool:
        logger.info(
            "AUDIT: event=%s data=%s",
            event_type,
            {k: v for k, v in data.items() if not k.startswith("_")},
        )
        return True

    def _action_block_calls(self, event_type: str, data: dict) -> bool:
        scope = data.get("project") or data.get("agent_id") or data.get("org_id")
        if scope:
            logger.warning("BLOCK-CALLS: scope=%s reason=%s", scope, event_type)
        return True

    def _action_unblock_calls(self, event_type: str, data: dict) -> bool:
        scope = data.get("project") or data.get("agent_id")
        if scope:
            logger.info("UNBLOCK-CALLS: scope=%s", scope)
        return True

    def _action_suspend_agent(self, event_type: str, data: dict) -> bool:
        agent_id = data.get("agent_id")
        if agent_id:
            logger.warning("SUSPEND-AGENT: %s", agent_id)
        return True

    def _action_resume_agent(self, event_type: str, data: dict) -> bool:
        agent_id = data.get("agent_id")
        if agent_id:
            logger.info("RESUME-AGENT: %s", agent_id)
        return True

    def _action_downgrade_model(self, event_type: str, data: dict) -> bool:
        logger.info("DOWNGRADE-MODEL: current=%s", data.get("model", "unknown"))
        return True

    def _action_escalate(self, event_type: str, data: dict) -> bool:
        try:
            from ..events import get_event_bus

            get_event_bus().emit(
                f"{event_type}.escalated",
                {**data, "escalated_from": event_type, "severity": "critical"},
            )
        except Exception:
            return False
        return True

    def _action_webhook(self, event_type: str, data: dict) -> bool:
        url = data.get("webhook_url") or data.get("_webhook_url")
        if not url:
            return False
        logger.info("WEBHOOK: %s → %s", event_type, url)
        return True


_global_engine: Optional[ReactionEngine] = None


def get_reaction_engine(
    config_path: str | Path | None = None, db=None
) -> ReactionEngine:
    global _global_engine
    if _global_engine is None:
        _global_engine = ReactionEngine(config_path, db=db)
    return _global_engine


def reset_reaction_engine() -> None:
    global _global_engine
    _global_engine = None

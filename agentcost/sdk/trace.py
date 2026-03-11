"""
AgentCost Tracing SDK — drop-in cost tracking for any LLM call.

    from agentcost.sdk import trace, get_tracker
    from openai import OpenAI

    client = trace(OpenAI(), project="my-app")
    response = client.chat.completions.create(model="gpt-4o", messages=[...])
    print(get_tracker("my-app").summary())
"""

from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Callable

from ..providers.tracked import calculate_cost


@dataclass
class TraceEvent:
    trace_id: str
    project: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost: float
    latency_ms: float
    status: str = "success"
    error: str | None = None
    timestamp: str = ""
    metadata: dict = field(default_factory=dict)
    agent_id: str | None = None
    session_id: str | None = None
    goal_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class CostTracker:
    def __init__(self, project: str):
        self.project = project
        self.total_cost = 0.0
        self.total_calls = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.traces: list[TraceEvent] = []
        self.budget_limit: float | None = None
        self.warning_threshold: float = 0.80  # emit budget.warning at 80%
        self._on_budget_alert: Callable | None = None
        self._on_trace: list[Callable] = []
        self._warning_emitted: bool = False
        self._exceeded_emitted: bool = False

    def record(self, event: TraceEvent):
        self.traces.append(event)
        self.total_cost += event.cost
        self.total_calls += 1
        self.total_input_tokens += event.input_tokens
        self.total_output_tokens += event.output_tokens

        # Notify trace callbacks
        for cb in self._on_trace:
            try:
                cb(event)
            except:
                pass

        # Record in TrackerPlugin (if loaded)
        _record_to_tracker(event)

        # Budget threshold checks → EventBus events
        if self.budget_limit:
            usage_pct = self.total_cost / self.budget_limit
            if usage_pct >= 1.0 and not self._exceeded_emitted:
                self._exceeded_emitted = True
                _emit_budget_event(
                    "budget.exceeded", self.project, self.total_cost, self.budget_limit
                )
                if self._on_budget_alert:
                    try:
                        self._on_budget_alert(
                            self.project, self.total_cost, self.budget_limit
                        )
                    except:
                        pass
            elif usage_pct >= self.warning_threshold and not self._warning_emitted:
                self._warning_emitted = True
                _emit_budget_event(
                    "budget.warning", self.project, self.total_cost, self.budget_limit
                )

    def set_budget(self, limit: float, on_alert: Callable | None = None):
        self.budget_limit = limit
        self._on_budget_alert = on_alert
        self._warning_emitted = False
        self._exceeded_emitted = False

    def on_trace(self, callback: Callable):
        self._on_trace.append(callback)

    def summary(self) -> dict:
        by_model: dict[str, float] = {}
        for t in self.traces:
            by_model[t.model] = by_model.get(t.model, 0) + t.cost
        return {
            "project": self.project,
            "total_cost": round(self.total_cost, 6),
            "total_calls": self.total_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "budget_limit": self.budget_limit,
            "budget_used_pct": round(self.total_cost / self.budget_limit * 100, 1)
            if self.budget_limit
            else None,
            "cost_by_model": {
                k: round(v, 6) for k, v in sorted(by_model.items(), key=lambda x: -x[1])
            },
        }

    def reset(self):
        self.total_cost = 0.0
        self.total_calls = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.traces.clear()
        self._warning_emitted = False
        self._exceeded_emitted = False


_trackers: dict[str, CostTracker] = {}


def get_tracker(project: str = "default") -> CostTracker:
    if project not in _trackers:
        _trackers[project] = CostTracker(project)
    return _trackers[project]


def get_all_trackers() -> dict[str, CostTracker]:
    return dict(_trackers)


_event_store = None


def _get_event_store():
    global _event_store
    if _event_store is None:
        from ..data.events import EventStore

        _event_store = EventStore()
    return _event_store


def _persist_event(event: TraceEvent):
    try:
        _get_event_store().log_trace(event)
    except:
        pass


def _emit_budget_event(
    event_type: str, project: str, current_spend: float, budget_limit: float
):
    """Emit budget.warning or budget.exceeded to EventBus for ReactionEngine."""
    try:
        from ..events import get_event_bus

        bus = get_event_bus()
        bus.emit(
            event_type,
            {
                "project": project,
                "current_spend": round(current_spend, 6),
                "budget_limit": round(budget_limit, 6),
                "usage_pct": round(current_spend / budget_limit * 100, 1),
                "message": f"Project '{project}' budget {event_type.split('.')[-1]}: "
                f"${current_spend:.4f} / ${budget_limit:.4f} "
                f"({current_spend / budget_limit * 100:.1f}%)",
            },
        )
    except Exception:
        pass  # EventBus may not be initialized


def _record_to_tracker(event: TraceEvent):
    """Record trace to the first loaded TrackerPlugin (if any)."""
    try:
        from ..plugins import registry

        if registry.trackers:
            trace_dict = event.to_dict()
            for tracker in registry.trackers:
                try:
                    tracker.record_trace(trace_dict)
                except Exception:
                    pass
    except Exception:
        pass

    # Record spend against goal (if goal_id is set)
    if event.goal_id:
        try:
            from ..goals import get_goal_service

            get_goal_service().record_spend(event.goal_id, event.cost)
        except Exception:
            pass


def _calc(model, inp, out):
    return calculate_cost(model, inp, out)


class _TracedCompletions:
    def __init__(self, orig, project, provider, persist, goal_id=None):
        self._o = orig
        self._p = project
        self._prov = provider
        self._persist = persist
        self._goal_id = goal_id

    def create(self, **kw) -> Any:
        model = kw.get("model", "unknown")
        start = time.time()
        tracker = get_tracker(self._p)
        try:
            r = self._o.create(**kw)
            lat = (time.time() - start) * 1000
            it = r.usage.prompt_tokens if r.usage else 0
            ot = r.usage.completion_tokens if r.usage else 0
            ev = TraceEvent(
                trace_id=uuid.uuid4().hex[:12],
                project=self._p,
                model=model,
                provider=self._prov,
                input_tokens=it,
                output_tokens=ot,
                cost=_calc(model, it, ot),
                latency_ms=lat,
                status="success",
                timestamp=datetime.now().isoformat(),
                goal_id=self._goal_id,
            )
            tracker.record(ev)
            if self._persist:
                _persist_event(ev)
            return r
        except Exception as e:
            lat = (time.time() - start) * 1000
            ev = TraceEvent(
                trace_id=uuid.uuid4().hex[:12],
                project=self._p,
                model=model,
                provider=self._prov,
                input_tokens=0,
                output_tokens=0,
                cost=0,
                latency_ms=lat,
                status="error",
                error=str(e)[:500],
                timestamp=datetime.now().isoformat(),
                goal_id=self._goal_id,
            )
            tracker.record(ev)
            if self._persist:
                _persist_event(ev)
            raise


class _TracedChat:
    def __init__(self, chat, project, provider, persist, goal_id=None):
        self.completions = _TracedCompletions(
            chat.completions, project, provider, persist, goal_id
        )


class _TracedOpenAI:
    def __init__(self, client, project, provider, persist, goal_id=None):
        self._c = client
        self.chat = _TracedChat(client.chat, project, provider, persist, goal_id)

    def __getattr__(self, n):
        return getattr(self._c, n)


class _TracedMessages:
    def __init__(self, orig, project, persist, goal_id=None):
        self._o = orig
        self._p = project
        self._persist = persist
        self._goal_id = goal_id

    def create(self, **kw) -> Any:
        model = kw.get("model", "unknown")
        start = time.time()
        tracker = get_tracker(self._p)
        try:
            r = self._o.create(**kw)
            lat = (time.time() - start) * 1000
            it = r.usage.input_tokens
            ot = r.usage.output_tokens
            ev = TraceEvent(
                trace_id=uuid.uuid4().hex[:12],
                project=self._p,
                model=model,
                provider="anthropic",
                input_tokens=it,
                output_tokens=ot,
                cost=_calc(model, it, ot),
                latency_ms=lat,
                status="success",
                timestamp=datetime.now().isoformat(),
                goal_id=self._goal_id,
            )
            tracker.record(ev)
            if self._persist:
                _persist_event(ev)
            return r
        except Exception as e:
            lat = (time.time() - start) * 1000
            ev = TraceEvent(
                trace_id=uuid.uuid4().hex[:12],
                project=self._p,
                model=model,
                provider="anthropic",
                input_tokens=0,
                output_tokens=0,
                cost=0,
                latency_ms=lat,
                status="error",
                error=str(e)[:500],
                timestamp=datetime.now().isoformat(),
                goal_id=self._goal_id,
            )
            tracker.record(ev)
            if self._persist:
                _persist_event(ev)
            raise


class _TracedAnthropic:
    def __init__(self, client, project, persist, goal_id=None):
        self._c = client
        self.messages = _TracedMessages(client.messages, project, persist, goal_id)

    def __getattr__(self, n):
        return getattr(self._c, n)


def trace(
    client: Any,
    project: str = "default",
    persist: bool = True,
    goal_id: str | None = None,
    prompt_id: str | None = None,
    prompt_version: int | None = None,
) -> Any:
    """Wrap an OpenAI or Anthropic client with automatic cost tracking.

    If prompt_id and prompt_version are set, every trace event will include
    them in metadata for prompt-level cost analytics.
    """
    ct = type(client).__module__
    _extra_meta = {}
    if prompt_id:
        _extra_meta["prompt_id"] = prompt_id
    if prompt_version is not None:
        _extra_meta["prompt_version"] = prompt_version

    if "openai" in ct or hasattr(client, "chat"):
        prov = "openai"
        if hasattr(client, "_base_url"):
            b = str(getattr(client, "_base_url", ""))
            if "anthropic" in b:
                prov = "anthropic"
            elif "groq" in b:
                prov = "groq"
            elif "11434" in b or "ollama" in b.lower():
                prov = "ollama"
        traced = _TracedOpenAI(client, project, prov, persist, goal_id)
        traced._prompt_meta = _extra_meta
        return traced
    elif "anthropic" in ct or hasattr(client, "messages"):
        traced = _TracedAnthropic(client, project, persist, goal_id)
        traced._prompt_meta = _extra_meta
        return traced
    else:
        raise TypeError(
            f"Unsupported client: {type(client).__name__}. Use openai.OpenAI or anthropic.Anthropic"
        )

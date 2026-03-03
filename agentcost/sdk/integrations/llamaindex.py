"""
LlamaIndex Integration — AgentCost callback handler for automatic cost tracking.

Usage:
    from agentcost.sdk.integrations.llamaindex import AgentCostLlamaIndex
    from llama_index.core import Settings
    Settings.callback_manager.add_handler(AgentCostLlamaIndex(project="my-app"))

    # All LLM calls through LlamaIndex are now tracked.

Works with both llama-index-core and legacy llama-index imports.
Does NOT require llama-index to be installed — the module is always
importable (errors at runtime only if used without the package).
"""
from __future__ import annotations
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from ..trace import TraceEvent, get_tracker, _persist_event, _calc

# ── Import resolution (eager, at module load time) ───────────────────────────
# Resolve real LlamaIndex types or fall back to stubs so the module is always
# importable and _CBEventType / _EventPayload are never None.

try:
    from llama_index.core.callbacks.schema import CBEventType as _CBEventType, EventPayload as _EventPayload
except ImportError:
    try:
        from llama_index.callbacks.schema import CBEventType as _CBEventType, EventPayload as _EventPayload
    except ImportError:
        # Stubs — module importable, works for testing, won't pass LlamaIndex isinstance checks
        class _CBEventType:  # type: ignore
            LLM = "llm"
        class _EventPayload:  # type: ignore
            SERIALIZED = "serialized"
            RESPONSE = "response"
            PROMPT = "prompt"

# Public constant for testing convenience
LLM_EVENT = _CBEventType.LLM


class AgentCostLlamaIndex:
    """
    LlamaIndex callback handler for automatic cost tracking.

    Tracks LLM calls with model name, token counts, cost, and latency.
    Integrates with LlamaIndex's callback manager system.
    """

    def __init__(self, project: str = "default", persist: bool = True, agent_id: str = None):
        self.project = project
        self.persist = persist
        self.agent_id = agent_id
        self._pending: Dict[str, dict] = {}

        # For LlamaIndex BaseCallbackHandler compatibility
        self.event_starts_to_trace = [_CBEventType.LLM]
        self.event_ends_to_trace = [_CBEventType.LLM]

    def start_trace(self, trace_id: Optional[str] = None) -> None:
        """Called at the start of a trace. Required by LlamaIndex interface."""
        pass

    def end_trace(self, trace_id: Optional[str] = None,
                  trace_map: Optional[Dict[str, List[str]]] = None) -> None:
        """Called at the end of a trace. Required by LlamaIndex interface."""
        pass

    def on_event_start(self, event_type, payload: Optional[Dict[str, Any]] = None,
                       event_id: str = "", parent_id: str = "", **kwargs) -> str:
        """Called when a callback event starts."""
        # Only track LLM events
        evt = getattr(event_type, 'value', event_type) if hasattr(event_type, 'value') else event_type
        llm_val = getattr(_CBEventType.LLM, 'value', _CBEventType.LLM)
        if evt != llm_val and event_type != _CBEventType.LLM:
            return event_id

        model = "unknown"
        if payload:
            model = (
                payload.get("model_name")
                or payload.get(
                    getattr(_EventPayload, "SERIALIZED", "serialized"), {}
                ).get("model", "unknown")
            )
        self._pending[event_id] = {"model": model, "start": time.time()}
        return event_id

    def on_event_end(self, event_type, payload: Optional[Dict[str, Any]] = None,
                     event_id: str = "", **kwargs) -> None:
        """Called when a callback event ends. Extracts usage and logs trace."""
        evt = getattr(event_type, 'value', event_type) if hasattr(event_type, 'value') else event_type
        llm_val = getattr(_CBEventType.LLM, 'value', _CBEventType.LLM)
        if evt != llm_val and event_type != _CBEventType.LLM:
            return

        pending = self._pending.pop(event_id, None)
        if not pending:
            return

        latency = (time.time() - pending["start"]) * 1000
        model = pending["model"]
        it, ot = _extract_tokens_llamaindex(payload)

        ev = TraceEvent(
            trace_id=event_id[:12] or uuid.uuid4().hex[:12],
            project=self.project,
            model=model,
            provider="llamaindex",
            input_tokens=it,
            output_tokens=ot,
            cost=_calc(model, it, ot),
            latency_ms=latency,
            status="success",
            timestamp=datetime.now().isoformat(),
            agent_id=self.agent_id,
        )
        get_tracker(self.project).record(ev)
        if self.persist:
            _persist_event(ev)

    def summary(self) -> dict:
        return get_tracker(self.project).summary()


# ── Token extraction ──────────────────────────────────────────────────────────

def _extract_tokens_llamaindex(payload: Optional[Dict]) -> tuple:
    """Extract (input_tokens, output_tokens) from LlamaIndex event payload."""
    it, ot = 0, 0
    if not payload:
        return it, ot

    response_key = getattr(_EventPayload, "RESPONSE", "response")
    prompt_key = getattr(_EventPayload, "PROMPT", "prompt")

    # Try to extract from response object
    response = payload.get(response_key) or payload.get("response")
    if response:
        raw = getattr(response, "raw", None) or {}
        usage = getattr(raw, "usage", None)
        if usage is None and isinstance(raw, dict):
            usage = raw.get("usage")
        if usage:
            if isinstance(usage, dict):
                it = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
                ot = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
            else:
                it = getattr(usage, "prompt_tokens", 0) or getattr(usage, "input_tokens", 0) or 0
                ot = getattr(usage, "completion_tokens", 0) or getattr(usage, "output_tokens", 0) or 0

    # Fallback: direct token counts in payload
    if not it:
        it = payload.get("prompt_tokens", 0)
        if not it:
            prompt_data = payload.get(prompt_key, {})
            if isinstance(prompt_data, dict):
                it = prompt_data.get("tokens", 0)
    if not ot:
        ot = payload.get("completion_tokens", 0)

    return it, ot
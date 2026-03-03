"""
LangChain Integration — AgentCost callback handler for automatic cost tracking.

Usage:
    from agentcost.sdk.integrations.langchain import AgentCostCallback
    callback = AgentCostCallback(project="research-agent")
    llm = ChatOpenAI(model="gpt-4o", callbacks=[callback])
    agent = create_react_agent(llm, tools, prompt)
    result = agent.invoke({"input": "Analyze market trends..."})
    print(callback.summary())

Works with both langchain-core and legacy langchain imports.
When langchain is not installed, uses `object` as base so the module
is still importable for testing — but won't pass LangChain's isinstance
check at runtime (which is expected).
"""

import time
import uuid
from datetime import datetime
from typing import Dict, List
from ..trace import TraceEvent, get_tracker, _persist_event, _calc

# ── Resolve base class at import time ─────────────────────────────────────────
# LangChain validates callbacks with isinstance(cb, BaseCallbackHandler),
# so we MUST actually inherit from it when langchain is installed.

try:
    from langchain_core.callbacks.base import BaseCallbackHandler as _Base
except ImportError:
    try:
        from langchain.callbacks.base import BaseCallbackHandler as _Base
    except ImportError:
        _Base = object  # stub — module importable but won't work with LangChain


# ── Helper functions ──────────────────────────────────────────────────────────


def _extract_model(serialized: Dict, kwargs: Dict) -> str:
    """Extract model name from LangChain callback args."""
    return (
        kwargs.get("invocation_params", {}).get("model_name")
        or kwargs.get("invocation_params", {}).get("model")
        or serialized.get("kwargs", {}).get("model_name")
        or serialized.get("kwargs", {}).get("model")
        or "unknown"
    )


def _extract_tokens(response) -> tuple:
    """Extract (input_tokens, output_tokens) from LLMResult."""
    it, ot = 0, 0

    # Primary: llm_output.token_usage
    llm_output = getattr(response, "llm_output", None) or {}
    tu = llm_output.get("token_usage", {})
    it = tu.get("prompt_tokens", 0)
    ot = tu.get("completion_tokens", 0)

    # Fallback: generation_info per generation
    if not it and hasattr(response, "generations"):
        for gen_list in response.generations:
            for gen in gen_list:
                info = getattr(gen, "generation_info", {}) or {}
                usage = info.get("usage", {}) or {}
                it += usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
                ot += usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)

    return it, ot


# ── Callback Handler ──────────────────────────────────────────────────────────


class AgentCostCallback(_Base):
    """
    LangChain callback handler for automatic cost tracking.

    Tracks model name, input/output tokens, cost, and latency for every
    LLM call in a LangChain chain or agent. Supports both completion and
    chat model APIs.
    """

    def __init__(
        self,
        project: str = "default",
        persist: bool = True,
        agent_id: str = None,
        **kwargs,
    ):
        if _Base is not object:
            super().__init__(**kwargs)
        self.project = project
        self.persist = persist
        self.agent_id = agent_id
        self._pending: Dict[str, dict] = {}

    # ── LLM start (completions API) ──────────────────────────────────────

    def on_llm_start(
        self, serialized: Dict, prompts: List[str], *, run_id=None, **kwargs
    ) -> None:
        rid = str(run_id) if run_id else uuid.uuid4().hex[:12]
        model = _extract_model(serialized, kwargs)
        self._pending[rid] = {"model": model, "start": time.time()}

    # ── Chat model start ─────────────────────────────────────────────────

    def on_chat_model_start(
        self, serialized: Dict, messages: List, *, run_id=None, **kwargs
    ) -> None:
        rid = str(run_id) if run_id else uuid.uuid4().hex[:12]
        model = _extract_model(serialized, kwargs)
        self._pending[rid] = {"model": model, "start": time.time()}

    # ── LLM end ──────────────────────────────────────────────────────────

    def on_llm_end(self, response, *, run_id=None, **kwargs) -> None:
        rid = str(run_id) if run_id else ""
        p = self._pending.pop(rid, None)
        if not p:
            return

        latency = (time.time() - p["start"]) * 1000
        model = p["model"]
        it, ot = _extract_tokens(response)

        ev = TraceEvent(
            trace_id=rid[:12],
            project=self.project,
            model=model,
            provider="langchain",
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

    # ── LLM error ────────────────────────────────────────────────────────

    def on_llm_error(self, error, *, run_id=None, **kwargs) -> None:
        rid = str(run_id) if run_id else ""
        p = self._pending.pop(rid, None)
        if not p:
            return

        latency = (time.time() - p["start"]) * 1000
        ev = TraceEvent(
            trace_id=rid[:12],
            project=self.project,
            model=p["model"],
            provider="langchain",
            input_tokens=0,
            output_tokens=0,
            cost=0,
            latency_ms=latency,
            status="error",
            error=str(error)[:500],
            timestamp=datetime.now().isoformat(),
            agent_id=self.agent_id,
        )
        get_tracker(self.project).record(ev)
        if self.persist:
            _persist_event(ev)

    # ── Summary ──────────────────────────────────────────────────────────

    def summary(self) -> dict:
        return get_tracker(self.project).summary()

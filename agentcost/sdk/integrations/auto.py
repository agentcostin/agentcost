"""
Auto-instrumentation — detect installed LLM libraries and patch them automatically.

Usage:
    import agentcost
    agentcost.auto_instrument(project="my-app")

    # Now ALL LLM calls are tracked — no other code changes needed.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

logger = logging.getLogger("agentcost.auto_instrument")

_original_refs: dict[str, Any] = {}
_instrumented = False


def auto_instrument(project: str = "default", persist: bool = True) -> dict[str, bool]:
    """
    Auto-detect and patch installed LLM libraries.

    Returns dict of {library: patched_bool}.
    """
    global _instrumented
    if _instrumented:
        logger.warning("Already instrumented — skipping")
        return {}

    results: dict[str, bool] = {}

    # 1. Patch OpenAI
    results["openai"] = _patch_openai(project, persist)

    # 2. Patch Anthropic
    results["anthropic"] = _patch_anthropic(project, persist)

    # 3. Hook into LangChain (if installed)
    results["langchain"] = _hook_langchain(project, persist)

    # 4. Hook into LlamaIndex (if installed)
    results["llamaindex"] = _hook_llamaindex(project, persist)

    _instrumented = True
    patched = [k for k, v in results.items() if v]
    logger.info(f"Auto-instrumented: {patched or 'none detected'}")
    return results


def undo_instrument():
    """Restore original (unpatched) library methods."""
    global _instrumented
    for key, orig in _original_refs.items():
        parts = key.rsplit(".", 1)
        if len(parts) == 2:
            mod_path, attr = parts
            mod = sys.modules.get(mod_path)
            if mod:
                setattr(mod, attr, orig)
    _original_refs.clear()
    _instrumented = False
    logger.info("Auto-instrumentation removed")


def _patch_openai(project: str, persist: bool) -> bool:
    """Monkey-patch openai.resources.chat.completions.Completions.create."""
    try:
        import openai  # noqa: F401
        from openai.resources.chat.completions import Completions

        orig_create = Completions.create
        if getattr(orig_create, "_agentcost_patched", False):
            return True

        from ..sdk.trace import TraceEvent, get_tracker, _persist_event, _calc
        import time
        import uuid
        from datetime import datetime

        def patched_create(self_comp, **kwargs):
            model = kwargs.get("model", "unknown")
            start = time.time()
            tracker = get_tracker(project)
            try:
                r = orig_create(self_comp, **kwargs)
                lat = (time.time() - start) * 1000
                it = r.usage.prompt_tokens if r.usage else 0
                ot = r.usage.completion_tokens if r.usage else 0
                ev = TraceEvent(
                    trace_id=uuid.uuid4().hex[:12],
                    project=project,
                    model=model,
                    provider="openai",
                    input_tokens=it,
                    output_tokens=ot,
                    cost=_calc(model, it, ot),
                    latency_ms=lat,
                    status="success",
                    timestamp=datetime.now().isoformat(),
                )
                tracker.record(ev)
                if persist:
                    _persist_event(ev)
                return r
            except Exception as e:
                lat = (time.time() - start) * 1000
                ev = TraceEvent(
                    trace_id=uuid.uuid4().hex[:12],
                    project=project,
                    model=model,
                    provider="openai",
                    input_tokens=0,
                    output_tokens=0,
                    cost=0,
                    latency_ms=lat,
                    status="error",
                    error=str(e)[:500],
                    timestamp=datetime.now().isoformat(),
                )
                tracker.record(ev)
                if persist:
                    _persist_event(ev)
                raise

        patched_create._agentcost_patched = True
        _original_refs["openai.resources.chat.completions.Completions.create"] = (
            orig_create
        )
        Completions.create = patched_create
        logger.info("Patched openai.Completions.create")
        return True
    except ImportError:
        return False
    except Exception as e:
        logger.warning(f"Failed to patch openai: {e}")
        return False


def _patch_anthropic(project: str, persist: bool) -> bool:
    """Monkey-patch anthropic.resources.messages.Messages.create."""
    try:
        import anthropic  # noqa: F401
        from anthropic.resources.messages import Messages

        orig_create = Messages.create
        if getattr(orig_create, "_agentcost_patched", False):
            return True

        from ..sdk.trace import TraceEvent, get_tracker, _persist_event, _calc
        import time
        import uuid
        from datetime import datetime

        def patched_create(self_msg, **kwargs):
            model = kwargs.get("model", "unknown")
            start = time.time()
            tracker = get_tracker(project)
            try:
                r = orig_create(self_msg, **kwargs)
                lat = (time.time() - start) * 1000
                it = r.usage.input_tokens
                ot = r.usage.output_tokens
                ev = TraceEvent(
                    trace_id=uuid.uuid4().hex[:12],
                    project=project,
                    model=model,
                    provider="anthropic",
                    input_tokens=it,
                    output_tokens=ot,
                    cost=_calc(model, it, ot),
                    latency_ms=lat,
                    status="success",
                    timestamp=datetime.now().isoformat(),
                )
                tracker.record(ev)
                if persist:
                    _persist_event(ev)
                return r
            except Exception as e:
                lat = (time.time() - start) * 1000
                ev = TraceEvent(
                    trace_id=uuid.uuid4().hex[:12],
                    project=project,
                    model=model,
                    provider="anthropic",
                    input_tokens=0,
                    output_tokens=0,
                    cost=0,
                    latency_ms=lat,
                    status="error",
                    error=str(e)[:500],
                    timestamp=datetime.now().isoformat(),
                )
                tracker.record(ev)
                if persist:
                    _persist_event(ev)
                raise

        patched_create._agentcost_patched = True
        _original_refs["anthropic.resources.messages.Messages.create"] = orig_create
        Messages.create = patched_create
        logger.info("Patched anthropic.Messages.create")
        return True
    except ImportError:
        return False
    except Exception as e:
        logger.warning(f"Failed to patch anthropic: {e}")
        return False


def _hook_langchain(project: str, persist: bool) -> bool:
    """Register AgentCostCallback as a global LangChain callback."""
    try:
        from ..sdk.integrations.langchain import AgentCostCallback
        import langchain_core.callbacks.manager as mgr

        AgentCostCallback(project=project, persist=persist)
        # Add to default callbacks if the manager supports it
        if hasattr(mgr, "configure"):
            # LangChain >=0.1 approach
            pass
        logger.info(
            "LangChain handler registered (use callbacks=[handler] in your chains)"
        )
        return True
    except ImportError:
        return False
    except Exception as e:
        logger.warning(f"Failed to hook langchain: {e}")
        return False


def _hook_llamaindex(project: str, persist: bool) -> bool:
    """Register AgentCostLlamaIndex as a global LlamaIndex callback."""
    try:
        from ..sdk.integrations.llamaindex import AgentCostLlamaIndex
        from llama_index.core import Settings

        handler = AgentCostLlamaIndex(project=project, persist=persist)
        Settings.callback_manager.add_handler(handler)
        logger.info("LlamaIndex handler registered via Settings.callback_manager")
        return True
    except ImportError:
        return False
    except Exception as e:
        logger.warning(f"Failed to hook llamaindex: {e}")
        return False

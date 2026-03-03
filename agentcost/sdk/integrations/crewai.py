"""
AgentCost CrewAI Integration — Phase 5 Block 3

Tracks per-crew and per-agent costs in CrewAI multi-agent workflows.

Usage:
    from agentcost.sdk.integrations.crewai import AgentCostCrewCallbacks
    from crewai import Crew, Agent, Task

    callbacks = AgentCostCrewCallbacks(project="my-crew")
    crew = Crew(agents=[...], tasks=[...], callbacks=[callbacks])
    result = crew.kickoff()
    print(callbacks.summary())
"""
from __future__ import annotations
import time
import logging
import uuid
from typing import Any

logger = logging.getLogger("agentcost.integrations.crewai")


class AgentCostCrewCallbacks:
    """
    CrewAI step callback that tracks costs per agent and per task.
    Works with CrewAI's callback system (step_callback parameter).
    """

    def __init__(self, project: str = "crewai", agent_id: str = None):
        self.project = project
        self.agent_id = agent_id
        self._events: list[dict] = []
        self._current_agent: str = "unknown"
        self._current_task: str = "unknown"
        self._call_start: float = 0

        # Try to get the tracker
        try:
            from ...sdk.trace import get_tracker
            self._tracker = get_tracker(project)
        except Exception:
            self._tracker = None

    def on_agent_start(self, agent_name: str, **kwargs) -> None:
        """Called when a CrewAI agent starts working."""
        self._current_agent = agent_name
        logger.debug(f"CrewAI agent started: {agent_name}")

    def on_task_start(self, task_description: str, **kwargs) -> None:
        """Called when a task begins."""
        self._current_task = task_description[:100]

    def on_llm_start(self, model: str = "unknown", **kwargs) -> None:
        """Called before an LLM call."""
        self._call_start = time.time()

    def on_llm_end(self, model: str = "unknown", input_tokens: int = 0,
                    output_tokens: int = 0, cost: float = 0, **kwargs) -> None:
        """Called after an LLM call completes."""
        latency = int((time.time() - self._call_start) * 1000) if self._call_start else 0
        event = {
            "agent": self._current_agent,
            "task": self._current_task,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
            "latency_ms": latency,
        }
        self._events.append(event)

    def __call__(self, step_output: Any) -> None:
        """
        CrewAI step_callback interface.
        Called after each agent step with the step output.
        """
        # Extract info from CrewAI step output
        agent_name = "unknown"
        if hasattr(step_output, "agent"):
            agent_name = getattr(step_output.agent, "role", str(step_output.agent))
        elif hasattr(step_output, "name"):
            agent_name = step_output.name

        self._current_agent = agent_name
        self._events.append({
            "agent": agent_name,
            "task": self._current_task,
            "model": "crewai-step",
            "input_tokens": 0,
            "output_tokens": 0,
            "cost": 0,
            "latency_ms": 0,
            "step": True,
        })

    def summary(self) -> dict:
        """Cost summary grouped by agent."""
        by_agent: dict[str, dict] = {}
        total_cost = 0
        for ev in self._events:
            if ev.get("step"):
                continue
            agent = ev["agent"]
            if agent not in by_agent:
                by_agent[agent] = {"calls": 0, "cost": 0, "tokens": 0}
            by_agent[agent]["calls"] += 1
            by_agent[agent]["cost"] += ev["cost"]
            by_agent[agent]["tokens"] += ev["input_tokens"] + ev["output_tokens"]
            total_cost += ev["cost"]
        return {
            "project": self.project,
            "total_cost": total_cost,
            "total_calls": len([e for e in self._events if not e.get("step")]),
            "by_agent": by_agent,
        }


class AgentCostAutoGenHandler:
    """
    Microsoft AutoGen agent conversation tracker.

    Hooks into AutoGen's message passing to track LLM costs
    per agent in multi-agent conversations.

    Usage:
        from agentcost.sdk.integrations.crewai import AgentCostAutoGenHandler
        handler = AgentCostAutoGenHandler(project="autogen-research")

        # Register with AutoGen agents
        assistant = AssistantAgent("assistant", llm_config=llm_config)
        assistant.register_hook("process_message_before_send", handler.on_message)
    """

    def __init__(self, project: str = "autogen"):
        self.project = project
        self._events: list[dict] = []
        self._conversation_id = str(uuid.uuid4())[:8]

    def on_message(self, sender: str = "unknown", message: Any = None, **kwargs) -> Any:
        """Hook for AutoGen message processing."""
        event = {
            "agent": sender,
            "conversation_id": self._conversation_id,
            "timestamp": time.time(),
        }

        # Try to extract content
        if isinstance(message, dict):
            event["content_length"] = len(str(message.get("content", "")))
        elif isinstance(message, str):
            event["content_length"] = len(message)

        self._events.append(event)
        return message  # Pass through

    def on_llm_call(self, agent: str, model: str, input_tokens: int,
                     output_tokens: int, cost: float, latency_ms: int = 0) -> None:
        """Manually log an LLM call from an AutoGen agent."""
        self._events.append({
            "agent": agent,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
            "latency_ms": latency_ms,
            "conversation_id": self._conversation_id,
        })

    def summary(self) -> dict:
        by_agent: dict[str, dict] = {}
        total_cost = 0
        for ev in self._events:
            agent = ev.get("agent", "unknown")
            cost = ev.get("cost", 0)
            if agent not in by_agent:
                by_agent[agent] = {"messages": 0, "llm_calls": 0, "cost": 0}
            by_agent[agent]["messages"] += 1
            if "model" in ev:
                by_agent[agent]["llm_calls"] += 1
            by_agent[agent]["cost"] += cost
            total_cost += cost
        return {
            "project": self.project,
            "conversation_id": self._conversation_id,
            "total_cost": total_cost,
            "total_messages": len(self._events),
            "by_agent": by_agent,
        }

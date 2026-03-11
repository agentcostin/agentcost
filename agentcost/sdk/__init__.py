"""AgentCost SDK — drop-in cost tracking for LLM applications."""

from .trace import trace, get_tracker, get_all_trackers, CostTracker, TraceEvent
from .remote import RemoteTracker


def get_prompt(
    name: str,
    *,
    environment: str = "production",
    variables: dict | None = None,
    version: int | None = None,
    agentcost_url: str | None = None,
):
    """Resolve a prompt from the AgentCost server.

    Usage:
        from agentcost.sdk import get_prompt, trace

        prompt = get_prompt("support-bot",
                            environment="production",
                            variables={"product": "AgentCost"})

        client = trace(OpenAI(), project="support",
                       prompt_id=prompt["prompt_id"],
                       prompt_version=prompt["version"])

        response = client.chat.completions.create(
            model=prompt.get("model") or "gpt-4.1",
            messages=[{"role": "system", "content": prompt["content"]},
                      {"role": "user", "content": user_msg}]
        )
    """
    import os
    import json

    try:
        import urllib.request

        url = agentcost_url or os.environ.get("AGENTCOST_URL", "http://localhost:8100")
        payload = json.dumps(
            {
                "environment": environment,
                "variables": variables or {},
                "version": version,
            }
        ).encode()

        req = urllib.request.Request(
            f"{url}/api/prompts/{name}/resolve",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        # Fallback: try local service directly
        try:
            from ..prompts import get_prompt_service

            svc = get_prompt_service()
            return svc.resolve(
                name,
                environment=environment,
                variables=variables,
                version=version,
            )
        except Exception:
            raise


__all__ = [
    "trace",
    "get_tracker",
    "get_all_trackers",
    "CostTracker",
    "TraceEvent",
    "RemoteTracker",
    "get_prompt",
]

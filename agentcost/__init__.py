"""
AgentCost — AI Agent Economic Benchmarking

Benchmark LLMs on real professional tasks. Measure quality per dollar.
Compare models head-to-head. Find out which AI is worth what it costs.
"""

__version__ = "0.5.0"


def auto_instrument(project: str = "default", persist: bool = True) -> dict[str, bool]:
    """Auto-detect and patch installed LLM libraries for cost tracking."""
    from .sdk.integrations.auto import auto_instrument as _auto

    return _auto(project=project, persist=persist)

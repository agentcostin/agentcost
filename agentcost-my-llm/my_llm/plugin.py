"""
my-llm — AgentCost Provider Plugin
"""
from agentcost.plugins import (
    ProviderPlugin, PluginMeta, PluginType,
)


class MyLlmPlugin(ProviderPlugin):
    meta = PluginMeta(
        name="my-llm",
        version="0.1.0",
        plugin_type=PluginType.PROVIDER,
        description="Cost calculation for my-llm models",
    )

    # TODO: Add your model pricing
    PRICING = {
        "my-model-large": {"input": 1.00, "output": 3.00},
        "my-model-small": {"input": 0.10, "output": 0.30},
    }

    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float | None:
        p = self.PRICING.get(model)
        if not p:
            return None
        return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000

    def supported_models(self) -> list[str]:
        return list(self.PRICING.keys())

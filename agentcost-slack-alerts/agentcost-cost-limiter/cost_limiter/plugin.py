"""
cost-limiter — AgentCost Policy Plugin
"""
from agentcost.plugins import (
    PolicyPlugin, PolicyContext, PolicyDecision, PluginMeta, PluginType,
)


class CostLimiterPlugin(PolicyPlugin):
    meta = PluginMeta(
        name="cost-limiter",
        version="0.1.0",
        plugin_type=PluginType.POLICY,
        description="Custom policy rule: cost-limiter",
    )

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
        # TODO: Implement your policy logic here
        if ctx.estimated_cost > 1.0:
            return PolicyDecision(allowed=False, reason="Cost exceeds $1.00 limit",
                action="require_approval")
        return PolicyDecision(allowed=True)

"""
AgentCost — Cost Forecasting Example

Predict future AI costs based on historical trace data.

Usage:
    pip install agentcostin
    python examples/forecasting.py
"""

from agentcost.forecast import CostForecaster

# Create forecaster and add sample daily costs
forecaster = CostForecaster()

# Simulate 14 days of cost data
import random
random.seed(42)
daily_costs = [round(random.uniform(15, 45) * (1 + i * 0.02), 2) for i in range(14)]
for i, cost in enumerate(daily_costs):
    forecaster.add_daily_cost(cost)

print("📊 Historical daily costs:")
for i, c in enumerate(daily_costs):
    print(f"   Day {i+1:2d}: ${c:.2f}")

# Predict next 7 days
prediction = forecaster.predict(days_ahead=7, method="ensemble")
print("\n🔮 Forecast (ensemble method):")
print(f"   Next 7 days estimated total: ${prediction.total:.2f}")
print(f"   Daily average: ${prediction.daily_average:.2f}")
print(f"   Trend: {prediction.trend}")

# Check budget exhaustion
result = forecaster.predict_budget_exhaustion(budget=500.0)
if result:
    print("\n⚠️  Budget exhaustion predicted:")
    print("   Budget: $500.00")
    print(f"   Exhaustion in: {result.get('days_remaining', '?')} days")
else:
    print("\n✅ Budget ($500) not projected to be exhausted")

print("\n💡 Tip: Use via API: GET /api/forecast/{project}?days=30&method=ensemble")

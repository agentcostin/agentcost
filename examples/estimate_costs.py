"""
AgentCost — Cost Estimation Example

Estimate costs BEFORE making LLM calls. Compare 42 models.

Usage:
    pip install agentcostin
    python examples/estimate_costs.py
"""

from agentcost.estimator import CostEstimator

estimator = CostEstimator()

# Estimate cost for a single model
prompt = "Analyze this quarterly report and provide key insights with recommendations."
estimate = estimator.estimate("gpt-4o", prompt, task_type="analysis", max_output_tokens=2000)

print(f"📝 Prompt: \"{prompt[:60]}...\"")
print("   Model: gpt-4o")
print(f"   Estimated input tokens:  {estimate.input_tokens:,}")
print(f"   Estimated output tokens: {estimate.output_tokens:,}")
print(f"   Estimated cost: ${estimate.cost:.6f}")

# Compare across popular models
print("\n📊 Model comparison for the same prompt:\n")
models = ["gpt-4o", "gpt-4o-mini", "claude-3-5-sonnet", "claude-3-5-haiku",
          "gemini-1.5-pro", "gemini-1.5-flash"]

comparison = estimator.compare_models(prompt, models, "analysis")
print(f"   {'Model':<25} {'Est. Cost':>12} {'Input Tok':>12} {'Output Tok':>12}")
print(f"   {'─'*25} {'─'*12} {'─'*12} {'─'*12}")
for item in comparison:
    print(f"   {item['model']:<25} ${item['estimated_cost']:>10.6f} {item['input_tokens']:>11,} {item['output_tokens']:>11,}")

cheapest = min(comparison, key=lambda x: x["estimated_cost"])
most_expensive = max(comparison, key=lambda x: x["estimated_cost"])
savings = most_expensive["estimated_cost"] - cheapest["estimated_cost"]

print(f"\n💡 Cheapest: {cheapest['model']} (${cheapest['estimated_cost']:.6f})")
print(f"   Most expensive: {most_expensive['model']} (${most_expensive['estimated_cost']:.6f})")
print(f"   Potential savings: ${savings:.6f} per call ({savings/most_expensive['estimated_cost']*100:.0f}%)")

print("\n💡 Tip: Use via API: POST /api/estimate or GET /api/estimate/compare?prompt=...")

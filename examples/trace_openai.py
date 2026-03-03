"""
Example: Using AgentCost SDK to trace LLM costs.

Run: python examples/trace_openai.py
Then: python -m agentcost traces --summary
Or:   python -m agentcost dashboard   (open http://localhost:8500)
"""

from openai import OpenAI
from agentcost.sdk import trace, get_tracker

# 1. Wrap your OpenAI client — one line change
client = trace(OpenAI(), project="demo-app")

# 2. Use it exactly as before — costs are tracked automatically
print("Making 3 LLM calls...\n")

for i, prompt in enumerate([
    "What is the capital of France? Answer in one word.",
    "Write a haiku about programming.",
    "Explain quantum computing in two sentences.",
], 1):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=100,
    )
    content = response.choices[0].message.content
    print(f"  [{i}] {prompt[:50]}...")
    print(f"      → {content[:80]}")
    print()

# 3. Check accumulated costs
tracker = get_tracker("demo-app")
summary = tracker.summary()

print("=" * 50)
print(f"  Total Cost:    ${summary['total_cost']:.6f}")
print(f"  Total Calls:   {summary['total_calls']}")
print(f"  Input Tokens:  {summary['total_input_tokens']:,}")
print(f"  Output Tokens: {summary['total_output_tokens']:,}")
print()
print("  Cost by Model:")
for model, cost in summary["cost_by_model"].items():
    print(f"    {model}: ${cost:.6f}")
print("=" * 50)
print()
print("View in dashboard: python -m agentcost dashboard")
print("View in CLI:       python -m agentcost traces --summary")

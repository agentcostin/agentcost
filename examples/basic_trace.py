"""
AgentCost — Basic Trace Example

The simplest possible integration: wrap your OpenAI client in one line.

Usage:
    pip install agentcostin openai
    export OPENAI_API_KEY=sk-...
    python examples/basic_trace.py
    agentcost dashboard  # view results at http://localhost:8500
"""

from agentcost.sdk import trace
from openai import OpenAI

# One line: wrap your client
client = trace(OpenAI(), project="basic-example")

# Use it exactly as before
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "What is 2+2?"}],
    max_tokens=50,
)

print(f"Response: {response.choices[0].message.content}")
print("\n✅ Call tracked! View in dashboard: agentcost dashboard")

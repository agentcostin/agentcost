"""
Example: Tracing costs through a corporate LiteLLM proxy.

Set env vars first:
  export LITELLM_PROXY_URL=https://aigw.ea.jio.com
  export LITELLM_API_KEY=sk-your-key

Run: python examples/trace_proxy.py
"""

import os
import httpx
from openai import OpenAI
from agentcost.sdk import trace, get_tracker

proxy_url = os.environ.get("LITELLM_PROXY_URL", "http://localhost:4000")
api_key = os.environ.get("LITELLM_API_KEY", "")

if not proxy_url.rstrip("/").endswith("/v1"):
    proxy_url = proxy_url.rstrip("/") + "/v1"

# Create OpenAI client pointing at your proxy
# Use verify=False for corporate gateways with internal CAs
raw_client = OpenAI(
    api_key=api_key,
    base_url=proxy_url,
    http_client=httpx.Client(verify=False, timeout=httpx.Timeout(300.0, connect=10.0)),
)

# Wrap with AgentCost tracing
client = trace(raw_client, project="proxy-demo")

print(f"Proxy: {proxy_url}")
print("Making test call...\n")

response = client.chat.completions.create(
    model="gpt-4o-mini",  # Use your proxy's model name
    messages=[{"role": "user", "content": "Say hello in 3 languages"}],
    max_tokens=100,
)

print(f"Response: {response.choices[0].message.content}\n")

summary = get_tracker("proxy-demo").summary()
print(f"Cost: ${summary['total_cost']:.6f}")
print(f"Calls: {summary['total_calls']}")
print("\nView dashboard: python -m agentcost dashboard")

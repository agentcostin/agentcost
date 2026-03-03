"""
AgentCost + Ollama — Track costs of local LLM inference.

Prerequisites:
    1. Install Ollama:  https://ollama.com/download
    2. Pull a model:    ollama pull llama3.2
    3. Ollama runs at:  http://10.166.73.108:11434 (default)

Usage:
    python trace_ollama.py

Even though local models have $0 API cost, tracking them lets you:
  - Compare local vs cloud model quality on the same tasks
  - Monitor token usage and latency across your fleet
  - Set budgets that combine cloud + local spending
  - Generate scorecards for local model performance
"""

from openai import OpenAI
from agentcost.sdk import trace, get_tracker

# ── Option 1: SDK trace() wrapper (recommended) ─────────────────────────────
# Point OpenAI client at Ollama's OpenAI-compatible endpoint

ollama = OpenAI(
    base_url="http://10.166.73.108:11434/v1",
    api_key="ollama",  # Ollama doesn't need a key, but the SDK requires one
)

# Wrap with AgentCost — auto-detects Ollama from the URL
client = trace(ollama, project="local-llm-test")

print("🦙 Running local Ollama model via SDK trace()...\n")

response = client.chat.completions.create(
    model="llama3.2",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain what a neural network is in 2 sentences."},
    ],
    temperature=0.7,
)

print(f"Response: {response.choices[0].message.content}\n")

# Check tracked costs
tracker = get_tracker("local-llm-test")
summary = tracker.summary()
print("📊 Tracker Summary:")
print(f"   Cost:     ${summary['total_cost']:.6f}  (local = $0)")
print(f"   Calls:    {summary['total_calls']}")
print(f"   Tokens:   {summary['total_input_tokens']} in → {summary['total_output_tokens']} out")
print("   Provider: ollama (auto-detected)")
print()


# ── Option 2: TrackedProvider (for benchmarking) ────────────────────────────
from agentcost.providers.tracked import TrackedProvider

print("🔬 Running via TrackedProvider...\n")

provider = TrackedProvider(
    model="llama3.2",
    provider="ollama",
    # base_url="http://10.166.73.108:11434",  # default, or set OLLAMA_HOST env
)

result = provider.chat("Write a haiku about programming.")

print(f"Response: {result.content}")
print(f"   Model:    {result.model}")
print(f"   Tokens:   {result.input_tokens} in → {result.output_tokens} out")
print(f"   Cost:     ${result.cost:.6f}")
print(f"   Latency:  {result.latency_ms:.0f}ms")
print()


# ── Option 3: CLI commands ──────────────────────────────────────────────────
print("💻 CLI examples (run these in your terminal):\n")
print("  # Benchmark a local model")
print('  python -m agentcost benchmark --model llama3.2 --provider ollama --tasks 3')
print()
print("  # Compare local models")
print('  python -m agentcost compare --models "llama3.2,mistral,phi3" --provider ollama')
print()
print("  # Compare local vs cloud")
print('  python -m agentcost compare --models "llama3.2,gpt-4o-mini" --tasks 3')
print("  # (note: cloud models need OPENAI_API_KEY set)")
print()
print("  # Remote Ollama server")
print('  python -m agentcost benchmark --model llama3.2 --provider ollama --ollama-url http://gpu-server:11434')
print()


# ── Custom cost pricing for internal chargeback ─────────────────────────────
print("💰 Custom pricing (for internal chargeback):\n")
print("  Set AGENTCOST_OLLAMA_PRICING to charge internal teams for GPU usage:")
print('  export AGENTCOST_OLLAMA_PRICING="0.05,0.10"  # $0.05/$0.10 per 1M tokens')
print("  Then all Ollama traces will use your custom rates instead of $0.")
print()

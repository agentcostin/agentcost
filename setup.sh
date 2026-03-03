#!/usr/bin/env bash
set -euo pipefail

echo ""
echo "🧮 AgentCost — Setup"
echo "════════════════════════════════════════"
echo ""

# Check Python
command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3.10+ required"; exit 1; }
echo "✅ Python $(python3 --version | cut -d' ' -f2)"

# Install deps
echo ""
echo "📦 Installing Python dependencies…"
pip install -q openai anthropic litellm websockets python-dotenv 2>/dev/null \
  || pip install -q openai anthropic litellm websockets python-dotenv --break-system-packages 2>/dev/null
echo "✅ Dependencies installed"

# Env file
if [ ! -f .env ]; then
  cp .env.example .env
  echo "📝 Created .env — add your OPENAI_API_KEY"
else
  echo "📝 .env already exists"
fi

# Data dir
mkdir -p ~/.agentcost
echo "✅ Data directory: ~/.agentcost/"

# ACP server (optional)
if command -v node >/dev/null 2>&1; then
  NODE_V=$(node -v | sed 's/v//' | cut -d. -f1)
  if [ "$NODE_V" -ge 18 ]; then
    echo ""
    echo "📦 Installing ACP server dependencies…"
    cd acp-server && npm install --silent 2>/dev/null && cd ..
    echo "✅ ACP server ready (optional — not needed for basic benchmarks)"
  fi
fi

echo ""
echo "════════════════════════════════════════"
echo "✅ Setup complete!"
echo ""
echo "Quick start:"
echo ""
echo "  1. Add your API key to .env:"
echo "     export OPENAI_API_KEY=sk-..."
echo ""
echo "  2. Run a benchmark:"
echo "     python -m agentcost benchmark --model gpt-4o --tasks 5"
echo ""
echo "  3. Compare models:"
echo "     python -m agentcost compare --models \"gpt-4o,gpt-4o-mini\" --tasks 5"
echo ""
echo "  4. View leaderboard:"
echo "     python -m agentcost leaderboard"
echo ""
echo "════════════════════════════════════════"

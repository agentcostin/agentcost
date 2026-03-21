#!/bin/bash
# AgentCost Live Simulator — Apply Script
# Run from the root of your agentcost repo:
#   bash APPLY.sh
#
# OR just apply the git patch:
#   git apply simulator.patch

set -e

echo "🔬 AgentCost Live Simulator — Applying changes..."
echo ""

# Check we're in the right directory
if [ ! -f "dashboard/index.html" ]; then
    echo "❌ Error: dashboard/index.html not found."
    echo "   Run this script from the root of the agentcost repo."
    exit 1
fi

# Backup current dashboard
cp dashboard/index.html dashboard/index.html.backup
echo "✅ Backed up dashboard/index.html → dashboard/index.html.backup"

# Apply the patch
if [ -f "simulator.patch" ]; then
    git apply simulator.patch
    echo "✅ Applied simulator.patch"
else
    # Fallback: copy the pre-built file
    cp dashboard/index.html.new dashboard/index.html
    echo "✅ Replaced dashboard/index.html with simulator version"
fi

echo ""
echo "🎉 Done! The Cost Simulator is now available in your dashboard."
echo ""
echo "Next steps:"
echo "  1. Start your backend:   agentcost dashboard"
echo "  2. Open:                 http://localhost:8500"
echo "  3. Click '🔬 Cost Simulator' in the sidebar"
echo "  4. Click START SIMULATION"
echo "  5. Inject chaos events and watch costs spike!"
echo ""
echo "To revert: cp dashboard/index.html.backup dashboard/index.html"

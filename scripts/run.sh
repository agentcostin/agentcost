#!/usr/bin/env bash
set -euo pipefail

# Load env vars
[ -f .env ] && set -a && source .env && set +a

# Pass all arguments through to the CLI
python -m agentcost "$@"

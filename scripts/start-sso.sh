#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# AgentCost Block 1: SSO/SAML Quick Start
#
# Starts Keycloak + PostgreSQL + AgentCost API with auth enabled.
#
# Prerequisites:
#   - Docker & Docker Compose
#   - Port 8080 (Keycloak), 5432 (Postgres), 8100 (API) free
#
# Usage:
#   chmod +x scripts/start-sso.sh
#   ./scripts/start-sso.sh
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  AgentCost — Block 1: SSO/SAML Authentication Setup    ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Step 1: Create .env if missing ──────────────────────────────
if [ ! -f .env ]; then
    echo "📝 Creating .env from template..."
    cp .env.enterprise .env
    echo "   ✅ Created .env — edit for production use"
else
    echo "📝 .env already exists, using existing config"
fi

# ── Step 2: Start infrastructure ────────────────────────────────
echo ""
echo "🐳 Starting Docker services..."
docker compose up -d

# ── Step 3: Wait for Keycloak ───────────────────────────────────
echo ""
echo "⏳ Waiting for Keycloak to be ready..."
MAX_WAIT=120
ELAPSED=0
while ! curl -sf http://localhost:8080/health/ready > /dev/null 2>&1; do
    sleep 3
    ELAPSED=$((ELAPSED + 3))
    if [ $ELAPSED -ge $MAX_WAIT ]; then
        echo "   ❌ Keycloak didn't start within ${MAX_WAIT}s"
        echo "   Check logs: docker compose -f docker-compose.enterprise.yml logs keycloak"
        exit 1
    fi
    printf "   Waiting... (%ds)\r" $ELAPSED
done
echo "   ✅ Keycloak is ready                    "

# ── Step 4: Wait for API ────────────────────────────────────────
echo ""
echo "⏳ Waiting for AgentCost API..."
ELAPSED=0
while ! curl -sf http://localhost:8100/api/health > /dev/null 2>&1; do
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    if [ $ELAPSED -ge 60 ]; then
        echo "   ❌ API didn't start within 60s"
        echo "   Check logs: docker compose -f docker-compose.enterprise.yml logs api"
        exit 1
    fi
    printf "   Waiting... (%ds)\r" $ELAPSED
done
echo "   ✅ AgentCost API is ready               "

# ── Step 5: Print summary ──────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                    🎉 All Services Running              ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║                                                         ║"
echo "║  AgentCost API:  http://localhost:8100                  ║"
echo "║  API Docs:       http://localhost:8100/docs             ║"
echo "║  Auth Health:    http://localhost:8100/auth/health      ║"
echo "║                                                         ║"
echo "║  Keycloak Admin: http://localhost:8080                  ║"
echo "║    Username:     admin                                  ║"
echo "║    Password:     admin                                  ║"
echo "║                                                         ║"
echo "║  ── Login Flows ──────────────────────────────────────  ║"
echo "║  OIDC Login:     http://localhost:8100/auth/login       ║"
echo "║  SAML SSO:       http://localhost:8100/auth/saml/login  ║"
echo "║  SAML Metadata:  http://localhost:8100/auth/saml/metadata║"
echo "║  Current User:   http://localhost:8100/auth/me          ║"
echo "║                                                         ║"
echo "║  ── Demo Accounts ────────────────────────────────────  ║"
echo "║  Admin:  admin@agentcost.dev / admin123                 ║"
echo "║  User:   user@agentcost.dev  / user123                  ║"
echo "║                                                         ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "To stop:  docker compose down"
echo "To reset: docker compose down -v"
echo ""

# Publishing to Docker Hub — Setup Guide

## One-Time Setup

### 1. Create Docker Hub Account & Repository

1. Sign up / log in at [hub.docker.com](https://hub.docker.com)
2. Create a repository: `agentcostin/agentcost`
3. Set visibility to **Public**

### 2. Create Docker Hub Access Token

1. Go to [hub.docker.com/settings/security](https://hub.docker.com/settings/security)
2. Click **New Access Token**
3. Name: `github-actions`
4. Permissions: **Read & Write**
5. Copy the token (you won't see it again)

### 3. Add GitHub Repository Secrets

Go to your GitHub repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret Name | Value |
|-------------|-------|
| `DOCKERHUB_USERNAME` | Your Docker Hub username (e.g., `agentcostin`) |
| `DOCKERHUB_TOKEN` | The access token from step 2 |

### 4. Trigger a Build

Either:
- Push a version tag: `git tag v1.2.1 && git push origin v1.2.1`
- Or manually trigger: GitHub → Actions → Docker → Run workflow

### 5. Verify

```bash
# Pull and run
docker pull agentcostin/agentcost:latest
docker run -d -p 8100:8100 -v agentcost_data:/data agentcostin/agentcost:latest

# Seed demo data
curl -X POST http://localhost:8100/api/seed \
  -H "Content-Type: application/json" \
  -d '{"days": 14}'

# Open http://localhost:8100
```

## Demo Deployment (demo.agentcost.in)

### Quick Deploy on Any VPS

```bash
# SSH into your server
ssh user@your-server

# Clone and deploy
git clone https://github.com/agentcostin/agentcost.git
cd agentcost
docker compose -f docker-compose.demo.yml up -d

# Check health
curl http://localhost:8100/api/health
```

### With Caddy Reverse Proxy (HTTPS)

```bash
# Install Caddy
sudo apt install -y caddy

# Configure
echo 'demo.agentcost.in {
  reverse_proxy localhost:8100
}' | sudo tee /etc/caddy/Caddyfile

# Restart
sudo systemctl restart caddy
```

### Recommended VPS Specs

| Provider | Plan | Cost | Notes |
|----------|------|------|-------|
| Hetzner CX22 | 2 vCPU, 4GB RAM | €4.35/mo | Best value |
| DigitalOcean | Basic, 2GB | $12/mo | Easy setup |
| Vultr | 1 vCPU, 2GB | $10/mo | Good latency |

The community edition with SQLite runs comfortably on 2GB RAM.

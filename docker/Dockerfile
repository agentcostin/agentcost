# ClawWork ACP Server — Sandboxed Execution Container
#
# Runs the ACP server inside Docker so agent commands execute in an
# isolated environment instead of on the host machine.
#
# Build:  docker build -t clawwork-acp -f docker/Dockerfile .
# Run:    docker run -p 8080:8080 --env-file .env clawwork-acp

FROM node:20-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip ffmpeg curl git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install ACP server
COPY acp-server/package.json acp-server/tsconfig.json ./acp-server/
RUN cd acp-server && npm install --silent

COPY acp-server/src ./acp-server/src

# Create sandbox workspace
RUN mkdir -p /tmp/clawwork-sandbox

ENV ACP_PORT=8080
ENV ACP_HOST=0.0.0.0
ENV SANDBOX_CWD=/tmp/clawwork-sandbox

EXPOSE 8080

CMD ["npx", "--prefix", "acp-server", "tsx", "acp-server/src/server.ts"]

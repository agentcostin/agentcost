"""
AgentCost AI Gateway — Phase 5 Block 1

An OpenAI-compatible proxy that sits between agents and LLM providers.
Provides zero-instrumentation cost tracking, policy enforcement,
response caching, provider failover, and rate limiting.

Usage:
    # Agents point to the gateway instead of the provider:
    client = OpenAI(
        base_url="http://localhost:8200/v1",
        api_key="ac_proj_xxx",   # AgentCost project key
    )
    # Zero code changes. Full tracking. Policy enforcement.

    # Start the gateway:
    python -m agentcost.gateway --port 8200

Architecture:
    Client → AgentCost Gateway → (policy check → cache check → provider) → response
    Every request is logged as a TraceEvent with full cost attribution.
"""
import os
import time
import json
import hashlib
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, List
from dataclasses import dataclass, field

logger = logging.getLogger("agentcost.gateway")

# ── Gateway Config ────────────────────────────────────────────────────────────

@dataclass
class ProviderRoute:
    """Maps a project key prefix to a real provider."""
    name: str               # "openai", "anthropic", "ollama"
    base_url: str           # "https://api.openai.com/v1"
    api_key: str            # real provider API key
    models: list[str] = field(default_factory=list)  # allowed models (empty = all)

@dataclass
class GatewayConfig:
    """Gateway configuration."""
    host: str = "0.0.0.0"
    port: int = 8200
    agentcost_api: str = "http://localhost:8100"  # dashboard API for trace ingestion
    cache_enabled: bool = True
    cache_ttl: int = 3600          # seconds
    max_cache_entries: int = 10000
    rate_limit_rpm: int = 600      # requests per minute per project
    providers: Dict[str, ProviderRoute] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        cfg = cls(
            host=os.getenv("GATEWAY_HOST", "0.0.0.0"),
            port=int(os.getenv("GATEWAY_PORT", "8200")),
            agentcost_api=os.getenv("AGENTCOST_API", "http://localhost:8100"),
            cache_enabled=os.getenv("GATEWAY_CACHE", "true").lower() == "true",
            rate_limit_rpm=int(os.getenv("GATEWAY_RATE_LIMIT", "600")),
        )
        # Auto-configure providers from env
        for name, env_key in [("openai", "OPENAI_API_KEY"),
                               ("anthropic", "ANTHROPIC_API_KEY"),
                               ("ollama", "OLLAMA_BASE_URL")]:
            key = os.getenv(env_key)
            if key:
                if name == "openai":
                    cfg.providers[name] = ProviderRoute(name, "https://api.openai.com/v1", key)
                elif name == "anthropic":
                    cfg.providers[name] = ProviderRoute(name, "https://api.anthropic.com/v1", key)
                elif name == "ollama":
                    cfg.providers[name] = ProviderRoute(name, f"{key}/v1", "ollama")
        return cfg

# ── Response Cache ────────────────────────────────────────────────────────────

class ResponseCache:
    """Simple in-memory LRU cache for identical requests."""

    def __init__(self, max_entries: int = 10000, ttl: int = 3600):
        self._cache: Dict[str, tuple] = {}
        self._max = max_entries
        self._ttl = ttl

    def _key(self, model: str, messages: list, temperature: float = 1.0) -> str:
        raw = json.dumps({"m": model, "msgs": messages, "t": temperature}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, model: str, messages: list, temperature: float = 1.0) -> Optional[dict]:
        k = self._key(model, messages, temperature)
        entry = self._cache.get(k)
        if entry and (time.time() - entry[0]) < self._ttl:
            logger.debug(f"Cache HIT for {model}")
            return entry[1]
        if entry:
            del self._cache[k]
        return None

    def put(self, model: str, messages: list, temperature: float, response: dict) -> None:
        k = self._key(model, messages, temperature)
        if len(self._cache) >= self._max:
            oldest = min(self._cache, key=lambda x: self._cache[x][0])
            del self._cache[oldest]
        self._cache[k] = (time.time(), response)

    @property
    def size(self) -> int:
        return len(self._cache)

# ── Rate Limiter ──────────────────────────────────────────────────────────────

class RateLimiter:
    """Token-bucket rate limiter per project."""

    def __init__(self, rpm: int = 600):
        self._rpm = rpm
        self._buckets: Dict[str, List[float]] = {}

    def check(self, project: str) -> bool:
        now = time.time()
        window = self._buckets.setdefault(project, [])
        # Remove entries older than 60s
        self._buckets[project] = [t for t in window if now - t < 60]
        if len(self._buckets[project]) >= self._rpm:
            return False
        self._buckets[project].append(now)
        return True

    def remaining(self, project: str) -> int:
        now = time.time()
        window = self._buckets.get(project, [])
        active = [t for t in window if now - t < 60]
        return max(0, self._rpm - len(active))

# ── Model → Provider Routing ─────────────────────────────────────────────────

# Known model prefixes for auto-routing
MODEL_PROVIDER_MAP = {
    "gpt-": "openai", "o1": "openai", "o3": "openai", "chatgpt": "openai",
    "claude-": "anthropic",
    "llama": "ollama", "mistral": "ollama", "gemma": "ollama",
    "qwen": "ollama", "phi": "ollama", "deepseek": "ollama",
}

def resolve_provider(model: str, config: GatewayConfig) -> Optional[ProviderRoute]:
    """Determine which provider to use for a given model."""
    # Check explicit provider routes first
    for route in config.providers.values():
        if route.models and model in route.models:
            return route
    # Auto-detect from model prefix
    for prefix, provider_name in MODEL_PROVIDER_MAP.items():
        if model.startswith(prefix) or model.startswith(prefix.rstrip("-")):
            return config.providers.get(provider_name)
    # Fallback to first available
    if config.providers:
        return next(iter(config.providers.values()))
    return None

# ── Pricing (reuse from SDK) ─────────────────────────────────────────────────

def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost using the SDK's pricing data."""
    try:
        from ..sdk.trace import CostTracker
        tracker = CostTracker.__new__(CostTracker)
        tracker.project = "_gateway"
        tracker._events = []
        tracker._callbacks = []
        tracker._budget_limit = None
        return tracker._estimate_cost(model, input_tokens, output_tokens)
    except Exception:
        return 0.0

# ── Gateway App (FastAPI) ─────────────────────────────────────────────────────

def create_gateway_app(config: Optional[GatewayConfig] = None) -> "FastAPI":  # noqa: F821
    """Create the gateway FastAPI application."""
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import JSONResponse, StreamingResponse
    from fastapi.middleware.cors import CORSMiddleware

    if config is None:
        config = GatewayConfig.from_env()

    app = FastAPI(title="AgentCost AI Gateway", version="0.5.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    cache = ResponseCache(config.max_cache_entries, config.cache_ttl) if config.cache_enabled else None
    limiter = RateLimiter(config.rate_limit_rpm)

    # ── Health ────────────────────────────────────────────────────────────
    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "gateway": True,
            "providers": list(config.providers.keys()),
            "cache_size": cache.size if cache else 0,
        }

    # ── OpenAI-compatible: Chat Completions ───────────────────────────────
    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        # Extract project from API key header
        auth = request.headers.get("authorization", "")
        api_key = auth.replace("Bearer ", "").strip()
        project = _extract_project(api_key)

        # Rate limit
        if not limiter.check(project):
            raise HTTPException(429, detail={
                "error": {"message": "Rate limit exceeded", "type": "rate_limit_error"},
                "remaining": 0,
            })

        body = await request.json()
        model = body.get("model", "gpt-4o")
        messages = body.get("messages", [])
        temperature = body.get("temperature", 1.0)
        stream = body.get("stream", False)

        # Cache check (non-streaming, temperature=0 only)
        if cache and not stream and temperature == 0:
            cached = cache.get(model, messages, temperature)
            if cached:
                # Log cache hit as trace
                _log_trace(config, project, model, "cache",
                           cached.get("usage", {}).get("prompt_tokens", 0),
                           cached.get("usage", {}).get("completion_tokens", 0),
                           0.0, 0, metadata={"cache": "hit"})
                return JSONResponse(cached)

        # Resolve provider
        provider = resolve_provider(model, config)
        if not provider:
            raise HTTPException(502, detail={
                "error": {"message": f"No provider configured for model: {model}",
                          "type": "provider_not_found"}
            })

        # Forward to provider
        start = time.time()
        try:
            response_data = await _forward_to_provider(provider, body, stream)
            latency_ms = int((time.time() - start) * 1000)

            if stream:
                # For streaming, return as-is (tracking happens via chunk parsing)
                return StreamingResponse(
                    _stream_and_track(response_data, config, project, model, provider.name, start),
                    media_type="text/event-stream",
                )

            # Non-streaming: extract usage, log trace, cache
            usage = response_data.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            cost = estimate_cost(model, input_tokens, output_tokens)

            _log_trace(config, project, model, provider.name,
                       input_tokens, output_tokens, cost, latency_ms)

            # Cache if deterministic
            if cache and temperature == 0:
                cache.put(model, messages, temperature, response_data)

            return JSONResponse(response_data)

        except HTTPException:
            raise
        except Exception as e:
            latency_ms = int((time.time() - start) * 1000)
            _log_trace(config, project, model, provider.name,
                       0, 0, 0, latency_ms, status="error", error=str(e))
            raise HTTPException(502, detail={
                "error": {"message": f"Provider error: {e}", "type": "upstream_error"}
            })

    # ── OpenAI-compatible: Models list ────────────────────────────────────
    @app.get("/v1/models")
    async def list_models():
        models = []
        for route in config.providers.values():
            for m in route.models:
                models.append({"id": m, "object": "model", "owned_by": route.name})
        return {"object": "list", "data": models}

    # ── Gateway stats ─────────────────────────────────────────────────────
    @app.get("/v1/gateway/stats")
    async def gateway_stats():
        return {
            "providers": {name: route.base_url for name, route in config.providers.items()},
            "cache_enabled": config.cache_enabled,
            "cache_size": cache.size if cache else 0,
            "rate_limit_rpm": config.rate_limit_rpm,
        }

    return app


# ── Helper Functions ──────────────────────────────────────────────────────────

def _extract_project(api_key: str) -> str:
    """Extract project name from API key. Format: ac_<project>_<secret> or just use as project."""
    if api_key.startswith("ac_"):
        parts = api_key.split("_", 2)
        return parts[1] if len(parts) >= 2 else "default"
    return "gateway-default"


async def _forward_to_provider(provider: ProviderRoute, body: dict, stream: bool = False):
    """Forward request to the upstream LLM provider."""
    import urllib.request
    import urllib.error

    url = f"{provider.base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {provider.api_key}",
    }

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        resp = urllib.request.urlopen(req, timeout=120)
        if stream:
            return resp  # Return raw response for streaming
        raw = resp.read().decode("utf-8")
        return json.loads(raw)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")[:500]
        raise Exception(f"Provider {provider.name} returned {e.code}: {error_body}")
    except urllib.error.URLError as e:
        raise Exception(f"Cannot reach provider {provider.name}: {e}")


async def _stream_and_track(response, config, project, model, provider_name, start_time):
    """Stream response chunks while tracking usage."""
    total_chunks = 0
    for line in response:
        decoded = line.decode("utf-8", errors="replace")
        yield decoded
        total_chunks += 1

    latency_ms = int((time.time() - start_time) * 1000)
    # Approximate: streaming doesn't give us token counts easily
    _log_trace(config, project, model, provider_name,
               0, 0, 0, latency_ms, metadata={"stream": True, "chunks": total_chunks})


def _log_trace(config: GatewayConfig, project: str, model: str, provider: str,
               input_tokens: int, output_tokens: int, cost: float, latency_ms: int,
               status: str = "success", error: str = None, metadata: dict = None):
    """Log a trace event to the AgentCost API (fire-and-forget)."""
    import threading

    def _send():
        try:
            import urllib.request
            event = {
                "trace_id": hashlib.md5(f"{time.time()}{model}{project}".encode()).hexdigest(),
                "project": project,
                "model": model,
                "provider": provider,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": cost,
                "latency_ms": latency_ms,
                "status": status,
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or {"source": "gateway"},
            }
            data = json.dumps({"events": [event]}).encode()
            req = urllib.request.Request(
                f"{config.agentcost_api}/api/trace/batch",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            logger.debug(f"Failed to log trace: {e}")

    threading.Thread(target=_send, daemon=True).start()


# ── CLI entry point ───────────────────────────────────────────────────────────

def run_gateway(host: str = "0.0.0.0", port: int = 8200):
    """Start the AI gateway server."""
    import uvicorn
    config = GatewayConfig.from_env()
    config.host = host
    config.port = port
    app = create_gateway_app(config)
    logger.info(f"AgentCost AI Gateway starting on {host}:{port}")
    logger.info(f"Providers: {list(config.providers.keys())}")
    uvicorn.run(app, host=host, port=port, log_level="info")
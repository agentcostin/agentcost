"""
Tracked LLM Provider — wraps any LLM API with automatic cost tracking.

Supports:
  - OpenAI (direct)
  - Anthropic (direct)
  - LiteLLM SDK (100+ providers via litellm.completion())
  - LiteLLM Proxy (virtual keys via OpenAI-compatible proxy endpoint)
  - Any OpenAI-compatible API (via base_url)

Intercepts token usage and calculates cost per call.
"""

from __future__ import annotations
import os
import time
from dataclasses import dataclass, field
from typing import Any

# ── Pricing per 1M tokens (early 2026 — update as needed) ───────────────────

MODEL_PRICING: dict[str, dict[str, float]] = {
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "o1": {"input": 15.00, "output": 60.00},
    "o1-mini": {"input": 3.00, "output": 12.00},
    "o3-mini": {"input": 1.10, "output": 4.40},
    # Anthropic
    "claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
    # Google
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    # Deepseek
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
    # Meta / Llama (typical hosted pricing)
    "meta-llama/llama-3.1-70b-instruct": {"input": 0.35, "output": 0.40},
    "meta-llama/llama-3.1-8b-instruct": {"input": 0.05, "output": 0.08},
    # Mistral
    "mistral/mistral-large-latest": {"input": 2.00, "output": 6.00},
    "mistral/mistral-small-latest": {"input": 0.20, "output": 0.60},
    # Groq
    "groq/llama-3.1-70b-versatile": {"input": 0.59, "output": 0.79},
    "groq/llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
    # Together AI
    "together_ai/meta-llama/Llama-3.1-70B-Instruct-Turbo": {
        "input": 0.54,
        "output": 0.54,
    },
    # Ollama / Local models — $0 API cost (compute is your own hardware)
    # Users can override with custom pricing via AGENTCOST_OLLAMA_PRICING env
    "llama3.2": {"input": 0.00, "output": 0.00},
    "llama3.1": {"input": 0.00, "output": 0.00},
    "llama3": {"input": 0.00, "output": 0.00},
    "llama2": {"input": 0.00, "output": 0.00},
    "mistral": {"input": 0.00, "output": 0.00},
    "mixtral": {"input": 0.00, "output": 0.00},
    "gemma2": {"input": 0.00, "output": 0.00},
    "gemma": {"input": 0.00, "output": 0.00},
    "phi3": {"input": 0.00, "output": 0.00},
    "phi4": {"input": 0.00, "output": 0.00},
    "qwen2.5": {"input": 0.00, "output": 0.00},
    "qwen2": {"input": 0.00, "output": 0.00},
    "codellama": {"input": 0.00, "output": 0.00},
    "deepseek-coder-v2": {"input": 0.00, "output": 0.00},
    "starcoder2": {"input": 0.00, "output": 0.00},
    "nomic-embed-text": {"input": 0.00, "output": 0.00},
    # Default fallback
    "_default": {"input": 2.50, "output": 10.00},
}


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class LLMCallResult:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    latency_ms: float
    raw_response: Any = None


@dataclass
class UsageAccumulator:
    """Tracks cumulative usage across multiple calls."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0
    total_calls: int = 0
    calls: list[dict] = field(default_factory=list)

    def record(self, result: LLMCallResult):
        self.total_input_tokens += result.input_tokens
        self.total_output_tokens += result.output_tokens
        self.total_cost += result.cost
        self.total_calls += 1
        self.calls.append(
            {
                "model": result.model,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cost": result.cost,
                "latency_ms": result.latency_ms,
            }
        )

    def reset(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0
        self.total_calls = 0
        self.calls = []


# ── Pricing helpers ──────────────────────────────────────────────────────────


def get_pricing(model: str) -> dict[str, float]:
    """Look up pricing for a model, with fuzzy matching."""
    # Check custom Ollama pricing from env: AGENTCOST_OLLAMA_PRICING="0.01,0.02" (input,output per 1M)
    _ollama_override = os.environ.get("AGENTCOST_OLLAMA_PRICING")
    if _ollama_override and _is_ollama_model(model):
        try:
            parts = _ollama_override.split(",")
            return {
                "input": float(parts[0]),
                "output": float(parts[1]) if len(parts) > 1 else float(parts[0]),
            }
        except (ValueError, IndexError):
            pass

    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    # Strip common LiteLLM prefixes for matching
    stripped = model
    for prefix in (
        "openai/",
        "anthropic/",
        "groq/",
        "together_ai/",
        "mistral/",
        "bedrock/",
        "vertex_ai/",
        "azure/",
        "ollama/",
        "huggingface/",
        "replicate/",
        "cohere/",
        "deepseek/",
        "fireworks_ai/",
        "anyscale/",
    ):
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix) :]
            break
    if stripped in MODEL_PRICING:
        return MODEL_PRICING[stripped]
    # Strip Ollama tags like ":7b", ":latest", ":13b-instruct-q4_0"
    base_model = stripped.split(":")[0] if ":" in stripped else stripped
    if base_model in MODEL_PRICING:
        return MODEL_PRICING[base_model]
    # Fuzzy: check if a known key is a substring
    for key in MODEL_PRICING:
        if key != "_default" and (key in model or model in key):
            return MODEL_PRICING[key]
    # If it looks like an Ollama model (no slash, no known cloud prefix), assume local → $0
    if _is_ollama_model(model):
        return {"input": 0.00, "output": 0.00}
    return MODEL_PRICING["_default"]


def _is_ollama_model(model: str) -> bool:
    """Heuristic: detect models that are likely served by Ollama (local, no cloud prefix)."""
    cloud_prefixes = (
        "gpt-",
        "claude-",
        "gemini-",
        "o1",
        "o3",
        "openai/",
        "anthropic/",
        "groq/",
        "together",
        "mistral/",
        "bedrock/",
        "vertex_ai/",
        "azure/",
    )
    m = model.lower()
    return not any(m.startswith(p) for p in cloud_prefixes)


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = get_pricing(model)
    return (
        input_tokens * pricing["input"] + output_tokens * pricing["output"]
    ) / 1_000_000


def _try_litellm_cost(
    model: str, input_tokens: int, output_tokens: int
) -> float | None:
    """Try to use LiteLLM's built-in cost calculation (has 300+ models)."""
    try:
        import litellm

        cost = litellm.completion_cost(
            model=model,
            prompt=str(input_tokens),
            completion=str(output_tokens),
        )
        if cost and cost > 0:
            return cost
    except Exception:
        pass
    return None


# ── Provider ─────────────────────────────────────────────────────────────────


class TrackedProvider:
    """
    Wraps LLM APIs with automatic cost tracking.

    Supported providers:
      - "openai"    → direct OpenAI SDK
      - "anthropic" → direct Anthropic SDK
      - "ollama"    → local Ollama instance (OpenAI-compatible API)
      - "litellm"   → LiteLLM SDK (100+ providers, auto-routes by model prefix)
      - "proxy"     → LiteLLM Proxy / any OpenAI-compatible endpoint (virtual keys)

    Usage::

        # Direct OpenAI
        provider = TrackedProvider(model="gpt-4o")

        # Direct Anthropic
        provider = TrackedProvider(model="claude-sonnet-4-5-20250929", provider="anthropic")

        # Local Ollama
        provider = TrackedProvider(model="llama3.2", provider="ollama")
        provider = TrackedProvider(model="mistral:7b", provider="ollama",
                                   base_url="http://gpu-server:11434")

        # LiteLLM SDK — any supported model, auto-routed
        provider = TrackedProvider(model="groq/llama-3.1-70b-versatile", provider="litellm")

        # LiteLLM Proxy with virtual key
        provider = TrackedProvider(
            model="gpt-4o",
            provider="proxy",
            base_url="http://localhost:4000",
            api_key="sk-virtual-key-123",
        )

        result = provider.chat("Summarize this document...")
        print(f"Cost: ${result.cost:.4f}")
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        provider: str = "openai",
        verify_ssl: bool = True,
    ):
        self.model = model
        self.provider_name = provider
        self.base_url = base_url
        self.verify_ssl = verify_ssl
        self.usage = UsageAccumulator()
        self._use_litellm_sdk = provider == "litellm"
        self._litellm = None

        # ── Ollama (local LLM via OpenAI-compatible API) ─────────────
        if provider == "ollama":
            import openai

            ollama_url = base_url or os.environ.get(
                "OLLAMA_HOST", "http://10.166.73.108:11434"
            )
            # Ollama serves OpenAI-compatible API at /v1
            if not ollama_url.rstrip("/").endswith("/v1"):
                ollama_url = ollama_url.rstrip("/") + "/v1"
            # Ollama doesn't need a real API key but the SDK requires one
            self._client = openai.OpenAI(
                api_key=api_key or "ollama",
                base_url=ollama_url,
            )
            self.provider_name = "ollama"

        elif provider == "anthropic":
            import anthropic

            kwargs_a: dict[str, Any] = {
                "api_key": api_key or os.environ.get("ANTHROPIC_API_KEY"),
            }
            if not verify_ssl:
                import httpx as _httpx

                kwargs_a["http_client"] = _httpx.Client(verify=False)
            self._client = anthropic.Anthropic(**kwargs_a)

        elif provider == "litellm":
            try:
                import litellm

                self._litellm = litellm
                litellm.suppress_debug_info = True
                litellm.drop_params = True  # auto-drop unsupported params per model
                if not verify_ssl:
                    litellm.ssl_verify = False
                    os.environ["SSL_VERIFY"] = "false"
                    os.environ["LITELLM_SSL_VERIFY"] = "false"
                if api_key:
                    self._set_litellm_key(model, api_key)
                self._client = None
            except ImportError:
                raise ImportError("litellm not installed. Run: pip install litellm")

        elif provider == "proxy":
            import openai
            import httpx as _httpx

            proxy_url = base_url or os.environ.get(
                "LITELLM_PROXY_URL", "http://localhost:4000"
            )
            proxy_key = api_key or os.environ.get("LITELLM_API_KEY", "")
            if not proxy_url.rstrip("/").endswith("/v1"):
                proxy_url = proxy_url.rstrip("/") + "/v1"

            # Corporate gateways often use internal CAs that Python doesn't trust.
            # Pass a custom httpx client with SSL verification control.
            http_client = _httpx.Client(
                verify=verify_ssl,
                timeout=_httpx.Timeout(60.0, connect=10.0),
            )
            self._client = openai.OpenAI(
                api_key=proxy_key,
                base_url=proxy_url,
                http_client=http_client,
            )
            try:
                import litellm

                self._litellm = litellm
                litellm.drop_params = True
            except ImportError:
                pass

        else:
            # OpenAI / OpenAI-compatible
            import openai

            kwargs: dict[str, Any] = {}
            if api_key:
                kwargs["api_key"] = api_key
            if base_url:
                kwargs["base_url"] = base_url
            if not verify_ssl:
                import httpx as _httpx

                kwargs["http_client"] = _httpx.Client(verify=False)
            self._client = openai.OpenAI(**kwargs)

    @staticmethod
    def _set_litellm_key(model: str, api_key: str):
        """Route API key to the right env var based on model prefix."""
        m = model.lower()
        mappings = {
            "anthropic": "ANTHROPIC_API_KEY",
            "claude": "ANTHROPIC_API_KEY",
            "groq": "GROQ_API_KEY",
            "together": "TOGETHERAI_API_KEY",
            "mistral": "MISTRAL_API_KEY",
            "cohere": "COHERE_API_KEY",
            "replicate": "REPLICATE_API_KEY",
            "bedrock": "AWS_ACCESS_KEY_ID",
            "vertex": "GOOGLE_APPLICATION_CREDENTIALS",
            "deepseek": "DEEPSEEK_API_KEY",
            "fireworks": "FIREWORKS_AI_API_KEY",
        }
        for prefix, env_var in mappings.items():
            if prefix in m:
                os.environ.setdefault(env_var, api_key)
                return
        os.environ.setdefault("OPENAI_API_KEY", api_key)

    def _calc_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost, preferring LiteLLM's database when available."""
        if self._litellm:
            lc = _try_litellm_cost(self.model, input_tokens, output_tokens)
            if lc is not None:
                return lc
        return calculate_cost(self.model, input_tokens, output_tokens)

    # Models that use reasoning (o1, o3, gpt-5, etc.) need special handling:
    # - No temperature (or temperature=1 only)
    # - Use max_completion_tokens instead of max_tokens
    # - Need higher token budgets (reasoning eats tokens)
    REASONING_MODEL_PATTERNS = ("o1", "o3", "gpt-5")

    def _is_reasoning_model(self) -> bool:
        m = self.model.lower()
        return any(p in m for p in self.REASONING_MODEL_PATTERNS)

    def chat(
        self,
        prompt: str,
        system: str = "You are a professional AI assistant completing work tasks.",
        temperature: float | None = 0.7,
        max_tokens: int = 4096,
    ) -> LLMCallResult:
        """Send a chat completion and track costs."""
        start = time.time()

        is_reasoning = self._is_reasoning_model()

        # Reasoning models: don't send temperature, use max_completion_tokens,
        # increase budget so there's room for reasoning + actual answer
        if is_reasoning:
            temperature = None
            effective_max = max(max_tokens, 16384)  # reasoning needs headroom
        else:
            effective_max = max_tokens

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        if self._use_litellm_sdk:
            # ── LiteLLM SDK mode ──────────────────────────────────────
            kwargs_l: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
            }
            if is_reasoning:
                kwargs_l["max_completion_tokens"] = effective_max
            else:
                kwargs_l["max_tokens"] = effective_max
            if temperature is not None:
                kwargs_l["temperature"] = temperature
            kwargs_l["drop_params"] = True
            try:
                response = self._litellm.completion(**kwargs_l)
            except Exception as param_err:
                err_lower = str(param_err).lower()
                if "temperature" in err_lower or "unsupported" in err_lower:
                    kwargs_l.pop("temperature", None)
                    # Also try swapping max_tokens ↔ max_completion_tokens
                    if "max_tokens" in err_lower and "max_tokens" in kwargs_l:
                        val = kwargs_l.pop("max_tokens")
                        kwargs_l["max_completion_tokens"] = val
                    response = self._litellm.completion(**kwargs_l)
                else:
                    raise
            content = response.choices[0].message.content or ""
            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0
            raw = response

        elif self.provider_name == "anthropic":
            # ── Anthropic direct ──────────────────────────────────────
            kwargs_a2: dict[str, Any] = {
                "model": self.model,
                "max_tokens": effective_max,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            }
            if temperature is not None:
                kwargs_a2["temperature"] = temperature
            response = self._client.messages.create(**kwargs_a2)
            content = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            raw = response

        else:
            # ── OpenAI / Proxy / OpenAI-compatible ────────────────────
            try:
                kwargs_oai: dict[str, Any] = {
                    "model": self.model,
                    "messages": messages,
                }
                if is_reasoning:
                    kwargs_oai["max_completion_tokens"] = effective_max
                else:
                    kwargs_oai["max_tokens"] = effective_max
                if temperature is not None:
                    kwargs_oai["temperature"] = temperature
                try:
                    response = self._client.chat.completions.create(**kwargs_oai)
                except Exception as param_err:
                    # Retry dropping unsupported params
                    err_lower = str(param_err).lower()
                    if (
                        "temperature" in err_lower
                        or "unsupported" in err_lower
                        or "max_tokens" in err_lower
                    ):
                        kwargs_oai.pop("temperature", None)
                        if "max_tokens" in kwargs_oai:
                            val = kwargs_oai.pop("max_tokens")
                            kwargs_oai["max_completion_tokens"] = val
                        response = self._client.chat.completions.create(**kwargs_oai)
                    else:
                        raise
            except Exception as e:
                str(e)
                # Extract useful info from OpenAI error responses
                if hasattr(e, "status_code"):
                    code = e.status_code
                    if code == 401:
                        raise ConnectionError(
                            f"Authentication failed (HTTP 401). Your API key or virtual key "
                            f"is invalid for {self.base_url or 'OpenAI API'}."
                        ) from e
                    elif code == 404:
                        raise ConnectionError(
                            f"Model '{self.model}' not found (HTTP 404). "
                            f"Check the model name is correct on your proxy/provider."
                        ) from e
                    elif code == 429:
                        raise ConnectionError(
                            "Rate limited (HTTP 429). Wait and retry, or check your "
                            "virtual key's rate/budget limits."
                        ) from e
                    elif code == 500 or code == 502 or code == 503:
                        raise ConnectionError(
                            f"Server error (HTTP {code}) from "
                            f"{self.base_url or 'API'}. The proxy or upstream provider "
                            f"may be down."
                        ) from e
                # Re-raise with the original message if we can't improve it
                raise

            content = response.choices[0].message.content or ""
            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0
            raw = response

        latency = (time.time() - start) * 1000

        # Reasoning models (gpt-5, o1, o3) may return empty content if all tokens
        # went to internal reasoning. Try to extract from alternative fields.
        if (
            not content
            and is_reasoning
            and hasattr(response, "choices")
            and response.choices
        ):
            msg = response.choices[0].message
            # Check common alternative fields used by proxies/APIs
            for attr in ("reasoning_content", "reasoning", "refusal"):
                val = getattr(msg, attr, None)
                if val and isinstance(val, str) and len(val.strip()) > 0:
                    content = val
                    break
            # Check model_extra dict (OpenAI SDK stores unknown fields here)
            if not content and hasattr(msg, "model_extra") and msg.model_extra:
                for key in ("reasoning_content", "content_blocks", "text"):
                    if key in msg.model_extra and msg.model_extra[key]:
                        v = msg.model_extra[key]
                        content = v if isinstance(v, str) else str(v)
                        break
        cost = self._calc_cost(input_tokens, output_tokens)

        result = LLMCallResult(
            content=content,
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            latency_ms=latency,
            raw_response=raw,
        )

        self.usage.record(result)
        return result

    def reset_usage(self):
        self.usage.reset()

    def __repr__(self) -> str:
        return (
            f"TrackedProvider(model={self.model!r}, provider={self.provider_name!r}"
            + (f", base_url={self.base_url!r}" if self.base_url else "")
            + ")"
        )

# Semantic Caching

AgentCost's AI Gateway includes semantic caching — a similarity-based cache that matches requests even when the wording is different. Instead of requiring an identical prompt to get a cache hit, semantic caching recognizes that "What is Python?" and "Tell me about the Python language" are asking the same thing, and returns the cached response.

This reduces LLM costs significantly for support bots, FAQ systems, and any application where users ask similar questions in different words.

## How It Works

When a request arrives at the gateway:

1. **Exact match check** — SHA256 hash lookup, O(1). If the exact same prompt was cached, return it instantly.
2. **Semantic match check** — Compare the request against all cached entries for the same model using word n-gram Jaccard similarity. If the best match exceeds the similarity threshold, return the cached response.
3. **Cache miss** — Forward to the LLM provider, cache the response with its text fingerprint.

```
User: "Explain Python programming"
            │
            ▼
    ┌─ Exact match? ── YES → Return cached response
    │       │
    │      NO
    │       │
    │       ▼
    │  Semantic match? ── SCORE 0.6 > 0.35 threshold
    │       │                      │
    │      YES                    Return cached response
    │       │                    (tagged as "semantic hit")
    │      NO
    │       │
    │       ▼
    └─ Forward to LLM → Cache response → Return
```

## Quick Start

Semantic caching works through the AI Gateway. No code changes needed in your application — just point your LLM client at the gateway.

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8200/v1",
    api_key="ac_myproject_xxx",
)

# First call — goes to OpenAI, response is cached
response = client.chat.completions.create(
    model="gpt-4.1",
    messages=[{"role": "user", "content": "What is Python programming?"}],
    temperature=0,
)

# Second call — different wording, but semantic cache hits
response = client.chat.completions.create(
    model="gpt-4.1",
    messages=[{"role": "user", "content": "Tell me about Python programming"}],
    temperature=0,
)
# → Returns cached response, zero cost, ~0ms latency
```

## Configuration

Configure via environment variables in `docker-compose.yml` or when starting the gateway:

```yaml
environment:
  AGENTCOST_CACHE_TYPE: semantic           # 'exact' or 'semantic' (default: exact)
  AGENTCOST_CACHE_SIMILARITY: "0.5"        # Similarity threshold (0.0-1.0)
  AGENTCOST_CACHE_MAX_ENTRIES: "5000"       # Max cached responses
  AGENTCOST_CACHE_TTL: "3600"              # Cache TTL in seconds
  AGENTCOST_CACHE_TEMP_THRESHOLD: "0.2"    # Max temperature for caching
```

### Similarity Threshold Tuning

The threshold controls how similar two prompts must be to count as a match. The right value depends on your use case:

| Threshold | Behavior | Best for |
|-----------|----------|----------|
| **0.3** | Aggressive matching, more hits, higher risk of wrong answers | FAQ bots with narrow topics |
| **0.5** | Balanced — good default for most applications | General purpose |
| **0.7** | Conservative, fewer hits but very high precision | Code generation, technical queries |

## Embedding Backends

AgentCost supports two embedding backends:

### N-gram Jaccard (default, zero dependencies)

Uses word n-gram shingling with Jaccard similarity. Fast, no external dependencies, works well for typical LLM prompts. This is the default backend.

Strengths: zero setup, fast, no API costs. Weaknesses: purely lexical — misses synonyms ("car" vs "automobile").

### Sentence Transformers (optional, higher quality)

If `sentence-transformers` is installed, AgentCost automatically upgrades to dense embeddings using the `all-MiniLM-L6-v2` model. This captures semantic meaning beyond word overlap.

```bash
pip install sentence-transformers
```

When dense embeddings are active, the similarity threshold is automatically adjusted (Jaccard scores are typically lower than cosine scores).

## Monitoring

Check cache performance via the stats endpoint:

```bash
curl http://localhost:8200/v1/gateway/cache/stats
```

```json
{
  "total_hits": 1247,
  "total_misses": 523,
  "exact_hits": 890,
  "semantic_hits": 357,
  "hit_rate_pct": 70.45,
  "semantic_hit_rate_pct": 20.17,
  "total_cost_saved": 12.340000,
  "entries": 2100,
  "similarity_threshold": 0.5,
  "embedding_backend": "n-gram-jaccard",
  "avg_similarity_score": 0.412
}
```

Key metrics to watch:

- **semantic_hit_rate_pct**: If this is 0%, your users are asking unique questions (or threshold is too high). If it's very high, consider lowering the threshold may be returning incorrect cached responses.
- **avg_similarity_score**: Shows the average similarity of the best match found during lookups. If this is consistently just below your threshold, consider lowering the threshold slightly.

## How It Compares

| Feature | AgentCost | Helicone |
|---------|-----------|----------|
| Exact-match cache | ✅ | ✅ |
| Semantic cache | ✅ N-gram + optional dense embeddings | ✅ Embedding-based |
| Self-hosted | ✅ Fully local, zero API calls | ❌ Cloud-only |
| Cache stats | ✅ Per-project, per-model breakdown | ✅ |
| Cost saved tracking | ✅ Automatic | ✅ |
| Air-gapped support | ✅ Works offline | ❌ |

AgentCost's semantic cache runs entirely locally with zero external dependencies. No embedding API calls, no cloud services — your prompts never leave your infrastructure.

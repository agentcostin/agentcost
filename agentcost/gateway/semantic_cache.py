"""
AgentCost Semantic Cache — similarity-based caching for LLM responses.

Unlike exact-match caching (which only hits on identical requests), semantic
caching matches requests that are similar — "What is Python?" will match
a cached response for "Tell me about the Python language."

Uses word n-gram shingling with Jaccard similarity — zero external
dependencies, works well even with a single cached entry, and handles
the short-text queries typical of LLM prompts.

If sentence-transformers is installed, automatically upgrades to dense
embeddings for higher-quality matching.

Usage:
    from agentcost.gateway.semantic_cache import SemanticCache

    cache = SemanticCache(similarity_threshold=0.85)
    cache.put(model, messages, temperature, response)
    result = cache.get(model, messages, temperature)
    if result:
        response, hit_type = result  # hit_type = 'exact' or 'semantic'
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger("agentcost.gateway.semantic_cache")


# ── Text Processing ──────────────────────────────────────────────────────────


_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "can",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "between",
        "out",
        "off",
        "over",
        "under",
        "again",
        "then",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "all",
        "each",
        "both",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "not",
        "only",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "but",
        "and",
        "or",
        "if",
        "that",
        "this",
        "it",
        "its",
        "my",
        "your",
        "his",
        "her",
        "our",
        "their",
        "what",
        "which",
        "who",
        "i",
        "me",
        "we",
        "you",
        "he",
        "she",
        "they",
        "them",
        "about",
        "up",
        "please",
        "tell",
        "explain",
        "describe",
        "give",
    }
)


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful words (remove stopwords)."""
    words = _normalize(text).split()
    return [w for w in words if w not in _STOPWORDS and len(w) > 1]


def _word_ngrams(text: str, n: int = 2) -> Set[str]:
    """Generate word n-gram shingles from text.

    For "python programming language tutorial":
      unigrams: {python, programming, language, tutorial}
      bigrams:  {python_programming, programming_language, language_tutorial}

    Combining unigrams + bigrams gives good balance of precision and recall.
    """
    keywords = _extract_keywords(text)
    if not keywords:
        return set()

    shingles = set(keywords)  # unigrams always included
    for i in range(len(keywords) - n + 1):
        shingles.add("_".join(keywords[i : i + n]))
    return shingles


def _messages_to_text(messages: list) -> str:
    """Extract text content from chat messages."""
    parts = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
    return " ".join(parts)


def jaccard_similarity(a: Set[str], b: Set[str]) -> float:
    """Jaccard similarity = |A ∩ B| / |A ∪ B|."""
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union > 0 else 0.0


# ── Optional: Dense Embeddings ───────────────────────────────────────────────


_sentence_model = None
_sentence_model_checked = False


def _get_sentence_model():
    """Lazy-load sentence-transformers if available."""
    global _sentence_model, _sentence_model_checked
    if _sentence_model_checked:
        return _sentence_model
    _sentence_model_checked = True
    try:
        from sentence_transformers import SentenceTransformer

        _sentence_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Semantic cache: using sentence-transformers for embeddings")
    except ImportError:
        logger.debug("sentence-transformers not installed, using n-gram shingling")
    return _sentence_model


def _dense_similarity(text1: str, text2: str) -> float:
    """Compute cosine similarity using dense embeddings."""
    model = _get_sentence_model()
    if not model:
        return -1.0  # signal to fall back

    embeddings = model.encode([text1, text2])
    # Cosine similarity
    a, b = embeddings[0], embeddings[1]
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Semantic Cache Entry ─────────────────────────────────────────────────────


class SemanticCacheEntry:
    __slots__ = (
        "key",
        "model",
        "shingles",
        "text",
        "response",
        "timestamp",
        "embedding",
    )

    def __init__(
        self,
        key: str,
        model: str,
        shingles: Set[str],
        text: str,
        response: dict,
        timestamp: float,
        embedding=None,
    ):
        self.key = key
        self.model = model
        self.shingles = shingles
        self.text = text
        self.response = response
        self.timestamp = timestamp
        self.embedding = embedding  # dense vector, if available


# ── Semantic Cache ───────────────────────────────────────────────────────────


class SemanticCache:
    """Similarity-based LLM response cache.

    Lookup order:
        1. Exact-match (SHA256 hash) → instant, O(1)
        2. Semantic match (n-gram Jaccard or dense cosine) → O(n) per model

    Args:
        similarity_threshold: Minimum similarity for a semantic hit (0.0–1.0).
            For Jaccard (default): 0.4–0.6 is good (Jaccard scores are lower than cosine).
            For dense embeddings: 0.80–0.90 is good.
        max_entries: Maximum cached entries before eviction.
        ttl: Time-to-live in seconds.
        temp_threshold: Max temperature for cacheable requests.
        use_dense: Try to use sentence-transformers if available.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.5,
        max_entries: int = 5000,
        ttl: int = 3600,
        temp_threshold: float = 0.2,
        use_dense: bool = True,
    ):
        self._entries: Dict[str, SemanticCacheEntry] = {}
        self._model_index: Dict[str, List[str]] = {}
        self._similarity_threshold = similarity_threshold
        self._max_entries = max_entries
        self._ttl = ttl
        self._temp_threshold = temp_threshold
        self._use_dense = use_dense and _get_sentence_model() is not None

        # Auto-adjust threshold for dense embeddings (cosine scores higher)
        if self._use_dense and similarity_threshold <= 0.6:
            self._similarity_threshold = 0.85
            logger.info(
                "Dense embeddings active — auto-adjusted threshold to %.2f",
                self._similarity_threshold,
            )

        # Stats
        self.exact_hits: int = 0
        self.semantic_hits: int = 0
        self.misses: int = 0
        self.total_cost_saved: float = 0.0
        self.total_latency_saved_ms: int = 0
        self._per_project: Dict[str, dict] = {}
        self._per_model: Dict[str, dict] = {}
        self._similarity_scores: list[float] = []
        self._started_at: float = time.time()

    def is_cacheable(self, temperature: float, stream: bool) -> bool:
        return not stream and temperature <= self._temp_threshold

    def get(
        self,
        model: str,
        messages: list,
        temperature: float = 1.0,
        tools: list = None,
    ) -> Optional[Tuple[dict, str]]:
        """Look up cache. Returns (response, hit_type) or None.

        hit_type: 'exact' or 'semantic'.
        """
        now = time.time()
        exact_key = self._exact_key(model, messages, temperature, tools)

        # 1. Exact match (O(1))
        entry = self._entries.get(exact_key)
        if entry and (now - entry.timestamp) < self._ttl:
            self.exact_hits += 1
            return (entry.response, "exact")
        elif entry:
            self._remove_entry(exact_key)

        # 2. Semantic match (O(n) within same model)
        text = _messages_to_text(messages)
        query_shingles = _word_ngrams(text)
        if not query_shingles:
            self.misses += 1
            return None

        best_score = 0.0
        best_entry: Optional[SemanticCacheEntry] = None

        model_keys = list(self._model_index.get(model, []))
        for key in model_keys:
            candidate = self._entries.get(key)
            if not candidate:
                continue
            if (now - candidate.timestamp) >= self._ttl:
                self._remove_entry(key)
                continue

            # Compute similarity
            if self._use_dense and candidate.embedding is not None:
                score = _dense_similarity(text, candidate.text)
                if score < 0:
                    score = jaccard_similarity(query_shingles, candidate.shingles)
            else:
                score = jaccard_similarity(query_shingles, candidate.shingles)

            if score > best_score:
                best_score = score
                best_entry = candidate

        # Track scores for monitoring
        self._similarity_scores.append(best_score)
        if len(self._similarity_scores) > 200:
            self._similarity_scores.pop(0)

        if best_score >= self._similarity_threshold and best_entry:
            self.semantic_hits += 1
            logger.debug(
                "Semantic HIT: score=%.3f model=%s text='%s' matched='%s'",
                best_score,
                model,
                text[:60],
                best_entry.text[:60],
            )
            return (best_entry.response, "semantic")

        self.misses += 1
        return None

    def put(
        self,
        model: str,
        messages: list,
        temperature: float,
        response: dict,
        tools: list = None,
    ) -> None:
        """Store a response with its shingles (and dense embedding if available)."""
        text = _messages_to_text(messages)
        if not text.strip():
            return

        exact_key = self._exact_key(model, messages, temperature, tools)

        if len(self._entries) >= self._max_entries:
            self._evict_oldest()

        shingles = _word_ngrams(text)

        # Dense embedding (optional)
        embedding = None
        if self._use_dense:
            model_inst = _get_sentence_model()
            if model_inst:
                try:
                    embedding = model_inst.encode(text)
                except Exception:
                    pass

        entry = SemanticCacheEntry(
            key=exact_key,
            model=model,
            shingles=shingles,
            text=text[:500],
            response=response,
            timestamp=time.time(),
            embedding=embedding,
        )
        self._entries[exact_key] = entry
        self._model_index.setdefault(model, []).append(exact_key)

    def record_hit(
        self,
        project: str,
        model: str,
        cost_saved: float,
        latency_saved_ms: int = 0,
    ) -> None:
        """Record stats for a cache hit (called by gateway)."""
        self.total_cost_saved += cost_saved
        self.total_latency_saved_ms += latency_saved_ms
        ps = self._per_project.setdefault(
            project, {"hits": 0, "misses": 0, "cost_saved": 0.0}
        )
        ps["hits"] += 1
        ps["cost_saved"] += cost_saved
        ms = self._per_model.setdefault(
            model, {"hits": 0, "misses": 0, "cost_saved": 0.0}
        )
        ms["hits"] += 1
        ms["cost_saved"] += cost_saved

    def record_miss(self, project: str, model: str) -> None:
        ps = self._per_project.setdefault(
            project, {"hits": 0, "misses": 0, "cost_saved": 0.0}
        )
        ps["misses"] += 1
        ms = self._per_model.setdefault(
            model, {"hits": 0, "misses": 0, "cost_saved": 0.0}
        )
        ms["misses"] += 1

    def clear(self) -> int:
        count = len(self._entries)
        self._entries.clear()
        self._model_index.clear()
        return count

    @property
    def size(self) -> int:
        return len(self._entries)

    def to_dict(self) -> dict:
        """Full stats for the /cache/stats endpoint."""
        total_lookups = self.exact_hits + self.semantic_hits + self.misses
        return {
            "total_hits": self.exact_hits + self.semantic_hits,
            "total_misses": self.misses,
            "exact_hits": self.exact_hits,
            "semantic_hits": self.semantic_hits,
            "hit_rate_pct": round(
                (self.exact_hits + self.semantic_hits) / total_lookups * 100, 2
            )
            if total_lookups > 0
            else 0,
            "semantic_hit_rate_pct": round(self.semantic_hits / total_lookups * 100, 2)
            if total_lookups > 0
            else 0,
            "total_cost_saved": round(self.total_cost_saved, 6),
            "total_latency_saved_ms": self.total_latency_saved_ms,
            "entries": self.size,
            "max_entries": self._max_entries,
            "ttl_seconds": self._ttl,
            "temp_threshold": self._temp_threshold,
            "similarity_threshold": self._similarity_threshold,
            "embedding_backend": "sentence-transformers"
            if self._use_dense
            else "n-gram-jaccard",
            "avg_similarity_score": round(
                sum(self._similarity_scores) / len(self._similarity_scores), 3
            )
            if self._similarity_scores
            else 0,
            "uptime_seconds": int(time.time() - self._started_at),
            "by_project": {
                k: {**v, "cost_saved": round(v["cost_saved"], 6)}
                for k, v in self._per_project.items()
            },
            "by_model": {
                k: {**v, "cost_saved": round(v["cost_saved"], 6)}
                for k, v in sorted(
                    self._per_model.items(),
                    key=lambda x: x[1]["cost_saved"],
                    reverse=True,
                )[:20]
            },
        }

    def reset_stats(self) -> None:
        self.exact_hits = 0
        self.semantic_hits = 0
        self.misses = 0
        self.total_cost_saved = 0.0
        self.total_latency_saved_ms = 0
        self._per_project.clear()
        self._per_model.clear()
        self._similarity_scores.clear()
        self._started_at = time.time()

    # ── Internal ──────────────────────────────────────────────────

    def _exact_key(self, model, messages, temperature, tools=None) -> str:
        raw = json.dumps(
            {
                "m": model,
                "msgs": messages,
                "t": round(temperature, 2),
                "tools": tools or [],
            },
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def _remove_entry(self, key: str) -> None:
        entry = self._entries.pop(key, None)
        if entry:
            keys = self._model_index.get(entry.model, [])
            try:
                keys.remove(key)
            except ValueError:
                pass

    def _evict_oldest(self) -> None:
        if not self._entries:
            return
        oldest = min(self._entries, key=lambda k: self._entries[k].timestamp)
        self._remove_entry(oldest)

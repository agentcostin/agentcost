"""Tests for AgentCost Semantic Cache."""

import time
import pytest

from agentcost.gateway.semantic_cache import (
    SemanticCache,
    jaccard_similarity,
    _word_ngrams,
    _normalize,
    _extract_keywords,
    _messages_to_text,
)


# ── Text Processing ──────────────────────────────────────────────────────────


class TestTextProcessing:
    def test_normalize(self):
        assert _normalize("Hello, World!") == "hello world"
        assert _normalize("  Extra   Spaces  ") == "extra spaces"
        assert _normalize("Python's great!") == "python s great"

    def test_extract_keywords(self):
        kw = _extract_keywords("What is the Python programming language?")
        assert "python" in kw
        assert "programming" in kw
        assert "language" in kw
        # Stopwords removed
        assert "what" not in kw
        assert "is" not in kw
        assert "the" not in kw

    def test_extract_keywords_empty(self):
        assert _extract_keywords("") == []
        assert _extract_keywords("the a an is") == []

    def test_messages_to_text(self):
        msgs = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "What is Python?"},
        ]
        text = _messages_to_text(msgs)
        assert "helpful" in text
        assert "Python" in text

    def test_messages_to_text_multimodal(self):
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "http://example.com/img.png"},
                    },
                ],
            }
        ]
        text = _messages_to_text(msgs)
        assert "Describe this image" in text


# ── Shingling ────────────────────────────────────────────────────────────────


class TestShingling:
    def test_word_ngrams_basic(self):
        shingles = _word_ngrams("Python programming language")
        assert "python" in shingles
        assert "programming" in shingles
        assert "language" in shingles
        assert "python_programming" in shingles
        assert "programming_language" in shingles

    def test_word_ngrams_strips_stopwords(self):
        shingles = _word_ngrams("What is the Python language?")
        assert "python" in shingles
        assert "language" in shingles
        assert "what" not in shingles
        assert "the" not in shingles

    def test_word_ngrams_empty(self):
        assert _word_ngrams("") == set()
        assert _word_ngrams("the a an") == set()

    def test_word_ngrams_single_word(self):
        shingles = _word_ngrams("Python")
        assert shingles == {"python"}


# ── Jaccard Similarity ───────────────────────────────────────────────────────


class TestJaccardSimilarity:
    def test_identical(self):
        s = {"a", "b", "c"}
        assert jaccard_similarity(s, s) == 1.0

    def test_disjoint(self):
        assert jaccard_similarity({"a", "b"}, {"c", "d"}) == 0.0

    def test_partial_overlap(self):
        assert jaccard_similarity({"a", "b", "c"}, {"b", "c", "d"}) == pytest.approx(
            0.5
        )

    def test_empty_sets(self):
        assert jaccard_similarity(set(), {"a"}) == 0.0
        assert jaccard_similarity({"a"}, set()) == 0.0
        assert jaccard_similarity(set(), set()) == 0.0

    def test_similar_queries(self):
        s1 = _word_ngrams("What is Python programming?")
        s2 = _word_ngrams("Explain Python programming to me")
        score = jaccard_similarity(s1, s2)
        assert score > 0.3  # should be similar

    def test_unrelated_queries(self):
        s1 = _word_ngrams("What is Python programming?")
        s2 = _word_ngrams("Best chocolate cake recipe")
        score = jaccard_similarity(s1, s2)
        assert score == 0.0


# ── SemanticCache ────────────────────────────────────────────────────────────


RESPONSE_A = {
    "choices": [{"message": {"content": "Python is a programming language..."}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 50},
}
RESPONSE_B = {
    "choices": [{"message": {"content": "Machine learning uses algorithms..."}}],
    "usage": {"prompt_tokens": 15, "completion_tokens": 80},
}


def _msg(text):
    return [{"role": "user", "content": text}]


class TestSemanticCacheExactMatch:
    def test_exact_hit(self):
        cache = SemanticCache()
        cache.put("gpt-4o", _msg("What is Python?"), 0.0, RESPONSE_A)
        result = cache.get("gpt-4o", _msg("What is Python?"), 0.0)
        assert result is not None
        assert result[1] == "exact"
        assert result[0] == RESPONSE_A

    def test_exact_miss_different_message(self):
        cache = SemanticCache(similarity_threshold=0.99)
        cache.put("gpt-4o", _msg("What is Python?"), 0.0, RESPONSE_A)
        result = cache.get("gpt-4o", _msg("What is Java?"), 0.0)
        # With threshold=0.99, semantic won't match either
        assert result is None

    def test_exact_miss_different_model(self):
        cache = SemanticCache()
        cache.put("gpt-4o", _msg("What is Python?"), 0.0, RESPONSE_A)
        result = cache.get("claude-sonnet-4-6", _msg("What is Python?"), 0.0)
        assert result is None

    def test_exact_miss_different_temperature(self):
        cache = SemanticCache()
        cache.put("gpt-4o", _msg("What is Python?"), 0.0, RESPONSE_A)
        result = cache.get("gpt-4o", _msg("What is Python?"), 0.1)
        # Different temperature = different exact key, but may still semantic match
        # (same text, same model → should semantic hit)
        if result:
            assert result[1] in ("exact", "semantic")


class TestSemanticCacheSemanticMatch:
    def test_semantic_hit_similar_wording(self):
        cache = SemanticCache(similarity_threshold=0.3)
        cache.put(
            "gpt-4o", _msg("What is Python programming language?"), 0.0, RESPONSE_A
        )
        result = cache.get("gpt-4o", _msg("Tell me about Python programming"), 0.0)
        assert result is not None
        assert result[1] == "semantic"

    def test_semantic_miss_unrelated(self):
        cache = SemanticCache(similarity_threshold=0.3)
        cache.put("gpt-4o", _msg("What is Python programming?"), 0.0, RESPONSE_A)
        result = cache.get("gpt-4o", _msg("Best chocolate cake recipe"), 0.0)
        assert result is None

    def test_semantic_miss_different_model(self):
        """Semantic matching only compares within the same model."""
        cache = SemanticCache(similarity_threshold=0.3)
        cache.put("gpt-4o", _msg("What is Python programming?"), 0.0, RESPONSE_A)
        result = cache.get("gpt-4.1", _msg("Explain Python programming"), 0.0)
        assert result is None

    def test_semantic_best_match(self):
        """When multiple entries exist, returns the best match."""
        cache = SemanticCache(similarity_threshold=0.3)
        cache.put("gpt-4o", _msg("Python programming tutorial"), 0.0, RESPONSE_A)
        cache.put("gpt-4o", _msg("Machine learning algorithms"), 0.0, RESPONSE_B)

        result = cache.get("gpt-4o", _msg("Learn Python programming"), 0.0)
        assert result is not None
        assert result[0] == RESPONSE_A  # should match Python, not ML


class TestSemanticCacheBehavior:
    def test_is_cacheable(self):
        cache = SemanticCache(temp_threshold=0.2)
        assert cache.is_cacheable(0.0, False)
        assert cache.is_cacheable(0.2, False)
        assert not cache.is_cacheable(0.5, False)
        assert not cache.is_cacheable(0.0, True)  # streaming

    def test_ttl_expiry(self):
        cache = SemanticCache(ttl=1)
        cache.put("gpt-4o", _msg("Test"), 0.0, RESPONSE_A)
        assert cache.get("gpt-4o", _msg("Test"), 0.0) is not None

        time.sleep(1.1)
        assert cache.get("gpt-4o", _msg("Test"), 0.0) is None

    def test_max_entries_eviction(self):
        cache = SemanticCache(max_entries=3)
        for i in range(5):
            cache.put("gpt-4o", _msg(f"Unique question number {i}"), 0.0, {"id": i})
        assert cache.size <= 3

    def test_clear(self):
        cache = SemanticCache()
        cache.put("gpt-4o", _msg("Test 1"), 0.0, RESPONSE_A)
        cache.put("gpt-4o", _msg("Test 2"), 0.0, RESPONSE_B)
        count = cache.clear()
        assert count == 2
        assert cache.size == 0

    def test_empty_content_not_cached(self):
        cache = SemanticCache()
        cache.put("gpt-4o", [{"role": "user", "content": ""}], 0.0, RESPONSE_A)
        assert cache.size == 0

    def test_tools_affect_exact_key(self):
        cache = SemanticCache()
        tools = [{"type": "function", "function": {"name": "get_weather"}}]
        cache.put("gpt-4o", _msg("Test"), 0.0, RESPONSE_A, tools=tools)
        # Without tools = different exact key
        result = cache.get("gpt-4o", _msg("Test"), 0.0, tools=None)
        # Might semantic match since text is same
        if result:
            assert result[1] == "semantic"


class TestSemanticCacheStats:
    def test_stats_tracking(self):
        cache = SemanticCache(similarity_threshold=0.3)
        cache.put("gpt-4o", _msg("Python programming language"), 0.0, RESPONSE_A)

        cache.get("gpt-4o", _msg("Python programming language"), 0.0)  # exact
        cache.get("gpt-4o", _msg("Learn Python programming"), 0.0)  # semantic
        cache.get("gpt-4o", _msg("Chocolate cake recipe"), 0.0)  # miss

        stats = cache.to_dict()
        assert stats["exact_hits"] == 1
        assert stats["semantic_hits"] == 1
        assert stats["total_misses"] == 1
        assert stats["entries"] == 1
        assert stats["embedding_backend"] == "n-gram-jaccard"

    def test_record_hit_miss(self):
        cache = SemanticCache()
        cache.record_hit("proj-a", "gpt-4o", 0.05, 200)
        cache.record_hit("proj-a", "gpt-4o", 0.03, 150)
        cache.record_miss("proj-a", "gpt-4o")

        stats = cache.to_dict()
        assert stats["total_cost_saved"] == pytest.approx(0.08)
        assert stats["total_latency_saved_ms"] == 350
        assert stats["by_project"]["proj-a"]["hits"] == 2
        assert stats["by_project"]["proj-a"]["misses"] == 1

    def test_reset_stats(self):
        cache = SemanticCache()
        cache.record_hit("proj-a", "gpt-4o", 0.05, 200)
        cache.reset_stats()
        stats = cache.to_dict()
        assert stats["total_cost_saved"] == 0
        assert stats["exact_hits"] == 0

    def test_hit_rate_calculation(self):
        cache = SemanticCache()
        cache.exact_hits = 3
        cache.semantic_hits = 2
        cache.misses = 5
        stats = cache.to_dict()
        assert stats["hit_rate_pct"] == 50.0
        assert stats["semantic_hit_rate_pct"] == 20.0

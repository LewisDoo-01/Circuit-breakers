"""Regression tests for P1-7: two embedding API calls per cache miss.

The Gemini client is stubbed, so these tests never touch the network.
"""
import os
import sys
import types

import numpy as np
import pytest

# Stub google.genai BEFORE importing semantic_cache, so no real client is built
# and no API call can escape.
_API_CALLS = {"n": 0}


class _FakeEmbedding:
    def __init__(self, values):
        self.values = values


class _FakeResult:
    def __init__(self, values):
        self.embeddings = [_FakeEmbedding(values)]


class _FakeModels:
    def embed_content(self, model, contents):
        _API_CALLS["n"] += 1
        rng = np.random.default_rng(abs(hash(contents)) % (2**32))
        return _FakeResult(list(rng.normal(size=16)))


class _FakeClient:
    def __init__(self, api_key=None):
        self.models = _FakeModels()


_fake_genai = types.ModuleType("genai")
_fake_genai.Client = _FakeClient
sys.modules["google.genai"] = _fake_genai
import google  # noqa: E402

google.genai = _fake_genai
os.environ.setdefault("GOOGLE_API_KEY", "fake-key-for-tests")

import semantic_cache  # noqa: E402
from semantic_cache import SemanticCache  # noqa: E402


@pytest.fixture(autouse=True)
def reset_counter():
    _API_CALLS["n"] = 0
    yield


def test_one_embedding_call_per_cache_miss():
    # ORIGINAL BUG: lookup() embedded the query, then store() embedded the SAME
    # query again - two paid API calls and two network round trips per miss, in
    # the layer whose entire purpose is to reduce cost and latency.
    cache = SemanticCache(similarity_threshold=0.85, ttl_seconds=600)
    query = "Lam the nao de quen mat khau?"

    cache.lookup(query)
    after_lookup = _API_CALLS["n"]
    cache.store(query, "Vao Cai dat > Bao mat.")
    after_store = _API_CALLS["n"]

    assert after_lookup == 1
    assert after_store == 1, f"store() re-embedded the query ({after_store} calls total)"
    assert cache.embedding_api_calls == 1


def test_store_accepts_a_precomputed_embedding():
    cache = SemanticCache()
    vector = cache._get_embedding("cau hoi rieng")
    calls_before = _API_CALLS["n"]

    cache.store("cau hoi rieng", "tra loi", embedding=vector)

    assert _API_CALLS["n"] == calls_before


def test_repeated_identical_query_is_embedded_once():
    cache = SemanticCache()
    for _ in range(5):
        cache.lookup("cung mot cau hoi")
    assert _API_CALLS["n"] == 1


def test_memo_is_bounded():
    # An unbounded memo would be a slow memory leak on a long-running gateway.
    cache = SemanticCache(embedding_memo_size=4)
    for i in range(20):
        cache._get_embedding(f"cau hoi {i}")
    assert len(cache._embedding_memo) <= 4


def test_memo_evicts_least_recently_used():
    cache = SemanticCache(embedding_memo_size=2)
    cache._get_embedding("a")
    cache._get_embedding("b")
    cache._get_embedding("a")  # 'a' becomes most recent, so 'b' is next out
    cache._get_embedding("c")

    assert "a" in cache._embedding_memo
    assert "b" not in cache._embedding_memo


def test_cached_vector_is_identical_not_recomputed():
    cache = SemanticCache()
    first = cache._get_embedding("on dinh")
    second = cache._get_embedding("on dinh")
    assert first is second


def test_lookup_and_store_round_trip_still_works():
    # Guards against the memo breaking the actual caching behaviour.
    cache = SemanticCache(similarity_threshold=0.85, ttl_seconds=600)
    query = "Thoi han hoan tien la bao lau?"

    reply, _ = cache.lookup(query)
    assert reply is None
    cache.store(query, "30 ngay.")

    reply, score = cache.lookup(query)
    assert reply == "30 ngay."
    assert score == pytest.approx(1.0, abs=1e-6)
    assert cache.get_hit_rate() == pytest.approx(0.5)


def test_embeddings_are_normalised():
    cache = SemanticCache()
    vector = cache._get_embedding("bat ky")
    assert np.linalg.norm(vector) == pytest.approx(1.0, abs=1e-9)


def test_missing_api_key_raises_a_useful_error(monkeypatch):
    # ORIGINAL BUG: a bare KeyError('GOOGLE_API_KEY') that told the user nothing.
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        SemanticCache()


def test_module_does_not_hardcode_a_guessed_model_id():
    # The model id lives in one named constant, so it can be corrected in one
    # place when the provider's catalogue changes.
    assert isinstance(semantic_cache.EMBEDDING_MODEL, str)
    assert semantic_cache.EMBEDDING_MODEL

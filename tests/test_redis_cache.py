"""Regression tests for P1-8 (O(N) round trips) and P1-9 (non-atomic set).

Skipped entirely when no Redis server is reachable.
"""
import pytest

redis = pytest.importorskip("redis")

from cache import ResponseCache, SharedRedisCache  # noqa: E402

REDIS_URL = "redis://localhost:6379"
PREFIX = "pytest:cache:"


def _redis_available():
    try:
        return bool(redis.Redis.from_url(REDIS_URL, socket_connect_timeout=1).ping())
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _redis_available(), reason="no Redis server on localhost:6379"
)


@pytest.fixture
def cache():
    c = SharedRedisCache(REDIS_URL, ttl_seconds=300,
                         similarity_threshold=0.85, prefix=PREFIX)
    c.flush()
    yield c
    c.flush()
    c.close()


class _CommandCounter:
    """Counts commands actually sent to Redis."""

    def __init__(self):
        self.n = 0
        self._real = redis.Redis.execute_command

    def __enter__(self):
        counter = self

        def counting(client, *args, **kwargs):
            counter.n += 1
            return counter._real(client, *args, **kwargs)

        redis.Redis.execute_command = counting
        return self

    def __exit__(self, *exc):
        redis.Redis.execute_command = self._real


# ---------------------------------------------------------------------------
# P1-8: round trips must not scale one-per-entry
# ---------------------------------------------------------------------------

def test_lookup_does_not_issue_one_round_trip_per_entry(cache):
    # ORIGINAL BUG (measured): 300 entries cost 334 Redis commands and 199 ms
    # for a single lookup, because get() did one HGET per key - plus another
    # HGET for "response" every time the best score improved.
    n_entries = 200
    for i in range(n_entries):
        cache.set(f"Cau hoi so {i} ve chinh sach van chuyen", f"Tra loi {i}")

    with _CommandCounter() as counter:
        value, score = cache.get("Cau hoi so 150 ve chinh sach van chuyen nhe")

    assert value == "Tra loi 150", f"correctness regressed: {value!r} @ {score}"
    assert counter.n < n_entries / 4, (
        f"{counter.n} commands for {n_entries} entries still scales per-entry"
    )


def test_batching_does_not_change_the_winner(cache):
    # The pipelined version must pick exactly the same entry as a plain scan.
    entries = {
        "Lam the nao de huy don hang": "Vao Don hang > Huy don",
        "Phi giao hang la bao nhieu": "30.000 VND",
        "Chinh sach doi tra the nao": "Doi tra trong 7 ngay",
    }
    for query, response in entries.items():
        cache.set(query, response)

    value, score = cache.get("Lam the nao de huy don hang da dat")
    assert value == "Vao Don hang > Huy don"
    assert score >= 0.85


def test_scan_batch_boundary_is_handled(cache, monkeypatch):
    # Exercise the partial-final-batch path of _iter_key_batches().
    monkeypatch.setattr(SharedRedisCache, "_scan_batch", 3)
    for i in range(7):  # 7 = 2 full batches + 1 leftover
        cache.set(f"Cau hoi rieng biet so {i}", f"Tra loi {i}")

    value, _ = cache.get("Cau hoi rieng biet so 5")
    assert value == "Tra loi 5"


def test_exact_match_short_circuits(cache):
    cache.set("Thoi han hoan tien", "30 ngay")
    with _CommandCounter() as counter:
        value, score = cache.get("Thoi han hoan tien")
    assert (value, score) == ("30 ngay", 1.0)
    assert counter.n <= 2, "exact hit should not scan the keyspace"


def test_missing_entry_returns_none(cache):
    cache.set("Cau hoi hoan toan khac biet ve van chuyen", "abc")
    value, _ = cache.get("Chu de khong lien quan gi ca ve ke toan")
    assert value is None


# ---------------------------------------------------------------------------
# P1-9: set() must be atomic
# ---------------------------------------------------------------------------

def test_set_always_leaves_a_ttl(cache):
    # ORIGINAL BUG: HSET and EXPIRE were two separate commands. A crash or a
    # dropped connection between them left the key with TTL -1 - cached forever,
    # never refreshed, invisible to the eviction policy.
    cache.set("Kiem tra ttl", "gia tri")
    key = f"{PREFIX}{cache._query_hash('Kiem tra ttl')}"

    ttl = cache._redis.ttl(key)
    assert ttl > 0, f"key stored without expiry (ttl={ttl})"
    assert ttl <= 300


def test_a_key_without_ttl_is_what_we_are_preventing(cache):
    # Demonstrates the failure mode itself, so the test above has teeth.
    cache._redis.hset(f"{PREFIX}manual", mapping={"query": "q", "response": "r"})
    assert cache._redis.ttl(f"{PREFIX}manual") == -1  # -1 means "never expires"


def test_privacy_filter_blocks_writes_and_reads(cache):
    cache.set("what is my account balance", "1,000,000")
    value, score = cache.get("what is my account balance")
    assert (value, score) == (None, 0.0)


def test_false_hit_guardrail_applies_to_redis_too(cache):
    # The guardrail must protect BOTH backends, not just the in-memory one.
    cache.set("Toi co the huy don hang khong?", "Co, ban co the huy don hang.")
    value, score = cache.get("Toi khong the huy don hang?")

    assert value is None, "Redis backend served the inverted answer"
    assert score >= 0.85
    assert cache.false_hit_log[0]["reason"] == "polarity_mismatch"


def test_redis_and_memory_backends_agree(cache):
    memory = ResponseCache(ttl_seconds=300, similarity_threshold=0.85)
    pairs = [
        ("Lam the nao de huy don hang", "Vao Don hang > Huy don"),
        ("Phi giao hang bao nhieu", "30.000 VND"),
    ]
    for query, response in pairs:
        cache.set(query, response)
        memory.set(query, response)

    for probe in ["Lam the nao de huy don hang da dat",
                  "Phi giao hang bao nhieu tien",
                  "Chu de khong lien quan ve ke toan"]:
        redis_value, _ = cache.get(probe)
        memory_value, _ = memory.get(probe)
        assert redis_value == memory_value, f"backends disagree on {probe!r}"

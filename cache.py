from __future__ import annotations

import hashlib
import math
import re
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Shared utilities — use these in both ResponseCache and SharedRedisCache
# ---------------------------------------------------------------------------

# An unescaped "." matches ANY character, so the original "credit.card" also
# matched "creditXcard", and "user.\d+" matched "userZ42".  Over-matching is the
# safe direction for privacy, but it silently shrinks the cache hit rate, so
# spell the separator out instead of leaving it to a wildcard.
PRIVACY_PATTERNS = re.compile(
    r"\b(balance|password|credit[ ._-]?card|ssn|social[ ._-]?security"
    r"|user[ ._-]?\d+|account[ ._-]?\d+)\b",
    re.IGNORECASE,
)


def _is_uncacheable(query: str) -> bool:
    """Return True if query contains privacy-sensitive keywords."""
    return bool(PRIVACY_PATTERNS.search(query))


# ---------------------------------------------------------------------------
# False-hit guardrail
#
# The similarity function is a bag of character n-grams and word tokens.  It
# throws away word order and weights every token by frequency mass, not by
# meaning.  So a single short token that INVERTS the answer -- "khong", "tat",
# "90" -- moves the score by about 1/N while flipping what the user asked.
#
# Verified failure before this guardrail existed:
#     cached: "Toi co the huy don hang khong?"  ("can I cancel?")
#     query:  "Toi khong the huy don hang?"     ("I CANNOT cancel?")
#     score 0.898 >= threshold 0.85 -> HIT -> the user asking whether they are
#     blocked was served "Yes, you can cancel."
#
# So the question is not "do these two strings DIFFER?" (the old 4-digit check)
# but "do these two strings CONTRADICT each other?".  Three detectors cover the
# contradiction classes that actually cause harm:
#     1. quantity conflict  - 30 days vs 90 days, 2023 vs 2024
#     2. antonym conflict   - enable/disable, bat/tat
#     3. polarity conflict  - negation present on one side only
# ---------------------------------------------------------------------------

# Vietnamese is written both with and without diacritics, so fold them away and
# compare on a single normalised form.  Folding does create collisions ("tat"
# is both "tat" = turn off and "tat" = all); _NOT_A_TOGGLE below resolves those.
_D_STROKE = str.maketrans({"đ": "d", "Đ": "d"})
_TOKEN_RE = re.compile(r"[a-z]+|\d+(?:[.,]\d+)*")

# Negation words whose reading depends on POSITION.  In Vietnamese "khong" is a
# NEGATION before a verb ("khong the huy" = cannot cancel) but an INTERROGATIVE
# PARTICLE at the end of a clause ("huy duoc khong?" = can I cancel?).  This is
# the crux of the bug: both strings above contain "khong", so comparing sets of
# negation words finds no difference at all.  Position is what separates them.
_NEGATION_WORDS = {
    # Vietnamese (position-dependent)
    "khong", "ko", "k", "chua", "chang", "chan",
    # English (a trailing negation is not a question particle, but the same
    # "is anything meaningful after it" test is harmless here)
    "not", "no", "never", "cannot", "cant", "wont", "dont", "doesnt",
    "didnt", "isnt", "arent", "wasnt", "havent", "hasnt", "without", "unable",
}

# Sentence-final flavour particles.  A negation word followed only by these is
# still clause-final, i.e. still an interrogative particle.
_TAIL_PARTICLES = {"a", "ah", "vay", "nhi", "nhe", "ha", "day", "u", "ru", "z", "hen", "ay"}

# Antonym pairs.  Order inside a pair does not matter.
_ANTONYMS = [
    ("enable", "disable"), ("activate", "deactivate"), ("start", "stop"),
    ("open", "close"), ("add", "remove"), ("add", "delete"), ("show", "hide"),
    ("lock", "unlock"), ("allow", "block"), ("allow", "deny"),
    ("accept", "reject"), ("increase", "decrease"), ("upgrade", "downgrade"),
    ("connect", "disconnect"), ("install", "uninstall"),
    ("subscribe", "unsubscribe"), ("grant", "revoke"), ("login", "logout"),
    ("bat", "tat"), ("mo", "dong"), ("them", "xoa"), ("tang", "giam"),
    ("hien", "an"), ("cho", "chan"),
]

# Diacritic-folding collisions: these words only mean the antonym when NOT
# followed by one of these.  "bat dau" is "begin", not "turn on"; "tat ca" is
# "all", not "turn off".
_NOT_A_TOGGLE = {
    "bat": {"dau", "buoc", "gap", "chuoc", "ky", "ngo"},
    "tat": {"ca", "nhien", "yeu", "tan", "bat"},
    "mo": {"ta", "hinh", "phong"},
    "an": {"toan", "ninh", "com"},
    "cho": {"phep", "thue"},
}

# Unit aliases, so "30 ngay" and "30 days" compare on the same axis.
_UNITS = {
    "ngay": "day", "day": "day", "days": "day",
    "tuan": "week", "week": "week", "weeks": "week",
    "thang": "month", "month": "month", "months": "month",
    "nam": "year", "year": "year", "years": "year",
    "gio": "hour", "hour": "hour", "hours": "hour",
    "phut": "minute", "minute": "minute", "minutes": "minute",
    "giay": "second", "second": "second", "seconds": "second",
    "lan": "time", "time": "time", "times": "time",
    "vnd": "vnd", "dong": "vnd", "usd": "usd", "gb": "gb", "mb": "mb",
}


def _fold(text: str) -> str:
    """Lowercase and strip Vietnamese diacritics so 'không' == 'khong'."""
    folded = unicodedata.normalize("NFD", text.lower()).translate(_D_STROKE)
    return "".join(c for c in folded if not unicodedata.combining(c))


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(_fold(text))


def _negation_count(toks: list[str]) -> int:
    """Count real negations, ignoring clause-final interrogative particles."""
    count = 0
    for i, tok in enumerate(toks):
        if tok not in _NEGATION_WORDS:
            continue
        rest = toks[i + 1:]
        # Nothing meaningful after it -> question particle ("... khong?"),
        # not a negation.
        if not rest or all(r in _TAIL_PARTICLES for r in rest):
            continue
        count += 1
    return count


def _is_toggle(toks: list[str], i: int) -> bool:
    """False when a folded token is a lookalike rather than the real antonym."""
    blocked = _NOT_A_TOGGLE.get(toks[i])
    if not blocked:
        return True
    nxt = toks[i + 1] if i + 1 < len(toks) else None
    return nxt not in blocked


def _has_word(toks: list[str], word: str) -> bool:
    return any(t == word and _is_toggle(toks, i) for i, t in enumerate(toks))


def _measures(toks: list[str]) -> tuple[dict[str, set[float]], set[float]]:
    """Split numbers into unit-qualified quantities and bare numbers."""
    quantities: dict[str, set[float]] = {}
    bare: set[float] = set()
    for i, tok in enumerate(toks):
        if not tok[0].isdigit():
            continue
        try:
            value = float(re.sub(r"[.,](?=\d{3}\b)", "", tok).replace(",", "."))
        except ValueError:
            continue
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        unit = _UNITS.get(nxt) if nxt else None
        if unit:
            quantities.setdefault(unit, set()).add(value)
        else:
            bare.add(value)
    return quantities, bare


def false_hit_reason(query: str, cached_key: str) -> str | None:
    """Return why serving cached_key's answer to query would be wrong, else None.

    This runs on every cache lookup, so it stays O(number of tokens) and uses no
    model and no network.
    """
    tq, tc = _tokens(query), _tokens(cached_key)
    if tq == tc:
        return None

    # 1. Quantity conflict -- generalises the old 4-digit-only check.
    quant_q, bare_q = _measures(tq)
    quant_c, bare_c = _measures(tc)
    for unit in set(quant_q) & set(quant_c):
        if quant_q[unit] != quant_c[unit]:
            return f"quantity_mismatch:{unit}"
    if bare_q and bare_c and bare_q != bare_c:
        return "number_mismatch"

    # 2. Antonym conflict -- one side says enable, the other says disable.
    for left, right in _ANTONYMS:
        q_left, q_right = _has_word(tq, left), _has_word(tq, right)
        c_left, c_right = _has_word(tc, left), _has_word(tc, right)
        if (q_left and not q_right and c_right and not c_left) or (
            q_right and not q_left and c_left and not c_right
        ):
            return f"antonym_opposition:{left}/{right}"

    # 3. Polarity conflict -- negation on exactly one side.  Double negation is
    #    rare enough in real queries that parity is a good enough proxy.
    if (_negation_count(tq) % 2) != (_negation_count(tc) % 2):
        return "polarity_mismatch"

    return None


def _looks_like_false_hit(query: str, cached_key: str) -> bool:
    """Backwards-compatible boolean form of false_hit_reason()."""
    return false_hit_reason(query, cached_key) is not None


# ---------------------------------------------------------------------------
# In-memory cache (existing)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CacheEntry:
    key: str
    value: str
    created_at: float
    metadata: dict[str, str]


class ResponseCache:
    """Simple in-memory cache skeleton.

    TODO(student): Add a better semantic similarity function and false-hit guardrails.
    Use the module-level _is_uncacheable() and _looks_like_false_hit() helpers in your
    get() and set() methods.  For production, replace with SharedRedisCache.
    """

    def __init__(self, ttl_seconds: int, similarity_threshold: float):
        self.ttl_seconds = ttl_seconds
        self.similarity_threshold = similarity_threshold
        self._entries: list[CacheEntry] = []
        self.false_hit_log: list[dict[str, object]] = []

    def get(self, query: str) -> tuple[str | None, float]:
        """Look up a cached response by semantic similarity."""
        if _is_uncacheable(query):
            return None, 0.0

        now = time.time()
        self._entries = [e for e in self._entries if now - e.created_at <= self.ttl_seconds]

        best_score = 0.0
        best_entry: CacheEntry | None = None
        for entry in self._entries:
            score = self.similarity(query, entry.key)
            if score > best_score:
                best_score = score
                best_entry = entry

        if best_score >= self.similarity_threshold and best_entry is not None:
            reason = false_hit_reason(query, best_entry.key)
            if reason is not None:
                self.false_hit_log.append({
                    "query": query,
                    "cached_key": best_entry.key,
                    "score": best_score,
                    "reason": reason,
                })
                return None, best_score
            return best_entry.value, best_score

        return None, best_score

    def set(self, query: str, value: str, metadata: dict[str, str] | None = None) -> None:
        """Store a response in cache."""
        if _is_uncacheable(query):
            return
        self._entries.append(CacheEntry(
            key=query,
            value=value,
            created_at=time.time(),
            metadata=metadata or {},
        ))

    @staticmethod
    def similarity(a: str, b: str) -> float:
        """Compute cosine similarity over character n-grams + word tokens."""
        if a == b:
            return 1.0

        def tokenize(text: str) -> list[str]:
            text_lower = text.lower()
            words = text_lower.split()
            ngrams = []
            for word in words:
                for i in range(len(word) - 2):
                    ngrams.append(word[i : i + 3])
            return words + ngrams

        vec_a = Counter(tokenize(a))
        vec_b = Counter(tokenize(b))

        common_keys = set(vec_a.keys()) & set(vec_b.keys())
        dot_product = sum(vec_a[k] * vec_b[k] for k in common_keys)
        mag_a = math.sqrt(sum(v * v for v in vec_a.values()))
        mag_b = math.sqrt(sum(v * v for v in vec_b.values()))

        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot_product / (mag_a * mag_b)


# ---------------------------------------------------------------------------
# Redis shared cache (new)
# ---------------------------------------------------------------------------


class SharedRedisCache:
    """Redis-backed shared cache for multi-instance deployments.

    Data model:
        Key    = "{prefix}{query_hash}"
        Value  = Redis Hash with fields:  "query", "response"
        TTL    = Redis EXPIRE (automatic cleanup - no manual eviction)

    Similarity lookup walks every key under the prefix, which is O(N) in the
    number of cached entries.  Measured on a local Redis with only 300 entries,
    the naive one-HGET-per-key version issued 334 commands and took 199 ms for a
    single lookup -- a cache that exists to REMOVE latency was adding 200 ms.

    Batching the reads into pipelines keeps the same data model but collapses
    those N round trips into N/_scan_batch of them.  That is a constant-factor
    win, not an algorithmic one: the scan is still O(N).

    The real fix beyond this teaching example is a vector index (Redis Stack /
    RediSearch `FT.SEARCH ... KNN`), which turns the lookup into an approximate
    nearest-neighbour query and never walks the keyspace at all.  That needs a
    Redis module this repo does not assume, so it is deliberately out of scope.
    """

    #: How many keys to read per pipeline round trip.
    _scan_batch = 500

    def __init__(
        self,
        redis_url: str,
        ttl_seconds: int,
        similarity_threshold: float,
        prefix: str = "rl:cache:",
    ):
        import redis as redis_lib

        self.ttl_seconds = ttl_seconds
        self.similarity_threshold = similarity_threshold
        self.prefix = prefix
        self.false_hit_log: list[dict[str, object]] = []
        self._redis: Any = redis_lib.Redis.from_url(redis_url, decode_responses=True)

    def ping(self) -> bool:
        """Check Redis connectivity."""
        try:
            return bool(self._redis.ping())
        except Exception:
            return False

    def get(self, query: str) -> tuple[str | None, float]:
        """Look up a cached response from Redis."""
        if _is_uncacheable(query):
            return None, 0.0

        exact_key = f"{self.prefix}{self._query_hash(query)}"
        exact_response = self._redis.hget(exact_key, "response")
        if exact_response is not None:
            return exact_response, 1.0

        best_score = 0.0
        best_key: str | None = None
        best_cached_query: str | None = None

        # Read the candidate queries in pipelined batches instead of one HGET
        # per key.  Note we only track the WINNING key here -- the old code
        # fetched the "response" field every time the best score improved, which
        # cost an extra round trip per improvement for a value it then threw
        # away.  The winner's response is fetched once, after the loop.
        for batch in self._iter_key_batches():
            pipe = self._redis.pipeline(transaction=False)
            for key in batch:
                pipe.hget(key, "query")
            for key, cached_query in zip(batch, pipe.execute()):
                # A key can expire between the SCAN and the HGET; skip it.
                if cached_query is None:
                    continue
                score = ResponseCache.similarity(query, cached_query)
                if score > best_score:
                    best_score = score
                    best_key = key
                    best_cached_query = cached_query

        best_response = self._redis.hget(best_key, "response") if best_key else None

        if best_score >= self.similarity_threshold and best_response is not None:
            reason = false_hit_reason(query, best_cached_query or "")
            if reason is not None:
                self.false_hit_log.append({
                    "query": query,
                    "cached_key": best_cached_query,
                    "score": best_score,
                    "reason": reason,
                })
                return None, best_score
            return best_response, best_score

        return None, best_score

    def _iter_key_batches(self):
        """Yield keys under this prefix in batches, for pipelined reads."""
        batch: list[str] = []
        for key in self._redis.scan_iter(f"{self.prefix}*", count=self._scan_batch):
            batch.append(key)
            if len(batch) >= self._scan_batch:
                yield batch
                batch = []
        if batch:
            yield batch

    def set(self, query: str, value: str, metadata: dict[str, str] | None = None) -> None:
        """Store a response in Redis with TTL, atomically.

        HSET and EXPIRE as two separate commands are not atomic: if the process
        dies or the connection drops in between, the key is written with NO TTL
        and lives in Redis forever.  A MULTI/EXEC transaction makes the pair
        all-or-nothing.
        """
        if _is_uncacheable(query):
            return
        key = f"{self.prefix}{self._query_hash(query)}"
        pipe = self._redis.pipeline(transaction=True)
        pipe.hset(key, mapping={"query": query, "response": value})
        pipe.expire(key, self.ttl_seconds)
        pipe.execute()

    def flush(self) -> None:
        """Remove all entries with this cache prefix (for testing)."""
        for batch in self._iter_key_batches():
            pipe = self._redis.pipeline(transaction=False)
            for key in batch:
                pipe.delete(key)
            pipe.execute()

    def close(self) -> None:
        """Close Redis connection."""
        if self._redis is not None:
            self._redis.close()

    @staticmethod
    def _query_hash(query: str) -> str:
        """Deterministic short hash for a query string."""
        return hashlib.md5(query.lower().strip().encode()).hexdigest()[:12]

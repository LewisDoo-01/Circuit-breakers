"""Regression tests for P0-3: the cache served semantically INVERTED answers.

Each test states the original buggy behaviour it pins down.
"""
import pytest

from cache import ResponseCache, _looks_like_false_hit, false_hit_reason

# ---------------------------------------------------------------------------
# Dangerous false hits: serving the cached answer here would be WRONG.
# The original guardrail only compared 4-digit numbers, so every case below
# except the year one slipped straight through.
# ---------------------------------------------------------------------------
MUST_FLAG = [
    # The headline bug: "can I cancel?" vs "I CANNOT cancel?".  Both strings
    # contain the token "khong", so a set-difference of negation words finds
    # nothing - only POSITION separates the question particle from the negation.
    ("vi_negation_vs_question_particle",
     "Toi khong the huy don hang?", "Toi co the huy don hang khong?"),
    ("vi_negation_with_diacritics",
     "Tôi không thể hủy đơn hàng?",
     "Tôi có thể hủy đơn hàng không?"),
    ("en_negation", "I cannot reset my password", "I can reset my password"),
    ("en_antonym", "How do I enable 2FA?", "How do I disable 2FA?"),
    ("en_derivational_antonym", "How to subscribe", "How to unsubscribe"),
    ("vi_antonym", "Lam sao de bat thong bao", "Lam sao de tat thong bao"),
    ("vi_antonym_diacritics",
     "Làm sao để bật thông báo",
     "Làm sao để tắt thông báo"),
    # Not 4 digits, so the original check ignored it entirely.
    ("quantity_with_unit", "Thoi han hoan tien 30 ngay", "Thoi han hoan tien 90 ngay"),
    ("quantity_days_english", "refund window is 30 days", "refund window is 7 days"),
    # This is the one class the original DID catch; keep it pinned.
    ("four_digit_year", "Revenue in 2023", "Revenue in 2024"),
]

# ---------------------------------------------------------------------------
# Genuine hits.  A guardrail that blocks these "fixes" the bug by destroying
# the cache hit rate, which is the entire point of having a cache.
# ---------------------------------------------------------------------------
MUST_NOT_FLAG = [
    ("en_synonym", "How do I reset my order?", "How can I reset my order?"),
    ("vi_synonym", "Lam the nao de huy don hang da dat?",
     "Huy don hang da dat lam the nao?"),
    # Both end in the interrogative particle "khong" - that is NOT a polarity
    # mismatch, and treating it as one would block a very common phrasing.
    ("both_question_particle", "Cong ty co ho tro giao hang hoa toc khong?",
     "Ben minh co giao hang hoa toc khong?"),
    ("both_question_particle_diacritics",
     "Công ty có hỗ trợ giao hàng hỏa tốc không?",
     "Bên mình có giao hàng hỏa tốc không?"),
    ("identical", "Thoi han hoan tien?", "Thoi han hoan tien?"),
    ("punctuation_and_case_only", "Thoi han hoan tien", "  thoi han hoan tien!! "),
    # Diacritic folding makes "bắt đầu" (begin) look like "bật" (turn on) and
    # "tất cả" (all) look like "tắt" (turn off).  These must not fire.
    ("collision_bat_dau", "Khi nao bat dau giao hang", "Bao gio bat dau giao hang"),
    ("collision_tat_ca", "Tat ca don hang cua toi", "Tat ca cac don hang cua toi"),
    ("same_polarity", "Toi khong the dang nhap", "Toi khong dang nhap duoc"),
    ("same_quantity", "Giao hang trong 2 gio", "Ho tro giao hang 2 gio"),
]


@pytest.mark.parametrize("name,query,cached", MUST_FLAG, ids=[c[0] for c in MUST_FLAG])
def test_dangerous_false_hits_are_blocked(name, query, cached):
    reason = false_hit_reason(query, cached)
    assert reason is not None, f"{name}: inverted/contradicting answer would be served"
    assert _looks_like_false_hit(query, cached) is True


@pytest.mark.parametrize("name,query,cached", MUST_NOT_FLAG,
                         ids=[c[0] for c in MUST_NOT_FLAG])
def test_genuine_hits_are_not_blocked(name, query, cached):
    # Over-blocking is also a bug: it silently destroys the cache hit rate.
    reason = false_hit_reason(query, cached)
    assert reason is None, f"{name}: guardrail over-blocked with {reason!r}"


def test_guardrail_is_symmetric():
    # Whether a pair contradicts must not depend on which side is the query.
    for _, query, cached in MUST_FLAG + MUST_NOT_FLAG:
        forward = false_hit_reason(query, cached) is not None
        backward = false_hit_reason(cached, query) is not None
        assert forward == backward, f"asymmetric verdict for {query!r} vs {cached!r}"


def test_end_to_end_inverted_answer_is_not_served():
    # ORIGINAL BUG (verified): this returned "Co, ban co the huy don hang."
    # at score 0.898 - the user asking whether they are BLOCKED was told YES.
    cache = ResponseCache(ttl_seconds=600, similarity_threshold=0.85)
    cache.set("Toi co the huy don hang khong?", "Co, ban co the huy don hang.")

    value, score = cache.get("Toi khong the huy don hang?")

    assert value is None
    assert score >= 0.85, "the similarity function still scores these as near-identical"
    assert cache.false_hit_log, "a blocked false hit must be logged for review"


def test_false_hit_log_names_the_specific_rule():
    # ORIGINAL BUG: the reason was hardcoded to "date_or_number_mismatch" even
    # when the mismatch had nothing to do with dates or numbers.
    cache = ResponseCache(ttl_seconds=600, similarity_threshold=0.85)
    cache.set("Toi co the huy don hang khong?", "Co, ban co the huy don hang.")
    cache.get("Toi khong the huy don hang?")

    reason = cache.false_hit_log[0]["reason"]
    assert reason == "polarity_mismatch", f"unhelpful reason: {reason!r}"


def test_genuine_synonym_still_hits_end_to_end():
    # Guards against the guardrail eating the feature it protects.
    cache = ResponseCache(ttl_seconds=600, similarity_threshold=0.85)
    cache.set("Lam the nao de huy don hang da dat?", "Vao Don hang > Huy don.")

    value, score = cache.get("Lam the nao de huy don hang da dat")

    assert value == "Vao Don hang > Huy don.", f"synonym lost its cache hit (score={score})"
    assert cache.false_hit_log == []


def test_privacy_filter_still_runs_before_the_guardrail():
    # Pre-existing behaviour that must not regress: privacy-sensitive queries
    # are never cached at all, so they never reach the guardrail.
    cache = ResponseCache(ttl_seconds=600, similarity_threshold=0.85)
    cache.set("what is my account balance", "1,000,000 VND")

    value, score = cache.get("what is my account balance")

    assert value is None
    assert score == 0.0


def test_guardrail_is_cheap_enough_for_every_lookup():
    # It runs on the hot path, so it must stay far below a millisecond.
    import time

    pairs = [(q, c) for _, q, c in MUST_FLAG + MUST_NOT_FLAG]
    start = time.perf_counter()
    for _ in range(200):
        for query, cached in pairs:
            false_hit_reason(query, cached)
    elapsed = time.perf_counter() - start
    per_call = elapsed / (200 * len(pairs))

    assert per_call < 1e-3, f"{per_call * 1e6:.0f} us per call is too slow for a cache lookup"


# ---------------------------------------------------------------------------
# P1 #15: the privacy regex used "." where it meant a literal separator
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    "what is my credit card number",
    "my credit-card expired",
    "credit_card details",
    "what is my balance",
    "reset my password",
    "my ssn is private",
    "social security number",
    "user_42 profile",
    "account 99 details",
])
def test_privacy_sensitive_queries_are_still_blocked(query):
    from cache import _is_uncacheable
    assert _is_uncacheable(query) is True


@pytest.mark.parametrize("query", [
    "creditXcard",       # "." matched any char, so this used to be blocked
    "userZ42",           # likewise
    "accountZ99",
    "gia san pham la bao nhieu",
    "thoi han giao hang",
])
def test_unrelated_queries_are_cacheable(query):
    # ORIGINAL BUG: unescaped dots in the pattern made these look sensitive,
    # silently shrinking the cache hit rate for no privacy benefit.
    from cache import _is_uncacheable
    assert _is_uncacheable(query) is False

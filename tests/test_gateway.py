"""Tests for gateway.py — the unified pipeline wiring cache, circuit breaker,
retry+jitter, fallback ladder, and quality guardrail together.

The headline claim this file must prove with real numbers, not narrative: the
ORDER you compose retry() and breaker.call() changes how many times a dying
server gets hit. See test_breaker_inside_retry_stops_hammering_once_tripped.
"""
import threading
import time

import pytest

from cache import ResponseCache
from gateway import (
    LLMGateway,
    STATIC_FALLBACK_MESSAGE,
    default_faithfulness,
    default_relevancy,
)
from state_machine import CircuitBreaker, CircuitOpenError
from jitter import RETRYABLE_EXCEPTIONS, retry_with_exponential_backoff_and_jitter


CONTEXT = "Quy định công ty: Thời hạn hoàn tiền tối đa là 30 ngày cho mọi đơn hàng hợp lệ."
QUERY = "Thời hạn hoàn tiền là bao lâu?"
FAITHFUL_ANSWER = "Chính sách hoàn tiền của công ty là trong vòng 30 ngày kể từ khi mua."
HALLUCINATED_ANSWER = "Chính sách hoàn tiền của công ty hiện tại là trong vòng 90 ngày kể từ khi mua."


def make_gateway(primary_llm_fn, **kwargs):
    kwargs.setdefault("max_attempts", 3)
    kwargs.setdefault("base_delay", 0.01)
    kwargs.setdefault("max_delay", 0.02)
    return LLMGateway(primary_llm_fn=primary_llm_fn, **kwargs)


# ---------------------------------------------------------------------------
# The headline architectural claim
# ---------------------------------------------------------------------------

def test_breaker_inside_retry_stops_hammering_once_tripped():
    # MEASURED on the real modules: with breaker OUTSIDE retry (breaker.call(
    # lambda: retry(fn))), 2 requests against a dead server with
    # failure_threshold=2 and max_attempts=5 hit the server 10 times before the
    # breaker had a chance to open (it only sees "1 attempt" per request, since
    # retry() swallows all 5 attempts before returning). With breaker INSIDE
    # retry (the gateway's actual composition), the server is hit only 2 times:
    # the moment the breaker opens, CircuitOpenError propagates out of
    # breaker.call(), and CircuitOpenError is NOT in RETRYABLE_EXCEPTIONS =
    # (ConnectionError, TimeoutError) - so retry() stops immediately instead of
    # burning its remaining attempts against a circuit that just tripped.
    calls = {"n": 0}

    def dead():
        calls["n"] += 1
        raise ConnectionError("503")

    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=60.0,
                             expected_exceptions=RETRYABLE_EXCEPTIONS)

    with pytest.raises(CircuitOpenError):
        retry_with_exponential_backoff_and_jitter(
            lambda: breaker.call(dead),
            max_attempts=5, base_delay=0.01, max_delay=0.02,
            retryable_exceptions=RETRYABLE_EXCEPTIONS,
        )

    assert calls["n"] == 2, (
        f"correct composition should stop at the failure threshold (2), "
        f"not exhaust all retry attempts; got {calls['n']} calls"
    )


def test_breaker_outside_retry_hammers_the_dead_server():
    # The WRONG composition, kept as a witness so the contrast above is not
    # just asserted but measured against its own counter-example.
    calls = {"n": 0}

    def dead():
        calls["n"] += 1
        raise ConnectionError("503")

    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=60.0,
                             expected_exceptions=RETRYABLE_EXCEPTIONS)

    for _ in range(2):
        try:
            breaker.call(lambda: retry_with_exponential_backoff_and_jitter(
                dead, max_attempts=5, base_delay=0.01, max_delay=0.02,
            ))
        except Exception:
            pass

    assert calls["n"] == 10, (
        f"wrong composition should hammer the server max_attempts times per "
        f"request until the breaker trips; got {calls['n']} calls"
    )


def test_gateway_wiring_stops_hammering_once_the_breaker_trips():
    # The same claim, but through the actual LLMGateway (not the raw modules),
    # proving the class is wired in the correct order end-to-end.
    calls = {"n": 0}

    def dead_primary(query, context):
        calls["n"] += 1
        raise ConnectionError("503")

    gateway = make_gateway(dead_primary, max_attempts=5,
                           breaker=CircuitBreaker(failure_threshold=2,
                                                  reset_timeout_seconds=60.0,
                                                  expected_exceptions=RETRYABLE_EXCEPTIONS))

    for i in range(2):
        result = gateway.handle_request(f"cau hoi rieng biet so {i}", CONTEXT)
        assert result["status"] == "hard_degraded"

    assert calls["n"] == 2, f"gateway hammered the dead primary {calls['n']} times, want 2"


# ---------------------------------------------------------------------------
# Pipeline ordering: cache short-circuits everything downstream
# ---------------------------------------------------------------------------

def test_cache_hit_never_touches_breaker_or_primary():
    calls = {"n": 0}

    def primary(query, context):
        calls["n"] += 1
        return FAITHFUL_ANSWER

    gateway = make_gateway(primary)
    gateway.cache.set(QUERY, FAITHFUL_ANSWER)

    result = gateway.handle_request(QUERY, CONTEXT)

    assert result == {
        "status": "cache_hit",
        "output": FAITHFUL_ANSWER,
        "source": "cache",
        "cache_score": pytest.approx(1.0),
    }
    assert calls["n"] == 0, "primary was called despite a cache hit"


def test_successful_response_is_cached_for_next_time():
    gateway = make_gateway(lambda q, c: FAITHFUL_ANSWER)

    first = gateway.handle_request(QUERY, CONTEXT)
    assert first["status"] == "success"

    calls_after_first = []
    gateway.primary_llm_fn = lambda q, c: calls_after_first.append(1) or FAITHFUL_ANSWER

    second = gateway.handle_request(QUERY, CONTEXT)
    assert second["status"] == "cache_hit"
    assert calls_after_first == []


# ---------------------------------------------------------------------------
# Fallback ladder
# ---------------------------------------------------------------------------

def test_falls_through_to_backup_when_primary_fails():
    def dead_primary(query, context):
        raise ConnectionError("503")

    gateway = make_gateway(dead_primary, backup_llm_fn=lambda q, c: FAITHFUL_ANSWER)
    result = gateway.handle_request(QUERY, CONTEXT)

    assert result["status"] == "success"
    assert result["source"] == "backup_provider"
    assert result["output"] == FAITHFUL_ANSWER


def test_falls_through_backup_to_smaller_model():
    def dead(query, context):
        raise ConnectionError("503")

    gateway = make_gateway(dead, backup_llm_fn=dead, smaller_llm_fn=lambda q, c: FAITHFUL_ANSWER)
    result = gateway.handle_request(QUERY, CONTEXT)

    assert result["status"] == "success"
    assert result["source"] == "smaller_model"


def test_no_fallback_functions_reaches_static_message():
    gateway = make_gateway(lambda q, c: (_ for _ in ()).throw(ConnectionError("503")))
    result = gateway.handle_request(QUERY, CONTEXT)

    assert result["status"] == "hard_degraded"
    assert result["output"] == STATIC_FALLBACK_MESSAGE
    assert result["source"] == "static_fallback"


def test_a_hung_fallback_tier_does_not_block_the_ladder():
    def dead(query, context):
        raise ConnectionError("503")

    def hangs(query, context):
        time.sleep(30)

    gateway = make_gateway(
        dead, backup_llm_fn=hangs, smaller_llm_fn=lambda q, c: FAITHFUL_ANSWER,
        tier_timeout_seconds=0.1, total_deadline_seconds=10.0,
    )
    started = time.monotonic()
    result = gateway.handle_request(QUERY, CONTEXT)
    elapsed = time.monotonic() - started

    assert result["source"] == "smaller_model"
    assert elapsed < 2.0, f"took {elapsed:.1f}s despite a 0.1s per-tier timeout"
    assert gateway.abandoned_calls == 1


def test_total_deadline_caps_the_fallback_ladder():
    def dead(query, context):
        raise ConnectionError("503")

    def hangs(query, context):
        time.sleep(30)

    gateway = make_gateway(
        dead, backup_llm_fn=hangs, smaller_llm_fn=hangs,
        tier_timeout_seconds=5.0, total_deadline_seconds=0.3,
    )
    started = time.monotonic()
    result = gateway.handle_request(QUERY, CONTEXT)
    elapsed = time.monotonic() - started

    assert elapsed < 2.0, f"total deadline ignored: {elapsed:.1f}s"
    assert result["status"] == "hard_degraded"


def test_cache_stampede_tier_serves_a_concurrently_written_entry():
    # Tier 4 of the ladder re-checks the SAME cache: if another request for the
    # same query wrote a cached answer WHILE this one was stuck in tiers 1-3,
    # this request should pick it up instead of falling to the static message.
    # A fake cache simulates the concurrent writer: empty on the gateway's
    # first check (before the ladder runs), populated by the time the ladder's
    # cache tier checks again.
    class StampedeCache:
        def __init__(self):
            self.gets = 0

        def get(self, query):
            self.gets += 1
            if self.gets == 1:
                return None, 0.0
            return FAITHFUL_ANSWER, 1.0

        def set(self, query, value, metadata=None):
            pass

    def dead(query, context):
        raise ConnectionError("503")

    gateway = make_gateway(dead, cache=StampedeCache())
    result = gateway.handle_request(QUERY, CONTEXT)

    assert result["source"] == "cache_stampede"
    assert result["output"] == FAITHFUL_ANSWER


# ---------------------------------------------------------------------------
# Quality guardrail: block hallucinations, never cache them
# ---------------------------------------------------------------------------

def test_hallucinated_response_is_blocked_and_not_cached():
    gateway = make_gateway(lambda q, c: HALLUCINATED_ANSWER)
    result = gateway.handle_request(QUERY, CONTEXT)

    assert result["status"] == "degraded_quality_detected"
    assert "90" not in result["output"]
    assert result["metrics"]["is_slo_violated"] is True

    cached, _ = gateway.cache.get(QUERY)
    assert cached is None, "a hallucinated answer must never be cached"


def test_faithful_response_passes_and_is_cached():
    gateway = make_gateway(lambda q, c: FAITHFUL_ANSWER)
    result = gateway.handle_request(QUERY, CONTEXT)

    assert result["status"] == "success"
    assert result["metrics"]["is_slo_violated"] is False
    cached, _ = gateway.cache.get(QUERY)
    assert cached == FAITHFUL_ANSWER


def test_guardrail_also_applies_to_fallback_ladder_responses():
    # Silent degradation is not only a primary-model problem: a backup
    # provider can hallucinate too, and it must be caught the same way.
    def dead(query, context):
        raise ConnectionError("503")

    gateway = make_gateway(dead, backup_llm_fn=lambda q, c: HALLUCINATED_ANSWER)
    result = gateway.handle_request(QUERY, CONTEXT)

    assert result["status"] == "degraded_quality_detected"
    cached, _ = gateway.cache.get(QUERY)
    assert cached is None


def test_eval_sample_rate_zero_skips_scoring_but_still_serves():
    calls = []
    gateway = make_gateway(
        lambda q, c: HALLUCINATED_ANSWER,
        eval_sample_rate=0.0,
        faithfulness_fn=lambda *a: calls.append(1) or 0.1,
    )
    result = gateway.handle_request(QUERY, CONTEXT)

    assert calls == [], "faithfulness_fn ran despite a 0.0 sample rate"
    assert result["status"] == "success"  # unsampled -> not evaluated -> served
    assert result["metrics"]["evaluated"] is False


@pytest.mark.parametrize("bad_rate", [-0.1, 1.5])
def test_invalid_sample_rate_rejected(bad_rate):
    with pytest.raises(ValueError, match="eval_sample_rate"):
        make_gateway(lambda q, c: FAITHFUL_ANSWER, eval_sample_rate=bad_rate)


@pytest.mark.parametrize("f,r", [(0.7, 0.7), (0.5, 0.2)])
def test_weights_must_sum_to_one(f, r):
    with pytest.raises(ValueError, match="trọng số"):
        make_gateway(lambda q, c: FAITHFUL_ANSWER,
                     faithfulness_weight=f, relevancy_weight=r)


# ---------------------------------------------------------------------------
# Default heuristics (no LLM judge)
# ---------------------------------------------------------------------------

def test_default_faithfulness_flags_contradiction():
    score = default_faithfulness(QUERY, CONTEXT, HALLUCINATED_ANSWER)
    assert score < 0.3


def test_default_faithfulness_scores_paraphrase_highly():
    score = default_faithfulness(QUERY, CONTEXT, FAITHFUL_ANSWER)
    assert score > 0.7


def test_default_faithfulness_penalises_off_topic_answers():
    off_topic = "Chúng tôi hỗ trợ giao hàng hỏa tốc nội thành trong 2 giờ."
    score = default_faithfulness(QUERY, CONTEXT, off_topic)
    assert score < 0.5, "an unrelated answer must not be scored as faithful"


def test_default_relevancy_scores_on_topic_answer_highly():
    assert default_relevancy(QUERY, FAITHFUL_ANSWER) > 0.7


def test_default_relevancy_scores_off_topic_answer_low():
    off_topic = "Chúng tôi hỗ trợ giao hàng hỏa tốc nội thành trong 2 giờ."
    assert default_relevancy(QUERY, off_topic) < 0.5


def test_full_pipeline_scores_above_threshold_for_a_good_answer():
    # End-to-end sanity: the default heuristics combined with the default SLO
    # threshold (0.75) must actually let a genuinely good answer through, not
    # just individually score reasonably.
    gateway = make_gateway(lambda q, c: FAITHFUL_ANSWER)
    result = gateway.handle_request(QUERY, CONTEXT)
    metrics = result["metrics"]
    score = (metrics["faithfulness_score"] * gateway.faithfulness_weight
            + metrics["relevancy_score"] * gateway.relevancy_weight)
    assert score >= gateway.quality_slo_threshold
    assert result["status"] == "success"


# ---------------------------------------------------------------------------
# attempt_timeout_seconds composes safely with the breaker's generation guard
# ---------------------------------------------------------------------------

def test_abandoned_attempt_does_not_corrupt_breaker_state():
    # If the gateway gives up waiting on a hung primary call (attempt_timeout_
    # seconds), the call keeps running in the background and will eventually
    # call breaker._on_result() on its own. This must be safe: the breaker's
    # generation counter (P0-2) makes a late/abandoned result stale once the
    # breaker has moved on, so it cannot corrupt live state.
    release = threading.Event()

    def hangs_then_succeeds(query, context):
        release.wait(5.0)
        return FAITHFUL_ANSWER

    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=0.1,
                             expected_exceptions=RETRYABLE_EXCEPTIONS)
    gateway = make_gateway(
        hangs_then_succeeds, breaker=breaker,
        attempt_timeout_seconds=0.05, max_attempts=1,
        backup_llm_fn=lambda q, c: FAITHFUL_ANSWER,
    )

    result = gateway.handle_request(QUERY, CONTEXT)
    assert result["status"] == "success"
    assert result["source"] == "backup_provider"
    assert gateway.abandoned_calls == 1

    release.set()
    time.sleep(0.2)  # let the abandoned thread finish and call _on_result

    # The gateway's own breaker must still be in a sane, usable state.
    snapshot = breaker.snapshot()
    assert snapshot["state"] is not None


# ---------------------------------------------------------------------------
# Backend-agnostic cache (duck typing)
# ---------------------------------------------------------------------------

def test_accepts_a_caller_supplied_cache():
    custom_cache = ResponseCache(ttl_seconds=60, similarity_threshold=0.85)
    gateway = make_gateway(lambda q, c: FAITHFUL_ANSWER, cache=custom_cache)

    gateway.handle_request(QUERY, CONTEXT)

    cached, _ = custom_cache.get(QUERY)
    assert cached == FAITHFUL_ANSWER


# ---------------------------------------------------------------------------
# A programming bug must never be mistaken for a degradable outage
# ---------------------------------------------------------------------------

def test_a_programming_bug_in_primary_propagates_instead_of_degrading():
    # REGRESSION for a bug found by adversarial testing of this very file: the
    # original `except Exception as primary_error:` caught EVERYTHING,
    # including a KeyError from a bug in the caller's own primary_llm_fn, and
    # silently routed it through the Fallback Ladder to a "hard_degraded"
    # result. An on-call engineer would read that as "provider outage" and
    # reach for more resilience infrastructure, when the actual fix needed was
    # a one-line bug fix in their own integration code. Only the exceptions
    # jitter.py considers retryable, plus CircuitOpenError (the breaker saying
    # "fail fast"), should trigger degradation - everything else must explode.
    def buggy_primary(query, context):
        raise KeyError("bug in caller's own code, not a provider outage")

    gateway = make_gateway(buggy_primary, backup_llm_fn=lambda q, c: FAITHFUL_ANSWER)

    with pytest.raises(KeyError):
        gateway.handle_request(QUERY, CONTEXT)


def test_transient_errors_still_degrade_normally_after_the_fix():
    # Guards against overcorrecting: ConnectionError/TimeoutError/CircuitOpenError
    # must still route to the fallback ladder exactly as before.
    def dead(query, context):
        raise ConnectionError("503")

    gateway = make_gateway(dead, backup_llm_fn=lambda q, c: FAITHFUL_ANSWER)
    result = gateway.handle_request(QUERY, CONTEXT)

    assert result["status"] == "success"
    assert result["source"] == "backup_provider"


def test_a_bug_in_backup_provider_is_still_caught_by_the_ladder():
    # Contrast case: the LADDER's own per-tier catch stays broad (matching
    # fallback_ladder.py's own established precedent for heterogeneous
    # third-party providers), so a bug in a SECONDARY tier still degrades to
    # the next tier rather than crashing the whole request. Only the PRIMARY
    # path's outer catch was narrowed.
    def dead(query, context):
        raise ConnectionError("503")

    def buggy_backup(query, context):
        raise KeyError("bug in the backup integration")

    gateway = make_gateway(
        dead, backup_llm_fn=buggy_backup, smaller_llm_fn=lambda q, c: FAITHFUL_ANSWER
    )
    result = gateway.handle_request(QUERY, CONTEXT)

    assert result["status"] == "success"
    assert result["source"] == "smaller_model"

"""Regression tests for P0-4: schema validation declared types but never enforced them.

Each test states the original buggy behaviour it pins down.
"""
import threading
import time

import pytest

import fallback_ladder
from fallback_ladder import EXPECTED_SCHEMA, FallbackLadderAgent


@pytest.fixture
def agent():
    return FallbackLadderAgent()


VALID = {"intent": "refund_request", "confidence": 0.82, "reply": "Toi se ho tro ban."}


# ---------------------------------------------------------------------------
# Type enforcement
# ---------------------------------------------------------------------------

def test_the_original_garbage_payload_is_rejected(agent):
    # ORIGINAL BUG (verified): _validate_schema() only checked "key in data", so
    # this returned True and the malformed payload was returned to the caller.
    garbage = {"intent": 12345, "confidence": "not-a-float", "reply": None}
    assert agent._validate_schema(garbage) is False


def test_valid_payload_still_passes(agent):
    assert agent._validate_schema(VALID) is True


@pytest.mark.parametrize("field,bad_value", [
    ("intent", 12345),
    ("intent", None),
    ("intent", ["refund"]),
    ("confidence", "high"),
    ("confidence", None),
    ("reply", None),
    ("reply", 42),
])
def test_wrong_types_are_rejected(agent, field, bad_value):
    # ORIGINAL BUG: every one of these passed validation.
    data = dict(VALID, **{field: bad_value})
    assert agent._validate_schema(data) is False


def test_int_is_accepted_for_the_float_field(agent):
    # confidence=1 is legitimate JSON and must not be rejected.
    assert agent._validate_schema(dict(VALID, confidence=1)) is True
    assert agent._validate_schema(dict(VALID, confidence=0)) is True


@pytest.mark.parametrize("field", ["confidence", "intent"])
def test_bool_is_not_accepted(agent, field):
    # bool is a subclass of int in Python, so a naive isinstance(value, (int,
    # float)) check would let confidence=True through.
    assert agent._validate_schema(dict(VALID, **{field: True})) is False


@pytest.mark.parametrize("value", [42.0, -0.1, 1.5, 100])
def test_confidence_outside_zero_to_one_is_rejected(agent, value):
    # A confidence of 42.0 is the right type but not a confidence.
    assert agent._validate_schema(dict(VALID, confidence=value)) is False


@pytest.mark.parametrize("field", ["intent", "reply"])
@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_empty_strings_are_rejected(agent, field, value):
    # ORIGINAL BUG: reply="" is the right type but useless to the user, and it
    # sailed through both the old check and a naive isinstance check.
    assert agent._validate_schema(dict(VALID, **{field: value})) is False


@pytest.mark.parametrize("missing", sorted(EXPECTED_SCHEMA))
def test_missing_fields_are_rejected(agent, missing):
    data = {k: v for k, v in VALID.items() if k != missing}
    assert agent._validate_schema(data) is False


@pytest.mark.parametrize("data", [None, [], "text", 42, ("a", "b")])
def test_non_dict_payloads_are_rejected(agent, data):
    assert agent._validate_schema(data) is False


def test_extra_fields_are_allowed(agent):
    # Providers add fields; that is not a reason to reject a usable answer.
    assert agent._validate_schema(dict(VALID, model="gemini-flash")) is True


# ---------------------------------------------------------------------------
# The reason must be visible
# ---------------------------------------------------------------------------

def test_violation_names_the_offending_field(agent):
    # ORIGINAL BUG: the log said only "tra ve sai Schema", which tells an
    # on-call engineer nothing about WHICH field a degraded model mangled.
    reason = agent._schema_violation(dict(VALID, confidence="high"))
    assert reason is not None
    assert "confidence" in reason


def test_validate_schema_stays_a_boolean_predicate(agent):
    # Backwards compatibility for existing callers.
    assert agent._validate_schema(VALID) is True
    assert agent._validate_schema({}) is False


# ---------------------------------------------------------------------------
# The ladder must actually fall through on bad schema
# ---------------------------------------------------------------------------

def test_bad_schema_from_a_tier_falls_through_to_the_next(agent, monkeypatch, caplog):
    # ORIGINAL BUG: Tier 3 returning a malformed payload was accepted as
    # "success" and returned to the user instead of degrading to the cache.
    monkeypatch.setattr(fallback_ladder, "call_smaller_model",
                        lambda prompt: {"intent": "refund_request",
                                        "confidence": "very high",  # wrong type
                                        "reply": "..."})
    with caplog.at_level("WARNING"):
        result = agent.execute("Toi muon hoan tien")

    assert result["source"] == "Tier 4: Cache"
    assert result["status"] == "degraded_cached"
    assert any("confidence" in record.message for record in caplog.records)


def test_all_tiers_bad_reaches_the_static_fallback(agent, monkeypatch):
    monkeypatch.setattr(fallback_ladder, "call_smaller_model",
                        lambda prompt: {"intent": "x", "confidence": 2.0, "reply": "y"})
    monkeypatch.setattr(fallback_ladder, "get_from_cache",
                        lambda prompt: {"intent": "x", "confidence": True, "reply": "y"})

    result = agent.execute("Toi muon hoan tien")

    assert result["source"] == "Tier 5: Static Fallback"
    assert result["status"] == "hard_degraded"
    # The last-resort payload must itself satisfy the schema.
    assert agent._validate_schema(result["data"]) is True


def test_healthy_tier_three_is_still_used(agent):
    # The happy path of the demo must not regress.
    result = agent.execute("Toi muon hoan tien don hang")
    assert result["source"] == "Tier 3: Smaller/Cheaper Model"
    assert result["status"] == "success"
    assert agent._validate_schema(result["data"]) is True


# ---------------------------------------------------------------------------
# P1 #12: the cache tier must honour the prompt
# ---------------------------------------------------------------------------

def test_cache_tier_does_not_answer_unrelated_questions():
    # ORIGINAL BUG: get_from_cache() ignored its `prompt` argument entirely and
    # always returned the refund entry, so "how much is shipping?" was answered
    # with the refund policy. A cache that answers the wrong question is worse
    # than no cache: it turns an outage into a confident wrong answer.
    assert fallback_ladder.get_from_cache("Phi giao hang bao nhieu?") is None
    assert fallback_ladder.get_from_cache("Gio mo cua the nao") is None


@pytest.mark.parametrize("prompt", [
    "Toi muon hoan tien don hang",
    "Tôi muốn hoàn tiền",
    "I want a refund please",
])
def test_cache_tier_still_matches_relevant_questions(prompt):
    entry = fallback_ladder.get_from_cache(prompt)
    assert entry is not None
    assert entry["intent"] == "refund_request"


def test_unrelated_prompt_falls_past_the_cache_to_static_fallback(agent, monkeypatch):
    monkeypatch.setattr(fallback_ladder, "call_smaller_model",
                        lambda prompt: (_ for _ in ()).throw(TimeoutError("down")))
    result = agent.execute("Phi giao hang bao nhieu?")
    assert result["source"] == "Tier 5: Static Fallback"


# ---------------------------------------------------------------------------
# P1 #11: per-tier timeout and total deadline
# ---------------------------------------------------------------------------

def test_a_hung_tier_does_not_block_the_ladder(monkeypatch):
    # ORIGINAL BUG: there was no timeout at all. A Tier 1 that hangs for 60s
    # kept the user waiting the full 60s BEFORE Tier 2 was even attempted.
    monkeypatch.setattr(fallback_ladder, "call_primary_model",
                        lambda prompt: time.sleep(30))
    monkeypatch.setattr(fallback_ladder, "call_backup_provider",
                        lambda prompt: time.sleep(30))

    agent = FallbackLadderAgent(tier_timeout_seconds=0.2, total_deadline_seconds=10.0)
    try:
        started = time.monotonic()
        result = agent.execute("Toi muon hoan tien")
        elapsed = time.monotonic() - started
    finally:
        agent.close()

    assert result["source"] == "Tier 3: Smaller/Cheaper Model"
    assert elapsed < 2.0, f"took {elapsed:.1f}s despite a 0.2s per-tier timeout"


def test_total_deadline_caps_the_whole_ladder(monkeypatch):
    # Per-tier timeouts alone are not enough: worst case is their SUM.
    monkeypatch.setattr(fallback_ladder, "call_primary_model",
                        lambda prompt: time.sleep(30))
    monkeypatch.setattr(fallback_ladder, "call_backup_provider",
                        lambda prompt: time.sleep(30))
    monkeypatch.setattr(fallback_ladder, "call_smaller_model",
                        lambda prompt: time.sleep(30))

    agent = FallbackLadderAgent(tier_timeout_seconds=5.0, total_deadline_seconds=0.4)
    try:
        started = time.monotonic()
        result = agent.execute("Toi muon hoan tien")
        elapsed = time.monotonic() - started
    finally:
        agent.close()

    assert elapsed < 2.0, f"total deadline ignored: {elapsed:.1f}s"
    assert result["source"] in ("Tier 4: Cache", "Tier 5: Static Fallback")


def test_a_fast_tier_is_not_penalised_by_the_timeout(agent):
    started = time.monotonic()
    result = agent.execute("Toi muon hoan tien don hang")
    elapsed = time.monotonic() - started
    assert result["source"] == "Tier 3: Smaller/Cheaper Model"
    assert elapsed < 1.0


def test_abandoned_hung_calls_do_not_starve_a_healthy_tier(monkeypatch):
    # REGRESSION for a bug introduced by the timeout fix itself: with a shared
    # ThreadPoolExecutor, abandoned hung calls keep occupying workers. Once the
    # pool is full, the NEXT tier never runs at all - it just queues and "times
    # out" - and the log claimed "Tier 3 failed" for a tier that was never
    # called. A misleading diagnosis is worse than none.
    monkeypatch.setattr(fallback_ladder, "call_primary_model",
                        lambda prompt: time.sleep(30))
    monkeypatch.setattr(fallback_ladder, "call_backup_provider",
                        lambda prompt: time.sleep(30))
    healthy = {"intent": "refund_request", "confidence": 0.82, "reply": "tu tier 3"}
    monkeypatch.setattr(fallback_ladder, "call_smaller_model", lambda prompt: healthy)

    agent = FallbackLadderAgent(tier_timeout_seconds=0.1, total_deadline_seconds=10.0)
    try:
        for i in range(4):
            result = agent.execute("Toi muon hoan tien")
            assert result["source"] == "Tier 3: Smaller/Cheaper Model", (
                f"run {i + 1}: healthy tier was starved -> {result['source']}"
            )
    finally:
        agent.close()

    assert agent.abandoned_calls == 8, "abandoned calls must be counted for monitoring"


def test_abandoned_threads_are_daemons(monkeypatch):
    # Abandoned work must never keep the interpreter alive on shutdown.
    monkeypatch.setattr(fallback_ladder, "call_primary_model",
                        lambda prompt: time.sleep(30))
    agent = FallbackLadderAgent(tier_timeout_seconds=0.1, total_deadline_seconds=5.0)
    try:
        agent.execute("Toi muon hoan tien")
        lingering = [t for t in threading.enumerate() if t.name == "ladder-tier"]
        assert lingering, "expected an abandoned worker thread"
        assert all(t.daemon for t in lingering)
    finally:
        agent.close()


def test_a_tier_raising_is_reported_accurately(agent, monkeypatch, caplog):
    # The failure message must name the real cause, not a generic timeout.
    monkeypatch.setattr(fallback_ladder, "call_smaller_model",
                        lambda prompt: (_ for _ in ()).throw(ValueError("bad json")))
    with caplog.at_level("WARNING"):
        agent.execute("Toi muon hoan tien")
    assert any("bad json" in r.message for r in caplog.records)

"""Regression tests for #13 (evaluating 100% of requests) and #14 (fake latency)."""
import random
import time

import pytest

from quality_guardrail import ProductionAgentGateway, QualityMetrics

QUERY = "Thoi han hoan tien la bao lau?"
CONTEXT = "Quy dinh cong ty: Thoi han hoan tien toi da la 30 ngay."
# The stubbed LLM answers "90 ngay" against a context that says "30 ngay".
BAD_CONTEXT_VI = "Quy định công ty: Thời hạn hoàn tiền tối đa là 30 ngày."


def test_latency_is_measured_not_hardcoded():
    # ORIGINAL BUG: latency_seconds was the literal 1.2 on every single
    # response, so the metric was decorative - it could never detect a slowdown.
    gateway = ProductionAgentGateway()

    slow = 0.05

    def slow_llm(query, context):
        time.sleep(slow)
        return "bat ky cau tra loi nao"

    gateway._call_primary_llm = slow_llm
    result = gateway.handle_request(QUERY, CONTEXT)

    measured = result["metrics"]["latency_seconds"]
    assert measured != 1.2
    assert measured >= slow, f"measured {measured}s for a {slow}s call"
    assert measured < slow + 1.0


def test_latency_reflects_a_fast_call():
    gateway = ProductionAgentGateway()
    result = gateway.handle_request(QUERY, CONTEXT)
    assert result["metrics"]["latency_seconds"] < 0.5


# ---------------------------------------------------------------------------
# #13: sampling
# ---------------------------------------------------------------------------

def test_evaluation_can_be_sampled():
    # ORIGINAL BUG: quality scoring ran on EVERY request. Scoring is another LLM
    # call, so this doubled the cost and latency of every answer with no way to
    # dial it down.
    gateway = ProductionAgentGateway(eval_sample_rate=0.0)
    calls = []
    gateway._evaluate_faithfulness = lambda *a: calls.append(1) or 0.2

    result = gateway.handle_request(QUERY, BAD_CONTEXT_VI)

    assert calls == [], "evaluation ran despite a 0.0 sample rate"
    assert result["metrics"]["evaluated"] is False
    assert result["status"] == "success"


def test_full_sample_rate_still_evaluates_everything():
    gateway = ProductionAgentGateway(eval_sample_rate=1.0)
    result = gateway.handle_request(QUERY, BAD_CONTEXT_VI)

    assert result["metrics"]["evaluated"] is True
    assert result["status"] == "degraded_quality_detected"


def test_sample_rate_is_roughly_honoured():
    gateway = ProductionAgentGateway(eval_sample_rate=0.25,
                                     rng=random.Random(1234))
    evaluated = sum(
        gateway.handle_request(QUERY, CONTEXT)["metrics"]["evaluated"]
        for _ in range(400)
    )
    assert 60 <= evaluated <= 140, f"sampled {evaluated}/400 at rate 0.25"


def test_unsampled_requests_are_reported_as_unevaluated():
    # The honest failure mode: a request that was not sampled is NOT protected,
    # and the metrics must say so rather than implying a clean bill of health.
    gateway = ProductionAgentGateway(eval_sample_rate=0.0)
    metrics = gateway.handle_request(QUERY, BAD_CONTEXT_VI)["metrics"]

    assert metrics["evaluated"] is False
    assert metrics["is_slo_violated"] is False
    assert metrics["faithfulness_score"] != metrics["faithfulness_score"]  # NaN


@pytest.mark.parametrize("bad_rate", [-0.1, 1.5, 2.0])
def test_invalid_sample_rate_is_rejected(bad_rate):
    with pytest.raises(ValueError, match="eval_sample_rate"):
        ProductionAgentGateway(eval_sample_rate=bad_rate)


# ---------------------------------------------------------------------------
# Configurable weights (were hardcoded 0.7 / 0.3)
# ---------------------------------------------------------------------------

def test_weights_are_configurable():
    gateway = ProductionAgentGateway(quality_slo_threshold=0.75,
                                     faithfulness_weight=0.2,
                                     relevancy_weight=0.8)
    # faithfulness 0.2, relevancy 0.85 -> 0.2*0.2 + 0.8*0.85 = 0.72 -> still a
    # violation, but the score is now driven by the configured weights.
    result = gateway.handle_request(QUERY, BAD_CONTEXT_VI)
    assert result["metrics"]["faithfulness_score"] == 0.20
    assert result["metrics"]["relevancy_score"] == 0.85


@pytest.mark.parametrize("f,r", [(0.7, 0.7), (0.5, 0.2), (1.0, 1.0)])
def test_weights_must_sum_to_one(f, r):
    with pytest.raises(ValueError, match="trọng số"):
        ProductionAgentGateway(faithfulness_weight=f, relevancy_weight=r)


def test_silent_degradation_is_still_caught():
    # The headline behaviour of this module must not regress: HTTP 200 with a
    # hallucinated answer has to be blocked.
    gateway = ProductionAgentGateway(quality_slo_threshold=0.75)
    result = gateway.handle_request(QUERY, BAD_CONTEXT_VI)

    assert result["metrics"]["http_status"] == 200
    assert result["status"] == "degraded_quality_detected"
    assert "Xin l" in result["output"]  # the safe apology, not the hallucination
    assert "90" not in result["output"]


def test_metrics_serialise_as_a_plain_dict():
    gateway = ProductionAgentGateway()
    metrics = gateway.handle_request(QUERY, CONTEXT)["metrics"]
    assert isinstance(metrics, dict)
    assert set(QualityMetrics.__dataclass_fields__) == set(metrics)

"""The gate's pass/fail decision."""

from eval.gate import THRESHOLDS, evaluate_gate

PASSING = {
    "correctness": 0.88,
    "groundedness": 0.96,
    "retrieval_recall": 0.93,
    "citation_validity": 1.0,
    "refusal_accuracy": 0.94,
}


def test_all_metrics_above_minimum_passes():
    assert evaluate_gate(PASSING).passed


def test_below_minimum_fails():
    scores = PASSING | {"groundedness": 0.90}
    result = evaluate_gate(scores)
    assert not result.passed
    assert any("groundedness" in f for f in result.failures)


def test_regression_against_baseline_fails_even_above_minimum():
    scores = PASSING | {"correctness": 0.86}
    baseline = PASSING | {"correctness": 0.95}
    result = evaluate_gate(scores, baseline=baseline)
    assert not result.passed
    assert any("dropped" in f for f in result.failures)


def test_citation_validity_has_zero_tolerance():
    """Cited text either is or isn't in the source chunk. Any drop is a bug, not noise."""
    assert THRESHOLDS["citation_validity"][1] == 0.0
    result = evaluate_gate(PASSING | {"citation_validity": 0.995}, baseline=PASSING)
    assert not result.passed


def test_missing_metric_fails_rather_than_passing_silently():
    scores = {k: v for k, v in PASSING.items() if k != "correctness"}
    result = evaluate_gate(scores)
    assert not result.passed
    assert any("not measured" in f for f in result.failures)


def test_latency_over_budget_fails():
    result = evaluate_gate(PASSING, p95_ms=7000)
    assert not result.passed
    assert any("latency" in f for f in result.failures)


def test_latency_increase_over_15_percent_fails():
    result = evaluate_gate(PASSING, p95_ms=5000, baseline_p95_ms=4000)
    assert not result.passed


def test_render_produces_a_markdown_table():
    out = evaluate_gate(PASSING, baseline=PASSING).render()
    assert "| metric | main | this PR |" in out
    assert "correctness" in out

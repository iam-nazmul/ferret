"""Graph topology and node behavior, with fakes for every external service."""

import pytest

from app.graph.build import _after_grade, _after_route, build_graph, rewrite
from app.graph.nodes.route import route
from app.graph.nodes.verify import verify
from app.graph.state import initial_state
from tests.conftest import FakeReranker, FakeRetriever, make_chunk


async def test_route_detects_multi_hop():
    result = await route({"question": "How does X compare to Y?"})
    assert result["is_multi_hop"]


async def test_route_treats_simple_questions_as_simple():
    result = await route({"question": "What is the refund window?"})
    assert not result["is_multi_hop"]


def test_route_edge_targets():
    assert _after_route({"is_multi_hop": True}) == "decompose"
    assert _after_route({"is_multi_hop": False}) == "retrieve"


def test_sufficient_answer_goes_straight_to_generate():
    assert _after_grade({"sufficient": True, "retry_count": 0}) == "generate"


def test_insufficient_triggers_exactly_one_retry():
    assert _after_grade({"sufficient": False, "retry_count": 0}) == "rewrite"
    assert _after_grade({"sufficient": False, "retry_count": 1}) == "generate"


async def test_rewrite_widens_with_headings_and_increments_retry():
    state = {
        "question": "refund window",
        "candidates": [make_chunk(heading_path=["Billing", "Refunds"])],
        "retry_count": 0,
    }
    result = await rewrite(state)
    assert result["retry_count"] == 1
    assert "Billing" in result["sub_queries"][0]


async def test_verify_flags_uncited_claims_without_blocking():
    state = {
        "answer": "The retention period is 90 days for all customer records.",
        "citations": [],
    }
    result = await verify(state)
    assert result["groundedness_violation"] is True
    assert result["messages"], "the answer is still returned"


def test_graph_compiles():
    graph = build_graph(FakeRetriever(), FakeReranker())
    assert graph is not None


def test_initial_state_carries_groups_and_zero_retries():
    state = initial_state("q", "user-1", frozenset({"eng"}))
    assert state["user_groups"] == frozenset({"eng"})
    assert state["retry_count"] == 0


@pytest.mark.parametrize(
    "question,expected",
    [
        ("What is the difference between A and B?", True),
        ("Compare our SLA to theirs", True),
        ("What is the SLA?", False),
        ("How long is the refund window?", False),
    ],
)
async def test_routing_signals(question, expected):
    assert (await route({"question": question}))["is_multi_hop"] is expected

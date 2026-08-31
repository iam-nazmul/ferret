"""Citation coverage. verify() flags, it never blocks."""

from app.graph.nodes.verify import (
    is_factual,
    split_sentences,
    uncited_factual_sentences,
)


def test_splits_sentences():
    assert len(split_sentences("One. Two! Three?")) == 3


def test_hedging_sentences_are_not_factual():
    assert not is_factual("Here is what I found in the documents provided.")
    assert not is_factual("Based on the documents, the following applies here.")


def test_short_sentences_are_not_factual():
    assert not is_factual("Yes.")


def test_claims_with_numbers_are_factual():
    assert is_factual("The refund window is 30 days from the invoice date.")


def test_supported_sentence_is_not_flagged():
    answer = "The refund window is 30 days from the invoice date."
    assert uncited_factual_sentences(answer, ["refund window is 30 days from the invoice"]) == []


def test_unsupported_sentence_is_flagged():
    answer = "The refund window is 30 days. Enterprise customers also get priority phone support."
    uncited = uncited_factual_sentences(answer, ["refund window is 30 days"])
    assert len(uncited) == 1
    assert "priority phone support" in uncited[0]


def test_no_citations_flags_every_factual_sentence():
    answer = "The retention period is 90 days for all customer data records."
    assert len(uncited_factual_sentences(answer, [])) == 1


def test_empty_answer_is_not_a_violation():
    assert uncited_factual_sentences("", ["anything"]) == []

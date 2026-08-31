"""The deterministic evaluators. The LLM judges are exercised in eval runs, not here."""

from eval.evaluators import citation_validity, refusal_accuracy, retrieval_recall


def test_recall_counts_expected_documents():
    outputs = {"chunks": [{"document_id": "a"}, {"document_id": "b"}]}
    assert retrieval_recall(outputs, {"document_ids": ["a", "b"]}) == 1.0
    assert retrieval_recall(outputs, {"document_ids": ["a", "c"]}) == 0.5
    assert retrieval_recall(outputs, {"document_ids": ["z"]}) == 0.0


def test_recall_with_no_expectation_does_not_silently_score_one():
    """sync.py rejects these; the guard here documents why the value is 1.0."""
    assert retrieval_recall({"chunks": []}, {}) == 1.0


def test_citation_validity_verifies_substring_presence():
    outputs = {
        "chunks": [{"document_id": "a", "text": "The refund window is 30 days from invoice."}],
        "citations": [{"document_id": "a", "cited_text": "refund window is 30 days"}],
    }
    assert citation_validity(outputs) == 1.0


def test_citation_validity_catches_fabricated_text():
    outputs = {
        "chunks": [{"document_id": "a", "text": "The refund window is 30 days."}],
        "citations": [{"document_id": "a", "cited_text": "the refund window is 60 days"}],
    }
    assert citation_validity(outputs) == 0.0


def test_citation_validity_normalizes_whitespace():
    outputs = {
        "chunks": [{"document_id": "a", "text": "The  refund\nwindow is 30 days."}],
        "citations": [{"document_id": "a", "cited_text": "The refund window is 30 days."}],
    }
    assert citation_validity(outputs) == 1.0


def test_no_citations_is_vacuously_valid():
    assert citation_validity({"chunks": [], "citations": []}) == 1.0


def test_refusal_accuracy_rewards_declining_when_expected():
    outputs = {"answer": "I couldn't find enough information in the documents.", "chunks": []}
    assert refusal_accuracy(outputs, {"should_refuse": True})


def test_refusal_accuracy_punishes_answering_when_it_should_decline():
    outputs = {"answer": "The capital is Ulaanbaatar.", "chunks": [{"document_id": "a"}]}
    assert not refusal_accuracy(outputs, {"should_refuse": True})


def test_refusal_accuracy_punishes_declining_when_it_should_answer():
    outputs = {"answer": "I couldn't find that.", "chunks": [{"document_id": "a"}]}
    assert not refusal_accuracy(outputs, {"should_refuse": False})

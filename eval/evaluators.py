"""Evaluators for the LangSmith gate.

LangSmith injects arguments BY PARAMETER NAME (inputs, outputs, reference_outputs) —
renaming a parameter produces a confusing runtime error, not a type error.

Three of the five are deterministic on purpose: free, fast, reproducible, and nobody
argues with their verdicts.
"""

import re
from typing import Annotated, Any, TypedDict

from app.llm.models import JUDGE_MODEL

CORRECTNESS_INSTRUCTIONS = """You are a teacher grading a quiz. You will be given a QUESTION, \
the GROUND TRUTH ANSWER, and the STUDENT ANSWER.

Grade criteria:
(1) Grade only on factual accuracy relative to the ground truth answer.
(2) The student answer must not contain statements that conflict with the ground truth.
(3) Extra information is acceptable as long as it is factually accurate.

Explain your reasoning step by step before giving a verdict."""

GROUNDEDNESS_INSTRUCTIONS = """Grade whether the ANSWER is fully grounded in the DOCUMENTS.

Return true only if every factual claim in the answer is supported by the documents.
Return false if the answer asserts anything the documents do not support, even if that \
assertion happens to be true in the world — unsupported claims are the failure mode we \
are measuring."""


class CorrectnessGrade(TypedDict):
    explanation: Annotated[str, ..., "Reasoning for the score"]
    correct: Annotated[bool, ..., "True if correct relative to the reference"]


class GroundednessGrade(TypedDict):
    explanation: Annotated[str, ..., "Reasoning for the score"]
    grounded: Annotated[bool, ..., "True if every claim is supported by the documents"]


def _grader(schema):
    from langchain.chat_models import init_chat_model

    return init_chat_model(JUDGE_MODEL).with_structured_output(schema)


# --- LLM judges ---------------------------------------------------------------


def correctness(inputs: dict, outputs: dict, reference_outputs: dict) -> bool:
    """Factual accuracy relative to the reference answer."""
    grade = _grader(CorrectnessGrade).invoke(
        [
            {"role": "system", "content": CORRECTNESS_INSTRUCTIONS},
            {
                "role": "user",
                "content": (
                    f"QUESTION: {inputs['question']}\n"
                    f"GROUND TRUTH ANSWER: {reference_outputs.get('answer', '')}\n"
                    f"STUDENT ANSWER: {outputs.get('answer', '')}"
                ),
            },
        ]
    )
    return bool(grade["correct"])


def groundedness(inputs: dict, outputs: dict) -> bool:
    """Whether every claim in the answer is supported by the retrieved chunks."""
    chunks = outputs.get("chunks") or []
    if not chunks:
        # No documents and no answer is grounded-by-vacuity; no documents with an answer is not.
        return not (outputs.get("answer") or "").strip() or outputs.get("refused", False)

    documents = "\n\n---\n\n".join(c.get("text", "") for c in chunks)
    grade = _grader(GroundednessGrade).invoke(
        [
            {"role": "system", "content": GROUNDEDNESS_INSTRUCTIONS},
            {
                "role": "user",
                "content": f"ANSWER: {outputs.get('answer', '')}\n\nDOCUMENTS:\n{documents}",
            },
        ]
    )
    return bool(grade["grounded"])


# --- Deterministic ------------------------------------------------------------


def retrieval_recall(outputs: dict, reference_outputs: dict) -> float:
    """Fraction of expected document_ids that reached top-k. No LLM."""
    expected = set(reference_outputs.get("document_ids") or [])
    if not expected:
        # eval/sync.py rejects these; guard anyway so a stray example can't score 1.0.
        return 1.0
    got = {c.get("document_id") for c in (outputs.get("chunks") or [])}
    return len(expected & got) / len(expected)


def citation_validity(outputs: dict) -> float:
    """Fraction of cited_text spans genuinely present in their source chunk. No LLM.

    Zero tolerance in the gate: this either holds or there is a bug in app/llm/citations.py.
    """
    citations = outputs.get("citations") or []
    if not citations:
        return 1.0

    chunk_text = {c.get("document_id"): c.get("text", "") for c in (outputs.get("chunks") or [])}
    corpus = " ".join(chunk_text.values())

    valid = 0
    for c in citations:
        cited = (c.get("cited_text") or "").strip()
        if not cited:
            continue
        if _normalize(cited) in _normalize(corpus):
            valid += 1
    return valid / len(citations)


def refusal_accuracy(outputs: dict, reference_outputs: dict) -> bool:
    """On the refusal set: did the system actually decline instead of inventing an answer?"""
    should_refuse = bool(reference_outputs.get("should_refuse"))
    answer = (outputs.get("answer") or "").lower()
    refused = bool(
        re.search(
            r"couldn'?t find|could not find|don'?t have|do not have|no information|"
            r"not (?:in|covered by) the (?:indexed )?documents|unable to answer",
            answer,
        )
    ) or not (outputs.get("chunks") or [])
    return refused == should_refuse


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


ALL_EVALUATORS: list[Any] = [
    correctness,
    groundedness,
    retrieval_recall,
    citation_validity,
    refusal_accuracy,
]

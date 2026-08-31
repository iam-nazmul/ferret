"""Dataset hygiene — enforced at sync time so a bad example can't quietly score 1.0."""

import json
from pathlib import Path

import pytest

from eval.sync import DATASETS_DIR, load_dataset, validate_example


def test_all_shipped_datasets_load_and_validate():
    files = list(DATASETS_DIR.glob("*.jsonl"))
    assert files, "no datasets found"
    for path in files:
        assert load_dataset(path), f"{path.name} is empty"


def test_non_refusal_example_without_document_ids_is_rejected():
    with pytest.raises(ValueError, match="document_ids"):
        validate_example(
            {"inputs": {"question": "q"}, "outputs": {"answer": "a"}}, "test:1"
        )


def test_refusal_example_needs_no_document_ids():
    validate_example({"inputs": {"question": "q"}, "outputs": {"should_refuse": True}}, "test:1")


def test_missing_question_is_rejected():
    with pytest.raises(ValueError, match="question"):
        validate_example({"inputs": {}, "outputs": {"should_refuse": True}}, "test:1")


def test_comment_lines_are_skipped(tmp_path: Path):
    path = tmp_path / "x.jsonl"
    path.write_text(
        "// a comment\n"
        + json.dumps({"inputs": {"question": "q"}, "outputs": {"should_refuse": True}})
        + "\n"
    )
    assert len(load_dataset(path)) == 1

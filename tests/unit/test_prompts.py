"""Prompt-cache invariants.

The system prompt sits behind the cache_control breakpoint. One per-request byte
invalidates the prefix and raises cost ~35% with no visible error, so this is enforced
rather than trusted.
"""

import inspect

from app.llm import prompts
from app.llm.cache import cached_system, memory_block
from app.llm.prompts import ANSWER_SYSTEM_PROMPT


def test_system_prompt_has_no_interpolation_placeholders():
    assert "{" not in ANSWER_SYSTEM_PROMPT
    assert "%s" not in ANSWER_SYSTEM_PROMPT


def test_system_prompt_is_a_module_level_literal():
    """An f-string or .format() call would make the prefix vary per request."""
    source = inspect.getsource(prompts.system)
    assert 'ANSWER_SYSTEM_PROMPT = """' in source
    assert 'ANSWER_SYSTEM_PROMPT = f"""' not in source
    assert ".format(" not in source


def test_cached_system_sets_the_breakpoint():
    block = cached_system()
    assert len(block) == 1
    assert block[0]["cache_control"] == {"type": "ephemeral"}
    assert block[0]["text"] == ANSWER_SYSTEM_PROMPT


def test_cached_system_is_byte_identical_across_calls():
    assert cached_system() == cached_system()


def test_answer_rules_are_present():
    """These five rules are behavior, not wording — losing one is a silent regression."""
    lowered = ANSWER_SYSTEM_PROMPT.lower()
    assert "only from the provided documents" in lowered
    assert "cited" in lowered
    assert "conflict" in lowered
    assert "language the question was asked in" in lowered


def test_memory_block_is_empty_when_no_memories():
    assert memory_block([]) == ""


def test_memory_block_renders_facts():
    out = memory_block(["Works on billing", "Prefers bullets"])
    assert "Works on billing" in out and "Prefers bullets" in out

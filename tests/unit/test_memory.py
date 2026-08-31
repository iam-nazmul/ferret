"""Memory: namespace isolation, dedupe, and thread summarization."""

from langchain_core.messages import AIMessage, HumanMessage

from app.memory.checkpointer import summarize_if_needed
from app.memory.store import _near_duplicate, namespace


def test_namespace_is_always_scoped_to_one_user():
    """The store has no ACL layer — the namespace is the only isolation."""
    assert namespace("alice") == ("memories", "alice")
    assert namespace("alice") != namespace("bob")


def test_near_duplicate_detection():
    assert _near_duplicate("User works on the billing team", "User works on the billing team")
    assert not _near_duplicate("User works on billing", "User prefers bullet points")
    assert not _near_duplicate("", "anything")


def test_short_threads_are_not_summarized():
    messages = [HumanMessage(content=f"m{i}") for i in range(10)]
    assert summarize_if_needed(messages, threshold=40) is None


def test_long_threads_collapse_older_span():
    messages = []
    for i in range(50):
        messages.append(HumanMessage(content=f"question {i}"))
        messages.append(AIMessage(content=f"answer {i}"))

    result = summarize_if_needed(messages, threshold=40)
    assert result is not None
    assert len(result) < len(messages)
    assert result[0].type == "system"
    assert result[-1].content == messages[-1].content

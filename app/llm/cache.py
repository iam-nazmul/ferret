"""Prompt cache layout (SPEC §9)."""

from anthropic.types.beta import BetaTextBlockParam

from app.llm.prompts import ANSWER_SYSTEM_PROMPT


def cached_system(prompt: str = ANSWER_SYSTEM_PROMPT) -> list[BetaTextBlockParam]:
    """The system block with a cache breakpoint after it."""
    return [
        BetaTextBlockParam(
            type="text",
            text=prompt,
            cache_control={"type": "ephemeral"},
        )
    ]


def memory_block(memories: list[str]) -> str:
    """Long-term memories, rendered for the message prefix. Empty string when there are none."""
    if not memories:
        return ""
    lines = "\n".join(f"- {m}" for m in memories)
    return f"What you know about this user from previous conversations:\n{lines}"

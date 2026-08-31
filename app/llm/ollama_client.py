"""The local path: a self-hosted Ollama model behind `LLMClient`'s surface.

Selected by ENVIRONMENT=local. Gives up API citations and prompt caching — see
app/llm/README.md before relying on it for anything but local development.
"""

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from app.config import settings
from app.llm.client import LLMResponse
from app.llm.models import EFFORT_DEFAULT, LOCAL_MODEL
from app.llm.prompts import ANSWER_SYSTEM_PROMPT
from app.logging import get_logger
from app.metrics import tokens_total

log = get_logger(__name__)


class OllamaClient:
    """Mirrors `LLMClient`. `effort` and `model` are accepted and ignored: one local model
    serves answering, grading, decomposition, and extraction alike."""

    def __init__(self, model: str = LOCAL_MODEL, base_url: str | None = None) -> None:
        self._model = model
        self._base_url = base_url or settings.ollama_base_url

    async def answer(
        self,
        content: list[dict[str, Any]],
        *,
        effort: str = EFFORT_DEFAULT,
        model: str = LOCAL_MODEL,
        max_tokens: int = 16000,
    ) -> LLMResponse:
        """See `LLMClient.answer`. Never carries citations."""
        reply = await self._chat(max_tokens).ainvoke(self._messages(content))
        return self._wrap(reply)

    async def stream_answer(
        self,
        content: list[dict[str, Any]],
        *,
        effort: str = EFFORT_DEFAULT,
        model: str = LOCAL_MODEL,
        max_tokens: int = 64000,
    ) -> AsyncIterator[tuple[str, Any]]:
        """See `LLMClient.stream_answer`."""
        final: Any = None
        async for chunk in self._chat(max_tokens).astream(self._messages(content)):
            text = _text(chunk)
            if text:
                yield "token", text
            final = chunk if final is None else final + chunk
        yield "done", self._wrap(final)

    async def structured(
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        """See `LLMClient.structured`. Constrained by Ollama's `format`, not tool use —
        small models still return the wrong shape sometimes, hence the empty-dict fallback."""
        llm = self._chat(max_tokens).with_structured_output(schema, method="json_schema")
        try:
            result = await llm.ainvoke([SystemMessage(system), HumanMessage(user)])
        except Exception as exc:
            log.warning("ollama_structured_failed", model=self._model, error=str(exc))
            return {}
        return result if isinstance(result, dict) else {}

    def _chat(self, max_tokens: int) -> ChatOllama:
        return ChatOllama(
            model=self._model,
            base_url=self._base_url,
            temperature=0,
            num_predict=max_tokens,
        )

    def _messages(self, content: list[dict[str, Any]]) -> list[Any]:
        return [SystemMessage(ANSWER_SYSTEM_PROMPT), HumanMessage(render_content(content))]

    def _wrap(self, msg: Any) -> LLMResponse:
        usage = getattr(msg, "usage_metadata", None) or {}
        in_tok = int(usage.get("input_tokens", 0) or 0)
        out_tok = int(usage.get("output_tokens", 0) or 0)

        tokens_total.labels(kind="input").inc(in_tok)
        tokens_total.labels(kind="output").inc(out_tok)

        return LLMResponse(
            content=[{"type": "text", "text": _text(msg)}],
            stop_reason="end_turn",
            refusal_category=None,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cache_read_tokens=0,
        )


def render_content(content: list[dict[str, Any]]) -> str:
    """Flatten the document blocks `pack_context` builds into one prompt string.

    Ollama has no `document` block type; the documents become tagged text.
    """
    parts: list[str] = []
    for block in content:
        kind = block.get("type")
        if kind == "document":
            title = block.get("title", "")
            body = "".join(b.get("text", "") for b in block.get("source", {}).get("content", []))
            parts.append(f'<document title="{title}">\n{body}\n</document>')
        elif kind == "text":
            parts.append(block.get("text", ""))
    return "\n\n".join(p for p in parts if p)


def _text(msg: Any) -> str:
    """Message content is a string on Ollama, but list-of-blocks on other providers."""
    if msg is None:
        return ""
    content = getattr(msg, "content", "")
    if isinstance(content, str):
        return content
    return "".join(
        b.get("text", "") if isinstance(b, dict) else str(b)
        for b in content
        if not isinstance(b, dict) or b.get("type") == "text"
    )

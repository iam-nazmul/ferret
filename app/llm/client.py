"""The single path to the Anthropic API."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any, cast

from anthropic import AsyncAnthropic

from app.config import settings
from app.llm.cache import cached_system
from app.llm.models import ANSWER_MODEL, EFFORT_DEFAULT, LOCAL_MODEL
from app.logging import get_logger
from app.metrics import cache_read_tokens, tokens_total

if TYPE_CHECKING:
    from app.llm.ollama_client import OllamaClient

log = get_logger(__name__)

REFUSAL_BETA = "server-side-fallback-2026-07-01"


@dataclass(slots=True)
class LLMResponse:
    content: list[Any]
    stop_reason: str | None
    refusal_category: str | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int

    @property
    def refused(self) -> bool:
        return self.stop_reason == "refusal"


class LLMClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._client = AsyncAnthropic(api_key=api_key or settings.anthropic_api_key or None)

    async def answer(
        self,
        content: list[dict[str, Any]],
        *,
        effort: str = EFFORT_DEFAULT,
        model: str = ANSWER_MODEL,
        max_tokens: int = 16000,
    ) -> LLMResponse:
        """A non-streaming answer call. Used by eval and the CLI; the API streams instead."""
        # betas/fallbacks are only accepted on the beta namespace.
        resp = await self._client.beta.messages.create(
            model=model,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            output_config=cast(Any, {"effort": effort}),
            system=cached_system(),
            messages=[{"role": "user", "content": cast(Any, content)}],
            betas=[REFUSAL_BETA],
            fallbacks="default",
        )
        return self._wrap(resp)

    async def stream_answer(
        self,
        content: list[dict[str, Any]],
        *,
        effort: str = EFFORT_DEFAULT,
        model: str = ANSWER_MODEL,
        max_tokens: int = 64000,
    ) -> AsyncIterator[tuple[str, Any]]:
        """Yields ("token", str) as text arrives, then ("done", LLMResponse)."""
        async with self._client.beta.messages.stream(
            model=model,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            output_config=cast(Any, {"effort": effort}),
            system=cached_system(),
            messages=[{"role": "user", "content": cast(Any, content)}],
            betas=[REFUSAL_BETA],
            fallbacks="default",
        ) as stream:
            async for text in stream.text_stream:
                yield "token", text
            final = await stream.get_final_message()
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
        """A small structured call — grading, decomposition, extraction."""
        resp = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config=cast(Any, {"format": {"type": "json_schema", "schema": schema}}),
        )
        wrapped = self._wrap(resp)
        if wrapped.refused:
            return {}
        import json

        from app.llm.citations import answer_text

        try:
            return json.loads(answer_text(resp.content))
        except (ValueError, TypeError):
            log.warning("structured_parse_failed", model=model)
            return {}

    def _wrap(self, resp: Any) -> LLMResponse:
        usage = getattr(resp, "usage", None)
        cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        in_tok = int(getattr(usage, "input_tokens", 0) or 0)
        out_tok = int(getattr(usage, "output_tokens", 0) or 0)

        cache_read_tokens.inc(cache_read)
        tokens_total.labels(kind="input").inc(in_tok)
        tokens_total.labels(kind="output").inc(out_tok)

        stop_reason = getattr(resp, "stop_reason", None)
        category = None
        if stop_reason == "refusal":
            details = getattr(resp, "stop_details", None)
            category = getattr(details, "category", None)
            log.warning("claude_refusal", category=category)

        return LLMResponse(
            content=list(getattr(resp, "content", []) or []),
            stop_reason=stop_reason,
            refusal_category=category,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cache_read_tokens=cache_read,
        )


@lru_cache
def get_client() -> "LLMClient | OllamaClient":
    """The one LLM backend for the process. ENVIRONMENT=local swaps Anthropic for Ollama."""
    if settings.is_local:
        from app.llm.ollama_client import OllamaClient

        log.info("llm_backend_local", model=LOCAL_MODEL, base_url=settings.ollama_base_url)
        return OllamaClient()
    return LLMClient()

"""Heading-aware chunking."""

from functools import lru_cache

from app.config import settings
from app.ingest.types import Parsed, ParsedBlock, PreparedChunk


@lru_cache
def _encoder():
    try:
        import tiktoken

        return tiktoken.get_encoding("cl100k_base")
    except Exception:  # tiktoken unavailable (offline build) — fall back to an estimate
        return None


def count_tokens(text: str) -> int:
    enc = _encoder()
    if enc is None:
        return max(1, len(text) // 4)
    return len(enc.encode(text))


def heading_prefix(heading_path: list[str]) -> str:
    return f"{' > '.join(heading_path)}\n\n" if heading_path else ""


def chunk_document(
    parsed: Parsed,
    target_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[PreparedChunk]:
    """Pack blocks into chunks, never merging across a heading change."""
    target = target_tokens or settings.chunk_tokens
    overlap = overlap_tokens or settings.chunk_overlap_tokens

    chunks: list[PreparedChunk] = []
    buffer: list[ParsedBlock] = []
    buffer_tokens = 0
    ordinal = 0

    def flush() -> None:
        nonlocal buffer, buffer_tokens, ordinal
        if not buffer:
            return
        heading = buffer[0].heading_path
        body = "\n\n".join(b.text for b in buffer)
        text = heading_prefix(heading) + body
        chunks.append(
            PreparedChunk(
                text=text,
                locator=buffer[0].locator,
                heading_path=list(heading),
                token_count=count_tokens(text),
                ordinal=ordinal,
            )
        )
        ordinal += 1
        # Carry the tail forward as overlap.
        carry: list[ParsedBlock] = []
        carried = 0
        for block in reversed(buffer):
            block_tokens = count_tokens(block.text)
            if carried + block_tokens > overlap:
                break
            carry.insert(0, block)
            carried += block_tokens
        buffer = carry
        buffer_tokens = carried

    for block in parsed.blocks:
        if not block.text.strip():
            continue
        block_tokens = count_tokens(block.text)

        heading_changed = bool(buffer) and buffer[-1].heading_path != block.heading_path
        if heading_changed:
            flush()
            buffer, buffer_tokens = [], 0

        # A single oversized block becomes its own chunk rather than being dropped.
        if block_tokens > target:
            flush()
            buffer, buffer_tokens = [], 0
            for piece in _split_long(block, target):
                chunks.append(
                    PreparedChunk(
                        text=heading_prefix(block.heading_path) + piece,
                        locator=block.locator,
                        heading_path=list(block.heading_path),
                        token_count=count_tokens(piece),
                        ordinal=ordinal,
                    )
                )
                ordinal += 1
            continue

        if buffer_tokens + block_tokens > target:
            flush()

        buffer.append(block)
        buffer_tokens += block_tokens

    flush()
    return chunks


def _split_long(block: ParsedBlock, target: int) -> list[str]:
    """Split an oversized block on sentence boundaries."""
    import re

    sentences = re.split(r"(?<=[.!?])\s+", block.text)
    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for sentence in sentences:
        t = count_tokens(sentence)
        if current and current_tokens + t > target:
            pieces.append(" ".join(current))
            current, current_tokens = [], 0
        current.append(sentence)
        current_tokens += t
    if current:
        pieces.append(" ".join(current))
    return [p for p in pieces if p.strip()]

"""PDF parsing.

PyMuPDF gives page + bbox, which becomes the citation locator. A parser that returns
text with no position information makes citations useless for that source.
"""

from app.config import settings
from app.ingest.types import Parsed, ParsedBlock
from app.logging import get_logger

log = get_logger(__name__)


def parse_pdf(content: bytes, uri: str) -> Parsed:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=content, filetype="pdf")
    try:
        blocks: list[ParsedBlock] = []
        total_chars = 0
        heading_path: list[str] = []

        for page_no, page in enumerate(doc, start=1):
            page_dict = page.get_text("dict")
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:  # 0 = text
                    continue
                text, max_size = _block_text(block)
                if not text.strip():
                    continue
                total_chars += len(text)

                if _is_heading(text, max_size):
                    heading_path = _push_heading(heading_path, text.strip())
                    continue

                blocks.append(
                    ParsedBlock(
                        text=text.strip(),
                        locator={"page": page_no, "bbox": list(block.get("bbox", []))},
                        heading_path=list(heading_path),
                    )
                )

        page_count = doc.page_count
        if page_count and total_chars / page_count < settings.scanned_pdf_chars_per_page:
            log.info("scanned_pdf_detected", uri=uri, chars_per_page=total_chars / page_count)
            ocr_blocks = _ocr(doc)
            if ocr_blocks:
                blocks = ocr_blocks

        title = (doc.metadata or {}).get("title") or uri.rsplit("/", 1)[-1]
        return Parsed(title=title, blocks=blocks, page_count=page_count)
    finally:
        doc.close()


def _block_text(block: dict) -> tuple[str, float]:
    parts, max_size = [], 0.0
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            parts.append(span.get("text", ""))
            max_size = max(max_size, float(span.get("size", 0)))
        parts.append(" ")
    return "".join(parts), max_size


def _is_heading(text: str, size: float) -> bool:
    stripped = text.strip()
    return bool(stripped) and len(stripped) < 90 and size >= 13 and not stripped.endswith(".")


def _push_heading(path: list[str], heading: str) -> list[str]:
    """Flat two-level heading path; deeper nesting isn't reliably recoverable from font size."""
    return [path[0], heading] if path else [heading]


def _ocr(doc) -> list[ParsedBlock]:
    """OCR fallback. ~50x slower than text extraction — scanned-heavy sources need their own queue."""
    blocks: list[ParsedBlock] = []
    for page_no, page in enumerate(doc, start=1):
        try:
            textpage = page.get_textpage_ocr(flags=0, full=True)
            text = page.get_text(textpage=textpage)
        except Exception as exc:  # Tesseract missing or OCR failure
            log.warning("ocr_failed", page=page_no, error=str(exc))
            continue
        if text.strip():
            blocks.append(ParsedBlock(text=text.strip(), locator={"page": page_no, "ocr": True}))
    return blocks

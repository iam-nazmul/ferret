"""HTML parsing: boilerplate stripped, heading tree preserved."""

from app.ingest.types import Parsed, ParsedBlock
from app.logging import get_logger

log = get_logger(__name__)

_HEADINGS = {"h1", "h2", "h3", "h4"}


def parse_html(content: bytes, uri: str) -> Parsed:
    from lxml import html as lxml_html

    try:
        import trafilatura

        extracted = trafilatura.extract(
            content, include_comments=False, include_tables=True, output_format="html"
        )
    except Exception as exc:
        log.warning("trafilatura_failed", uri=uri, error=str(exc))
        extracted = None

    tree = lxml_html.fromstring(extracted or content)
    title = _text(tree.find(".//title")) or _text(tree.find(".//h1")) or uri

    blocks: list[ParsedBlock] = []
    heading_path: list[str] = []
    char_start = 0

    for el in tree.iter():
        tag = str(el.tag).lower() if isinstance(el.tag, str) else ""
        text = _text(el)
        if not text:
            continue

        if tag in _HEADINGS:
            level = int(tag[1])
            heading_path = heading_path[: level - 1] + [text]
            continue

        if tag in ("p", "li", "td", "pre", "blockquote"):
            anchor = el.get("id") or _nearest_anchor(el)
            blocks.append(
                ParsedBlock(
                    text=text,
                    locator={"anchor": anchor, "char_start": char_start},
                    heading_path=list(heading_path),
                )
            )
            char_start += len(text)

    return Parsed(title=title, blocks=blocks)


def _text(el) -> str:
    if el is None:
        return ""
    return " ".join((el.text_content() or "").split())


def _nearest_anchor(el) -> str:
    node = el
    for _ in range(4):
        node = node.getparent()
        if node is None:
            break
        if node.get("id"):
            return node.get("id")
    return ""

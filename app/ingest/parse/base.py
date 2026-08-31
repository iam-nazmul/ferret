"""Content-type dispatch."""

from app.ingest.types import Fetched, Parsed


def parse_content(fetched: Fetched) -> Parsed:
    ctype = (fetched.content_type or "").lower()
    if "pdf" in ctype or fetched.uri.lower().endswith(".pdf"):
        from app.ingest.parse.pdf import parse_pdf

        return parse_pdf(fetched.content, fetched.uri)
    if "html" in ctype or "xml" in ctype or fetched.uri.startswith("http"):
        from app.ingest.parse.html import parse_html

        return parse_html(fetched.content, fetched.uri)

    text = fetched.content.decode("utf-8", errors="replace")
    from app.ingest.types import ParsedBlock

    return Parsed(
        title=fetched.uri.rsplit("/", 1)[-1],
        blocks=[ParsedBlock(text=text, locator={"char_start": 0})],
    )

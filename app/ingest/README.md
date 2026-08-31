# app/ingest — corpus ingestion

Celery workers that turn sources into indexed chunks: `discover → fetch → parse → chunk → embed → upsert → mark`. **This module writes; the graph only reads.** It must never import from `app/graph/`.

Spec: [SPEC.md §7](../../SPEC.md).

## Layout

```
worker.py       # Celery app, beat schedule
cli.py          # python -m app.ingest.cli run|reindex
registry.py     # source kind → (discoverer, fetcher) mapping
types.py        # Discovered, Fetched, Parsed, ParsedBlock, PreparedChunk
pipeline.py     # the stage sequence, per document
discover/       # s3.py, sitemap.py, crawl.py
fetch/          # http.py (conditional GET), s3.py
parse/          # pdf.py (PyMuPDF + OCR fallback), html.py (trafilatura)
chunk.py        # heading-aware splitting
embed.py        # batched embeddings (shares config with app/retrieval/embed.py)
upsert.py       # transactional chunk replacement
```

## Idempotency

The whole pipeline keys on **`(source_id, uri, content_hash)`**. Same triple, no work. This is what makes every stage safe to re-run and every failure safe to retry — do not add a stage that breaks it.

`fetch` short-circuits on unchanged ETag/Last-Modified before doing anything expensive.

## Stage notes

**parse** — PyMuPDF `get_text("dict")` gives page + bbox, which becomes the citation `locator`. If the text layer is under 100 chars/page, treat the PDF as scanned and fall back to `unstructured` + OCR. HTML goes through trafilatura with the heading tree preserved.

**chunk** — 700 tokens, 100 overlap, split on heading boundaries. **Every chunk is prefixed with its `heading_path`** ("Security > Data Retention\n\n…"). This measurably improves retrieval: a fragment read in isolation is often meaningless, and the embedding has no other way to know where it came from. Tables become their own chunks, serialized as markdown.

**embed** — batches of 100, `text-embedding-3-large` truncated to 1024d, exponential backoff on rate limits.

**upsert** — delete + reinsert all chunks for a `document_id` **in one transaction**. A partial upsert leaves the index in a state that lies about what's in the corpus, and nothing downstream can detect it.

## Extending

**New source type** (SharePoint, Google Drive, a ticketing system):

1. Discoverer in `discover/` — yields `(uri, metadata)`.
2. Fetcher in `fetch/` — returns bytes + content type, honoring conditional requests.
3. Register the `kind` string in `registry.py`.
4. Parser in `parse/` only if the format is genuinely new.

Chunking, embedding, and upsert are shared. **Do not fork them per source** — divergence there is how two documents from different sources stop being comparable at retrieval time.

**New parser:** must produce a `locator` that the UI can deep-link to. A parser that returns text with no position information makes citations useless for that source type.

## Gotchas

- Crawling needs a per-source lock. Two overlapping crawls of the same sitemap will duplicate work and can deadlock on upsert.
- `robots.txt` is respected in `crawl.py`. Don't add a bypass flag.
- OCR is ~50x slower than text extraction. Scanned-heavy sources need their own queue or they starve everything else.
- Deleting a source cascades to documents and chunks. Intended — but confirm before wiring it to a UI button.
- Embedding cost is dominated by re-indexing unchanged content. If costs spike, `content_hash` short-circuiting is broken.

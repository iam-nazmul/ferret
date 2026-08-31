---
name: add-source-type
description: Add a new ingestion source type (SharePoint, Google Drive, a ticketing system, a new file format) to app/ingest/. Use when the corpus needs to cover a system Ferret can't currently read.
---

# Add a source type

Ingestion is `discover → fetch → parse → chunk → embed → upsert → mark`. A new source type touches the first three stages. **The last four are shared and must not be forked** — divergence there is how documents from different sources stop being comparable at retrieval time.

## Steps

**1. Discoverer** — `app/ingest/discover/<kind>.py`

Yields `(uri, metadata)` pairs. Metadata should carry anything useful for filtering later: `doc_type`, `effective_date`, `author`, `version`. Respect the source's pagination and rate limits.

**2. Fetcher** — `app/ingest/fetch/<kind>.py`

Returns bytes plus a content type. **Must support conditional fetching** (ETag, Last-Modified, or the source's equivalent) — without it, every run re-embeds the whole corpus and the embedding bill becomes the dominant cost.

**3. Register** — `app/ingest/registry.py`

Map the `kind` string to `(discoverer, fetcher)`. The string also goes in the `sources.kind` check constraint, which means a migration (see the `new-migration` skill).

**4. Parser** — `app/ingest/parse/<format>.py`, **only if the format is genuinely new**

A parser must produce a `locator` the UI can deep-link to: `{page, bbox}` for paginated formats, `{anchor, char_start}` for documents. A parser returning text with no position information makes citations useless for that source — which defeats the product's core property. If you can't produce a locator, say so and stop rather than shipping uncitable content.

**5. ACL** — decide how permissions map

`sources.acl_groups` is the default; `documents.acl_groups` overrides per document. If the source system has its own permissions, map them at discovery time. **Never default to a permissive group to "get it working"** — an over-broad ACL is a data-exposure bug that no test will catch unless you wrote it.

## Verify

```bash
python -m app.ingest.cli run --source-id <uuid>     # once
python -m app.ingest.cli run --source-id <uuid>     # twice — must be a no-op
pytest tests/integration/test_ingest.py -q
```

The second run producing work means `content_hash` short-circuiting is broken. Fix it before moving on; it's the property that makes everything else safe to retry.

Then check retrieval end to end:

```bash
python -m app.graph.cli "a question only the new source can answer" --user-groups <group>
```

Confirm the citation deep-links to the right place, not just that an answer appeared.

## Checklist

- [ ] Conditional fetch implemented and verified (second run is a no-op)
- [ ] `locator` produced and deep-links correctly in the UI
- [ ] ACL mapping decided and not defaulted to a broad group
- [ ] `kind` registered + migration for the check constraint
- [ ] Chunking/embedding/upsert **not** forked
- [ ] Integration test with a small fixture in `tests/fixtures/`
- [ ] OCR-heavy source? Give it its own Celery queue or it starves the others

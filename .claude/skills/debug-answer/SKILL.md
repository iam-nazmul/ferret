---
name: debug-answer
description: Diagnose a bad, incomplete, uncited, or refused answer from a run_id or a reproduction question. Use when a user reports a wrong answer or a 👎 lands in the weekly review.
---

# Debug a bad answer

Work the pipeline in order. Each stage has a distinct signature, and diagnosing out of order wastes the most expensive step (generation) on a problem that was upstream.

## Reproduce

```bash
python -m app.graph.cli "the question" --user-groups <the user's groups>
```

**Use the reporting user's groups.** Reproducing as an admin is the single most common way to conclude "works for me" on what is actually an ACL-scoped corpus gap.

If you have the `run_id`, open the LangSmith trace first — it has every node's inputs and outputs, including retrieval candidates and scores.

## Triage, in order

**1. Is the content even in the corpus?**

```sql
SELECT d.uri, d.status, d.indexed_at, count(c.id)
FROM documents d LEFT JOIN chunks c ON c.document_id = d.id
WHERE d.uri ILIKE '%<expected doc>%'
GROUP BY 1,2,3;
```

`status = 'failed'` or zero chunks → an ingestion problem, not a retrieval one. Stop here and check the worker logs for that document.

**2. Was it retrievable by this user?**

Compare `documents.acl_groups` against the user's groups. A correct "I don't know" for a user without access is not a bug — it's the ACL working.

**3. Did retrieval surface it?**

In the trace, check the `retrieve` node's candidates. If the right chunk isn't in the 30:
- exact identifiers missing → sparse side; check `websearch_to_tsquery` sanitization didn't strip the term
- paraphrase missing → dense side; check the query embedding config matches ingestion (same model, same 1024d truncation)
- nothing at all → filters. An `effective_after` filter silently excluding everything is common.

**4. Did rerank drop it?**

Chunk in the 30 but not the 8 → reranking. Check whether the reranker fell back to RRF order (there's a warning and a counter for this); a cold or down reranker looks exactly like a quality problem.

**5. Did generation ignore it?**

Right chunks in context, wrong answer:
- **uncited claims** → `groundedness_violation` should be set; if it isn't, `verify` has a gap
- **answer contradicts the chunk** → prompt issue; see the `prompt-change` skill
- **truncated mid-sentence** → `max_tokens` hit
- **refused** → check `stop_reason == "refusal"` and `stop_details.category`; that's a classifier decision, not a retrieval failure

**6. Chunk boundaries**

If the answer spans a heading break, the chunker may have split the fact from its context. Check whether the retrieved chunk carries its `heading_path` prefix — without it the fragment is often meaningless to both the embedder and the model.

## Close the loop

Every diagnosed bad answer becomes a golden-set example:

1. Add the question, a reference answer, and the expected `document_id`s to `eval/datasets/golden.jsonl`
2. `python -m eval.sync`
3. Fix the bug
4. `python -m eval.run_eval --gate`

A fix without a dataset entry will regress, and nobody will notice until a user reports it again.

## Report

State which stage failed and the evidence from the trace. "Retrieval didn't surface the chunk because the sparse query dropped the identifier" is a diagnosis; "the model got it wrong" is not.

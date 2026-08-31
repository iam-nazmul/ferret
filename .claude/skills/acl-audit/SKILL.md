---
name: acl-audit
description: Verify the ACL boundary is intact after changes to retrieval, auth, the graph, or ingestion. Use before merging anything that touches how user_groups flows or how chunks are selected — an ACL break is a data-exposure bug that ordinary tests won't catch.
---

# Audit the ACL boundary

Ferret's permission model is one predicate in one place. That's a strength — it's auditable — and a fragility: a single refactor can move filtering out of SQL and into Python without any test failing.

## The invariant

```sql
WHERE d.acl_groups && :user_groups AND d.status = 'indexed'
```

This must appear in **both** the dense and sparse CTEs in `app/retrieval/hybrid.py`, in the innermost query. Not in an outer wrapper, not in Python afterwards.

Unauthorized text that reaches a prompt is a leak whether or not the model quotes it — it's in the trace, in the checkpointer, and in the LangSmith run.

## Audit steps

**1. Grep for the predicate**

```bash
grep -n "acl_groups" app/retrieval/*.py app/graph/nodes/*.py app/api/**/*.py
```

Every hit should be either the SQL predicate or the `Principal.groups` plumbing. A hit in a list comprehension or a `filter()` call is a finding.

**2. Confirm groups can't be forged**

```bash
grep -rn "user_groups\|groups" app/api/schemas.py app/api/routes/
```

`user_groups` must come from `Principal` (derived from the verified JWT claim) and never from a request body, query parameter, or header the client controls. A Pydantic schema field named `groups` is a finding.

**3. Confirm nothing widens the set**

```bash
grep -rn "groups" app/graph/
```

Nodes read `state["user_groups"]`. Any assignment to it, union with another set, or default-to-all fallback is a finding.

**4. Check the empty case**

An empty group set must return zero rows, not all rows. `&&` against an empty array does this correctly — a "helpful" `if not groups: skip predicate` branch is the classic version of this bug.

**5. Run the test**

```bash
pytest tests/integration/test_acl.py -q
```

It asserts two users in different groups see only their own documents, that the other group's chunk text appears nowhere in the response, state, or trace, and that empty groups yield nothing.

**6. Check ingestion defaults**

```bash
grep -rn "acl_groups" app/ingest/
```

New sources must set `acl_groups` explicitly. A default of `['all']` or `[]`-means-public is a finding.

## Reporting

If you find a violation, report it as a security finding with the file and line, what data it exposes, and to whom — not as a style note. Don't fix it silently in a PR about something else; it deserves its own change and its own review.

If the audit is clean, say so plainly and list what you checked. "Looks fine" without the list is not an audit.

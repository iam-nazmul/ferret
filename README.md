# Ferret

**Ask questions about your company's documents and get answers with sources.**

Ferret reads your organization's PDFs — policies, contracts, manuals, reports — along with internal and external web pages, and answers questions about them in plain language. Every factual statement comes with a link to the exact page or section it came from, so you can check it yourself.

---

## What you can ask

Ferret is good at questions whose answers exist somewhere in your documents:

- *"How many days is the refund window on the Enterprise plan?"*
- *"What's the liability cap in Vendor X's MSA, and how does it differ from our standard template?"*
- *"What is the deployment approval process?"*
- *"What have the last three quarterly reports said about churn?"*

You can ask follow-up questions without repeating yourself — *"and what about the Pro plan?"* works.

Ferret answers in whatever language you ask in.

## What you get back

Every answer has small numbered markers like `[1]` next to each claim. Hover over one to see the exact sentence from the source document. Click it and the document opens on the right, scrolled to the relevant page.

The **Sources** panel on the right lists every passage Ferret looked at for the answer. If an answer seems off, this is the fastest way to see why.

## When Ferret says "I don't know"

If your documents don't contain the answer, Ferret tells you instead of guessing. That is deliberate. An assistant that invents a plausible-sounding policy number is worse than one that admits it can't find it.

You'll also occasionally see a note that Ferret found **conflicting information**. It will show you both sources rather than picking one — for contracts and policies, that's your call to make, not the software's.

---

## Getting started

1. Sign in with your normal work account (SSO).
2. Type a question, or pick one of the examples on the empty screen.
3. Read the answer, click a citation to verify anything that matters.
4. Use 👍 / 👎 on the answer. This is the main way Ferret improves — a 👎 with a one-line comment gets reviewed every week.

**Filters.** Above the input box you can narrow the search — by document type (policy, contract, report) or by date, e.g. only documents effective after January 2025. Useful when older superseded versions are cluttering the answer.

## What Ferret remembers

**Within a conversation,** Ferret remembers what you've been discussing, so follow-ups work naturally.

**Across conversations,** it remembers a small amount about you — your team, projects you ask about often, and formatting preferences ("always use bullet points"). It does *not* store the contents of documents in your profile, and it doesn't record personal details you haven't stated directly.

You are in control of this. Open **What Ferret knows about me** in the sidebar to see the full list, delete individual items, or clear everything.

## What you can and can't see

Ferret respects your existing document permissions. If you don't have access to a document, it is invisible to Ferret when answering *you* — it won't be quoted, summarized, or mentioned. Two colleagues on different teams can ask the same question and correctly get different answers.

Conversations are kept for 90 days by default, then deleted.

---

## Limitations worth knowing

- **Ferret only knows what's been indexed.** New documents appear within a few hours; ask an administrator if something is missing.
- **Scanned documents can be imperfect.** Where a PDF is a photograph of text rather than real text, Ferret reads it via OCR and may occasionally garble numbers. Citations let you verify.
- **It doesn't do math on your behalf** beyond what the documents state. If a document says "12%," Ferret will say 12% — it won't recompute it from a table.
- **It's read-only.** Ferret can't edit, sign, upload, or send anything.

## For administrators

The **Admin** tab (visible if you have the role) shows every configured source, when it last synced, how many documents it holds, and which ones failed to index with the reason. From there you can trigger a re-index or upload individual PDFs.

## Getting help

- Something wrong with an answer → 👎 with a comment; it lands in the weekly review.
- A document is missing or out of date → contact an administrator via the Admin tab.
- Something is broken → file an issue with the answer's ID, shown under the response.

---

*Building or running Ferret? See [CLAUDE.md](CLAUDE.md) for developer setup and [SPEC.md](SPEC.md) for the full design.*

"""Ask a question from the terminal.

    python -m app.graph.cli "your question" --user-groups eng,all

Use the reporting user's groups when reproducing a bug — running as an admin is the
most common way to conclude "works for me" on an ACL-scoped corpus gap.
"""

import argparse
import asyncio
import sys

from app.graph.build import build_graph
from app.graph.state import initial_state
from app.llm.citations import deep_link
from app.logging import configure_logging
from app.models.base import session_factory
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.types import RetrievalFilters


async def _run(question: str, groups: list[str], user_id: str, doc_type: list[str]) -> int:
    async with session_factory() as session:
        graph = build_graph(HybridRetriever(session))
        state = initial_state(
            question,
            user_id=user_id,
            user_groups=frozenset(groups),
            filters=RetrievalFilters(doc_type=doc_type) if doc_type else None,
        )
        result = await graph.ainvoke(state)

    print(f"\n{result.get('answer', '')}\n")

    citations = result.get("citations", [])
    if citations:
        print("Sources:")
        for i, c in enumerate(citations, 1):
            print(f"  [{i}] {c.document_title or c.uri} — {deep_link(c)}")
            if c.cited_text:
                print(f"      “{c.cited_text[:160]}”")

    chunks = result.get("chunks", [])
    print(f"\n{len(chunks)} chunks used, {len(result.get('candidates', []))} candidates")
    if result.get("groundedness_violation"):
        print("WARNING: answer contains uncited factual sentences", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask Ferret a question")
    parser.add_argument("question")
    parser.add_argument("--user-groups", default="all", help="comma-separated ACL groups")
    parser.add_argument("--user-id", default="cli")
    parser.add_argument("--doc-type", default="", help="comma-separated doc_type filter")
    args = parser.parse_args()

    configure_logging("WARNING")
    return asyncio.run(
        _run(
            args.question,
            [g.strip() for g in args.user_groups.split(",") if g.strip()],
            args.user_id,
            [d.strip() for d in args.doc_type.split(",") if d.strip()],
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())

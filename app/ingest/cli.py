"""Ingestion CLI.

    python -m app.ingest.cli run --source-id <uuid>
    python -m app.ingest.cli reindex --all
    python -m app.ingest.cli add --kind web_sitemap --uri https://... --acl-groups all
"""

import argparse
import asyncio
import uuid

from sqlalchemy import select

from app.ingest.pipeline import ingest_source
from app.logging import configure_logging, get_logger
from app.models import Source
from app.models.base import session_factory

log = get_logger(__name__)


async def _run(source_id: uuid.UUID) -> int:
    async with session_factory() as session:
        stats = await ingest_source(session, source_id)
    print(f"discovered={stats['discovered']} indexed={stats['indexed']} "
          f"skipped={stats['skipped']} failed={stats['failed']}")
    return 1 if stats["failed"] else 0


async def _reindex_all() -> int:
    async with session_factory() as session:
        ids = (
            await session.execute(select(Source.id).where(Source.enabled.is_(True)))
        ).scalars().all()
        total = {"discovered": 0, "indexed": 0, "skipped": 0, "failed": 0}
        for sid in ids:
            stats = await ingest_source(session, sid)
            for k in total:
                total[k] += stats[k]
    print(total)
    return 1 if total["failed"] else 0


async def _add(kind: str, uri: str, acl_groups: list[str], config: dict) -> int:
    async with session_factory() as session:
        source = Source(
            id=uuid.uuid4(), kind=kind, uri=uri, acl_groups=acl_groups, crawl_config=config
        )
        session.add(source)
        await session.commit()
        print(source.id)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ferret ingestion")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="ingest one source now")
    run.add_argument("--source-id", required=True)

    reindex = sub.add_parser("reindex", help="ingest every enabled source")
    reindex.add_argument("--all", action="store_true", required=True)

    add = sub.add_parser("add", help="register a source")
    add.add_argument("--kind", required=True, choices=["pdf_bucket", "web_sitemap", "upload"])
    add.add_argument("--uri", required=True)
    add.add_argument("--acl-groups", default="all")
    add.add_argument("--max-depth", type=int, default=3)

    args = parser.parse_args()
    configure_logging()

    if args.command == "run":
        return asyncio.run(_run(uuid.UUID(args.source_id)))
    if args.command == "reindex":
        return asyncio.run(_reindex_all())
    return asyncio.run(
        _add(
            args.kind,
            args.uri,
            [g.strip() for g in args.acl_groups.split(",") if g.strip()],
            {"max_depth": args.max_depth},
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())

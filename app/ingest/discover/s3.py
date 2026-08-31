"""S3 bucket discovery for PDF sources."""

from urllib.parse import urlparse

from app.ingest.types import Discovered
from app.logging import get_logger

log = get_logger(__name__)


async def discover(uri: str, config: dict) -> list[Discovered]:
    """List objects under an s3:// prefix.

    boto3 is imported lazily so the API and UI images don't need it.
    """
    import boto3

    from app.config import settings

    parsed = urlparse(uri)
    bucket, prefix = parsed.netloc, parsed.path.lstrip("/")
    suffixes = tuple(config.get("suffixes", [".pdf"]))

    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        region_name=settings.aws_region,
    )
    paginator = client.get_paginator("list_objects_v2")

    found: list[Discovered] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.lower().endswith(suffixes):
                continue
            found.append(
                Discovered(
                    uri=f"s3://{bucket}/{key}",
                    metadata={"etag": obj["ETag"].strip('"'), "size": obj["Size"]},
                )
            )
    log.info("s3_discovered", bucket=bucket, prefix=prefix, count=len(found))
    return found

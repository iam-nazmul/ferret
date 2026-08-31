"""S3 object fetch with ETag short-circuit."""

from urllib.parse import urlparse

from app.ingest.types import Fetched


async def fetch(uri: str, etag: str | None = None) -> Fetched:
    import boto3
    from botocore.exceptions import ClientError

    from app.config import settings

    parsed = urlparse(uri)
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        region_name=settings.aws_region,
    )
    kwargs = {"Bucket": parsed.netloc, "Key": parsed.path.lstrip("/")}
    if etag:
        kwargs["IfNoneMatch"] = etag

    try:
        obj = client.get_object(**kwargs)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("304", "NotModified"):
            return Fetched(uri=uri, content=b"", content_type="", etag=etag, unchanged=True)
        raise

    return Fetched(
        uri=uri,
        content=obj["Body"].read(),
        content_type=obj.get("ContentType", "application/pdf"),
        etag=obj["ETag"].strip('"'),
    )

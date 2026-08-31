"""Sitemap and BFS crawl discovery."""

import re
from collections import deque
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from lxml import etree

from app.ingest.types import Discovered
from app.logging import get_logger

log = get_logger(__name__)

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


async def discover(uri: str, config: dict) -> list[Discovered]:
    """Prefer sitemap.xml; fall back to a bounded BFS crawl."""
    try:
        urls = await _from_sitemap(uri)
        if urls:
            return [Discovered(uri=u) for u in _apply_patterns(urls, config)]
    except (httpx.HTTPError, etree.XMLSyntaxError) as exc:
        log.info("sitemap_unavailable", uri=uri, error=str(exc))

    urls = await _crawl(uri, config)
    return [Discovered(uri=u) for u in _apply_patterns(urls, config)]


async def _from_sitemap(base: str) -> list[str]:
    sitemap_url = base if base.endswith(".xml") else urljoin(base, "/sitemap.xml")
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(sitemap_url)
        resp.raise_for_status()
        root = etree.fromstring(resp.content)
    return [el.text for el in root.findall(".//sm:loc", _SITEMAP_NS) if el.text]


async def _crawl(base: str, config: dict) -> list[str]:
    max_depth = int(config.get("max_depth", 3))
    max_pages = int(config.get("max_pages", 500))
    origin = urlparse(base)

    robots = RobotFileParser()
    robots.set_url(urljoin(base, "/robots.txt"))
    robots_loaded = True
    try:
        robots.read()
    except Exception:
        robots_loaded = False
        log.info("robots_unreadable", uri=base)

    seen: set[str] = set()
    found: list[str] = []
    queue: deque[tuple[str, int]] = deque([(base, 0)])

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        while queue and len(found) < max_pages:
            url, depth = queue.popleft()
            if url in seen or depth > max_depth:
                continue
            seen.add(url)

            if robots_loaded and not robots.can_fetch("*", url):
                continue

            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except httpx.HTTPError:
                continue

            if "html" not in resp.headers.get("content-type", ""):
                continue
            found.append(url)

            if depth < max_depth:
                for href in re.findall(rb'href=["\']([^"\']+)["\']', resp.content):
                    link = urljoin(url, href.decode("utf-8", "ignore"))
                    parsed = urlparse(link)
                    if parsed.netloc == origin.netloc and link not in seen:
                        queue.append((link.split("#")[0], depth + 1))

    return found


def _apply_patterns(urls: list[str], config: dict) -> list[str]:
    include = config.get("include_patterns") or []
    exclude = config.get("exclude_patterns") or []
    out = []
    for url in urls:
        if include and not any(re.search(p, url) for p in include):
            continue
        if exclude and any(re.search(p, url) for p in exclude):
            continue
        out.append(url)
    return out

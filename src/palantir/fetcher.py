from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import feedparser
import httpx

try:
    import trafilatura
    _HAS_TRAFILATURA = True
except ImportError:
    _HAS_TRAFILATURA = False

_FEED_HEADERS = {
    "User-Agent": "Palantir/1.0 news reader",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}

_ARTICLE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-CA,en;q=0.9",
}


@dataclass
class Article:
    title: str
    url: str
    source: str
    summary: str
    published: Optional[datetime]
    full_text: Optional[str] = field(default=None)
    ai_summary: Optional[str] = field(default=None)
    ai_attempted: bool = field(default=False)
    ai_loading: bool = field(default=False)
    keywords: Optional[list[str]] = field(default=None)


class FeedCache:
    def __init__(self, ttl: int = 900) -> None:  # 15-minute TTL
        self._store: dict[str, tuple[float, list[Article]]] = {}
        self.ttl = ttl

    def get(self, url: str) -> Optional[list[Article]]:
        entry = self._store.get(url)
        if entry and (time.monotonic() - entry[0]) < self.ttl:
            return entry[1]
        return None

    def set(self, url: str, articles: list[Article]) -> None:
        self._store[url] = (time.monotonic(), articles)

    def invalidate_all(self) -> None:
        self._store.clear()


class FeedFetcher:
    def __init__(self) -> None:
        self.cache = FeedCache()

    async def fetch_feed(self, name: str, url: str) -> list[Article]:
        cached = self.cache.get(url)
        if cached is not None:
            return cached

        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=_FEED_HEADERS)
                resp.raise_for_status()
                raw = resp.text
        except Exception:
            return []

        parsed = feedparser.parse(raw)
        articles: list[Article] = []

        for entry in parsed.entries[:25]:
            published: Optional[datetime] = None
            if getattr(entry, "published_parsed", None):
                try:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass

            summary = ""
            for attr in ("summary", "description", "content"):
                val = getattr(entry, attr, None)
                if val:
                    if isinstance(val, list):
                        val = val[0].get("value", "")
                    summary = _strip_html(val)[:600]
                    break

            articles.append(Article(
                title=_strip_html(entry.get("title", "Untitled")).strip(),
                url=entry.get("link", ""),
                source=name,
                summary=summary,
                published=published,
            ))

        self.cache.set(url, articles)
        return articles

    async def fetch_topic(self, feeds: list[dict]) -> list[Article]:
        tasks = [self.fetch_feed(f["name"], f["url"]) for f in feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        merged: list[Article] = []
        for r in results:
            if isinstance(r, list):
                merged.extend(r)
        merged.sort(
            key=lambda a: a.published or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return merged

    async def fetch_article_text(self, url: str) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=_ARTICLE_HEADERS)
                resp.raise_for_status()
                html = resp.text
        except Exception as exc:
            return f"[Fetch error: {exc}]"

        if _HAS_TRAFILATURA:
            text = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
            )
            if text:
                return text

        return _strip_html(html)[:8000]


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#\d+;", "", text)
    return re.sub(r"\s+", " ", text).strip()

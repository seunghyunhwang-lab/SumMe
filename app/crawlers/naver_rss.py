"""
네이버 뉴스 RSS 크롤러
실시간(속보) + 일일(오전/저녁 TOP10) 공용으로 사용
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx

from ..models import RawItem

# ── RSS 피드 목록 ─────────────────────────────────────────────
RSS_SOURCES = [
    # 연합뉴스
    {"url": "https://www.yna.co.kr/rss/news.xml", "name": "연합뉴스"},
    # 조선일보
    {"url": "https://www.chosun.com/arc/outboundfeeds/rss/", "name": "조선일보"},
    # 동아일보
    {"url": "https://rss.donga.com/total.xml", "name": "동아일보"},
    # 한국경제
    {"url": "https://www.hankyung.com/feed/all-news", "name": "한국경제"},
    # MBC
    {"url": "https://imnews.imbc.com/rss/news/news_00.xml", "name": "MBC"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SumMe-Bot/1.0)",
}


async def _fetch_rss(url: str, client: httpx.AsyncClient) -> str:
    """RSS XML 텍스트를 비동기로 가져옴"""
    try:
        resp = await client.get(url, headers=HEADERS, timeout=10.0, follow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception:
        return ""


def _parse_published(entry) -> datetime | None:
    """feedparser entry의 published 필드를 UTC datetime으로 변환"""
    if hasattr(entry, "published"):
        try:
            return parsedate_to_datetime(entry.published).astimezone(timezone.utc)
        except Exception:
            pass
    return None


def _entry_to_raw(entry, source_name: str) -> RawItem | None:
    title = getattr(entry, "title", "").strip()
    link = getattr(entry, "link", "").strip()
    if not title or not link:
        return None

    # 본문 발췌 (summary 또는 description)
    content = (
        getattr(entry, "summary", "")
        or getattr(entry, "description", "")
    ).strip()
    # HTML 태그 제거 (간단히)
    import re
    content = re.sub(r"<[^>]+>", "", content).strip()

    return RawItem(
        title=f"[{source_name}] {title}",
        source_url=link,
        content=content[:500],
        category="news",
        published_at=_parse_published(entry),
    )


async def crawl(limit_per_source: int = 10) -> list[RawItem]:
    """모든 RSS 소스에서 최신 기사 수집"""
    items: list[RawItem] = []

    async with httpx.AsyncClient() as client:
        xmls = await asyncio.gather(*[
            _fetch_rss(src["url"], client) for src in RSS_SOURCES
        ])

    for src, xml in zip(RSS_SOURCES, xmls):
        if not xml:
            continue
        feed = feedparser.parse(xml)
        for entry in feed.entries[:limit_per_source]:
            item = _entry_to_raw(entry, src["name"])
            if item:
                items.append(item)

    return items

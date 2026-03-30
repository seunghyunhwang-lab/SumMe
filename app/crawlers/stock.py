"""
주식/경제 뉴스 RSS 크롤러
소스: 매일경제 증권, 한국경제 경제·증권, 연합뉴스 경제
주식·증권 관련 키워드 필터링 적용
"""
from __future__ import annotations
import asyncio
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx

from ..models import RawItem

STOCK_SOURCES = [
    {"url": "https://www.mk.co.kr/rss/40300001/",          "name": "매일경제(증권)"},
    {"url": "https://www.hankyung.com/feed/finance",        "name": "한국경제(증권)"},
    {"url": "https://www.hankyung.com/feed/economy",        "name": "한국경제(경제)"},
    {"url": "https://www.yna.co.kr/rss/economy.xml",        "name": "연합뉴스(경제)"},
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SumMe-Bot/1.0)"}

# 주식/경제 관련 키워드 필터
STOCK_KEYWORDS = [
    "주식", "증권", "코스피", "코스닥", "주가", "상장", "IPO", "공모",
    "투자", "배당", "금리", "환율", "채권", "ETF", "펀드",
    "종목", "시가총액", "외국인", "기관", "매수", "매도",
    "실적", "영업이익", "매출", "흑자", "적자", "순이익",
    "주주", "공시", "유상증자", "자사주", "M&A", "인수",
    "경기", "인플레이션", "금융", "은행", "증시",
]


def _is_stock_related(title: str, content: str) -> bool:
    text = title + content
    return any(kw in text for kw in STOCK_KEYWORDS)


async def _fetch(url: str, client: httpx.AsyncClient) -> str:
    try:
        r = await client.get(url, headers=HEADERS, timeout=10.0, follow_redirects=True)
        r.raise_for_status()
        return r.text
    except Exception:
        return ""


def _parse_published(entry) -> datetime | None:
    for field in ("published", "updated"):
        val = getattr(entry, field, None)
        if val:
            try:
                return parsedate_to_datetime(val).astimezone(timezone.utc)
            except Exception:
                pass
    return None


async def crawl(limit_per_source: int = 8) -> list[RawItem]:
    """주식/경제 RSS에서 관련 뉴스 기사 수집"""
    async with httpx.AsyncClient() as client:
        xmls = await asyncio.gather(*[
            _fetch(src["url"], client) for src in STOCK_SOURCES
        ])

    items: list[RawItem] = []
    seen_urls: set[str] = set()

    for src, xml in zip(STOCK_SOURCES, xmls):
        if not xml:
            continue
        feed = feedparser.parse(xml)
        count = 0
        for entry in feed.entries:
            if count >= limit_per_source:
                break
            title = getattr(entry, "title", "").strip()
            link  = getattr(entry, "link",  "").strip()
            if not title or not link or link in seen_urls:
                continue

            raw_content = (
                getattr(entry, "summary", "") or getattr(entry, "description", "")
            )
            content = re.sub(r"<[^>]+>", "", raw_content).strip()

            # 주식/경제 키워드 필터
            if not _is_stock_related(title, content):
                continue

            seen_urls.add(link)
            items.append(RawItem(
                title=f"[{src['name']}] {title}",
                source_url=link,
                content=content[:500],
                category="stock",
                published_at=_parse_published(entry),
            ))
            count += 1

    return items

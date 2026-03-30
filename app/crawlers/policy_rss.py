"""
복지/생활정책 RSS 크롤러
소스: 웰페어뉴스, 연합뉴스 사회
국민 실생활 혜택·지원금·복지 관련 키워드 필터링 적용
"""
from __future__ import annotations
import asyncio
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx

from ..models import RawItem

POLICY_SOURCES = [
    {"url": "https://www.welfarenews.net/rss/allArticle.xml", "name": "웰페어뉴스"},
    {"url": "https://www.yna.co.kr/rss/society.xml",          "name": "연합뉴스(사회)"},
    {"url": "https://www.yna.co.kr/rss/economy.xml",          "name": "연합뉴스(경제)"},
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SumMe-Bot/1.0)"}

# 실생활 복지·지원 관련 키워드
WELFARE_KEYWORDS = [
    # 지원·혜택
    "지원금", "지원사업", "지원 대상", "지원신청", "혜택", "복지",
    "수급", "보조금", "장학금", "바우처", "쿠폰", "무료",
    # 급여·제도
    "생계급여", "의료급여", "주거급여", "교육급여",
    "기초생활", "긴급복지", "차상위",
    # 대상 계층
    "노인", "어르신", "장애인", "임신", "출산", "육아", "임산부",
    "청년", "취업", "실업", "구직",
    # 의료·건강
    "의료비", "건강보험", "본인부담", "검진", "예방접종",
    # 주거
    "임대주택", "전세자금", "주거비",
    # 신청·절차
    "신청 방법", "신청일", "접수", "자격 요건", "선정 기준",
    # 제도·정책
    "정책", "제도", "시행", "개정", "지급",
]


def _is_welfare_related(title: str, content: str) -> bool:
    text = title + content
    return any(kw in text for kw in WELFARE_KEYWORDS)


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


async def crawl(limit_per_source: int = 10) -> list[RawItem]:
    """복지·지원 관련 뉴스/정책 기사 수집"""
    async with httpx.AsyncClient() as client:
        xmls = await asyncio.gather(*[
            _fetch(src["url"], client) for src in POLICY_SOURCES
        ])

    items: list[RawItem] = []
    seen_urls: set[str] = set()

    for src, xml in zip(POLICY_SOURCES, xmls):
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

            # 복지/지원 키워드 필터
            if not _is_welfare_related(title, content):
                continue

            seen_urls.add(link)
            items.append(RawItem(
                title=f"[{src['name']}] {title}",
                source_url=link,
                content=content[:500],
                category="policy",
                published_at=_parse_published(entry),
            ))
            count += 1

    return items

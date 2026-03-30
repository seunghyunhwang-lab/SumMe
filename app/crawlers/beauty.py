"""
뷰티/패션 트렌드 RSS 크롤러
소스: 보그, 엘르, 코스모폴리탄, 한국경제 라이프, 아시아경제 라이프
뷰티·스킨케어·패션 관련 키워드 필터링 적용
"""
from __future__ import annotations
import asyncio
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx

from ..models import RawItem

BEAUTY_SOURCES = [
    {"url": "https://www.vogue.co.kr/rss",                 "name": "보그코리아"},
    {"url": "https://www.elle.co.kr/rss",                  "name": "엘르코리아"},
    {"url": "https://www.cosmopolitan.co.kr/rss",          "name": "코스모폴리탄"},
    {"url": "https://www.hankyung.com/feed/life",          "name": "한국경제(라이프)"},
    {"url": "https://www.asiae.co.kr/rss/life.htm",        "name": "아시아경제(라이프)"},
]

# 올리브영 Playwright 크롤러는 보조 소스로만 사용
OLIVEYOUNG_URL = (
    "https://www.oliveyoung.co.kr/store/main/getBestList.do"
    "?pageIdx=1&rowsPerPage=20&cateId=&type=1"
)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SumMe-Bot/1.0)"}

# 뷰티·패션 관련 키워드
BEAUTY_KEYWORDS = [
    # 스킨케어
    "스킨케어", "피부", "세럼", "크림", "토너", "에센스", "보습",
    "선크림", "자외선", "미백", "주름", "모공", "수분",
    # 메이크업
    "메이크업", "립", "파운데이션", "쿠션", "블러셔", "아이섀도",
    "마스카라", "컨실러", "프라이머",
    # 헤어
    "헤어", "샴푸", "트리트먼트", "두피", "염색",
    # 브랜드·제품
    "뷰티", "화장품", "코스메틱", "향수", "퍼퓸",
    "올리브영", "드러그스토어",
    # 트렌드
    "패션", "트렌드", "룩", "스타일", "컬렉션", "시즌",
    "무신사", "럭셔리", "브랜드",
    # 헬스/웰니스
    "다이어트", "영양제", "비타민", "건강",
]


def _is_beauty_related(title: str, content: str) -> bool:
    text = title + content
    return any(kw in text for kw in BEAUTY_KEYWORDS)


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


async def _crawl_rss(limit_per_source: int = 8) -> list[RawItem]:
    """RSS 기반 뷰티/패션 뉴스 수집"""
    async with httpx.AsyncClient() as client:
        xmls = await asyncio.gather(*[
            _fetch(src["url"], client) for src in BEAUTY_SOURCES
        ])

    items: list[RawItem] = []
    seen_urls: set[str] = set()

    for src, xml in zip(BEAUTY_SOURCES, xmls):
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

            # Vogue/Elle/Cosmo는 필터 완화 (이미 뷰티 전문 매체)
            is_specialist = src["name"] in ("보그코리아", "엘르코리아", "코스모폴리탄")
            if not is_specialist and not _is_beauty_related(title, content):
                continue

            seen_urls.add(link)
            items.append(RawItem(
                title=f"[{src['name']}] {title}",
                source_url=link,
                content=content[:500],
                category="beauty",
                published_at=_parse_published(entry),
            ))
            count += 1

    return items


async def _crawl_oliveyoung(limit: int = 5) -> list[RawItem]:
    """올리브영 신제품 Playwright 크롤러 (보조)"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return []

    items: list[RawItem] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page    = await browser.new_page()
        await page.set_extra_http_headers({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        })
        try:
            await page.goto(OLIVEYOUNG_URL, timeout=20_000, wait_until="domcontentloaded")
            await page.wait_for_selector(".prd_info", timeout=10_000)
            cards = await page.query_selector_all(".prd_info")
            for card in cards[:limit]:
                brand   = await _text(card, ".tx_brand")
                name    = await _text(card, ".tx_name")
                price   = await _text(card, ".tx_cur .tx_num")
                link_el = await card.query_selector("a")
                href    = await link_el.get_attribute("href") if link_el else ""
                if href and not href.startswith("http"):
                    href = "https://www.oliveyoung.co.kr" + href
                if not name:
                    continue
                title   = f"[올리브영 신제품] {brand} {name}".strip()
                content = f"{brand} {name} 가격: {price}원. 올리브영 신제품 등록."
                items.append(RawItem(
                    title=title,
                    source_url=href or OLIVEYOUNG_URL,
                    content=content,
                    category="beauty",
                    published_at=datetime.now(timezone.utc),
                ))
        except Exception:
            pass
        finally:
            await browser.close()
    return items


async def _text(element, selector: str) -> str:
    el = await element.query_selector(selector)
    if el:
        return (await el.inner_text()).strip()
    return ""


async def crawl(limit: int = 10) -> list[RawItem]:
    """RSS(주) + 올리브영(보조) 뷰티 콘텐츠 수집"""
    rss_items, oy_items = await asyncio.gather(
        _crawl_rss(limit_per_source=6),
        _crawl_oliveyoung(limit=4),
    )
    all_items = rss_items + oy_items
    return all_items[:limit] if len(all_items) > limit else all_items

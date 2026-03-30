"""
일일 파이프라인
- 오전 7시: 오늘 누적 뉴스 TOP10 (중요도 상위)
- 오전 9시: 법제처 정책/법령
- 오전 10시: 올리브영 신제품
- 오후 6시: 저녁 주요뉴스 TOP10
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone

from ..crawlers import naver_rss, policy_rss, beauty as beauty_crawler, stock as stock_crawler
from ..summarizer import summarize_daily, summarize_realtime
from ..database import upsert_feed_item, get_db
from ..models import FeedItemCreate, RawItem

logger = logging.getLogger(__name__)


# ── 오전 뉴스 TOP10 선별 ──────────────────────────────────────
async def _pick_top_news(limit: int = 10) -> list[RawItem]:
    """오늘 0시 이후 수집된 realtime 뉴스 중 중요도 상위 limit개 선별"""
    db = get_db()
    from datetime import date
    today_start = datetime.combine(date.today(), datetime.min.time()).isoformat()
    rows = await asyncio.to_thread(
        lambda: db.table("feed_items")
        .select("title, source_url, summary, importance_score, published_at")
        .eq("feed_type", "realtime")
        .eq("category", "news")
        .eq("is_duplicate", False)
        .gte("crawled_at", today_start)
        .order("importance_score", desc=True)
        .limit(limit)
        .execute()
        .data
    )
    return [
        RawItem(
            title=r["title"],
            source_url=r["source_url"],
            content=r["summary"] if isinstance(r["summary"], str) else " ".join(r["summary"] or []),
            category="news",
            published_at=r.get("published_at"),
        )
        for r in rows
    ]


async def _process_daily(raw: RawItem) -> dict | None:
    try:
        result = await summarize_daily(raw)
        # importance는 3줄 요약이므로 realtime 빠른 요약으로 importance 추출
        rt = await summarize_realtime(raw)
        item = FeedItemCreate(
            category=raw.category,
            feed_type="daily",
            title=raw.title,
            summary=result.summary,
            importance_score=rt.importance,
            source_url=raw.source_url,
            published_at=raw.published_at or datetime.now(timezone.utc),
            why_important=result.why_important,
        )
        return item.model_dump(mode="json")
    except Exception as e:
        logger.warning("daily item 처리 실패: %s | %s", raw.title[:60], e)
        return None


async def _save_all(items: list[dict]) -> int:
    saved = 0
    for item_dict in items:
        try:
            await asyncio.to_thread(upsert_feed_item, item_dict)
            saved += 1
        except Exception as e:
            logger.error("DB 저장 실패: %s", e)
    return saved


# ── 공개 진입점 ───────────────────────────────────────────────

async def run_morning_news() -> dict:
    """오전 7시: 오늘의 주요뉴스 TOP10"""
    logger.info("▶ 일일 오전 뉴스 파이프라인 시작")
    start = datetime.now(timezone.utc)

    raws = await _pick_top_news(limit=10)
    if not raws:
        # DB에 오늘 뉴스가 없으면 실시간 크롤링 후 TOP10 선별
        all_news = await naver_rss.crawl(limit_per_source=10)
        # 빠른 중요도 평가 후 상위 10개 선택
        scored = await asyncio.gather(*[summarize_realtime(r) for r in all_news])
        paired = sorted(zip(scored, all_news), key=lambda x: -x[0].importance)
        raws = [p[1] for p in paired[:10]]

    results = await asyncio.gather(*[_process_daily(r) for r in raws])
    valid   = [r for r in results if r is not None]
    saved   = await _save_all(valid)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info("✓ 오전 뉴스 완료: %d개 저장 (%.1fs)", saved, elapsed)
    return {"stage": "morning_news", "saved": saved, "elapsed_sec": round(elapsed, 1)}


async def run_policy() -> dict:
    """오전 9시: 법제처 정책/법령"""
    logger.info("▶ 일일 정책 파이프라인 시작")
    start = datetime.now(timezone.utc)

    raws    = await policy_rss.crawl(limit_per_source=10)
    results = await asyncio.gather(*[_process_daily(r) for r in raws])
    valid   = [r for r in results if r is not None]
    saved   = await _save_all(valid)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info("✓ 정책 완료: %d개 저장 (%.1fs)", saved, elapsed)
    return {"stage": "policy", "saved": saved, "elapsed_sec": round(elapsed, 1)}


async def run_beauty() -> dict:
    """오전 10시: 뷰티/패션 트렌드 RSS + 올리브영"""
    logger.info("▶ 일일 뷰티 파이프라인 시작")
    start = datetime.now(timezone.utc)

    raws    = await beauty_crawler.crawl(limit=10)
    results = await asyncio.gather(*[_process_daily(r) for r in raws])
    valid   = [r for r in results if r is not None]
    saved   = await _save_all(valid)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info("✓ 뷰티 완료: %d개 저장 (%.1fs)", saved, elapsed)
    return {"stage": "beauty", "saved": saved, "elapsed_sec": round(elapsed, 1)}


async def run_stock() -> dict:
    """주식/경제 뉴스 RSS 크롤링"""
    logger.info("▶ 일일 주식/경제 뉴스 파이프라인 시작")
    start = datetime.now(timezone.utc)

    raws    = await stock_crawler.crawl(limit_per_source=8)
    results = await asyncio.gather(*[_process_daily(r) for r in raws])
    valid   = [r for r in results if r is not None]
    saved   = await _save_all(valid)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info("✓ 주식/경제 완료: %d개 저장 (%.1fs)", saved, elapsed)
    return {"stage": "stock", "saved": saved, "elapsed_sec": round(elapsed, 1)}


async def run_evening_news() -> dict:
    """오후 6시: 저녁 주요뉴스 TOP10"""
    logger.info("▶ 일일 저녁 뉴스 파이프라인 시작")
    # 오전과 동일 로직, 오후 시간대 기준으로 재선별
    result = await run_morning_news()
    result["stage"] = "evening_news"
    return result


async def run(stage: str = "all") -> dict:
    """POST /pipeline/daily 에서 호출. stage로 세분화 가능."""
    handlers = {
        "morning_news": run_morning_news,
        "policy":       run_policy,
        "beauty":       run_beauty,
        "stock":        run_stock,
        "evening_news": run_evening_news,
    }
    if stage in handlers:
        return await handlers[stage]()

    # "all": 전체 실행
    results = []
    for fn in handlers.values():
        try:
            r = await fn()
            results.append(r)
        except Exception as e:
            logger.error("daily stage 실패: %s", e)
    return {"stages": results}

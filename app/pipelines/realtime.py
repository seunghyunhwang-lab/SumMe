"""
실시간 파이프라인 (30분마다)
- 네이버 RSS 속보 뉴스
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone

from ..crawlers import naver_rss
from ..summarizer import summarize_realtime
from ..database import upsert_feed_item
from ..models import FeedItemCreate

logger = logging.getLogger(__name__)


async def _process_item(raw) -> dict | None:
    """단일 RawItem 요약 → DB 저장용 dict 반환"""
    try:
        result = await summarize_realtime(raw)
        item = FeedItemCreate(
            category=raw.category,
            feed_type="realtime",
            title=raw.title,
            summary=result.summary,
            importance_score=result.importance,
            source_url=raw.source_url,
            published_at=raw.published_at or datetime.now(timezone.utc),
        )
        return item.model_dump(mode="json")
    except Exception as e:
        logger.warning("realtime item 처리 실패: %s | %s", raw.title[:60], e)
        return None


async def run() -> dict:
    logger.info("▶ 실시간 파이프라인 시작")
    start = datetime.now(timezone.utc)

    # 속보 뉴스 크롤링
    news_items = await naver_rss.crawl(limit_per_source=5)
    raw_all = news_items
    logger.info("크롤링 완료: 뉴스 %d개", len(news_items))

    # 요약 (병렬 처리)
    results = await asyncio.gather(*[_process_item(r) for r in raw_all])
    valid = [r for r in results if r is not None]

    # DB 저장 (동기 Supabase SDK → to_thread)
    saved = 0
    for item_dict in valid:
        try:
            await asyncio.to_thread(upsert_feed_item, item_dict)
            saved += 1
        except Exception as e:
            logger.error("DB 저장 실패: %s", e)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info("✓ 실시간 파이프라인 완료: %d/%d 저장 (%.1fs)", saved, len(valid), elapsed)
    return {"saved": saved, "total": len(raw_all), "elapsed_sec": round(elapsed, 1)}

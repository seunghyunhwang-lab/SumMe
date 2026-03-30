"""
주간 파이프라인 (월요일 오전 8시)
- 지난주 feed_items에서 카테고리별 TOP5 추출
- Claude API로 주간 브리핑 텍스트 생성
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from collections import defaultdict

from ..database import fetch_last_week_items, upsert_feed_item
from ..summarizer import summarize_weekly
from ..models import FeedItemCreate

logger = logging.getLogger(__name__)

CATEGORIES = ["news", "policy", "stock", "beauty"]
TOP_N = 5


def _group_top(items: list[dict]) -> dict[str, list[dict]]:
    """카테고리별로 그룹화 후 importance_score 상위 TOP_N 반환"""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        cat = item.get("category", "news")
        grouped[cat].append(item)

    return {
        cat: sorted(grouped[cat], key=lambda x: -(x.get("importance_score") or 0))[:TOP_N]
        for cat in CATEGORIES
    }


async def run() -> dict:
    logger.info("▶ 주간 파이프라인 시작")
    start = datetime.now(timezone.utc)

    # 지난주 데이터 수집
    items = await asyncio.to_thread(fetch_last_week_items)
    logger.info("지난주 feed_items: %d개", len(items))

    if not items:
        logger.warning("주간 파이프라인: 데이터 없음")
        return {"saved": 0, "reason": "no data"}

    # 카테고리별 TOP5 그룹화
    top_by_cat = _group_top(items)

    # Claude API로 주간 브리핑 생성
    weekly = await summarize_weekly(top_by_cat)

    # 브리핑을 단일 feed_item으로 저장
    item = FeedItemCreate(
        category="news",       # 주간 브리핑은 news로 분류
        feed_type="weekly",
        title=weekly.title,
        summary=weekly.summary,
        importance_score=5,    # 주간 브리핑은 최고 중요도
        source_url=f"summe://weekly/{datetime.now(timezone.utc).date().isoformat()}",
        published_at=datetime.now(timezone.utc),
        why_important=" | ".join(weekly.highlights.values()),
    )
    item_dict = item.model_dump(mode="json")

    # highlights 를 별도 컬럼 없이 why_important에 직렬화해서 저장
    item_dict["why_important"] = str(weekly.highlights)

    await asyncio.to_thread(upsert_feed_item, item_dict)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info("✓ 주간 파이프라인 완료 (%.1fs)", elapsed)
    return {
        "saved": 1,
        "title": weekly.title,
        "categories_processed": list(top_by_cat.keys()),
        "elapsed_sec": round(elapsed, 1),
    }

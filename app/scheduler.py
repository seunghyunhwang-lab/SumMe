"""
APScheduler 내장 스케줄러
FastAPI 앱 lifespan 안에서 시작/종료
"""
from __future__ import annotations
import logging
import httpx
import pytz

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import settings

logger = logging.getLogger(__name__)
KST = pytz.timezone("Asia/Seoul")

_scheduler: AsyncIOScheduler | None = None


async def _call_pipeline(endpoint: str, params: dict | None = None) -> None:
    """파이프라인 엔드포인트를 내부 HTTP 호출"""
    url = f"http://{settings.host}:{settings.port}/pipeline/{endpoint}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                params=params or {},
                headers={"x-pipeline-secret": settings.pipeline_secret},
                timeout=300.0,  # 파이프라인은 최대 5분
            )
            resp.raise_for_status()
            logger.info("스케줄 실행 완료: /pipeline/%s → %s", endpoint, resp.json())
    except Exception as e:
        logger.error("스케줄 실행 실패: /pipeline/%s | %s", endpoint, e)


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=KST)

    # ── 실시간: 30분마다 ───────────────────────────────────────
    scheduler.add_job(
        _call_pipeline,
        CronTrigger(minute="*/30", timezone=KST),
        args=["realtime"],
        id="realtime",
        name="실시간 뉴스+주식",
        replace_existing=True,
        misfire_grace_time=60,
    )

    # ── 일일 오전 7시: 주요뉴스 TOP10 ─────────────────────────
    scheduler.add_job(
        _call_pipeline,
        CronTrigger(hour=7, minute=0, timezone=KST),
        args=["daily"],
        kwargs={"params": {"stage": "morning_news"}},
        id="daily_morning",
        name="오전 주요뉴스",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # ── 일일 오전 9시: 법제처 정책 ────────────────────────────
    scheduler.add_job(
        _call_pipeline,
        CronTrigger(hour=9, minute=0, timezone=KST),
        args=["daily"],
        kwargs={"params": {"stage": "policy"}},
        id="daily_policy",
        name="정책/법령",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # ── 일일 오전 10시: 올리브영 뷰티 ────────────────────────
    scheduler.add_job(
        _call_pipeline,
        CronTrigger(hour=10, minute=0, timezone=KST),
        args=["daily"],
        kwargs={"params": {"stage": "beauty"}},
        id="daily_beauty",
        name="뷰티 신제품",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # ── 일일 오후 6시: 저녁 주요뉴스 ─────────────────────────
    scheduler.add_job(
        _call_pipeline,
        CronTrigger(hour=18, minute=0, timezone=KST),
        args=["daily"],
        kwargs={"params": {"stage": "evening_news"}},
        id="daily_evening",
        name="저녁 주요뉴스",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # ── 주간: 월요일 오전 8시 ─────────────────────────────────
    scheduler.add_job(
        _call_pipeline,
        CronTrigger(day_of_week="mon", hour=8, minute=0, timezone=KST),
        args=["weekly"],
        id="weekly",
        name="주간 브리핑",
        replace_existing=True,
        misfire_grace_time=600,
    )

    return scheduler


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = build_scheduler()
    return _scheduler

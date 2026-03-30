from fastapi import APIRouter, Depends, HTTPException, Header
from ..config import settings
from ..pipelines import realtime, daily, weekly

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def _verify_secret(x_pipeline_secret: str | None = Header(default=None)):
    if x_pipeline_secret != settings.pipeline_secret:
        raise HTTPException(status_code=401, detail="Invalid pipeline secret")


@router.post("/realtime", dependencies=[Depends(_verify_secret)])
async def run_realtime():
    """30분마다 스케줄러가 호출. 속보 뉴스 + 주식 수집·요약·저장."""
    result = await realtime.run()
    return {"status": "ok", **result}


@router.post("/daily", dependencies=[Depends(_verify_secret)])
async def run_daily(stage: str = "all"):
    """
    하루 2회 (07:00 / 18:00) 또는 세부 stage 지정.
    stage: all | morning_news | policy | beauty | evening_news
    """
    result = await daily.run(stage=stage)
    return {"status": "ok", **result}


@router.post("/weekly", dependencies=[Depends(_verify_secret)])
async def run_weekly():
    """월요일 08:00 호출. 지난주 TOP5 → 주간 브리핑 생성."""
    result = await weekly.run()
    return {"status": "ok", **result}

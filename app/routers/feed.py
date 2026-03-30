from fastapi import APIRouter, Query, HTTPException
from ..database import fetch_feed, fetch_feed_item_by_id
from ..models import FeedResponse, FeedItemOut
import asyncio

router = APIRouter(prefix="/feed", tags=["feed"])


@router.get("", response_model=FeedResponse)
async def get_feed(
    category: str | None = Query(default=None, description="news | policy | stock | beauty"),
    type: str | None     = Query(default=None, alias="type", description="realtime | daily | weekly"),
    page: int            = Query(default=1, ge=1),
    limit: int           = Query(default=20, ge=1, le=100),
):
    """
    피드 조회. 중복 제거된 항목만 반환, importance_score 내림차순.
    """
    items = await asyncio.to_thread(fetch_feed, category, type, page, limit)
    return FeedResponse(
        page=page,
        limit=limit,
        items=[FeedItemOut(**item) for item in items],
    )


@router.get("/{item_id}", response_model=FeedItemOut)
async def get_feed_item(item_id: int):
    """단일 피드 아이템 조회"""
    item = await asyncio.to_thread(fetch_feed_item_by_id, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return FeedItemOut(**item)

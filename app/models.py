from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


# ── DB 저장 모델 ──────────────────────────────────────────────
class FeedItemCreate(BaseModel):
    category: Literal["news", "policy", "stock", "beauty"]
    feed_type: Literal["realtime", "daily", "weekly"]
    title: str
    summary: list[str] | str  # realtime: str, daily/weekly: list[str]
    importance_score: int = Field(ge=1, le=5)
    source_url: str
    published_at: datetime | None = None
    crawled_at: datetime = Field(default_factory=datetime.utcnow)
    is_duplicate: bool = False
    why_important: str | None = None   # daily 전용


# ── API 응답 모델 ─────────────────────────────────────────────
class FeedItemOut(BaseModel):
    id: int
    category: str
    feed_type: str
    title: str
    summary: list[str] | str
    importance_score: int
    source_url: str
    published_at: datetime | None
    crawled_at: datetime
    why_important: str | None


class FeedResponse(BaseModel):
    page: int
    limit: int
    items: list[FeedItemOut]


# ── 크롤러 내부 전달 모델 ─────────────────────────────────────
class RawItem(BaseModel):
    title: str
    source_url: str
    content: str = ""           # 요약에 사용할 원문/발췌
    category: str = "news"
    published_at: datetime | None = None


# ── 요약 결과 ─────────────────────────────────────────────────
class RealtimeSummary(BaseModel):
    summary: str
    importance: int = Field(ge=1, le=5)


class DailySummary(BaseModel):
    summary: list[str]          # 3줄
    why_important: str


class WeeklySummary(BaseModel):
    title: str
    summary: list[str]
    highlights: dict[str, str]  # category → 한 줄 하이라이트

from supabase import create_client, Client
from .config import settings

_client: Client | None = None


def get_db() -> Client:
    """Supabase 클라이언트 싱글톤 반환"""
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_key)
    return _client


# ── 공통 쿼리 헬퍼 ──────────────────────────────────────────────

def upsert_feed_item(item: dict) -> dict:
    """source_url 기준 upsert.
    - 신규: INSERT
    - 기존 동일 URL: 중요도가 높아지면 UPDATE, 아니면 스킵
    """
    db = get_db()
    existing = (
        db.table("feed_items")
        .select("id, importance_score")
        .eq("source_url", item["source_url"])
        .execute()
        .data
    )
    if existing:
        old = existing[0]
        if item.get("importance_score", 0) > old["importance_score"]:
            # 중요도 상승 → 기존 레코드 업데이트
            update_fields = {
                "title":            item.get("title"),
                "summary":          item.get("summary"),
                "importance_score": item.get("importance_score"),
                "crawled_at":       item.get("crawled_at"),
            }
            result = (
                db.table("feed_items")
                .update(update_fields)
                .eq("id", old["id"])
                .execute()
            )
            return result.data[0] if result.data else {}
        # 기존이 같거나 더 중요 → 스킵 (재삽입 없음)
        return {}

    result = db.table("feed_items").insert(item).execute()
    return result.data[0] if result.data else {}


def fetch_feed(
    category: str | None,
    feed_type: str | None,
    page: int,
    limit: int,
) -> list[dict]:
    db = get_db()
    query = (
        db.table("feed_items")
        .select("*")
        .eq("is_duplicate", False)
        .order("importance_score", desc=True)
        .order("crawled_at", desc=True)
    )
    if category:
        query = query.eq("category", category)
    if feed_type:
        query = query.eq("feed_type", feed_type)

    offset = (page - 1) * limit
    return query.range(offset, offset + limit - 1).execute().data


def fetch_feed_item_by_id(item_id: int) -> dict | None:
    """단일 피드 아이템 ID로 조회"""
    db = get_db()
    result = (
        db.table("feed_items")
        .select("*")
        .eq("id", item_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def fetch_last_week_items() -> list[dict]:
    """주간 파이프라인용: 지난 7일치 feed_items 반환"""
    db = get_db()
    from datetime import datetime, timedelta, timezone
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    return (
        db.table("feed_items")
        .select("*")
        .eq("is_duplicate", False)
        .gte("crawled_at", since)
        .order("importance_score", desc=True)
        .execute()
        .data
    )

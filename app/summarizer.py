"""
Claude API 요약 모듈
realtime / daily / weekly 각각 다른 프롬프트 사용
"""
from __future__ import annotations
import json
import asyncio
from functools import lru_cache

import anthropic

from .config import settings
from .models import RawItem, RealtimeSummary, DailySummary, WeeklySummary


@lru_cache(maxsize=1)
def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


# ── 실시간 요약 (1줄, 중요도 1-5) ─────────────────────────────
_REALTIME_SYSTEM = (
    "당신은 뉴스 편집 AI입니다. "
    "주어진 기사를 분석해 핵심만 1줄로 요약하고, "
    "중요도를 1(낮음)~5(높음)로 평가합니다. "
    "반드시 유효한 JSON만 반환하세요."
)
_REALTIME_USER = (
    "다음 기사를 한 줄로 요약해줘.\n"
    "제목: {title}\n내용: {content}\n\n"
    'JSON 형식: {{"summary": "한 줄 핵심 요약", "importance": 1~5 숫자}}'
)


async def summarize_realtime(item: RawItem) -> RealtimeSummary:
    prompt = _REALTIME_USER.format(
        title=item.title, content=item.content or item.title
    )
    text = await _call_claude(_REALTIME_SYSTEM, prompt, max_tokens=256)
    try:
        data = _extract_json(text)
        return RealtimeSummary(
            summary=data.get("summary", item.title[:100]),
            importance=max(1, min(5, int(data.get("importance", 3)))),
        )
    except Exception:
        return RealtimeSummary(summary=item.title[:100], importance=3)


# ── 일일 요약 (3줄 + 왜 중요한지) ────────────────────────────
_DAILY_SYSTEM = (
    "당신은 심층 뉴스 분석 AI입니다. "
    "기사를 3줄로 요약하고 왜 독자에게 중요한지 한 줄로 설명합니다. "
    "반드시 유효한 JSON만 반환하세요."
)
_DAILY_USER = (
    "다음 기사를 분석해줘.\n"
    "제목: {title}\n내용: {content}\n\n"
    "JSON 형식:\n"
    '{{"summary": ["1번째 줄", "2번째 줄", "3번째 줄"], '
    '"why_important": "왜 중요한지 한 줄"}}'
)

# ── 정책/복지 요약 (실생활 혜택 위주) ────────────────────────
_POLICY_SYSTEM = (
    "당신은 정부 정책과 복지 제도를 국민에게 쉽게 설명하는 AI입니다. "
    "정치적 내용은 제외하고 실생활 혜택과 신청 방법 위주로 설명합니다. "
    "반드시 유효한 JSON만 반환하세요."
)
_POLICY_USER = (
    "다음 정책/복지 기사를 분석해줘.\n"
    "제목: {title}\n내용: {content}\n\n"
    "이 정책/제도의 핵심 혜택과 신청 방법을 일반 국민 입장에서 3줄로 요약해줘. "
    "정치적 내용은 제외하고 실생활 혜택 위주로.\n\n"
    "JSON 형식:\n"
    '{{"summary": ["혜택/대상 설명", "신청방법 또는 조건", "주요 내용 한 줄"], '
    '"why_important": "국민 생활에 미치는 영향 한 줄"}}'
)

# ── 뷰티/패션 요약 (트렌드·소비자 정보 위주) ─────────────────
_BEAUTY_SYSTEM = (
    "당신은 뷰티와 패션 트렌드를 소비자 관점에서 분석하는 AI입니다. "
    "제품 정보, 트렌드, 사용법 등 실용적인 정보를 중심으로 설명합니다. "
    "반드시 유효한 JSON만 반환하세요."
)
_BEAUTY_USER = (
    "다음 뷰티/패션 기사를 분석해줘.\n"
    "제목: {title}\n내용: {content}\n\n"
    "이 뷰티 기사의 핵심 트렌드와 소비자에게 유용한 정보를 3줄로 요약해줘.\n\n"
    "JSON 형식:\n"
    '{{"summary": ["핵심 트렌드 또는 제품 정보", "소비자 활용 팁 또는 추천 방법", "주목할 포인트"], '
    '"why_important": "소비자에게 유용한 이유 한 줄"}}'
)


async def summarize_daily(item: RawItem) -> DailySummary:
    """카테고리에 맞는 프롬프트로 일일 요약 생성"""
    if item.category == "policy":
        system, user_tpl = _POLICY_SYSTEM, _POLICY_USER
    elif item.category == "beauty":
        system, user_tpl = _BEAUTY_SYSTEM, _BEAUTY_USER
    else:
        system, user_tpl = _DAILY_SYSTEM, _DAILY_USER

    prompt = user_tpl.format(title=item.title, content=item.content or item.title)
    text = await _call_claude(system, prompt, max_tokens=512)
    try:
        data = _extract_json(text)
        summary = data.get("summary", [item.title])
        if isinstance(summary, str):
            summary = [summary]
        return DailySummary(
            summary=summary[:3],
            why_important=data.get("why_important", ""),
        )
    except Exception:
        return DailySummary(summary=[item.title], why_important="")


# ── 주간 브리핑 (카테고리별 TOP5 → 종합 브리핑) ──────────────
_WEEKLY_SYSTEM = (
    "당신은 주간 뉴스 브리핑을 작성하는 에디터 AI입니다. "
    "제공된 뉴스 목록으로 독자 친화적인 주간 브리핑을 생성합니다. "
    "반드시 유효한 JSON만 반환하세요."
)
_WEEKLY_USER = """
지난주 주요 뉴스입니다. 카테고리별 TOP5가 제공됩니다.

{items_text}

주간 브리핑을 작성해줘.
JSON 형식:
{{
  "title": "N주차 주간 SumMe 브리핑",
  "summary": ["전체 요약 1줄", "전체 요약 2줄", "전체 요약 3줄"],
  "highlights": {{
    "news": "이번 주 뉴스 핵심 한 줄",
    "policy": "이번 주 정책 핵심 한 줄",
    "stock": "이번 주 시장 핵심 한 줄",
    "beauty": "이번 주 뷰티 핵심 한 줄"
  }}
}}
"""


async def summarize_weekly(items_by_category: dict[str, list[dict]]) -> WeeklySummary:
    lines = []
    for cat, items in items_by_category.items():
        lines.append(f"\n[{cat.upper()}]")
        for i, it in enumerate(items, 1):
            lines.append(f"  {i}. {it.get('title', '')} (중요도: {it.get('importance_score')})")

    prompt = _WEEKLY_USER.format(items_text="\n".join(lines))
    text = await _call_claude(_WEEKLY_SYSTEM, prompt, max_tokens=1024)
    try:
        data = _extract_json(text)
        from datetime import datetime
        week = datetime.utcnow().isocalendar()[1]
        return WeeklySummary(
            title=data.get("title", f"{week}주차 주간 SumMe 브리핑"),
            summary=data.get("summary", []),
            highlights=data.get("highlights", {}),
        )
    except Exception:
        from datetime import datetime
        week = datetime.utcnow().isocalendar()[1]
        return WeeklySummary(
            title=f"{week}주차 주간 SumMe 브리핑",
            summary=["주간 브리핑 생성 실패"],
            highlights={},
        )


# ── 공통 헬퍼 ─────────────────────────────────────────────────
async def _call_claude(system: str, user: str, max_tokens: int) -> str:
    """동기 SDK를 asyncio.to_thread 로 비동기 래핑"""
    def _sync():
        msg = _client().messages.create(
            model=settings.anthropic_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text

    return await asyncio.to_thread(_sync)


def _extract_json(text: str) -> dict:
    """응답에서 JSON 블록 추출 (마크다운 코드 블록 대응)"""
    import re
    # ```json ... ``` 또는 ``` ... ``` 형태 추출
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    # 순수 JSON 직접 파싱
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start != -1 and end > start:
        return json.loads(text[start:end])
    raise ValueError("JSON not found in response")

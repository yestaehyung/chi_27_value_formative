"""가치 수준 적응형 질문 전략 (주간덱 S3 정보격차 판단 + S6 질문 전략).

속성 질문("예산은요?")이 아니라 가치 수준 질문("받는 분이 어떻게 느끼면
좋겠어요?")으로 implicit hidden intention을 끌어낸다.

결정 규칙 (S3: 수집된 정보가 충분하면 추천, 부족하면 핵심 질문):
- 카테고리 모름 → 카테고리 질문
- 아직 추천 전 + 기준(비맥락 topic)이 2개 미만 + 직전 행동이 질문 아님
  → 가치 수준 질문 1회 (가장 불확실한 anchor를 겨냥)
- 그 외 → 추천 (PSCon 패턴상 질문은 연속 1회까지만)
"""
from sqlalchemy.orm import Session as DbSession

from app.db import models

# S6 질문 전략: 불확실 anchor → 가치 수준 질문
VALUE_QUESTIONS = {
    "Social": "받는 분이나 주변에서 이 선택을 어떻게 느끼면 좋겠어요?",
    "Emotional": "고르실 때 가장 불안하거나 꼭 피하고 싶은 상황이 있을까요? 반대로 어떤 느낌이면 기분이 좋으실까요?",
    "Functional": "성능, 가격, 오래 쓰는 신뢰 중에 무엇을 가장 포기하기 어려우세요?",
    "Conditional": "주로 어떤 상황에서 쓰게 될까요? 쓰실 분이나 용도를 알려주시면 좋아요.",
    "Epistemic": "비교하실 때 어떤 점이 가장 헷갈리세요? 기준을 같이 잡아드릴게요.",
}
DEFAULT_QUESTION = "이번 쇼핑에서 가장 중요하게 보는 기준을 하나만 꼽는다면 무엇일까요?"


def most_uncertain_anchor(snapshot: models.PreferenceStateSnapshot | None) -> str | None:
    """확인(confirmed) 점수와 전체(추론 포함) 점수의 격차가 가장 큰 anchor.
    격차 = 아직 사용자에게 확인받지 못한 추측의 양 — 다음 자극/질문의 타깃."""
    if snapshot is None:
        return None
    scores = snapshot.anchor_scores or {}
    breakdown = snapshot.anchor_breakdown or {}
    best, best_gap = None, 0.0
    for anchor, total in scores.items():
        confirmed = (breakdown.get(anchor) or {}).get("confirmedScore", 0.0)
        gap = total - confirmed
        if total >= 0.1 and gap >= 0.1 and gap > best_gap:
            best, best_gap = anchor, gap
    return best


def _last_agent_action(db: DbSession, session_id: str) -> str | None:
    last = (
        db.query(models.Turn)
        .filter(models.Turn.session_id == session_id)
        .filter(models.Turn.role == "service_agent")
        .order_by(models.Turn.turn_index.desc())
        .first()
    )
    return last.agent_action if last else None


def build_value_question(
    snapshot: models.PreferenceStateSnapshot | None,
    session: models.Session,
) -> tuple[str, str | None]:
    """(질문 텍스트, 겨냥한 anchor). 불확실 anchor가 없으면 시나리오 맥락으로 선택."""
    anchor = most_uncertain_anchor(snapshot)
    if anchor is None:
        goal = ((session.meta or {}).get("shoppingGoal") or "") + ((session.meta or {}).get("category") or "")
        if "선물" in goal:
            anchor = "Social"
        elif (session.meta or {}).get("category") is None:
            anchor = "Conditional"
    question = VALUE_QUESTIONS.get(anchor or "", DEFAULT_QUESTION)
    return question, anchor

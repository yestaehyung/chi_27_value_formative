"""Chat turn API (spec §20.2)."""
import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.agents.judge import judge_causal_relations
from app.agents.service_agent import handle_user_turn
from app.db import models, serializers
from app.db.database import SessionLocal, get_db
from app.db.schemas import TurnRequest

router = APIRouter(prefix="/api/sessions", tags=["turns"])


@router.post("/{session_id}/reply-suggestions")
async def reply_suggestions(session_id: str, db: DbSession = Depends(get_db)):
    """입력창 위 답변 칩 — 턴 응답과 분리해 따로 계산한다 (2026-08-14 지연 개선).

    턴 크리티컬 패스에서 ~1.3초를 빼는 대신, 프론트가 응답 표시 직후 이걸 호출한다.
    마지막 에이전트 턴(action·본문)과 최신 스냅샷 요약으로 재계산하므로 입력은 예전과
    동일하다. `forTurnId`는 프론트의 낡은 응답 가드용 — 그 사이 새 턴이 생겼으면 버린다.
    """
    from app.agents import response_generator as rg
    from app.llm.provider import get_provider

    session = db.get(models.Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    last_agent = (
        db.query(models.Turn)
        .filter(models.Turn.session_id == session_id, models.Turn.role == "service_agent")
        .order_by(models.Turn.turn_index.desc())
        .first()
    )
    if last_agent is None:
        return {"suggestions": [], "forTurnId": None}
    snapshot = (
        db.query(models.PreferenceStateSnapshot)
        .filter(models.PreferenceStateSnapshot.session_id == session_id)
        .order_by(models.PreferenceStateSnapshot.created_at.desc())
        .first()
    )
    recent_user = (
        db.query(models.Turn)
        .filter(models.Turn.session_id == session_id, models.Turn.role == "user")
        .order_by(models.Turn.turn_index.desc())
        .limit(5)
        .all()
    )
    suggestions = await rg.generate_reply_suggestions(
        get_provider(), last_agent.agent_action or "recommend", last_agent.content,
        snapshot.user_visible_summary if snapshot else None,
        recent_user_utterances=[t.content for t in reversed(recent_user)],
    )
    return {"suggestions": suggestions, "forTurnId": last_agent.id}


async def _process_turn_to_payload(session_id: str, content: str, role: str) -> dict:
    """자체 DB 세션으로 턴을 끝까지 처리하고 직렬화까지 마친 응답 dict를 만든다.

    요청 범위 세션을 쓰지 않는 이유: 클라이언트 연결이 끊기면 Starlette이 요청
    태스크를 취소하고 의존성 세션을 닫는다 — 그 세션을 물고 있으면 생성 중이던
    에이전트 응답이 유실된다(2026-08-16 실측: 사용자 발화만 남고 답변 없음).
    직렬화까지 이 안에서 끝내야 세션 종료 후 detached ORM 접근이 없다."""
    db = SessionLocal()
    try:
        session = db.get(models.Session, session_id)
        result = await handle_user_turn(db, session, content, role=role)
        impressions = [
            serializers.impression_to_dict(i, db.get(models.Product, i.product_id))
            for i in result.impressions
        ]
        return {
            "turn": serializers.turn_to_dict(result.user_turn),
            "agentResponse": serializers.turn_to_dict(result.agent_turn),
            "recommendedProducts": impressions,
            "preferenceState": serializers.participant_state(result.snapshot, session),
            "conflicts": [serializers.conflict_to_dict(c)
                          for c in serializers.participant_conflicts(result.conflicts)],
            "replySuggestions": result.reply_suggestions,
        }
    finally:
        db.close()


@router.post("/{session_id}/turns")
async def post_turn(session_id: str, req: TurnRequest, background_tasks: BackgroundTasks,
                    db: DbSession = Depends(get_db)):
    session = db.get(models.Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    if session.status != "active":
        raise HTTPException(400, "session is not active")

    # shield: 연결이 끊겨도(요청 취소) 처리 태스크는 계속 완주해 응답을 저장한다 —
    # 참가자는 새로고침하면 완성된 답변을 본다. 응답만 버려질 뿐 데이터는 남는다.
    # (그 경우 M5 judge 백그라운드 1회는 건너뛰지만 다음 턴에서 다시 평결된다.)
    task = asyncio.create_task(_process_turn_to_payload(session_id, req.content, req.role))
    payload = await asyncio.shield(task)
    # M5: judge는 턴을 막지 않는다 — 응답 후 비동기로 인과 엣지를 평결
    background_tasks.add_task(judge_causal_relations, session_id)
    return payload

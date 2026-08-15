"""Chat turn API (spec §20.2)."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.agents.judge import judge_causal_relations
from app.agents.service_agent import handle_user_turn
from app.db import models, serializers
from app.db.database import get_db
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
    suggestions = await rg.generate_reply_suggestions(
        get_provider(), last_agent.agent_action or "recommend", last_agent.content,
        snapshot.user_visible_summary if snapshot else None,
    )
    return {"suggestions": suggestions, "forTurnId": last_agent.id}


@router.post("/{session_id}/turns")
async def post_turn(session_id: str, req: TurnRequest, background_tasks: BackgroundTasks,
                    db: DbSession = Depends(get_db)):
    session = db.get(models.Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    if session.status != "active":
        raise HTTPException(400, "session is not active")

    result = await handle_user_turn(db, session, req.content, role=req.role)
    # M5: judge는 턴을 막지 않는다 — 응답 후 비동기로 인과 엣지를 평결
    background_tasks.add_task(judge_causal_relations, session_id)

    impressions = [
        serializers.impression_to_dict(i, db.get(models.Product, i.product_id))
        for i in result.impressions
    ]
    return {
        "turn": serializers.turn_to_dict(result.user_turn),
        "agentResponse": serializers.turn_to_dict(result.agent_turn),
        "recommendedProducts": impressions,
        "preferenceState": serializers.participant_state(result.snapshot, session),
        "conflicts": [serializers.conflict_to_dict(c) for c in serializers.participant_conflicts(result.conflicts)],
        "replySuggestions": result.reply_suggestions,
    }

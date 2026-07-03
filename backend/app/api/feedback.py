"""Feedback API (spec §20.3)."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.agents.judge import judge_causal_relations
from app.agents.service_agent import handle_feedback
from app.db import models, serializers
from app.db.database import get_db
from app.db.schemas import FeedbackRequest

router = APIRouter(prefix="/api/sessions", tags=["feedback"])


@router.post("/{session_id}/feedback")
async def post_feedback(session_id: str, req: FeedbackRequest, background_tasks: BackgroundTasks,
                        db: DbSession = Depends(get_db)):
    session = db.get(models.Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    product = db.get(models.Product, req.productId)
    if product is None:
        raise HTTPException(404, "product not found")

    result = await handle_feedback(
        db, session,
        product_id=req.productId,
        feedback_type=req.type,
        reason_code=req.reasonCode,
        reason_text=req.reasonText,
        turn_id=req.turnId,
    )
    # M5: judge는 응답을 막지 않는다 — 비동기 인과 엣지 평결
    background_tasks.add_task(judge_causal_relations, session_id)
    return {
        "feedbackEvent": serializers.feedback_to_dict(result.feedback_event),
        "updatedPreferenceState": serializers.participant_state(result.snapshot, session),
        "newConflicts": [serializers.conflict_to_dict(c) for c in serializers.participant_conflicts(result.new_conflicts)],
        "chosenRejectedPairsCreated": [serializers.pair_to_dict(p) for p in result.pairs],
        # 자세히(view_detail) 클릭의 상호작용 응답 — 상품 설명 + 궁금점 질문 턴 (2026-07-03)
        "agentTurn": serializers.turn_to_dict(result.agent_turn) if result.agent_turn else None,
        "replySuggestions": result.reply_suggestions,
    }

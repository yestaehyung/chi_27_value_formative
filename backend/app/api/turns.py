"""Chat turn API (spec §20.2)."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.agents.judge import judge_causal_relations
from app.agents.service_agent import handle_user_turn
from app.db import models, serializers
from app.db.database import get_db
from app.db.schemas import TurnRequest

router = APIRouter(prefix="/api/sessions", tags=["turns"])


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
        "preferenceState": serializers.snapshot_to_dict(result.snapshot) if result.snapshot else None,
        "conflicts": [serializers.conflict_to_dict(c) for c in result.conflicts],
    }

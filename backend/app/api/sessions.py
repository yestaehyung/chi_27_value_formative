"""Session API (spec §20.1)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.core.ids import new_id
from app.db import models, serializers
from app.db.database import get_db
from app.db.schemas import CreateSessionRequest
from app.ontology.state_builder import build_snapshot
from app.products.seed_loader import get_scenario

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("")
def create_session(req: CreateSessionRequest, db: DbSession = Depends(get_db)):
    if req.scenarioId == "custom":
        # 회상 인터뷰 결과를 초기 맥락으로 사용 (FS1, weekly deck S55)
        scenario = {
            "id": "custom",
            "title": req.customTitle or "직접 입력 시나리오",
            "initialUserNeed": req.customContext or "",
            "targetCategory": None,
            "context": "회상 인터뷰 기반",
        }
    else:
        scenario = get_scenario(req.scenarioId)
        if scenario is None:
            raise HTTPException(404, f"unknown scenario: {req.scenarioId}")
    # 참가자 단위 — trait 가치/자연어 명세가 세션을 넘어 누적된다 (2층 모델).
    participant_id = req.participantId
    if participant_id:
        if db.get(models.Participant, participant_id) is None:
            db.add(models.Participant(id=participant_id))
    else:
        participant_id = new_id("part")
        db.add(models.Participant(id=participant_id))
    session = models.Session(
        id=new_id("sess"),
        mode=req.mode,
        scenario_id=req.scenarioId,
        user_agent_id=req.userAgentId,
        participant_id=participant_id,
        current_stage="exploration",
        status="active",
        meta={
            "studyCondition": req.studyCondition,
            "category": scenario.get("targetCategory"),
            "shoppingGoal": scenario.get("title"),
            **({"customScenario": scenario} if req.scenarioId == "custom" else {}),
        },
    )
    db.add(session)
    db.flush()
    snapshot = build_snapshot(db, session)
    db.commit()
    return {
        "sessionId": session.id,
        "session": serializers.session_to_dict(session),
        "initialState": serializers.snapshot_to_dict(snapshot),
        "scenario": {k: v for k, v in scenario.items() if k != "groundTruthHiddenIntentions"},
    }


@router.get("/{session_id}")
def get_session(session_id: str, db: DbSession = Depends(get_db)):
    session = db.get(models.Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    turns = (
        db.query(models.Turn)
        .filter(models.Turn.session_id == session_id)
        .order_by(models.Turn.turn_index)
        .all()
    )
    impressions = (
        db.query(models.ProductImpression)
        .filter(models.ProductImpression.session_id == session_id)
        .order_by(models.ProductImpression.created_at, models.ProductImpression.rank)
        .all()
    )
    feedback = (
        db.query(models.FeedbackEvent)
        .filter(models.FeedbackEvent.session_id == session_id)
        .order_by(models.FeedbackEvent.created_at)
        .all()
    )
    snapshot = (
        db.query(models.PreferenceStateSnapshot)
        .filter(models.PreferenceStateSnapshot.session_id == session_id)
        .order_by(models.PreferenceStateSnapshot.created_at.desc())
        .first()
    )
    conflicts = (
        db.query(models.PreferenceConflict)
        .filter(models.PreferenceConflict.session_id == session_id)
        .filter(models.PreferenceConflict.status.in_(["open", "shown_to_user"]))
        .all()
    )
    scenario = (session.meta or {}).get("customScenario") or get_scenario(session.scenario_id) or {}
    return {
        "session": serializers.session_to_dict(session),
        "scenario": {k: v for k, v in scenario.items() if k != "groundTruthHiddenIntentions"},
        "turns": [serializers.turn_to_dict(t) for t in turns],
        "impressions": [
            serializers.impression_to_dict(i, db.get(models.Product, i.product_id))
            for i in impressions
        ],
        "feedback": [serializers.feedback_to_dict(f) for f in feedback],
        "preferenceState": serializers.snapshot_to_dict(snapshot) if snapshot else None,
        "conflicts": [serializers.conflict_to_dict(c) for c in conflicts],
    }

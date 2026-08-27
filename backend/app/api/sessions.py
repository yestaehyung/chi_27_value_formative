"""Session API (spec §20.1)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.core.conditions import ensure_condition
from app.core.config import settings
from app.core.ids import new_id
from app.db import models, serializers
from app.db.database import get_db
from app.db.schemas import CreateSessionRequest
from app.ontology.state_builder import build_snapshot
from app.products.seed_loader import get_scenario

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("")
def create_session(req: CreateSessionRequest, db: DbSession = Depends(get_db)):
    # 본실험 경로(2026-08-06~): 시나리오 대신 카테고리로 과제를 연다. 상품 풀을 본실험용으로
    # 재구성하면서 옛 시나리오(태블릿·코트…)의 카테고리에 상품이 0개가 됐고, 시나리오를
    # 유지하면 그 어긋남이 계속 재발한다. 카테고리는 DB에서 직접 확인하므로 어긋날 수 없다.
    # (시나리오 경로는 시뮬레이션·합성이 계속 쓰므로 아래에 그대로 남긴다.)
    if req.category:
        available = {
            c for (c,) in db.query(models.Product.category)
            .filter(models.Product.category.isnot(None)).distinct()
        }
        if req.category not in available:
            raise HTTPException(404, f"unknown category: {req.category}")
        # 미완주 세션 재개 (2026-08-27, v4 파일럿 관찰): 같은 참가자가 같은 과제를
        # 다시 열면(빈손 후 이탈→재진입·새로고침) 새 세션 대신 진행 중이던 세션을
        # 돌려준다. 감사(criterionAudit)까지 끝난 세션은 제외 — 완료 과제 불가침.
        # req.category가 있는 스터디 과제 경로에서만 발동 (데모·시뮬레이션 무영향).
        if req.participantId:
            existing = (
                db.query(models.Session)
                .filter(models.Session.participant_id == req.participantId,
                        models.Session.scenario_id == f"cat:{req.category}",
                        models.Session.status == "active")
                .order_by(models.Session.started_at.desc())
                .all()
            )
            for s in existing:
                if "criterionAudit" not in (s.meta or {}):
                    return {"sessionId": s.id, "resumed": True}
        # 모양은 get_scenario가 정의한다 — 조회(get_session·연구자 뷰)와 같은 복원 경로.
        scenario = get_scenario(f"cat:{req.category}")
    elif req.scenarioId == "custom":
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
    participant = db.get(models.Participant, participant_id) if participant_id else None
    if participant is None:
        participant_id = participant_id or new_id("part")
        participant = models.Participant(id=participant_id)
        db.add(participant)
    # 조건 우선순위: ① 참가자에 이미 붙은 값 → ② 요청이 명시한 값(신규 참가자만) → ③ 균형 배정.
    # ①이 최우선인 이유는 한 사람의 여러 과제가 반드시 같은 조건이어야 하기 때문이다.
    # ②는 테스트·데모가 조건을 고정하는 통로 — 본실험 프론트는 값을 보내지 않으므로 ③으로 간다.
    # (시뮬레이션은 조건 설계 밖이라 요청값을 그대로 쓴다.)
    study_condition = req.studyCondition
    if req.mode == "manual":
        if participant.study_condition is None and req.studyCondition:
            participant.study_condition = req.studyCondition
        study_condition = ensure_condition(db, participant)
    session = models.Session(
        id=new_id("sess"),
        mode=req.mode,
        scenario_id=scenario["id"] if req.category else req.scenarioId,
        user_agent_id=req.userAgentId,
        participant_id=participant_id,
        current_stage="exploration",
        status="active",
        meta={
            "studyCondition": study_condition,
            "category": scenario.get("targetCategory"),
            "shoppingGoal": scenario.get("title"),
            # 참가자가 선택 시점에 매긴 친숙도(2+2) — within-subjects 요인이라 세션에
            # 남아야 분석된다. 과제 직전 설문(TPRE_K1/K2)이 이 이분법의 조작 점검.
            **({"familiarity": req.familiarity} if req.familiarity else {}),
            **({"customScenario": scenario} if req.scenarioId == "custom" and not req.category else {}),
            # 파일럿 변형 도장 — 분석에서 본실험과 구조적으로 갈리게 한다
            **({"uiVariant": settings.ui_variant} if settings.ui_variant else {}),
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
        "preferenceState": serializers.participant_state(snapshot, session),
        # 참가자 화면용 페이로드 — ambiguous 충돌은 카드로 내보내지 않는다 (연구 뷰는 /api/research)
        "conflicts": [serializers.conflict_to_dict(c) for c in serializers.participant_conflicts(conflicts)],
    }

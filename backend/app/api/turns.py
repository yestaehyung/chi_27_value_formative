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

# 처리 중 세션 레지스트리 (단일 프로세스) — shield로 계속 도는 원본 파이프라인과
# 재시도/재전송이 같은 세션에 파이프라인을 겹쳐 돌리는 경합 방지 (2026-08-18 자체
# 점검에서 발견: 네트워크 단절 후 배너 재시도가 이중 응답을 만들 수 있었음).
_inflight_sessions: set[str] = set()


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


async def _process_turn_to_payload(session_id: str, content: str, role: str,
                                   client_request_id: str | None = None,
                                   retry_turn_id: str | None = None,
                                   input_source: str | None = None) -> dict:
    """자체 DB 세션으로 턴을 끝까지 처리하고 직렬화까지 마친 응답 dict를 만든다.

    요청 범위 세션을 쓰지 않는 이유: 클라이언트 연결이 끊기면 Starlette이 요청
    태스크를 취소하고 의존성 세션을 닫는다 — 그 세션을 물고 있으면 생성 중이던
    에이전트 응답이 유실된다(2026-08-16 실측: 사용자 발화만 남고 답변 없음).
    직렬화까지 이 안에서 끝내야 세션 종료 후 detached ORM 접근이 없다.
    retry_turn_id(2026-08-18): 응답 없는 기존 사용자 턴을 새 턴 없이 재처리."""
    db = SessionLocal()
    _inflight_sessions.add(session_id)
    try:
        session = db.get(models.Session, session_id)
        existing = db.get(models.Turn, retry_turn_id) if retry_turn_id else None
        try:
            result = await handle_user_turn(db, session, content, role=role,
                                            client_request_id=client_request_id,
                                            existing_turn=existing,
                                            input_source=input_source)
        except Exception:
            # 파이프라인 하드 실패 — 사용자 턴을 failed로 남겨 프론트가 재시도를 제안하게.
            db.rollback()
            pend = (db.query(models.Turn)
                    .filter(models.Turn.session_id == session_id,
                            models.Turn.status == "pending")
                    .order_by(models.Turn.turn_index.desc()).first())
            if pend is not None:
                pend.status = "failed"
                db.commit()
            raise
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
        _inflight_sessions.discard(session_id)
        db.close()


@router.post("/{session_id}/turns")
async def post_turn(session_id: str, req: TurnRequest, background_tasks: BackgroundTasks,
                    db: DbSession = Depends(get_db)):
    session = db.get(models.Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    if session.status != "active":
        raise HTTPException(400, "session is not active")

    if session_id in _inflight_sessions:
        # 같은 세션의 응답이 아직 생성 중 — 겹쳐 돌리지 않는다 (프론트: 잠시 후 재조회)
        raise HTTPException(409, "reply generation in progress")

    # 멱등 (2026-08-18): 같은 clientRequestId의 턴이 이미 있으면 새로 만들지 않는다 —
    # 502/타임아웃 후 재전송이 같은 발화를 두 번 저장하는 것을 구조적으로 차단.
    # 프론트는 duplicate 응답을 받으면 세션을 다시 불러온다.
    if req.clientRequestId:
        dup = (db.query(models.Turn)
               .filter(models.Turn.session_id == session_id,
                       models.Turn.client_request_id == req.clientRequestId)
               .first())
        if dup is not None:
            return {"duplicate": True, "turnId": dup.id, "turnStatus": dup.status}

    # shield: 연결이 끊겨도(요청 취소) 처리 태스크는 계속 완주해 응답을 저장한다 —
    # 참가자는 새로고침하면 완성된 답변을 본다. 응답만 버려질 뿐 데이터는 남는다.
    # (그 경우 M5 judge 백그라운드 1회는 건너뛰지만 다음 턴에서 다시 평결된다.)
    task = asyncio.create_task(_process_turn_to_payload(
        session_id, req.content, req.role, client_request_id=req.clientRequestId,
        input_source=req.inputSource))
    payload = await asyncio.shield(task)
    # M5: judge는 턴을 막지 않는다 — 응답 후 비동기로 인과 엣지를 평결
    background_tasks.add_task(judge_causal_relations, session_id)
    return payload


@router.post("/{session_id}/proceed-recommend")
async def proceed_recommend(session_id: str):
    """ours-v3 칩 확인 게이트의 2단계 — 사용자가 칩을 확인/수정한 뒤 '추천 보기'를 누르면
    호출된다. recommend_after_resolution을 재사용해 **확인된 최신 기준으로** 재플래닝→
    리랭크→추천 턴을 만든다 (evidence purity 경로 그대로)."""
    from app.agents.service_agent import recommend_after_resolution

    if session_id in _inflight_sessions:
        raise HTTPException(409, "reply generation in progress")
    db = SessionLocal()
    _inflight_sessions.add(session_id)
    try:
        session = db.get(models.Session, session_id)
        if session is None:
            raise HTTPException(404, "session not found")
        if not (session.meta or {}).get("pendingRecommend"):
            raise HTTPException(409, "no pending recommendation")
        session.meta = {k: v for k, v in session.meta.items() if k != "pendingRecommend"}
        db.commit()
        snapshot = (
            db.query(models.PreferenceStateSnapshot)
            .filter(models.PreferenceStateSnapshot.session_id == session_id)
            .order_by(models.PreferenceStateSnapshot.turn_index.desc())
            .first()
        )
        turn, impressions, _products = await recommend_after_resolution(db, session, snapshot)
        return {
            "agentResponse": serializers.turn_to_dict(turn),
            "recommendedProducts": [
                serializers.impression_to_dict(i, db.get(models.Product, i.product_id))
                for i in impressions
            ],
        }
    finally:
        _inflight_sessions.discard(session_id)
        db.close()


@router.post("/{session_id}/turns/{turn_id}/retry")
async def retry_turn(session_id: str, turn_id: str, background_tasks: BackgroundTasks,
                     db: DbSession = Depends(get_db)):
    """응답 없이 남은 사용자 턴(pending/failed — 배포 재시작·파이프라인 실패의 흔적)을
    **같은 턴으로** 재처리한다. 새 턴을 만들지 않으므로 중복 발화가 생기지 않는다."""
    session = db.get(models.Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    turn = db.get(models.Turn, turn_id)
    if turn is None or turn.session_id != session_id:
        raise HTTPException(404, "turn not found")
    if turn.role not in ("user", "user_agent"):
        raise HTTPException(400, "not a user turn")
    answered = (db.query(models.Turn)
                .filter(models.Turn.session_id == session_id,
                        models.Turn.turn_index > turn.turn_index,
                        models.Turn.role == "service_agent")
                .first())
    if answered is not None:
        raise HTTPException(409, "turn already answered")
    if session_id in _inflight_sessions:
        raise HTTPException(409, "reply generation in progress")

    task = asyncio.create_task(_process_turn_to_payload(
        session_id, turn.content, turn.role, retry_turn_id=turn_id))
    payload = await asyncio.shield(task)
    background_tasks.add_task(judge_causal_relations, session_id)
    return payload

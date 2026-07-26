"""Conflict resolution API (spec §20.4)."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.db import models, serializers
from app.db.database import get_db
from app.db.schemas import ConflictResolveRequest
from app.preference_commit.conflict_resolver import resolve_conflict

router = APIRouter(prefix="/api/conflicts", tags=["conflicts"])


@router.post("/{conflict_id}/resolve")
async def post_resolve(conflict_id: str, req: ConflictResolveRequest, db: DbSession = Depends(get_db)):
    conflict = db.get(models.PreferenceConflict, conflict_id)
    if conflict is None:
        raise HTTPException(404, "conflict not found")
    if conflict.status not in ("open", "shown_to_user"):
        raise HTTPException(400, "conflict already resolved")

    # 해소 액션 파악 (재추천 여부 판단용) — keep_old는 기준 변화가 없음.
    options = conflict.suggested_resolutions or []
    opt = next((o for o in options if o.get("id") == req.optionId), None)
    action = opt["action"] if opt else req.optionId
    session = db.get(models.Session, conflict.session_id)

    event, snapshot, message, turn = resolve_conflict(db, conflict, req.optionId, req.manualText)
    resp = {
        "resolvedConflict": serializers.conflict_to_dict(conflict),
        "resolutionEvent": serializers.resolution_to_dict(event),
        "newPreferenceState": serializers.snapshot_to_dict(snapshot),
        "message": message,
        "turn": serializers.turn_to_dict(turn),  # 해소 발화 — 영속화된 Turn (프론트는 이걸 렌더)
    }
    # 기준이 실제로 바뀐 해소면 갱신된 기준으로 바로 재추천 — 해소가 dead-end가 되지 않게.
    # keep_old(변화 없음)는 생략. 재추천 실패해도 해소는 이미 커밋됐으므로 응답은 정상 반환.
    if action != "keep_old" and session is not None:
        try:
            from app.agents import service_agent

            rec_turn, impressions, _ = await service_agent.recommend_after_resolution(db, session, snapshot)
            resp["recommendTurn"] = serializers.turn_to_dict(rec_turn)
            resp["recommendedProducts"] = [
                serializers.impression_to_dict(i, db.get(models.Product, i.product_id))
                for i in impressions
            ]
        except Exception:  # noqa: BLE001
            logging.exception("post-resolution recommend failed")
    return resp

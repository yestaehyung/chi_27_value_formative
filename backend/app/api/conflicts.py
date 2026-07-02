"""Conflict resolution API (spec §20.4)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.db import models, serializers
from app.db.database import get_db
from app.db.schemas import ConflictResolveRequest
from app.preference_commit.conflict_resolver import resolve_conflict

router = APIRouter(prefix="/api/conflicts", tags=["conflicts"])


@router.post("/{conflict_id}/resolve")
def post_resolve(conflict_id: str, req: ConflictResolveRequest, db: DbSession = Depends(get_db)):
    conflict = db.get(models.PreferenceConflict, conflict_id)
    if conflict is None:
        raise HTTPException(404, "conflict not found")
    if conflict.status not in ("open", "shown_to_user"):
        raise HTTPException(400, "conflict already resolved")

    event, snapshot, message, turn = resolve_conflict(db, conflict, req.optionId, req.manualText)
    return {
        "resolvedConflict": serializers.conflict_to_dict(conflict),
        "resolutionEvent": serializers.resolution_to_dict(event),
        "newPreferenceState": serializers.snapshot_to_dict(snapshot),
        "message": message,
        "turn": serializers.turn_to_dict(turn),  # 해소 발화 — 영속화된 Turn (프론트는 이걸 렌더)
    }

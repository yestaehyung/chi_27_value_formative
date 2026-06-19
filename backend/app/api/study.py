"""Formative Study (FS1) 계측 API — DG3~DG6.

- 관찰 마커: 연구자가 신뢰/불신/혼란 순간을 현재 turn에 고정 기록 (DG4)
- evidence 열람 로깅: 사용자가 근거를 확인한 시점 기록 (DG3)
- ground-truth: 회상 인터뷰 hidden intention 저장 + 시스템 KG와 gap 분석 (DG5)
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from app.core.ids import new_id
from app.db import models, serializers
from app.db.database import get_db
from app.ontology.merge import _bigrams, _similar

# 흔한 기능어 — 매칭 신호에서 제외 (연구자 자유표현 ground-truth 대조용)
_STOP = {"것", "수", "게", "거", "더", "좀", "잘", "안", "은", "는", "이", "가", "을", "를",
         "에", "에게", "으로", "로", "와", "과", "도", "만", "맞기", "맞는", "있는", "있음", "선물"}


def _gap_match(gt: str, topic: str) -> bool:
    """연구자가 자유 표현으로 적은 ground-truth와 시스템 topic의 관대한 의미 매칭.
    (1) 문자 bigram Jaccard ≥ 0.35  또는  (2) 길이 2+ 내용어 2개 이상 공유."""
    if _similar(gt, topic):
        return True
    ba, bb = _bigrams(gt), _bigrams(topic)
    if ba and bb and len(ba & bb) / len(ba | bb) >= 0.35:
        return True
    ta = {w for w in gt.replace("(", " ").replace(")", " ").split() if len(w) >= 2 and w not in _STOP}
    tb = {w for w in topic.split() if len(w) >= 2 and w not in _STOP}
    # 부분 문자열 공유까지 허용 (조사 변형 흡수)
    shared = sum(1 for a in ta if any(a[:2] in b or b[:2] in a for b in tb))
    return shared >= 2

router = APIRouter(prefix="/api/study", tags=["study"])

MARKER_TAGS = {"trust", "distrust", "confusion", "correction_wish", "other"}


class MarkerRequest(BaseModel):
    tag: str
    note: Optional[str] = None


class InspectRequest(BaseModel):
    topicId: str


class GroundTruthRequest(BaseModel):
    items: list[str]  # 회상 인터뷰에서 추출한 hidden intention 라벨들


class SurveyRequest(BaseModel):
    answers: dict                       # {questionId: value}
    profile: Optional[dict] = None      # 파생 점수 (Functional/Social/.../Utilitarian/Hedonic 평균)
    label: Optional[str] = None         # 참가자 표시명 (선택)


@router.post("/survey")
def submit_survey(req: SurveyRequest, db: DbSession = Depends(get_db)):
    """FS1 사전 설문 제출 → 참가자 생성(설문 저장). 이후 세션이 이 참가자에 연결된다."""
    pid = new_id("part")
    label = req.label or f"FS-{pid.split('_')[-1][:6]}"
    db.add(models.Participant(
        id=pid,
        label=label,
        survey={"answers": req.answers, "profile": req.profile or {}},
    ))
    db.commit()
    return {"participantId": pid, "label": label}


def _current_turn_index(db: DbSession, session_id: str) -> int:
    last = (
        db.query(models.Turn)
        .filter(models.Turn.session_id == session_id)
        .order_by(models.Turn.turn_index.desc())
        .first()
    )
    return last.turn_index if last else 0


@router.post("/sessions/{session_id}/markers")
def add_marker(session_id: str, req: MarkerRequest, db: DbSession = Depends(get_db)):
    if db.get(models.Session, session_id) is None:
        raise HTTPException(404, "session not found")
    tag = req.tag if req.tag in MARKER_TAGS else "other"
    marker = models.ObservationMarker(
        id=new_id("mark"),
        session_id=session_id,
        turn_index=_current_turn_index(db, session_id),
        kind="marker",
        tag=tag,
        note=req.note,
    )
    db.add(marker)
    db.commit()
    return {"marker": serializers.marker_to_dict(marker)}


@router.post("/sessions/{session_id}/inspect")
def log_inspect(session_id: str, req: InspectRequest, db: DbSession = Depends(get_db)):
    """사용자가 evidence drawer로 근거를 확인 — 불신/검증 신호 (DG3)."""
    if db.get(models.Session, session_id) is None:
        raise HTTPException(404, "session not found")
    marker = models.ObservationMarker(
        id=new_id("insp"),
        session_id=session_id,
        turn_index=_current_turn_index(db, session_id),
        kind="inspect",
        tag="inspect_evidence",
        topic_id=req.topicId,
    )
    db.add(marker)
    db.commit()
    return {"ok": True}


@router.put("/sessions/{session_id}/ground-truth")
def set_ground_truth(session_id: str, req: GroundTruthRequest, db: DbSession = Depends(get_db)):
    session = db.get(models.Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    meta = dict(session.meta or {})
    meta["groundTruthHiddenIntentions"] = [s.strip() for s in req.items if s.strip()]
    session.meta = meta
    db.commit()
    return {"groundTruth": meta["groundTruthHiddenIntentions"]}


@router.get("/sessions/{session_id}/gap")
def ground_truth_gap(session_id: str, db: DbSession = Depends(get_db)):
    """회상 ground-truth ↔ 시스템 KG 대조 (DG5): caught / missed / extra."""
    session = db.get(models.Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    gt = (session.meta or {}).get("groundTruthHiddenIntentions", [])
    topics = (
        db.query(models.IntentionTopic)
        .filter(models.IntentionTopic.session_id == session_id)
        .filter(models.IntentionTopic.status.notin_(["rejected_by_user", "inactive"]))
        .all()
    )
    topic_labels = [t.label for t in topics]

    caught, missed = [], []
    matched_topic_labels = set()
    for g in gt:
        hit = next((tl for tl in topic_labels if _gap_match(g, tl)), None)
        if hit:
            caught.append({"groundTruth": g, "systemTopic": hit})
            matched_topic_labels.add(hit)
        else:
            missed.append(g)
    # 시스템이 잡았지만 ground-truth에 없던 것 = 신규 발견 (bottom-up 후보)
    extra = [
        {"label": t.label, "source": t.source, "explicitness": t.explicitness}
        for t in topics if t.label not in matched_topic_labels
    ]
    recall = round(len(caught) / len(gt), 2) if gt else None
    return {
        "groundTruthCount": len(gt),
        "caught": caught,
        "missed": missed,
        "extra": extra,
        "recall": recall,
        "discoveryCount": len(extra),
    }

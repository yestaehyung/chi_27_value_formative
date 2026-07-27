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
    """사전 설문 제출 → 참가자 생성(설문 저장) + between-subjects 조건 배정.
    조건은 여기서 한 번만 정해지고 이후 모든 세션이 이 값을 따른다."""
    from app.core.conditions import assign_condition

    pid = new_id("part")
    label = req.label or f"P-{pid.split('_')[-1][:6]}"
    condition = assign_condition(db)
    db.add(models.Participant(
        id=pid,
        label=label,
        survey={"answers": req.answers, "profile": req.profile or {}},
        study_condition=condition,
    ))
    db.commit()
    return {"participantId": pid, "label": label, "studyCondition": condition}


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


class PostSurveyRequest(BaseModel):
    answers: dict                    # {itemId: "1".."7"} — 7점 리커트
    profile: Optional[dict] = None   # 구인별 평균 (understanding/satisfaction/trust/…)


@router.put("/sessions/{session_id}/post-survey")
def submit_post_survey(session_id: str, req: PostSurveyRequest, db: DbSession = Depends(get_db)):
    """세션 종료 사후 설문 (이해·만족·신뢰 핵심 3구인 + 확장 4구인) — per-session,
    회상 GT와 같은 meta 채널에 저장. 재제출 시 덮어쓴다(마지막 응답이 유효)."""
    from datetime import datetime, timezone

    session = db.get(models.Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    meta = dict(session.meta or {})
    meta["postSurvey"] = {
        "answers": req.answers,
        "profile": req.profile or {},
        "submittedAt": datetime.now(timezone.utc).isoformat(),
    }
    session.meta = meta
    db.commit()
    return {"ok": True, "profile": meta["postSurvey"]["profile"]}


# ── 본실험(메인 스터디) 설문 채널 ────────────────────────────────────────
# 5개 도구 중 3개가 여기 붙는다 (사전 설문은 위 POST /survey를 그대로 쓴다):
#   과제 직전 → sessions.meta.preTaskSurvey
#   과제 직후 → sessions.meta.postSurvey (위 엔드포인트 재사용 — 문항 id만 다름)
#   전체 종료 → participants.survey.postStudy
#   기준별 검증 → criterion_validations 테이블


class PreTaskSurveyRequest(BaseModel):
    answers: dict                     # {questionId: value}
    category: Optional[str] = None    # 이 과제의 상품군 (문항 치환에 쓰인 값 그대로 보존)
    profile: Optional[dict] = None    # 구인별 평균 (domain_knowledge/criteria_clarity)


@router.put("/sessions/{session_id}/pre-task-survey")
def submit_pre_task_survey(session_id: str, req: PreTaskSurveyRequest, db: DbSession = Depends(get_db)):
    """쇼핑 과제 직전 설문 — 상품군 지식·경험 + 구매 기준 명확성(사전).
    직후 설문의 같은 문항과 짝지어 Δ(명확성 변화)를 낸다."""
    from datetime import datetime, timezone

    session = db.get(models.Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    meta = dict(session.meta or {})
    meta["preTaskSurvey"] = {
        "answers": req.answers,
        "category": req.category,
        "profile": req.profile or {},
        "submittedAt": datetime.now(timezone.utc).isoformat(),
    }
    session.meta = meta
    db.commit()
    return {"ok": True, "profile": meta["preTaskSurvey"]["profile"]}


class PostStudySurveyRequest(BaseModel):
    answers: dict
    profile: Optional[dict] = None    # interpretability / evidence / edit_usability


@router.put("/participants/{participant_id}/post-study-survey")
def submit_post_study_survey(
    participant_id: str, req: PostStudySurveyRequest, db: DbSession = Depends(get_db)
):
    """전체 과제 종료 후 설문 — 해석 이해가능성·근거 타당성·수정 사용성.
    세션이 아니라 참가자에 붙는다 (3개 과제 전체에 대한 회고)."""
    from datetime import datetime, timezone

    participant = db.get(models.Participant, participant_id)
    if participant is None:
        raise HTTPException(404, "participant not found")
    survey = dict(participant.survey or {})
    survey["postStudy"] = {
        "answers": req.answers,
        "profile": req.profile or {},
        "submittedAt": datetime.now(timezone.utc).isoformat(),
    }
    participant.survey = survey
    db.commit()
    return {"ok": True, "profile": survey["postStudy"]["profile"]}


# 우선순위 정렬 키 — high가 먼저 제시된다
_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


@router.get("/sessions/{session_id}/criterion-candidates")
def criterion_candidates(session_id: str, limit: int = 5, db: DbSession = Depends(get_db)):
    """기준별 검증 설문에 제시할 '주요 구매 기준' 3–5개 + 각 기준의 근거.
    활성 topic을 우선순위 → 확신도 순으로 정렬해 상위 N개. 근거는 evidence drawer와 동일 소스."""
    from app.api.preferences import build_topic_evidence

    session = db.get(models.Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    topics = (
        db.query(models.IntentionTopic)
        .filter(models.IntentionTopic.session_id == session_id)
        .filter(models.IntentionTopic.status.notin_(["rejected_by_user", "inactive"]))
        .all()
    )
    topics.sort(key=lambda t: (_PRIORITY_RANK.get(t.priority or "medium", 1), -(t.confidence or 0.0)))
    return {
        "criteria": [
            {
                "topic": serializers.topic_to_dict(t),
                "evidence": build_topic_evidence(db, t),
            }
            for t in topics[: max(1, limit)]
        ]
    }


class CriterionValidationItem(BaseModel):
    topicId: str
    topicLabel: Optional[str] = None
    matches: Optional[str] = None
    importance: Optional[int] = None
    evidenceSupports: Optional[str] = None
    formation: Optional[str] = None


class CriterionValidationRequest(BaseModel):
    items: list[CriterionValidationItem]


@router.post("/sessions/{session_id}/criterion-validations")
def submit_criterion_validations(
    session_id: str, req: CriterionValidationRequest, db: DbSession = Depends(get_db)
):
    """추론된 기준별 직접 검증 응답 저장. 재제출 시 해당 세션의 기존 응답을 갈아끼운다
    (설문은 과제당 1회 — 중복 행이 쌓이면 기준별 집계가 이중 계상된다)."""
    session = db.get(models.Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")

    # 쓸 행을 먼저 만들고, 하나라도 있을 때만 기존 응답을 교체한다.
    # (전부 알 수 없는 topic인 요청이 이전 응답을 날려버리는 사고 방지 — 지우기 전에 확인)
    rows = []
    for item in req.items:
        topic = db.get(models.IntentionTopic, item.topicId)
        if topic is None:
            continue  # 세션 중 삭제된 기준 — 조용히 건너뛴다
        rows.append(models.CriterionValidation(
            id=new_id("cval"),
            session_id=session_id,
            topic_id=topic.id,
            topic_label=item.topicLabel or topic.label,
            matches=item.matches,
            importance=item.importance,
            evidence_supports=item.evidenceSupports,
            formation=item.formation,
        ))
    if not rows:
        return {"saved": 0, "validations": []}

    (db.query(models.CriterionValidation)
       .filter(models.CriterionValidation.session_id == session_id)
       .delete(synchronize_session=False))
    for row in rows:
        db.add(row)
    saved = rows
    db.commit()
    return {"saved": len(saved),
            "validations": [serializers.criterion_validation_to_dict(r) for r in saved]}


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

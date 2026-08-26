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
    # Prolific 모집 파라미터 {pid, studyId, sessionId} — 승인/보상 매칭용 (2026-08-19)
    prolific: Optional[dict] = None


@router.post("/survey")
def submit_survey(req: SurveyRequest, db: DbSession = Depends(get_db)):
    """사전 설문 제출 → 참가자 생성(설문 저장) + between-subjects 조건 배정.
    조건은 여기서 한 번만 정해지고 이후 모든 세션이 이 값을 따른다."""
    from app.core.conditions import assign_condition

    pid = new_id("part")
    prolific = {
        k: str(v)[:64] for k, v in (req.prolific or {}).items()
        if k in ("pid", "studyId", "sessionId") and v
    }
    # Prolific PID가 있으면 라벨에 앞 8자를 붙여 관리자 화면에서 바로 매칭되게 한다
    label = req.label or (
        f"PL-{prolific['pid'][:8]}" if prolific.get("pid") else f"P-{pid.split('_')[-1][:6]}"
    )
    condition = assign_condition(db)
    db.add(models.Participant(
        id=pid,
        label=label,
        survey={"answers": req.answers, "profile": req.profile or {}},
        study_condition=condition,
        prolific=prolific or None,
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


FINAL_STATUSES = {"final", "shortlist", "explore_more", "none_suitable"}


class FinalChoiceRequest(BaseModel):
    # 결정 상태 4범주 (측정 계획 §5.1). 구버전 호환: status 없이 productId/noneReason만
    # 오면 final/none_suitable로 해석한다.
    status: Optional[str] = None
    productId: Optional[str] = None       # status=final일 때 필수
    shortlistIds: list[str] = []          # status=shortlist일 때 2개 이상
    noneReason: Optional[str] = None      # status=none_suitable 사유 / "no_products"
    # 2026-08-26 종료 절차 개편: 선택이 과제 상황에 맞는 이유(final/shortlist 필수는
    # 프론트가 강제) + 소프트 게이트 기록(2라운드 미만 종료 여부·시점 라운드 수)
    fitReason: Optional[str] = None
    earlyFinish: Optional[bool] = None
    roundsAtFinish: Optional[int] = None


@router.put("/sessions/{session_id}/final-choice")
def submit_final_choice(session_id: str, req: FinalChoiceRequest, db: DbSession = Depends(get_db)):
    """③ 최종 선택·결정 상태 확정 — 사후 기준 확인(④) **전에** 잠근다.

    기준을 뜯어보는 행위가 선택에 영향을 주지 못하게 하는 절차적 잠금이다.
    '필수 조건 위반 여부'는 여기서 판정하지 않는다 — 확정 시점의 기준 스냅샷과
    선택/후보 상품을 함께 저장해 분석 때 계산한다 (런타임 판정은 기준을 나중에 못 바꾼다).
    """
    from datetime import datetime, timezone

    session = db.get(models.Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    status = req.status or ("final" if req.productId else "none_suitable")
    if status not in FINAL_STATUSES:
        raise HTTPException(422, f"알 수 없는 결정 상태: {status}")
    if status == "final" and not req.productId:
        raise HTTPException(422, "최종 선택에는 productId가 필요하다")
    if status == "shortlist" and len(req.shortlistIds) < 2:
        raise HTTPException(422, "후보 목록에는 상품 2개 이상이 필요하다")
    if status == "none_suitable" and not req.noneReason:
        raise HTTPException(422, "적합 상품 없음에는 사유(noneReason)가 필요하다")
    shown = {
        pid for (pid,) in db.query(models.ProductImpression.product_id)
        .filter(models.ProductImpression.session_id == session_id)
    }
    for pid in [req.productId, *req.shortlistIds]:
        if pid and pid not in shown:
            raise HTTPException(422, "이 세션에서 노출된 적 없는 상품이다")
    # 확정 시점 기준 스냅샷 — 위반 분석의 재료 (rejected는 사용자가 이미 거른 기준이라 제외)
    topics = (
        db.query(models.IntentionTopic)
        .filter(models.IntentionTopic.session_id == session_id)
        .filter(models.IntentionTopic.status != "rejected_by_user")
        .all()
    )
    liked = [
        pid for (pid,) in db.query(models.FeedbackEvent.product_id)
        .filter(models.FeedbackEvent.session_id == session_id)
        .filter(models.FeedbackEvent.type == "like")
    ]
    meta = dict(session.meta or {})
    meta["finalChoice"] = {
        "status": status,
        "productId": req.productId,
        "shortlistIds": req.shortlistIds,
        "noneReason": req.noneReason,
        "fitReason": req.fitReason,
        "earlyFinish": bool(req.earlyFinish),
        "roundsAtFinish": req.roundsAtFinish,
        "decidedAt": datetime.now(timezone.utc).isoformat(),
        "criteriaAtDecision": [
            {
                "label": t.label, "status": t.status, "priority": t.priority,
                "explicitness": t.explicitness,
                "hardConstraint": bool((t.hints or {}).get("impliedHardConstraint")),
                "avoidance": bool((t.hints or {}).get("impliedAvoidance")),
            }
            for t in topics
        ],
        "likedIds": liked,
    }
    session.meta = meta
    db.commit()
    return {"ok": True, "finalChoice": meta["finalChoice"]}


class KnowledgeSurveyRequest(BaseModel):
    """제품군별 지식 행렬 (측정 계획 §4) — 카테고리 확정 직후 1회."""
    answers: dict                     # {"k:{카테고리}:SPK_1": "5", ...}
    scores: Optional[dict] = None     # {카테고리: 지식 5문항 평균(역채점 반영)}
    categories: list[str] = []


@router.put("/participants/{participant_id}/knowledge-survey")
def submit_knowledge_survey(
    participant_id: str, req: KnowledgeSurveyRequest, db: DbSession = Depends(get_db)
):
    """주관적 지식(Flynn & Goldsmith)·구매경험·초기 명확성·자유응답 저장 —
    참가자 단위 1회, 네 제품군을 한 행렬로. 조절변수 분석의 재료."""
    from datetime import datetime, timezone

    participant = db.get(models.Participant, participant_id)
    if participant is None:
        raise HTTPException(404, "participant not found")
    survey = dict(participant.survey or {})
    # 과제 직전 카테고리 단위 제출(2026-08-17)로 바뀌어 **병합** 저장한다 — 각 제출은
    # 해당 카테고리 분만 담고, 이전 카테고리 응답을 덮어쓰면 안 된다. 같은 카테고리
    # 재제출은 마지막 응답이 유효(기존 의미 유지).
    pk = dict(survey.get("productKnowledge") or {})
    survey["productKnowledge"] = {
        "answers": {**(pk.get("answers") or {}), **req.answers},
        "scores": {**(pk.get("scores") or {}), **(req.scores or {})},
        "categories": list(dict.fromkeys(list(pk.get("categories") or []) + list(req.categories))),
        "submittedAt": datetime.now(timezone.utc).isoformat(),
    }
    participant.survey = survey
    db.commit()
    return {"ok": True, "scores": survey["productKnowledge"]["scores"]}


class PostStudySurveyRequest(BaseModel):
    answers: dict
    profile: Optional[dict] = None    # 이해/투명성/통제/만족/신뢰/재사용 섹션 평균


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


class AuditOwnCriterion(BaseModel):
    """A파트 — 에이전트 기준 공개 전 참가자가 잠근 자기 기준 (측정 계획 §7.1A)."""
    label: str
    necessity: Optional[str] = None    # 반드시 충족 / 가능하면 충족 / 최종적으로 중요하지 않음
    influence: Optional[str] = None    # 예 / 아니오 / 판단하기 어려움


class CriterionValidationRequest(BaseModel):
    items: list[CriterionValidationItem]
    # 기준 감사 확장 (2026-08-13): A파트 자기 기준 + 에이전트가 놓친 기준.
    # precision/recall/F1의 재료 — items(B파트)와 함께 meta.criterionAudit에 저장.
    ownCriteria: list[AuditOwnCriterion] = []
    missingCriteria: list[str] = []


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

    # A파트(자기 기준)·누락 기준은 topic 행이 없어도 그 자체로 데이터다 —
    # baseline1(추론 없음)은 B파트가 비지만 A파트는 반드시 남아야 한다.
    from datetime import datetime, timezone

    meta = dict(session.meta or {})
    meta["criterionAudit"] = {
        "ownCriteria": [c.model_dump() for c in req.ownCriteria],
        "missingCriteria": req.missingCriteria,
        "submittedAt": datetime.now(timezone.utc).isoformat(),
    }
    session.meta = meta

    if rows:
        (db.query(models.CriterionValidation)
           .filter(models.CriterionValidation.session_id == session_id)
           .delete(synchronize_session=False))
        for row in rows:
            db.add(row)
    db.commit()
    return {"saved": len(rows),
            "validations": [serializers.criterion_validation_to_dict(r) for r in rows]}


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


# ─────────────────────────── 본실험 과제 계획 (서버 진실) ───────────────────────────
# 진행 상태가 sessionStorage에만 있으면 탭 유실·이전 라운드 잔존 큐로 "전부 완료"가
# 조기 표시된다(2026-08-16 실측). 계획은 Participant.task_plan에 저장하고, 완료는
# 세션의 finalChoice+postSurvey 마커(둘 다 종료 플로우의 필수 단계)로 서버가 센다.

class TaskPlanRequest(BaseModel):
    tasks: list[dict]  # [{category, familiarity: "familiar"(H)|"unfamiliar"(L)|"none"}]
    # 선정 로그 (2026-08-24 동결 문서 P0-8) — 후보 표시 순서·HL/LH 진행 순서·H/L 과제 id
    candidateDisplayOrder: list[str] | None = None
    sequence: str | None = None  # "HL" | "LH"
    hTaskId: str | None = None
    lTaskId: str | None = None


@router.put("/participants/{participant_id}/task-plan")
def save_task_plan(participant_id: str, req: TaskPlanRequest, db: DbSession = Depends(get_db)):
    from datetime import datetime, timezone

    part = db.get(models.Participant, participant_id)
    if part is None:
        raise HTTPException(404, "participant not found")
    tasks = []
    for t in req.tasks[:8]:
        cat = str(t.get("category") or "").strip()
        fam = t.get("familiarity")
        if not cat or fam not in ("familiar", "unfamiliar", "none"):
            raise HTTPException(422, "each task needs category + familiarity")
        tasks.append({"category": cat, "familiarity": fam})
    if not tasks:
        raise HTTPException(422, "tasks must not be empty")
    extras = {k: getattr(req, k) for k in ("candidateDisplayOrder", "sequence", "hTaskId", "lTaskId")
              if getattr(req, k) is not None}
    part.task_plan = {"tasks": tasks, **extras,
                      "savedAt": datetime.now(timezone.utc).isoformat()}
    db.commit()
    return {"ok": True, "count": len(tasks)}


@router.get("/participants/{participant_id}/task-progress")
def task_progress(participant_id: str, db: DbSession = Depends(get_db)):
    """계획 대비 진행 — done은 세션 meta의 finalChoice+postSurvey 존재로 판정.
    next = 계획 순서상 첫 미완료 과제. 계획이 없으면 tasks=[] (클라이언트 큐 폴백)."""
    part = db.get(models.Participant, participant_id)
    if part is None:
        raise HTTPException(404, "participant not found")
    plan = ((part.task_plan or {}).get("tasks")) or []
    sessions = db.query(models.Session).filter(
        models.Session.participant_id == participant_id).all()
    completed_categories = set()
    for s in sessions:
        meta = s.meta or {}
        # 완료 = finalChoice + (CC가 final이면 postSurvey) + criterionAudit 모두 존재.
        # criterionAudit 없이 새로고침하면 다음 과제로 넘어가는 것을 방지한다.
        fc = meta.get("finalChoice") or {}
        has_audit = bool(meta.get("criterionAudit"))
        if fc and has_audit and (meta.get("postSurvey") or fc.get("status") != "final"):
            cat = meta.get("category") or (s.scenario_id or "").removeprefix("cat:")
            if cat:
                completed_categories.add(cat)
    tasks = [{**t, "done": t["category"] in completed_categories} for t in plan]
    next_task = next((t for t in tasks if not t["done"]), None)
    remaining = sum(1 for t in tasks if not t["done"])
    # 과제 직전 지식 설문(카테고리 단위) 완료 목록 — 프론트가 이미 제출한 카테고리는
    # 재질문 없이 바로 세션을 연다 (새로고침 멱등).
    knowledge_done = (((part.survey or {}).get("productKnowledge") or {}).get("categories")) or []
    return {"tasks": tasks, "remaining": remaining,
            "knowledgeDone": knowledge_done,
            "next": ({"category": next_task["category"], "familiarity": next_task["familiarity"]}
                     if next_task else None)}

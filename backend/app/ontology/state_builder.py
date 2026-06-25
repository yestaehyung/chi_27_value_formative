"""Preference state snapshot builder (spec §8)."""
from sqlalchemy.orm import Session as DbSession

from app.core.ids import new_id
from app.db import models
from app.ontology.anchor_mapper import VALUE_ANCHORS
from app.preference_commit.summary_builder import build_user_visible_summary

PRIORITY_WEIGHT = {"low": 0.35, "medium": 0.6, "high": 0.85, "must_have": 1.0}


def get_active_topics(db: DbSession, session_id: str) -> list[models.IntentionTopic]:
    return (
        db.query(models.IntentionTopic)
        .filter(models.IntentionTopic.session_id == session_id)
        .filter(models.IntentionTopic.status.notin_(["rejected_by_user", "inactive"]))
        .all()
    )


STRENGTH_WEIGHT = {"low": 0.45, "medium": 0.75, "high": 1.0}
IMPACT_WEIGHT = {"low": 0.55, "medium": 0.8, "high": 1.0}
TEMPORAL_WEIGHT = {"emerging": 0.9, "active": 1.0, "weakened": 0.5, "resolved": 0.3}
CORRECTION_WEIGHT = {  # 사용자 확인/수정이 곧 가장 강한 evidence (이론모듈 §12.2)
    "confirmed": 1.0, "corrected_by_user": 1.0, "inferred": 0.85, "candidate": 0.65,
}


def compute_anchor_scores(
    db: DbSession,
    topics: list[models.IntentionTopic],
    open_conflict_topic_ids: set[str] | None = None,
) -> tuple[dict[str, float], dict[str, dict]]:
    """ValueScore — 가산형 가중 평균 (TCV: 가치는 독립·가산 기여; 기대-가치/MAUT).
    [2026-06-17] 곱셈+noisy-OR에서 전환 — docs/plans/2026-06-17-value-scoring-additive-design.md

    anchor a마다 (독립):
      활성 선택   : open conflict 토픽 제외 + resolved 매핑 제외 (연속 가중 대신 선택)
      weight(t)   = PRIORITY_WEIGHT[priority] × confidence   (중요도 × 확신)
      intensity   = m.score  (범주에서 파생; evidence_strength·decision_impact 이미 포함,
                              LLM 스칼라 아님 — anchor_mapper가 derive_anchor_score로 산출)
      score(a)    = Σ weight×intensity / Σ weight            (가중 평균 ∈ [0,1])
      confirmed(a)= 같은 식, m.confidence=='confirmed' 매핑만

    Returns (scores, breakdown):
    - scores: anchor → 전체(확인+추론) 가중평균
    - breakdown: anchor → {confirmedScore, contributors[]} (기여자 분해 — §7.3)
    """
    conflict_ids = open_conflict_topic_ids or set()
    num = {a: 0.0 for a in VALUE_ANCHORS}
    den = {a: 0.0 for a in VALUE_ANCHORS}
    num_confirmed = {a: 0.0 for a in VALUE_ANCHORS}
    den_confirmed = {a: 0.0 for a in VALUE_ANCHORS}
    contributors: dict[str, list[dict]] = {a: [] for a in VALUE_ANCHORS}

    for t in topics:
        if t.id in conflict_ids:                       # 활성 선택: 미해결 충돌 토픽 제외
            continue
        weight = PRIORITY_WEIGHT.get(t.priority, 0.6) * t.confidence
        if weight <= 0:
            continue
        mappings = db.query(models.AnchorMapping).filter(models.AnchorMapping.topic_id == t.id).all()
        for m in mappings:
            if m.temporal_status == "resolved" or m.anchor not in num:   # 철회/완료 매핑 제외
                continue
            intensity = m.score                        # 범주 파생값 (LLM 숫자 아님)
            num[m.anchor] += weight * intensity
            den[m.anchor] += weight
            if m.confidence == "confirmed":
                num_confirmed[m.anchor] += weight * intensity
                den_confirmed[m.anchor] += weight
            contribution = round(weight * intensity, 2)
            if contribution > 0.03:
                contributors[m.anchor].append({
                    "topicLabel": t.label,
                    "intensity": round(intensity, 2),
                    "confidence": m.confidence,
                    "evidenceStrength": m.evidence_strength,
                    "decisionImpact": m.decision_impact,
                    "temporalStatus": m.temporal_status,
                    "inConflict": False,
                    "contribution": contribution,
                })

    scores = {a: round(num[a] / den[a], 2) if den[a] > 0 else 0.0 for a in VALUE_ANCHORS}
    breakdown = {
        a: {
            "confirmedScore": (
                round(num_confirmed[a] / den_confirmed[a], 2) if den_confirmed[a] > 0 else 0.0
            ),
            "contributors": sorted(contributors[a], key=lambda c: -c["contribution"])[:4],
        }
        for a in VALUE_ANCHORS
    }
    return scores, breakdown


def build_snapshot(
    db: DbSession, session: models.Session, llm_summary: str | None = None,
) -> models.PreferenceStateSnapshot:
    topics = get_active_topics(db, session.id)
    meta = session.meta or {}
    # 한 줄 요약(state_summary)은 칩이 바뀐 commit에서만 새로 생성된다. 새 문장이 안
    # 넘어오면(칩 미변경·칩 편집·충돌 해소 등) 직전 스냅샷 문장을 이어받아 — B1로 강등돼
    # 깜빡이지 않게 한다. 직전도 없으면 build_user_visible_summary가 B1로 폴백.
    if not (llm_summary and llm_summary.strip()):
        prev = (
            db.query(models.PreferenceStateSnapshot)
            .filter(models.PreferenceStateSnapshot.session_id == session.id)
            .order_by(models.PreferenceStateSnapshot.created_at.desc())
            .first()
        )
        if prev and prev.user_visible_summary:
            llm_summary = prev.user_visible_summary.get("oneSentenceSummary")
    last_turn = (
        db.query(models.Turn)
        .filter(models.Turn.session_id == session.id)
        .order_by(models.Turn.turn_index.desc())
        .first()
    )
    turn_index = last_turn.turn_index if last_turn else 0

    rank = {"must_have": 3, "high": 2, "medium": 1, "low": 0}
    ordered = sorted(topics, key=lambda t: (rank.get(t.priority, 1), t.confidence), reverse=True)

    hard_constraints: list[str] = list(meta.get("extraHardConstraints", []))
    soft_preferences: list[str] = []
    avoidances: list[str] = list(meta.get("extraAvoidances", []))
    price_min: int | None = None
    price_max: int | None = None

    for t in ordered:
        hints = t.hints or {}
        # 구조화 예산 — LLM/mock이 추출한 숫자 그대로(문자열 파싱 없음). 여러 토픽이면 뒤가 우선.
        if hints.get("priceMin") is not None:
            price_min = hints["priceMin"]
        if hints.get("priceMax") is not None:
            price_max = hints["priceMax"]
        constraint = hints.get("impliedHardConstraint")
        avoid = hints.get("impliedAvoidance")
        if constraint and constraint not in hard_constraints:
            hard_constraints.append(constraint)
        elif avoid:
            label = f"{avoid} 제외"
            if label not in avoidances:
                avoidances.append(label)
        elif t.priority in ("high", "medium") and hints.get("kind") != "context":
            if t.label not in soft_preferences:
                soft_preferences.append(t.label)

    open_conflicts = (
        db.query(models.PreferenceConflict)
        .filter(models.PreferenceConflict.session_id == session.id)
        .filter(models.PreferenceConflict.status.in_(["open", "shown_to_user"]))
        .all()
    )
    conflict_topic_ids = {
        tid for c in open_conflicts for tid in (c.old_topic_id, c.new_topic_id) if tid
    }

    concept_ids = [
        link.concept_id
        for t in topics
        for link in db.query(models.TopicConcept).filter(models.TopicConcept.topic_id == t.id).all()
    ]

    anchor_scores, anchor_breakdown = compute_anchor_scores(db, topics, conflict_topic_ids)
    snapshot = models.PreferenceStateSnapshot(
        id=new_id("snap"),
        session_id=session.id,
        turn_index=turn_index,
        stage=session.current_stage,
        active_topic_ids=[t.id for t in ordered],
        active_concept_ids=list(dict.fromkeys(concept_ids)),
        anchor_scores=anchor_scores,
        anchor_breakdown=anchor_breakdown,
        motivation_scores=(session.meta or {}).get("motivationScores", {}),
        hard_constraints=hard_constraints,
        price_min=price_min,
        price_max=price_max,
        soft_preferences=soft_preferences,
        avoidances=avoidances,
        priority_order=[t.label for t in ordered],
        uncertainty={
            "unresolvedQuestions": meta.get("openQuestions", []),
            "ambiguousTopics": [t.label for t in topics if t.status == "candidate"],
            "conflictIds": [c.id for c in open_conflicts],
        },
        user_visible_summary=build_user_visible_summary(
            ordered, bool(open_conflicts), llm_sentence=llm_summary
        ),
    )
    db.add(snapshot)
    db.flush()
    return snapshot

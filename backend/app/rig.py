"""RIG — Relational Intention Graph (ideation: 메타경로 기반 예측·설명).

세션을 가로지르는 [대화 → 의도 → 이론 → 의도 → 상품] 경로를 분석한다.
- A. theory_transitions: 이론 단계 전이 (value trajectory의 dominant anchor 순서 집계)
- B. session_meta_path: 한 세션의 의도 구체화 경로 추출
- C. predict_intentions: 세션 횡단 경로 통계로 다음/최종 의도·상품 예측
  (데이터 희소성 극복 — 의도-개념-이론 공통 경로로 유사 사용자 데이터 차용)
"""
from collections import Counter, defaultdict

from sqlalchemy.orm import Session as DbSession

from app.db import models
from app.ontology.anchor_mapper import VALUE_ANCHORS


# ──────────────────────────────────────────────────────────────────────────
# 공통 헬퍼
# ──────────────────────────────────────────────────────────────────────────
def _dominant_anchor(scores: dict) -> str | None:
    if not scores:
        return None
    best = max(VALUE_ANCHORS, key=lambda a: scores.get(a, 0.0))
    return best if scores.get(best, 0.0) > 0.1 else None


def _session_anchor_sequence(db: DbSession, session_id: str) -> list[str]:
    """세션의 snapshot 순서대로 dominant anchor 시퀀스 (연속 중복 제거)."""
    snaps = (
        db.query(models.PreferenceStateSnapshot)
        .filter(models.PreferenceStateSnapshot.session_id == session_id)
        .order_by(models.PreferenceStateSnapshot.created_at)
        .all()
    )
    seq: list[str] = []
    for s in snaps:
        a = _dominant_anchor(s.anchor_scores or {})
        if a and (not seq or seq[-1] != a):
            seq.append(a)
    return seq


def _topic_concepts(db: DbSession, topic_id: str) -> list[models.Concept]:
    links = db.query(models.TopicConcept).filter(models.TopicConcept.topic_id == topic_id).all()
    return [c for c in (db.get(models.Concept, l.concept_id) for l in links) if c]


def _session_concept_sequence(db: DbSession, session_id: str) -> list[str]:
    """세션에서 의도(topic)가 생성된 순서대로 연결 개념(normalized_label) 시퀀스."""
    topics = (
        db.query(models.IntentionTopic)
        .filter(models.IntentionTopic.session_id == session_id)
        .filter(models.IntentionTopic.status.notin_(["rejected_by_user", "inactive"]))
        .order_by(models.IntentionTopic.created_at)
        .all()
    )
    seq: list[str] = []
    for t in topics:
        for c in _topic_concepts(db, t.id):
            if not seq or seq[-1] != c.normalized_label:
                seq.append(c.normalized_label)
    return seq


def _purchased_product(db: DbSession, session_id: str) -> models.Product | None:
    fb = (
        db.query(models.FeedbackEvent)
        .filter(models.FeedbackEvent.session_id == session_id)
        .filter(models.FeedbackEvent.type == "purchase")
        .order_by(models.FeedbackEvent.created_at.desc())
        .first()
    )
    return db.get(models.Product, fb.product_id) if fb else None


# ──────────────────────────────────────────────────────────────────────────
# A. 이론 단계 전이
# ──────────────────────────────────────────────────────────────────────────
def theory_transitions(db: DbSession) -> dict:
    sessions = db.query(models.Session).all()
    counts: Counter = Counter()
    for s in sessions:
        seq = _session_anchor_sequence(db, s.id)
        for a, b in zip(seq, seq[1:]):
            counts[(a, b)] += 1
    edges = [
        {"from": a, "to": b, "count": n}
        for (a, b), n in sorted(counts.items(), key=lambda x: -x[1])
    ]
    return {"transitions": edges, "sessionCount": len(sessions)}


# ──────────────────────────────────────────────────────────────────────────
# B. 세션 메타경로
# ──────────────────────────────────────────────────────────────────────────
def session_meta_path(db: DbSession, session_id: str) -> dict:
    """대화 → 의도(이론) → … → 상품 경로를 단계 리스트로 추출."""
    turns = (
        db.query(models.Turn)
        .filter(models.Turn.session_id == session_id)
        .order_by(models.Turn.turn_index)
        .all()
    )
    topics = (
        db.query(models.IntentionTopic)
        .filter(models.IntentionTopic.session_id == session_id)
        .all()
    )
    # 각 turn에서 새로 등장한 의도 (evidence가 그 turn을 가리키는 topic)
    topics_by_turn: dict[str, list[models.IntentionTopic]] = defaultdict(list)
    for t in topics:
        for ev in t.evidence_ids or []:
            if ev.startswith("turn"):
                topics_by_turn[ev].append(t)

    def top_anchor(t: models.IntentionTopic) -> str | None:
        ams = db.query(models.AnchorMapping).filter(models.AnchorMapping.topic_id == t.id).all()
        return max(ams, key=lambda a: a.score).anchor if ams else None

    steps = []
    for turn in turns:
        if turn.role not in ("user", "user_agent"):
            continue
        intents = [
            {"label": t.label, "anchor": top_anchor(t), "explicitness": t.explicitness}
            for t in topics_by_turn.get(turn.id, [])
        ]
        steps.append({
            "turnIndex": turn.turn_index,
            "utterance": turn.content[:80],
            "intentions": intents,
        })

    product = _purchased_product(db, session_id)
    return {
        "sessionId": session_id,
        "steps": steps,
        "finalProduct": (
            {"id": product.id, "title": product.title, "cueSummary": product.cue_summary or {}}
            if product else None
        ),
    }


# ──────────────────────────────────────────────────────────────────────────
# C. 경로 기반 의도 예측
# ──────────────────────────────────────────────────────────────────────────
def predict_intentions(db: DbSession, session_id: str) -> dict:
    """현재 세션이 지나온 개념을 공유하는 다른 세션들로부터, 이후에 자주 등장한
    개념/의도와 최종 구매 상품을 예측한다 (concept을 공통 backbone으로 사용).
    """
    current_seq = _session_concept_sequence(db, session_id)
    current_set = set(current_seq)
    cur_scenario = (db.get(models.Session, session_id).scenario_id
                    if db.get(models.Session, session_id) else None)

    other_sessions = [
        s for s in db.query(models.Session).all() if s.id != session_id
    ]

    next_concept_votes: Counter = Counter()
    concept_example_topics: dict[str, Counter] = defaultdict(Counter)
    concept_anchor: dict[str, Counter] = defaultdict(Counter)
    final_product_votes: Counter = Counter()
    matched_sessions = 0

    # 개념 라벨 → 표시용 한국어 라벨
    concept_label: dict[str, str] = {}
    for c in db.query(models.Concept).all():
        concept_label[c.normalized_label] = c.label

    for s in other_sessions:
        seq = _session_concept_sequence(db, s.id)
        if not seq:
            continue
        overlap = current_set & set(seq)
        # 시나리오가 같으면 약한 매칭이라도 허용 (cold-start 대비)
        if not overlap and s.scenario_id != cur_scenario:
            continue
        matched_sessions += 1
        # 현재 가지고 있지 않은, 그 세션에서 등장한 개념 = 후보 다음 의도
        for nl in seq:
            if nl in current_set:
                continue
            next_concept_votes[nl] += 1
        # 이 세션의 의도 라벨/앵커를 개념별로 모음 (예시 표시용)
        for t in (
            db.query(models.IntentionTopic)
            .filter(models.IntentionTopic.session_id == s.id)
            .all()
        ):
            for c in _topic_concepts(db, t.id):
                if c.normalized_label in current_set:
                    continue
                concept_example_topics[c.normalized_label][t.label] += 1
            am = db.query(models.AnchorMapping).filter(models.AnchorMapping.topic_id == t.id).all()
            for c in _topic_concepts(db, t.id):
                for a in am:
                    concept_anchor[c.normalized_label][a.anchor] += a.score
        prod = _purchased_product(db, s.id)
        if prod:
            final_product_votes[prod.id] += 1

    predicted = []
    for nl, votes in next_concept_votes.most_common(5):
        ex = concept_example_topics[nl].most_common(1)
        anchor = concept_anchor[nl].most_common(1)
        predicted.append({
            "conceptLabel": concept_label.get(nl, nl),
            "normalizedLabel": nl,
            "support": votes,
            "exampleIntention": ex[0][0] if ex else None,
            "topAnchor": anchor[0][0] if anchor else None,
        })

    final_products = []
    for pid, votes in final_product_votes.most_common(3):
        p = db.get(models.Product, pid)
        if p:
            final_products.append({"id": p.id, "title": p.title, "support": votes})

    return {
        "sessionId": session_id,
        "currentConcepts": [concept_label.get(c, c) for c in current_seq],
        "matchedSessions": matched_sessions,
        "predictedNextIntentions": predicted,
        "predictedFinalProducts": final_products,
    }


def top_predicted_concept(db: DbSession, session_id: str) -> dict | None:
    """에이전트 선제 질문용 — 가장 지지 높은 다음 의도 1개 (support>=2)."""
    pred = predict_intentions(db, session_id)
    for p in pred["predictedNextIntentions"]:
        if (p.get("support") or 0) >= 2 and p.get("exampleIntention"):
            return p
    return None

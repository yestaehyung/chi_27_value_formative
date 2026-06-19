"""Continuous value profile (이론모듈 Module H §12).

사용자를 label로 분류하지 않고 여러 가치 축 위의 continuous score로 표현한다:
anchors(6축) + user_types(분석 lens) + discovered_features(세션 관련 bottom-up feature).
"""
from sqlalchemy.orm import Session as DbSession

from app.db import models

# user type lens 추정: anchor 분포 + topic 신호의 선형 결합 (이론모듈 §5.3.4)
# trait(TCV5) anchor → user-type lens. 동기(Hedonic/Utilitarian)는 motivation 층에서 별도.
USER_TYPE_RULES = {
    "risk_averse": {"Emotional": 0.7, "Epistemic": 0.2},
    "socially_sensitive": {"Social": 0.75, "Conditional": 0.25},
    "budget_constrained": {"Functional": 0.7},
    "novice": {"Epistemic": 0.6, "Emotional": 0.3},
}

TYPE_TOPIC_BOOST = {
    "risk_averse": ["실패", "신뢰", "AS"],
    "socially_sensitive": ["선물", "체면", "저렴해 보이"],
    "budget_constrained": ["예산", "가격이 낮", "가성비"],
    "novice": ["브랜드를 잘 몰라", "모르"],
}


def build_value_profile(db: DbSession, session: models.Session) -> dict:
    snapshot = (
        db.query(models.PreferenceStateSnapshot)
        .filter(models.PreferenceStateSnapshot.session_id == session.id)
        .order_by(models.PreferenceStateSnapshot.created_at.desc())
        .first()
    )
    anchors: dict = (snapshot.anchor_scores or {}) if snapshot else {}

    topics = (
        db.query(models.IntentionTopic)
        .filter(models.IntentionTopic.session_id == session.id)
        .all()
    )
    topic_labels = " | ".join(t.label for t in topics)

    user_types: dict[str, float] = {}
    for utype, weights in USER_TYPE_RULES.items():
        score = sum(anchors.get(a, 0.0) * w for a, w in weights.items())
        for kw in TYPE_TOPIC_BOOST.get(utype, []):
            if kw in topic_labels:
                score = min(1.0, score + 0.12)
        user_types[utype] = round(score, 2)

    # 이 세션의 pair에서 비롯된 discovered feature 강도
    session_pair_ids = {
        p.id for p in db.query(models.ChosenRejectedPair)
        .filter(models.ChosenRejectedPair.session_id == session.id).all()
    }
    discovered: dict[str, float] = {}
    if session_pair_ids:
        for f in db.query(models.DiscoveredFeature).all():
            overlap = session_pair_ids & set(f.source_pair_ids or [])
            if overlap:
                base = (f.predictiveness_score or 0.5)
                share = len(overlap) / max(len(session_pair_ids), 1)
                discovered[f.label] = round(min(1.0, base * 0.6 + share * 0.6), 2)

    return {
        "sessionId": session.id,
        "anchors": anchors,
        "userTypes": user_types,
        "discoveredFeatures": discovered,
        "topicCount": len(topics),
        "correctedTopicCount": sum(1 for t in topics if t.status in ("corrected_by_user", "confirmed")),
    }

"""Stage 2 — 6-Anchor Mapping (spec §15.2).

Split into an LLM fetch phase (no DB writes) and an apply phase (fast writes),
so write locks are never held across slow LLM calls.
"""
from sqlalchemy.orm import Session as DbSession

from app.core.ids import new_id
from app.db import models
from app.llm.prompts import SYSTEM_BY_TASK, render_user_context
from app.llm.provider import LLMMessage, LLMProvider

# ── 2층 가치 모델 ───────────────────────────────────────────────────────────
# Trait 층 (TCV 5가치, Sheth/Newman/Gross 1991) — 비교적 안정적인 사람 특성.
# 의도(topic)→이론 매핑은 이 trait 층에만 이뤄지고, 참가자별로 세션을 넘어 누적된다.
TRAIT_ANCHORS = [
    "Functional",   # 성능·신뢰성·내구성·가격 대비 효용
    "Social",       # 사회집단 연상·사회적 이미지
    "Emotional",    # 긍정/부정 정서 (안심·신뢰 / 불안·후회 회피)
    "Epistemic",    # 호기심·새로움·정보 탐색·지식
    "Conditional",  # 특정 상황·맥락 의존 효용
]
# Motivation 층 (Arnold & Reynolds 2003 헤도닉 6 + Babin Utilitarian) — 상황적
# 쇼핑 동기. 설문 대신 대화로 끌어내며(아래 task), 세션 내에서 변동한다.
MOTIVATION_DIMS = [
    "Adventure",       # 탐험·우연한 발견·새로움
    "Gratification",   # 스트레스 해소·자기보상
    "Role",            # 타인을 위한 쇼핑의 즐거움 (선물)
    "BargainValue",    # 할인·득템의 즐거움
    "SocialShopping",  # 함께 고르기·타인 반응
    "Idea",            # 트렌드·신제품·영감 탐색
    "Utilitarian",     # 목적 달성·효율·과업 종료
]

# 하위호환: 기존 코드가 VALUE_ANCHORS를 참조 → trait 층을 가리키게 한다.
VALUE_ANCHORS = TRAIT_ANCHORS


async def fetch_anchor_mappings(
    provider: LLMProvider,
    pending_topics: list[dict],  # extracted topic dicts: {label, sourceEvidence}
) -> dict[str, list]:
    """LLM phase — returns {topicLabel: [anchor dicts]}."""
    if not pending_topics:
        return {}
    context = {
        "topics": [
            {"label": t["label"], "sourceEvidence": t.get("sourceEvidence", [])}
            for t in pending_topics
        ]
    }
    messages = [
        LLMMessage(role="system", content=SYSTEM_BY_TASK["anchor_mapping"]),
        LLMMessage(role="user", content=render_user_context(context)),
    ]
    out = await provider.generate_json(messages, task="anchor_mapping", context=context)
    by_label: dict[str, list] = {}
    for m in out.get("mappings") or []:
        if isinstance(m, dict) and m.get("topicLabel"):
            by_label[m["topicLabel"]] = m.get("anchors") or []
    return by_label


def apply_anchor_mappings(
    db: DbSession,
    topics: list[models.IntentionTopic],
    by_label: dict[str, list],
) -> None:
    """Write phase — fast, no awaits."""
    from app.ontology.merge import _similar

    for topic in topics:
        anchors = by_label.get(topic.label)
        if not anchors:  # tolerate slight label rephrasing by the LLM
            key = next((k for k in by_label if _similar(k, topic.label)), None)
            anchors = by_label.get(key) if key else None
        if not anchors:
            continue
        # replace previous mappings for this topic
        db.query(models.AnchorMapping).filter(models.AnchorMapping.topic_id == topic.id).delete()
        for a in anchors:
            if not isinstance(a, dict):
                continue
            # models sometimes emit schema notation like "Social|Conditional" — split it
            raw_names = str(a.get("anchor") or "").replace(",", "|").split("|")
            names = [n.strip().capitalize() for n in raw_names if n.strip()]
            names = [n for n in names if n in VALUE_ANCHORS]
            if not names:
                continue
            level = lambda v, default: v if v in ("low", "medium", "high") else default  # noqa: E731
            confidence = a.get("confidence") if a.get("confidence") in ("confirmed", "inferred", "weak") else "inferred"
            evidence_strength = level(a.get("evidenceStrength"), "medium")
            decision_impact = level(a.get("decisionImpact"), "medium")
            # M1/M2 (llm-measurement-design.md): LLM의 score 스칼라는 무시하고
            # 범주 3종에서 결정론적으로 산출한다 (levels.py — OQ2: derive-from-triple).
            from app.ontology.levels import derive_anchor_score

            score = derive_anchor_score(confidence, evidence_strength, decision_impact)
            for name in names:
                db.add(models.AnchorMapping(
                    id=new_id("anchor"),
                    topic_id=topic.id,
                    anchor=name,
                    score=score,
                    confidence=confidence,
                    evidence_strength=evidence_strength,
                    decision_impact=decision_impact,
                    temporal_status=a.get("temporalStatus")
                    if a.get("temporalStatus") in ("emerging", "active", "weakened", "resolved")
                    else "active",
                    rationale=a.get("rationale"),
                    evidence_ids=topic.evidence_ids or [],
                ))
    db.flush()

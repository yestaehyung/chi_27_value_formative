"""Stage 2 — 6-Anchor Mapping (spec §15.2).

Split into an LLM fetch phase (no DB writes) and an apply phase (fast writes),
so write locks are never held across slow LLM calls.
"""
from sqlalchemy.orm import Session as DbSession

from app.core.ids import new_id
from app.db import models
from app.llm.prompts import SYSTEM_BY_TASK, render_user_context
from app.llm.provider import LLMMessage, LLMProvider
# ── 2층 가치 모델 — 라벨 정의는 app/ontology/schema.py 가 단일 출처. 여기선 재노출. ──
#   TRAIT_ANCHORS  = TCV5 가치축 (Sheth/Newman/Gross 1991) — 의도→이론 매핑 대상
#   MOTIVATION_DIMS = 쇼핑 동기 (Arnold & Reynolds 2003) — 대화로 끌어냄
from app.ontology.schema import MOTIVATION_DIMS, TRAIT_ANCHORS, VALUE_ANCHORS  # noqa: F401


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

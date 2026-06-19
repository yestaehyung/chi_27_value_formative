"""User-visible summary builder (spec §30, §36).

Internal ontology terms (Social, Emotional, confidence…) are translated into
context-limited, correctable phrasing — never definitive statements about the user.
"""
from app.db import models

CHIP_TYPE_BY_PRIORITY = {"must_have": "must_have", "high": "important", "medium": "nice_to_have", "low": "nice_to_have"}


def topic_to_chip_type(topic: models.IntentionTopic) -> str:
    if topic.status == "candidate":
        return "uncertain"
    if (topic.hints or {}).get("kind") == "avoidance":
        return "avoid"
    return CHIP_TYPE_BY_PRIORITY.get(topic.priority, "nice_to_have")


def short_rationale(topic: models.IntentionTopic) -> str:
    ev = (topic.hints or {}).get("evidence") or []
    if ev:
        return ev[0].get("quoteOrSummary", "")[:80]
    return topic.description or ""


def build_user_visible_summary(
    ordered_topics: list[models.IntentionTopic],
    has_open_conflict: bool,
    max_count: int = 5,
) -> dict:
    top = ordered_topics[:max_count]
    chips = [
        {
            "id": t.id,
            "label": t.label,
            "type": topic_to_chip_type(t),
            "userEditable": True,
            "evidenceCount": len(t.evidence_ids or []),
            "displayRationale": short_rationale(t),
            "status": t.status,
            "priority": t.priority,
            "confidence": round(t.confidence, 2),
        }
        for t in top
    ]

    labels = [t.label for t in top]
    gift = any("선물" in l for l in labels)
    not_cheap = any("저렴해 보이지 않기" in l for l in labels)
    trust = any("신뢰" in l for l in labels)

    if gift and not_cheap:
        sentence = "선물용이므로 최저가보다 운동 기능, 장기 사용 신뢰, 선물로서의 적절한 인상을 더 중요하게 보고 있는 것 같아요."
        if not trust:
            sentence = "선물용이므로 최저가보다 선물로서의 적절한 인상과 기능 적합성을 더 중요하게 보고 있는 것 같아요."
    elif labels:
        head = ", ".join(labels[:3])
        sentence = f"지금은 '{head}' 기준을 중요하게 보고 있다고 이해했어요. 맞는지 확인해 주세요."
    else:
        sentence = "아직 기준을 파악하는 중이에요. 원하시는 조건을 자유롭게 말씀해 주세요."

    needs_confirmation = has_open_conflict or any(t.status in ("candidate", "inferred") for t in top)
    return {"chips": chips, "oneSentenceSummary": sentence, "needsConfirmation": needs_confirmation}

"""Stage 3 — Conceptualization (spec §15.3). LLM fetch / DB apply split."""
from sqlalchemy.orm import Session as DbSession

from app.core.ids import new_id
from app.db import models
from app.llm.prompts import SYSTEM_BY_TASK, render_user_context
from app.llm.provider import LLMMessage, LLMProvider


async def fetch_concepts(
    provider: LLMProvider,
    pending_topics: list[dict],
) -> dict[str, list]:
    """LLM phase — returns {topicLabel: [concept dicts]}."""
    if not pending_topics:
        return {}
    context = {"topics": [{"label": t["label"]} for t in pending_topics]}
    messages = [
        LLMMessage(role="system", content=SYSTEM_BY_TASK["conceptualization"]),
        LLMMessage(role="user", content=render_user_context(context)),
    ]
    out = await provider.generate_json(messages, task="conceptualization", context=context)
    by_label: dict[str, list] = {}
    for c in out.get("concepts") or []:
        if isinstance(c, dict) and c.get("topicLabel"):
            by_label[c["topicLabel"]] = c.get("concepts") or []
    return by_label


def apply_concepts(
    db: DbSession,
    topics: list[models.IntentionTopic],
    by_label: dict[str, list],
    created_by: str = "llm",
) -> list[models.Concept]:
    """Write phase — fast, no awaits. Returns the concepts that were touched."""
    from app.ontology.merge import _similar

    touched_concepts: dict[str, models.Concept] = {}
    for topic in topics:
        concepts_for_topic = by_label.get(topic.label)
        if not concepts_for_topic:  # tolerate slight label rephrasing by the LLM
            key = next((k for k in by_label if _similar(k, topic.label)), None)
            concepts_for_topic = by_label.get(key, []) if key else []
        for c in concepts_for_topic:
            if not isinstance(c, dict) or not c.get("label"):
                continue
            c.setdefault("normalizedLabel", c["label"])
            concept = (
                db.query(models.Concept)
                .filter(models.Concept.normalized_label == c["normalizedLabel"])
                .first()
            )
            if concept is None:
                concept = models.Concept(
                    id=new_id("concept"),
                    label=c["label"],
                    normalized_label=c["normalizedLabel"],
                    aliases=c.get("aliases", []),
                    source_topic_ids=[topic.id],
                    created_by=created_by,
                    status="observed",  # lifecycle (이론모듈 §11.2): 대화에서 관찰됨
                    origin=["llm_extraction"],
                )
                db.add(concept)
                db.flush()
            else:
                if topic.id not in (concept.source_topic_ids or []):
                    concept.source_topic_ids = (concept.source_topic_ids or []) + [topic.id]
                if concept.status == "seed":  # seed node가 실제 대화에서 관찰됨
                    concept.status = "observed"
            link = db.get(models.TopicConcept, (topic.id, concept.id))
            if link is None:
                db.add(models.TopicConcept(topic_id=topic.id, concept_id=concept.id, confidence=1.0))
            touched_concepts[concept.id] = concept
    db.flush()
    return list(touched_concepts.values())


def recompute_concept_anchors(db: DbSession, concepts: list[models.Concept]) -> None:
    """개념 → 이론 canonical 매핑 재계산 (ideation 2번).
    개념에 연결된 모든 topic의 AnchorMapping을 anchor별로 평균내 개념 수준 매핑을 만든다.
    confidence: 한 topic이라도 confirmed면 confirmed, 아니면 inferred."""
    from app.core.ids import new_id

    seen: set[str] = set()
    for concept in concepts:
        if concept.id in seen:
            continue
        seen.add(concept.id)
        topic_ids = [
            link.topic_id
            for link in db.query(models.TopicConcept)
            .filter(models.TopicConcept.concept_id == concept.id)
            .all()
        ]
        if not topic_ids:
            continue
        agg: dict[str, list[float]] = {}
        conf: dict[str, str] = {}
        for am in (
            db.query(models.AnchorMapping)
            .filter(models.AnchorMapping.topic_id.in_(topic_ids))
            .all()
        ):
            agg.setdefault(am.anchor, []).append(am.score)
            if am.confidence == "confirmed" or conf.get(am.anchor) != "confirmed":
                conf[am.anchor] = am.confidence if conf.get(am.anchor) != "confirmed" else "confirmed"
        # 기존 개념 매핑 교체
        db.query(models.ConceptAnchorMapping).filter(
            models.ConceptAnchorMapping.concept_id == concept.id
        ).delete()
        for anchor, scores in agg.items():
            db.add(models.ConceptAnchorMapping(
                id=new_id("canc"),
                concept_id=concept.id,
                anchor=anchor,
                score=round(sum(scores) / len(scores), 3),
                confidence=conf.get(anchor, "inferred"),
                support_count=len(scores),
            ))
    db.flush()

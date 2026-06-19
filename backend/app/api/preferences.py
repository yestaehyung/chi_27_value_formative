"""User correction of preference chips (spec §31) + evidence drawer (spec §18.6)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.db import models, serializers
from app.db.database import get_db
from app.db.schemas import ChipActionRequest
from app.ontology.state_builder import build_snapshot

router = APIRouter(prefix="/api/preferences", tags=["preferences"])

PRIORITY_UP = {"low": "medium", "medium": "high", "high": "must_have", "must_have": "must_have"}
PRIORITY_DOWN = {"must_have": "high", "high": "medium", "medium": "low", "low": "low"}

MESSAGES = {
    "confirm": "이 기준을 확인했어요. 더 확실하게 반영할게요.",
    "reject": "이 기준은 잘못 이해한 것이었네요. 제외할게요.",
    "increase_priority": "이 기준의 중요도를 높였어요.",
    "decrease_priority": "이 기준의 중요도를 낮췄어요.",
    "edit_label": "기준을 수정했어요.",
}


def _topic_state(topic: models.IntentionTopic) -> dict:
    return {
        "label": topic.label,
        "status": topic.status,
        "priority": topic.priority,
        "confidence": round(topic.confidence, 2),
    }


@router.post("/chips/{topic_id}/action")
def chip_action(topic_id: str, req: ChipActionRequest, db: DbSession = Depends(get_db)):
    topic = db.get(models.IntentionTopic, topic_id)
    if topic is None:
        raise HTTPException(404, "topic not found")
    session = db.get(models.Session, topic.session_id)
    before_state = _topic_state(topic)

    def _touch_concepts(new_status: str) -> None:
        """user correction은 linked concept의 lifecycle에도 반영 (이론모듈 §11.2)."""
        links = db.query(models.TopicConcept).filter(models.TopicConcept.topic_id == topic.id).all()
        for link in links:
            concept = db.get(models.Concept, link.concept_id)
            if concept is None:
                continue
            if "user_correction" not in (concept.origin or []):
                concept.origin = (concept.origin or []) + ["user_correction"]
            if new_status == "confirmed" and concept.status in ("seed", "observed", "candidate", "validated"):
                concept.status = "confirmed"

    if req.action == "confirm":
        topic.status = "confirmed"
        topic.confidence = max(topic.confidence, 0.95)
        _touch_concepts("confirmed")
    elif req.action == "reject":
        topic.status = "rejected_by_user"
        _touch_concepts("rejected")
    elif req.action == "increase_priority":
        topic.priority = PRIORITY_UP.get(topic.priority, topic.priority)
        topic.status = "confirmed"
    elif req.action == "decrease_priority":
        topic.priority = PRIORITY_DOWN.get(topic.priority, topic.priority)
    elif req.action == "edit_label":
        if not req.manualLabel:
            raise HTTPException(400, "manualLabel required for edit_label")
        topic.label = req.manualLabel
        topic.status = "corrected_by_user"
        topic.confidence = 1.0

    # correction trace (S58: 사용자가 어떤 시점에 무엇을 어떻게 수정했는가)
    if req.action != "show_evidence":
        from app.core.ids import new_id

        last_turn = (
            db.query(models.Turn)
            .filter(models.Turn.session_id == session.id)
            .order_by(models.Turn.turn_index.desc())
            .first()
        )
        db.add(models.CorrectionEvent(
            id=new_id("corr"),
            session_id=session.id,
            topic_id=topic.id,
            action=req.action,
            turn_index=last_turn.turn_index if last_turn else 0,
            before=before_state,
            after=_topic_state(topic),
            manual_label=req.manualLabel,
        ))

    db.flush()
    snapshot = build_snapshot(db, session)
    db.commit()
    return {
        "updatedTopic": serializers.topic_to_dict(topic),
        "newPreferenceState": serializers.snapshot_to_dict(snapshot),
        "message": MESSAGES.get(req.action, "반영했어요."),
    }


@router.get("/topics/{topic_id}/evidence")
def topic_evidence(topic_id: str, db: DbSession = Depends(get_db)):
    """Evidence drawer: why did the system infer this criterion? (spec §18.6)"""
    topic = db.get(models.IntentionTopic, topic_id)
    if topic is None:
        raise HTTPException(404, "topic not found")

    stored = {e["id"]: e for e in (topic.hints or {}).get("evidence", [])}
    # D1 evidence edges: per-evidence channel + explicitness (없으면 구 데이터 — 노드 라벨 폴백)
    edges = {
        e.evidence_id: e
        for e in db.query(models.IntentionEvidence)
        .filter(models.IntentionEvidence.topic_id == topic.id)
        .all()
    }
    items = []
    for ev_id in topic.evidence_ids or []:
        entry = {"id": ev_id, "type": "unknown", "quote": stored.get(ev_id, {}).get("quoteOrSummary", "")}
        edge = edges.get(ev_id)
        entry["channel"] = edge.channel if edge else topic.source
        entry["explicitness"] = edge.explicitness if edge else topic.explicitness
        if ev_id.startswith("turn"):
            turn = db.get(models.Turn, ev_id)
            if turn:
                entry.update(type="turn", quote=turn.content, role=turn.role)
        elif ev_id.startswith("fb"):
            fb = db.get(models.FeedbackEvent, ev_id)
            if fb:
                product = db.get(models.Product, fb.product_id)
                entry.update(
                    type="feedback",
                    feedbackType=fb.type,
                    productTitle=product.title if product else fb.product_id,
                    quote=fb.reason_text or stored.get(ev_id, {}).get("quoteOrSummary", fb.type),
                    productCues=(product.cue_summary or {}) if product else {},
                )
        if stored.get(ev_id, {}).get("type") == "product_cue":
            entry["type"] = "product_cue"
        items.append(entry)

    anchors = db.query(models.AnchorMapping).filter(models.AnchorMapping.topic_id == topic.id).all()
    concepts = [
        serializers.concept_to_dict(db.get(models.Concept, link.concept_id))
        for link in db.query(models.TopicConcept).filter(models.TopicConcept.topic_id == topic.id).all()
    ]
    return {
        "topic": serializers.topic_to_dict(topic),
        "evidence": items,
        "anchorMappings": [serializers.anchor_mapping_to_dict(a) for a in anchors],
        "concepts": concepts,
    }

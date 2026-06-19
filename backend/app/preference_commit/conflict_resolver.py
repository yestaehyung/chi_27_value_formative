"""Conflict resolution (spec §9, §20.4, Test 4)."""
from datetime import datetime, timezone

from sqlalchemy.orm import Session as DbSession

from app.core.ids import new_id
from app.db import models
from app.ontology.state_builder import build_snapshot

STATUS_BY_ACTION = {
    "accept_new": "accepted",
    "keep_old": "rejected",
    "merge": "accepted",
    "manual_edit": "manually_resolved",
    "downgrade_priority": "accepted",
    "delete_old_topic": "manually_resolved",
    "ask_clarification": "shown_to_user",
}

MESSAGE_BY_ACTION = {
    "accept_new": "알겠어요. 앞으로는 최저가보다 선물로 적절한 가격대와 신뢰도를 더 우선해서 추천할게요.",
    "keep_old": "네, 기존 기준을 그대로 유지할게요.",
    "merge": "앞으로는 예산 상한은 유지하되, 너무 저렴해 보이는 상품은 제외해서 추천할게요.",
    "manual_edit": "수정해주신 기준을 반영했어요.",
}


def resolve_conflict(
    db: DbSession,
    conflict: models.PreferenceConflict,
    option_id: str,
    manual_text: str | None,
) -> tuple[models.ConflictResolutionEvent, models.PreferenceStateSnapshot, str]:
    options = conflict.suggested_resolutions or []
    option = next((o for o in options if o.get("id") == option_id), None)
    action = option["action"] if option else option_id  # allow passing the action directly
    if manual_text:
        action = "manual_edit"

    session = db.get(models.Session, conflict.session_id)
    old_topic = db.get(models.IntentionTopic, conflict.old_topic_id) if conflict.old_topic_id else None
    new_topic = db.get(models.IntentionTopic, conflict.new_topic_id) if conflict.new_topic_id else None

    if action == "accept_new":
        if old_topic:
            old_topic.priority = "low"
            old_topic.status = "corrected_by_user"
        if new_topic:
            new_topic.status = "confirmed"
            new_topic.confidence = 1.0
            new_topic.priority = "high"
    elif action == "keep_old":
        if old_topic:
            old_topic.status = "confirmed"
            old_topic.confidence = 1.0
        if new_topic:
            new_topic.status = "rejected_by_user"
    elif action == "merge":
        # keep old preference (not deleted, Test 4), confirm new one, add the avoidance rule
        if old_topic:
            old_topic.status = "confirmed"
            old_topic.priority = "medium"
        if new_topic:
            new_topic.status = "confirmed"
            new_topic.confidence = 1.0
            new_topic.priority = "high"
            avoid = (new_topic.hints or {}).get("impliedAvoidance")
            if avoid:
                meta = dict(session.meta or {})
                extra = list(meta.get("extraAvoidances", []))
                label = f"{avoid} 제외"
                if label not in extra:
                    extra.append(label)
                meta["extraAvoidances"] = extra
                session.meta = meta
    elif action == "manual_edit":
        if new_topic and manual_text:
            new_topic.label = manual_text
            new_topic.description = manual_text
            new_topic.status = "corrected_by_user"
            new_topic.confidence = 1.0
        elif old_topic and manual_text:
            old_topic.label = manual_text
            old_topic.status = "corrected_by_user"
            old_topic.confidence = 1.0
    elif action == "downgrade_priority":
        if old_topic:
            old_topic.priority = "low"
    elif action == "delete_old_topic":
        if old_topic:
            old_topic.status = "inactive"

    conflict.status = STATUS_BY_ACTION.get(action, "manually_resolved")
    conflict.resolved_at = datetime.now(timezone.utc)

    db.flush()
    snapshot = build_snapshot(db, session)

    event = models.ConflictResolutionEvent(
        id=new_id("res"),
        conflict_id=conflict.id,
        session_id=conflict.session_id,
        selected_option_id=option["id"] if option else option_id,
        action=action,
        manual_text=manual_text,
        resulting_snapshot_id=snapshot.id,
    )
    db.add(event)
    db.commit()

    message = MESSAGE_BY_ACTION.get(action, "기준을 업데이트했어요.")
    return event, snapshot, message

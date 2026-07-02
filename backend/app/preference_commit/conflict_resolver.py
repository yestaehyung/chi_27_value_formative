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

def build_resolution_message(
    action: str,
    old_label: str | None = None,
    new_label: str | None = None,
    avoidance_label: str | None = None,
) -> str:
    """해결 확인 메시지를 시나리오 중립으로, 사용자의 실제 기준(토픽 라벨)에 근거해 만든다.
    데모 도메인(선물/최저가) 문자열을 박지 않는다 — §36 hedged·결정론 폴백.
    (풀 LLM 저작은 후속: 엔드포인트 async + 전용 task. 여기선 도메인 누수 제거가 목적.)
    """
    if action == "accept_new" and new_label:
        return f"알겠어요. 앞으로는 ‘{new_label}’을(를) 더 우선해서 추천할게요."
    if action == "keep_old":
        tail = f"(‘{old_label}’)" if old_label else ""
        return f"네, 기존 기준{tail}을 그대로 유지할게요."
    if action == "merge":
        if avoidance_label:
            return f"앞으로는 기존 기준은 유지하되, ‘{avoidance_label}’ 조건을 더해 추천할게요."
        return "두 기준을 함께 반영해서 추천할게요."
    if action == "manual_edit":
        return "수정해주신 기준을 반영했어요."
    if action == "downgrade_priority" and old_label:
        return f"‘{old_label}’의 우선순위를 낮춰서 반영할게요."
    if action == "delete_old_topic" and old_label:
        return f"‘{old_label}’ 기준은 더 이상 반영하지 않을게요."
    return "기준을 업데이트했어요."


def resolve_conflict(
    db: DbSession,
    conflict: models.PreferenceConflict,
    option_id: str,
    manual_text: str | None,
) -> tuple[models.ConflictResolutionEvent, models.PreferenceStateSnapshot, str, models.Turn]:
    options = conflict.suggested_resolutions or []
    option = next((o for o in options if o.get("id") == option_id), None)
    action = option["action"] if option else option_id  # allow passing the action directly
    if manual_text:
        action = "manual_edit"

    session = db.get(models.Session, conflict.session_id)
    old_topic = db.get(models.IntentionTopic, conflict.old_topic_id) if conflict.old_topic_id else None
    new_topic = db.get(models.IntentionTopic, conflict.new_topic_id) if conflict.new_topic_id else None
    avoidance_label: str | None = None

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
                avoidance_label = label
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

    message = build_resolution_message(
        action,
        old_label=old_topic.label if old_topic else None,
        new_label=new_topic.label if new_topic else None,
        avoidance_label=avoidance_label,
    )
    # 해소 발화를 Turn으로 영속화 (2026-07-02) — 이전엔 프론트 로컬 말풍선뿐이라
    # 새로고침·연구 replay에서 사라졌다. 시뮬레이션의 자동 해소도 대화 기록이 남는다.
    last_turn = (
        db.query(models.Turn)
        .filter(models.Turn.session_id == conflict.session_id)
        .order_by(models.Turn.turn_index.desc())
        .first()
    )
    turn = models.Turn(
        id=new_id("turn"),
        session_id=conflict.session_id,
        turn_index=(last_turn.turn_index + 1) if last_turn else 0,
        role="service_agent",
        content=message,
        agent_action="resolution",
        dialogue_acts=[],
    )
    db.add(turn)
    db.commit()
    return event, snapshot, message, turn

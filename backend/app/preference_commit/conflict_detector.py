"""Conflict detection (spec §17) — recall-first; LLM fetch / DB apply split."""
from sqlalchemy.orm import Session as DbSession

from app.core.ids import new_id
from app.db import models
from app.llm.prompts import SYSTEM_BY_TASK, render_user_context
from app.llm.provider import LLMMessage, LLMProvider

SEVERITY_BY_LABEL = {"direct_conflict": "direct", "ambiguous_conflict": "ambiguous"}

VALID_ACTIONS = {"keep_old", "accept_new", "merge", "manual_edit",
                 "ask_clarification", "downgrade_priority", "delete_old_topic"}


def _normalize_resolutions(options: list, old_assumption: str, new_signal: str) -> list:
    """Keep only well-formed LLM options; if too few survive, fall back to the
    standard keep/accept/merge/manual set so the conflict card always works."""
    valid = [
        o for o in options
        if isinstance(o, dict) and o.get("label") and o.get("action") in VALID_ACTIONS
    ]
    for i, o in enumerate(valid):
        o.setdefault("id", f"{o['action']}_{i}")
        o.setdefault("resultingStatePreview", "")
    if len(valid) >= 3:
        if not any(o["action"] == "manual_edit" for o in valid):
            valid.append({"id": "manual_edit", "label": "직접 수정하기", "action": "manual_edit",
                          "resultingStatePreview": "기준을 직접 수정합니다."})
        return valid
    short = (new_signal or "새 기준")[:40]
    old_short = (old_assumption or "기존 기준")[:40]
    return [
        {"id": "accept_new", "label": f"새 기준을 우선하기 — {short}", "action": "accept_new",
         "resultingStatePreview": "새 기준을 우선해서 추천합니다."},
        {"id": "keep_old", "label": f"기존 기준 유지하기 — {old_short}", "action": "keep_old",
         "resultingStatePreview": "기존 기준을 유지합니다."},
        {"id": "merge", "label": "두 기준을 절충해서 반영하기", "action": "merge",
         "resultingStatePreview": "두 기준을 모두 고려해 추천합니다."},
        {"id": "manual_edit", "label": "직접 수정하기", "action": "manual_edit",
         "resultingStatePreview": "기준을 직접 수정합니다."},
    ]


async def fetch_conflicts(
    provider: LLMProvider,
    existing_topics: list[dict],  # {id?, label, priority, status}
    new_topic_labels: list[str],
) -> list[dict]:
    """LLM phase — returns raw conflict dicts."""
    if not new_topic_labels or not existing_topics:
        return []
    context = {
        "existingTopics": existing_topics,
        "newTopics": [{"label": l} for l in new_topic_labels],
    }
    messages = [
        LLMMessage(role="system", content=SYSTEM_BY_TASK["conflict_detection"]),
        LLMMessage(role="user", content=render_user_context(context)),
    ]
    out = await provider.generate_json(messages, task="conflict_detection", context=context)
    return [
        c for c in (out.get("conflicts") or [])
        if isinstance(c, dict) and c.get("label") != "no_conflict"
    ]


def apply_conflicts(
    db: DbSession,
    session: models.Session,
    raw_conflicts: list[dict],
    existing_topics: list[models.IntentionTopic],
    new_topics: list[models.IntentionTopic],
) -> list[models.PreferenceConflict]:
    """Write phase — resolves labels to topic rows, dedupes, writes."""
    by_label = {t.label: t for t in existing_topics + new_topics}
    open_pairs = {
        (c.old_topic_id, c.new_topic_id)
        for c in db.query(models.PreferenceConflict)
        .filter(models.PreferenceConflict.session_id == session.id)
        .all()
    }

    created: list[models.PreferenceConflict] = []
    for c in raw_conflicts:
        if not isinstance(c.get("suggestedResolutions"), list):
            c["suggestedResolutions"] = []
        c["suggestedResolutions"] = _normalize_resolutions(
            c["suggestedResolutions"], c.get("oldAssumption") or "", c.get("newSignal") or "",
        )
        old_t = by_label.get(c.get("oldTopicLabel", ""))
        new_t = by_label.get(c.get("newTopicLabel", ""))
        key = (old_t.id if old_t else None, new_t.id if new_t else None)
        if key in open_pairs:
            continue
        conflict = models.PreferenceConflict(
            id=new_id("conflict"),
            session_id=session.id,
            severity=SEVERITY_BY_LABEL.get(c.get("label", ""), "weak"),
            status="open",
            old_topic_id=old_t.id if old_t else None,
            new_topic_id=new_t.id if new_t else None,
            old_assumption=c.get("oldAssumption"),
            new_signal=c.get("newSignal"),
            conflict_type=c.get("conflictType", "contradiction"),
            explanation_for_user=c.get("explanationForUser"),
            explanation_for_researcher=c.get("explanationForResearcher"),
            suggested_resolutions=c.get("suggestedResolutions", []),
        )
        db.add(conflict)
        open_pairs.add(key)
        created.append(conflict)
    db.flush()
    return created

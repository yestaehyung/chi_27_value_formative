"""Stage 1 — Intention Topic Extraction (spec §15.1)."""
from sqlalchemy.orm import Session as DbSession

from app.db import models
from app.llm.prompts import SYSTEM_BY_TASK, render_user_context
from app.llm.provider import LLMMessage, LLMProvider


def _feedback_context(db: DbSession, fb: models.FeedbackEvent) -> dict:
    product = db.get(models.Product, fb.product_id)
    return {
        "id": fb.id,
        "type": fb.type,
        "valence": fb.valence,
        "reasonCode": fb.reason_code,
        "reasonText": fb.reason_text,
        "productId": fb.product_id,
        "productTitle": product.title if product else None,
        "productCues": (product.cue_summary or {}) if product else {},
        "price": product.price if product else None,
        "longTermReviewRatio": product.long_term_review_ratio if product else None,
    }


async def extract_topics(
    db: DbSession,
    provider: LLMProvider,
    session: models.Session,
    turn_ids: list[str],
    feedback_ids: list[str],
    current_state: dict | None,
) -> list[dict]:
    turns = [db.get(models.Turn, tid) for tid in turn_ids]
    feedback = [db.get(models.FeedbackEvent, fid) for fid in feedback_ids]
    context = {
        "turns": [
            {"id": t.id, "role": t.role, "content": t.content}
            for t in turns if t is not None
        ],
        "feedback": [_feedback_context(db, f) for f in feedback if f is not None],
        "state": {"activeTopicLabels": (current_state or {}).get("activeTopicLabels", [])},
    }
    messages = [
        LLMMessage(role="system", content=SYSTEM_BY_TASK["topic_extraction"]),
        LLMMessage(role="user", content=render_user_context(context)),
    ]
    out = await provider.generate_json(messages, task="topic_extraction", context=context)
    topics = out.get("topics") or []

    # 하이브리드 가드: 예산처럼 결정적으로 파싱 가능한 제약은 LLM이 놓쳐도 규칙으로 보장
    # (algorithm-audit.md — LLM 추출의 비결정성에 대한 안전망)
    from app.products.scoring import parse_budget_won

    has_budget = any("예산" in (t.get("impliedHardConstraint") or "") for t in topics if isinstance(t, dict))
    if not has_budget:
        for t in turns:
            if t is None:
                continue
            text = t.content
            budget = parse_budget_won(text)
            if budget and any(k in text for k in ("이하", "이내", "안에", "안으로", "넘지", "까지", "예산", "아래")):
                man = budget // 10000
                topics.append({
                    "label": f"예산 {man}만원 이하",
                    "description": f"예산 상한이 약 {man}만원이다.",
                    "explicitness": "explicit", "confidence": 0.9, "priority": "must_have",
                    "kind": "constraint",
                    "impliedHardConstraint": f"예산 {man}만원 이하",
                    "sourceEvidence": [{"type": "turn", "id": t.id, "quoteOrSummary": text[:60]}],
                })
                break
    return topics

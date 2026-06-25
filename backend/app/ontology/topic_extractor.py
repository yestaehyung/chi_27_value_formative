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

    # 예산/가격 제약도 LLM(topic_extraction)이 kind=constraint로 추출한다 — 키워드 가드 없음.
    # (실제 경로 하드코딩 제거, 2026-06-24. 프롬프트가 canonical "가격 {min}~{max}원"을 지시;
    #  mock은 LLM이 없으므로 mock_rules가 자체 결정론 규칙으로 동등 출력을 만든다.)
    return topics

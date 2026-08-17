"""Condition-safe recommendation evidence boundary.

The action planner is allowed to see unconfirmed hypotheses so it can decide whether to ask a
hedged clarification question.  Product retrieval and reranking are not.  This module rebuilds
the recommendation specification from raw participant evidence plus only the intention topics
allowed by the assigned study condition, then exposes one policy consumed by both stages.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session as DbSession

from app.core.conditions import USES_UNCONFIRMED_INFERENCE, normalize_condition
from app.core.locale import KRW_PER_USD, is_en, product_display_price, product_display_title
from app.db import models
from app.llm.provider import LLMMessage
from app.products.scoring import parse_price_range


REJECTED_STATUSES = {"rejected_by_user", "inactive"}
USER_BACKED_STATUSES = {"confirmed", "corrected_by_user"}


@dataclass(frozen=True)
class RecommendationPolicy:
    """The complete, auditable input contract for retrieval and reranking."""

    condition: str | None
    search_text: str
    constraints_note: str
    hard_constraints: tuple[str, ...]
    price_min: int | None
    price_max: int | None
    criteria: tuple[dict, ...]
    direct_evidence_ids: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "condition": self.condition,
            "searchText": self.search_text,
            "constraintsNote": self.constraints_note,
            "hardConstraints": list(self.hard_constraints),
            "priceMin": self.price_min,
            "priceMax": self.price_max,
            "criteria": [dict(c) for c in self.criteria],
            "directEvidenceIds": list(self.direct_evidence_ids),
        }


def condition_for(session: models.Session | None) -> str | None:
    return normalize_condition((session.meta or {}).get("studyCondition")) if session else None


def uses_unconfirmed(session: models.Session | None) -> bool:
    """Only baseline2 may turn an unconfirmed inferred topic into recommendation evidence."""
    condition = condition_for(session)
    return USES_UNCONFIRMED_INFERENCE.get(condition, False) if condition else False


def eligible_criteria(
    db: DbSession,
    session: models.Session,
    *,
    include_unconfirmed: bool | None = None,
) -> list[dict]:
    """Return condition-eligible topic evidence with provenance.

    baseline1 intentionally has no topic path: its direct requirements come from raw turns and
    feedback through ``recommendation_spec``.  baseline2 receives every active topic.  ours and
    non-study sessions receive explicit or user-confirmed/corrected topics only.
    """
    condition = condition_for(session)
    if condition == "baseline1":
        return []
    if include_unconfirmed is None:
        include_unconfirmed = uses_unconfirmed(session)

    topics = (
        db.query(models.IntentionTopic)
        .filter(models.IntentionTopic.session_id == session.id)
        .filter(models.IntentionTopic.status.notin_(tuple(REJECTED_STATUSES)))
        .order_by(models.IntentionTopic.created_at, models.IntentionTopic.id)
        .all()
    )
    out: list[dict] = []
    for topic in topics:
        if not (
            include_unconfirmed
            or topic.explicitness == "explicit"
            or topic.status in USER_BACKED_STATUSES
        ):
            continue
        hints = topic.hints or {}
        criterion = {
            "topicId": topic.id,
            "label": topic.label,
            "description": topic.description,
            "kind": hints.get("kind") or "preference",
            "priority": topic.priority,
            "status": topic.status,
            "explicitness": topic.explicitness,
            "source": topic.source,
        }
        if hints.get("impliedAvoidance"):
            criterion["avoid"] = hints["impliedAvoidance"]
        if hints.get("impliedHardConstraint"):
            criterion["mustHave"] = hints["impliedHardConstraint"]
        if hints.get("priceMin") is not None:
            criterion["priceMin"] = hints["priceMin"]
        if hints.get("priceMax") is not None:
            criterion["priceMax"] = hints["priceMax"]
        out.append(criterion)
    return out


def _direct_evidence_context(db: DbSession, session: models.Session) -> dict:
    turns = (
        db.query(models.Turn)
        .filter(models.Turn.session_id == session.id)
        .filter(models.Turn.role.in_(("user", "user_agent")))
        .order_by(models.Turn.turn_index)
        .all()
    )
    feedback_rows = (
        db.query(models.FeedbackEvent)
        .filter(models.FeedbackEvent.session_id == session.id)
        .filter(models.FeedbackEvent.type.notin_(("view_detail", "click")))
        .order_by(models.FeedbackEvent.created_at)
        .all()
    )
    feedback = []
    for event in feedback_rows:
        product = db.get(models.Product, event.product_id) if event.product_id else None
        feedback.append({
            "id": event.id,
            "type": event.type,
            "valence": event.valence,
            "productTitle": product_display_title(product),
            "reasonText": event.reason_text or event.reason_code,
        })

    impressions = (
        db.query(models.ProductImpression)
        .filter(models.ProductImpression.session_id == session.id)
        .order_by(models.ProductImpression.created_at.desc())
        .limit(10)
        .all()
    )
    shown = []
    seen: set[str] = set()
    for impression in impressions:
        if impression.product_id in seen:
            continue
        seen.add(impression.product_id)
        product = db.get(models.Product, impression.product_id)
        if product is not None:
            shown.append({
                "id": product.id,
                "title": product_display_title(product),
                "price": product_display_price(product) if is_en() else product.price,
                "category": product.category,
            })
    return {
        "userUtterances": [
            {"id": turn.id, "content": turn.content}
            for turn in turns
            if turn.content
        ],
        "feedbackEvents": feedback,
        "lastShownProducts": shown,
    }


def _clean_text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _clean_string_list(value, *, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _clean_text(item)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _clean_price(value) -> int | None:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _fallback_spec(context: dict, criteria: list[dict]) -> dict:
    utterances = [
        _clean_text(row.get("content"))
        for row in context.get("userUtterances") or []
        if isinstance(row, dict)
    ]
    utterances = [text for text in utterances if text]
    raw = " ".join(utterances)
    price_min, price_max = parse_price_range(raw)
    usd_amounts = [
        float(a or b)
        for a, b in re.findall(
            r"\$\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:USD|dollars?)\b",
            raw,
            flags=re.IGNORECASE,
        )
        if a or b
    ]
    if usd_amounts:
        won = [round(amount * KRW_PER_USD) for amount in usd_amounts]
        lowered = raw.lower()
        if len(won) >= 2 and any(k in lowered for k in ("between", "from", "range")):
            price_min, price_max = min(won), max(won)
        elif any(k in lowered for k in ("at least", "minimum", "more than", "over ")):
            price_min, price_max = won[0], None
        else:
            price_min, price_max = None, won[-1]

    hard_constraints: list[str] = []
    for criterion in criteria:
        must_have = _clean_text(criterion.get("mustHave"))
        if must_have and must_have not in hard_constraints:
            hard_constraints.append(must_have)
        cmin = _clean_price(criterion.get("priceMin"))
        cmax = _clean_price(criterion.get("priceMax"))
        if cmin is not None:
            price_min = cmin
        if cmax is not None:
            price_max = cmax

    scenario = _clean_text(context.get("scenarioGoal"))
    category = _clean_text(context.get("category"))
    # Evidence-safe failure path: preserve the established all-utterance rewrite. Do not add
    # hypothesis labels or planner output; category/scenario are only empty-dialogue fallbacks.
    search_text = raw.strip() or category or scenario
    return {
        "searchText": search_text or scenario or category,
        # Raw utterances remain first-class rerank evidence. Treating their entire text as one
        # hard ``note`` criterion would incorrectly harden ordinary preferences on provider
        # failure, so the safe fallback leaves the note empty and relies on the structured price
        # fields, eligible criteria, and full utterance list.
        "constraintsNote": "",
        "hardConstraints": hard_constraints,
        "priceMin": price_min,
        "priceMax": price_max,
    }


async def build_recommendation_policy(
    db: DbSession,
    provider,
    session: models.Session,
) -> RecommendationPolicy:
    """Build the only evidence object retrieval and reranking may consume."""
    criteria = eligible_criteria(db, session)
    direct = _direct_evidence_context(db, session)
    meta = session.meta or {}
    context = {
        **direct,
        "scenarioGoal": meta.get("shoppingGoal") or meta.get("category") or "",
        "category": meta.get("category"),
        "eligibleCriteria": criteria,
    }
    fallback = _fallback_spec(context, criteria)
    try:
        result = await provider.generate_json(
            [LLMMessage(role="user", content="Build the recommendation specification.")],
            task="recommendation_spec",
            context=context,
        )
    except Exception:  # noqa: BLE001 - evidence-safe deterministic fallback below
        result = {}

    search_text = _clean_text(result.get("searchText")) or fallback["searchText"]
    constraints_note = (
        result["constraintsNote"].strip()
        if isinstance(result.get("constraintsNote"), str)
        else fallback["constraintsNote"]
    )
    hard_constraints = _clean_string_list(result.get("hardConstraints"))
    for constraint in fallback["hardConstraints"]:
        if constraint not in hard_constraints:
            hard_constraints.append(constraint)

    price_min = _clean_price(result.get("priceMin"))
    price_max = _clean_price(result.get("priceMax"))
    if price_min is None:
        price_min = fallback["priceMin"]
    if price_max is None:
        price_max = fallback["priceMax"]
    if price_min is not None and price_max is not None and price_min > price_max:
        price_min, price_max = price_max, price_min

    evidence_ids = [row["id"] for row in direct["userUtterances"]]
    evidence_ids.extend(row["id"] for row in direct["feedbackEvents"])
    return RecommendationPolicy(
        condition=condition_for(session),
        search_text=search_text,
        constraints_note=constraints_note,
        hard_constraints=tuple(hard_constraints),
        price_min=price_min,
        price_max=price_max,
        criteria=tuple(criteria),
        direct_evidence_ids=tuple(evidence_ids),
    )

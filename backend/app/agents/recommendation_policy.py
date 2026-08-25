"""Condition-safe recommendation evidence boundary.

The action planner is allowed to see unconfirmed hypotheses so it can decide whether to ask a
hedged clarification question.  Product retrieval and reranking are not.  This module rebuilds
the recommendation specification from raw participant evidence plus only the intention topics
allowed by the assigned study condition, then exposes one policy consumed by both stages.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session as DbSession

from app.core.conditions import USES_UNCONFIRMED_INFERENCE, normalize_condition
from app.core.locale import KRW_PER_USD, is_en, product_display_price, product_display_title
from app.db import models
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
    # "llm" = 스펙 컴파일러 정상 / "fallback" = 결정론 폴백 (감사용, 2026-08-19)
    spec_source: str = "llm"

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
            "specSource": self.spec_source,
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
    # 첫 추천은 세 조건 모두 동일한 직접 발화 경로만 쓴다. 추론 기준은 사용자가
    # 실제 상품을 한 번 본 뒤의 반응/추가 발화부터 추천 차이를 만들 수 있다.
    has_prior_impression = (
        db.query(models.ProductImpression)
        .filter(models.ProductImpression.session_id == session.id)
        .first()
        is not None
    )
    if not has_prior_impression:
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
        kind = hints.get("kind") or "preference"
        directly_stated = (
            topic.source == "user_utterance"
            and hints.get("confidenceLevel") == "directly_stated"
        )
        # 구조 규칙: 미확인 추론과 단순 확인(yes)은 절대 hard가 아니다. 사용자가 직접
        # 말한 필수/회피 조건 또는 직접 고쳐 쓴 constraint/avoidance만 hard가 된다.
        enforcement = "hard" if (
            topic.status == "corrected_by_user" and kind in ("constraint", "avoidance")
            or topic.status == "confirmed" and directly_stated
            and kind in ("constraint", "avoidance")
        ) else "soft"
        criterion = {
            "topicId": topic.id,
            "label": topic.label,
            "description": topic.description,
            "kind": kind,
            "priority": topic.priority,
            "status": topic.status,
            "explicitness": topic.explicitness,
            "source": topic.source,
            # 구매 옵션 속성 (2026-08-18): 의류 사이즈처럼 리스팅이 아니라 구매 단계에서
            # 고르는 속성 — 확인 불가(unk)를 배제 사유로 삼지 않는다 (위반 명시 시에만 배제).
            "purchaseOption": bool(hints.get("purchaseOption")),
            "enforcement": enforcement,
        }
        if enforcement == "hard" and hints.get("impliedAvoidance"):
            criterion["avoid"] = hints["impliedAvoidance"]
        if enforcement == "hard" and hints.get("impliedHardConstraint"):
            criterion["mustHave"] = hints["impliedHardConstraint"]
        if enforcement == "hard" and hints.get("priceMin") is not None:
            criterion["priceMin"] = hints["priceMin"]
        if enforcement == "hard" and hints.get("priceMax") is not None:
            criterion["priceMax"] = hints["priceMax"]
        out.append(criterion)
    return out


def _direct_evidence_context(db: DbSession, session: models.Session,
                             *, current_request_only: bool = False) -> dict:
    turns = (
        db.query(models.Turn)
        .filter(models.Turn.session_id == session.id)
        .filter(models.Turn.role.in_(("user", "user_agent")))
        .order_by(models.Turn.turn_index)
        .all()
    )
    if current_request_only and turns:
        # baseline1 (2026-08-20 정의 명확화): 조작 변인은 지속적 사용자 모델의 유무다.
        # b1의 추천 증거는 "현재 요청"으로 한정한다 — 마지막 사용자 발화 1개 + 그 이후의
        # 피드백(지금 보고 있는 결과에 대한 반응)만. 대화 이력에서 조건을 누적 컴파일하면
        # b1도 사실상 대화 수준 사용자 모델을 갖게 되어 b2와의 경계가 사라진다.
        # 플래너·렌더러의 대화 문맥은 그대로다 — 좁히는 것은 검색·행렬 증거뿐.
        turns = [turns[-1]]
    feedback_rows = (
        db.query(models.FeedbackEvent)
        .filter(models.FeedbackEvent.session_id == session.id)
        .filter(models.FeedbackEvent.type.notin_(("view_detail", "click")))
        .order_by(models.FeedbackEvent.created_at)
        .all()
    )
    if current_request_only and turns:
        cutoff = turns[-1].created_at
        feedback_rows = [f for f in feedback_rows
                         if cutoff is None or f.created_at is None or f.created_at >= cutoff]
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
    direct = _direct_evidence_context(
        db, session,
        # b1 = 무상태 검색 챗봇: 추천 증거를 현재 요청(마지막 발화 + 그 이후 피드백)으로
        # 한정한다. 세 조건은 "사용자 모델: 없음/숨김/수정가능" 한 축에 놓인다.
        current_request_only=condition_for(session) == "baseline1",
    )
    meta = session.meta or {}
    # recommendation_spec은 검색/하드 필터를 컴파일하므로 hard 기준만 받는다.
    # soft 기준은 아래 policy.criteria를 통해 rerank 순위에만 영향을 준다.
    compiler_criteria = [c for c in criteria if c.get("enforcement") == "hard"]
    context = {
        **direct,
        "scenarioGoal": meta.get("shoppingGoal") or meta.get("category") or "",
        "category": meta.get("category"),
        "eligibleCriteria": compiler_criteria,
    }
    fallback = _fallback_spec(context, compiler_criteria)
    try:
        # 메시지를 비워 보낸다 — provider가 context를 렌더해 유저 메시지로 넣는 계약.
        # 유저 메시지를 직접 넣으면 context 렌더가 건너뛰어져 LLM이 증거(발화·기준·
        # 피드백)를 전혀 못 받는다 (2026-08-19 실측: 라이브 164턴 중 160턴이 폴백 —
        # searchText가 발화 원문 이어붙임, constraintsNote 공백으로 rerank 유도 상실).
        result = await provider.generate_json(
            [],
            task="recommendation_spec",
            context=context,
        )
    except Exception:  # noqa: BLE001 - evidence-safe deterministic fallback below
        logging.exception("recommendation_spec LLM call failed — deterministic fallback")
        result = {}

    # 폴백은 안전장치지 정상 경로가 아니다 — 침묵 강등이 하루 동안 160/164턴을 숨겼다
    # (2026-08-19). 폴백 발동은 로그로 드러내고 spec_source로 데이터에도 남긴다
    # (llm_calls의 recommendationPolicy에 실려 배치 단위 감사가 가능해진다).
    spec_source = "llm"
    if not _clean_text(result.get("searchText")):
        spec_source = "fallback"
        if provider.name != "mock":
            logging.warning(
                "recommendation_spec fell back (no usable searchText) — session=%s",
                session.id)

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
    # 구조 가드: min=max는 "정확히 $X짜리만"이라는 스펙인데, 실제로는 상한 발화
    # ("under $150")를 LLM이 양쪽에 채운 오기입이다 (2026-08-25 실측 — rerank가
    # min을 읽고 "$499.99가 $500 예산 미달/초과" 같은 경계 오판을 낳는다). 상한만 남긴다.
    if price_min is not None and price_min == price_max:
        logging.warning("recommendation_spec price_min==price_max (%s) — dropping min", price_min)
        price_min = None

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
        spec_source=spec_source,
    )

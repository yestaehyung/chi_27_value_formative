"""Korean agent responses (spec §18, §24, §36 — hedged, never definitive about the user).

Templates below are the deterministic fallback (and the mock provider's output).
When a real LLM provider is configured, `generate_reply` rewrites the template
grounded on conversation context, product data, and the preference state.
"""
from app.db import models
from app.llm.prompts import AGENT_REPLY_SYSTEM, render_user_context
from app.llm.provider import LLMMessage, LLMProvider
from app.products.search import ScoredProduct

BUCKET_PHRASE = {
    "low_price_popular": "가격이 낮고 최근 판매가 많지만, 셀러 등급과 장기 사용 리뷰는 약한 편이에요",
    "high_trust_long_term": "가격은 조금 높지만 운동 기능이 분명하고 한달사용 리뷰 비율이 높아요",
    "seller_reliable": "셀러 등급이 높고 배송비가 없어 믿고 사기 좋은 쪽이에요",
    "design_or_identity": "디자인/선물 패키지 같은 인상 요소가 강한 쪽이에요",
    "novel_or_distinctive": "흔하지 않은 모델이라 특별한 느낌을 줄 수 있어요",
    "balanced": "가격과 신뢰의 균형이 잡힌 쪽이에요",
}

LETTERS = ["A", "B", "C", "D", "E"]


def clarify_text(category: str | None) -> str:
    if category is None:
        return (
            "어떤 상품을 찾고 계세요? 쓰실 분(본인/선물), 용도, 대략의 예산을 "
            "알려주시면 더 잘 찾아드릴 수 있어요."
        )
    return "어떤 분이 쓰실 물건인가요? 용도나 예산도 알려주시면 후보를 더 잘 좁힐 수 있어요."


def recommend_text(scored: list[ScoredProduct]) -> str:
    lines = ["말씀해주신 기준대로 세 가지 다른 방향의 상품을 보여드릴게요.", ""]
    for i, sp in enumerate(scored):
        letter = LETTERS[i] if i < len(LETTERS) else str(i + 1)
        p = sp.product
        price = f"{p.price:,}원" if p.price else "가격 정보 없음"
        lines.append(f"{letter}. {p.title} ({price}) — {BUCKET_PHRASE.get(sp.bucket, '')}.")
    lines.append("")
    lines.append("카드의 좋아요/싫어요로 반응해주시면 기준을 더 정확하게 잡을 수 있어요. "
                 "제가 이해한 기준은 오른쪽 패널에서 언제든 바꿔주실 수 있어요.")
    return "\n".join(lines)


def explain_text(products: list[models.Product]) -> str:
    if not products:
        return "조금 더 구체적으로 어떤 점이 궁금하신지 알려주시면 비교해드릴게요."
    lines = ["최근 보여드린 후보를 기준으로 비교해드릴게요.", ""]
    for p in products:
        ltr = f"{round((p.long_term_review_ratio or 0) * 100)}%"
        lines.append(
            f"- {p.title}: 평점 {p.rating}, 리뷰 {p.review_count:,}개, "
            f"한달사용 리뷰 비율 {ltr}, 셀러 등급 {p.seller_grade}."
        )
    best = max(products, key=lambda p: p.long_term_review_ratio or 0)
    lines.append("")
    lines.append(
        f"오래 쓰는 관점에서는 한달사용 리뷰 비율이 가장 높은 '{best.title}' 쪽이 "
        "오래 써도 괜찮을 가능성이 높아 보여요. 다만 이건 리뷰만 본 거라, 직접 기준을 알려주시면 더 정확해져요."
    )
    return "\n".join(lines)


def conflict_text(conflict: models.PreferenceConflict) -> str:
    base = conflict.explanation_for_user or "말씀해주신 기준 사이에 충돌이 있는 것 같아요."
    return f"기준이 바뀐 것 같아요.\n\n{base}\n\n아래 카드에서 어떻게 반영할지 선택해 주세요."


async def generate_reply(
    provider: LLMProvider,
    action: str,
    template_text: str,
    recent_turns: list[models.Turn],
    products: list[models.Product],
    state_summary: dict | None,
    conflict_explanation: str | None = None,
    must_ask_question: str | None = None,
) -> str:
    """LLM-grounded reply; falls back to the deterministic template on mock/error."""
    if provider.name == "mock":
        return template_text
    context = {
        "recentDialogue": [
            {"role": t.role, "content": t.content} for t in recent_turns[-8:]
        ],
        "decidedAction": action,
        "mustAskQuestion": must_ask_question,
        "productsToShow": [
            {
                "title": p.title, "price": p.price, "rating": p.rating,
                "reviewCount": p.review_count,
                "longTermReviewRatio": p.long_term_review_ratio,
                "recentSalesCount": p.recent_sales_count,
                "sellerGrade": p.seller_grade, "deliveryFee": p.delivery_fee,
                "cues": p.cue_summary or {},
            }
            for p in products
        ],
        "currentUnderstanding": state_summary or {},
        "conflictExplanation": conflict_explanation,
        "draftTemplate": template_text,
    }
    try:
        messages = [
            LLMMessage(role="system", content=AGENT_REPLY_SYSTEM),
            LLMMessage(role="user", content=render_user_context(context)),
        ]
        text = _strip_markdown((await provider.generate_text(messages, max_tokens=700)).strip())
        # 질문 보존 검증: 자연스러운 재구성은 허용하되(AGENT_REPLY_SYSTEM 규칙10),
        # 질문 자체가 통째로 빠지면 템플릿으로 폴백한다. (verbatim 강제 X — 어색함 방지)
        if must_ask_question and "?" not in text:
            return template_text
        return text or template_text
    except Exception:  # noqa: BLE001 — degrade gracefully to the template
        return template_text


LETTERS_CARD = ["A", "B", "C", "D", "E"]


async def generate_card_rationales(
    provider: LLMProvider,
    scored: list[ScoredProduct],
    state_summary: dict | None,
) -> dict[str, dict]:
    """상품 카드별 설명(reason/matched/weak)을 LLM이 생성 — 사용자 가치 기준에 연결.
    BUCKET_PHRASE/hidden_intention_fit 규칙(데모 잔재)을 대체한다 (B1).

    반환: {productId: {"reason":str, "matched":[str], "weak":[str]}}.
    실패/빈응답 시 graceful 폴백(상품 사실 기반 짧은 문구) — 카드가 비지 않게.
    """
    if not scored:
        return {}

    products_ctx = []
    letter_to_pid: dict[str, str] = {}
    for i, sp in enumerate(scored):
        letter = LETTERS_CARD[i] if i < len(LETTERS_CARD) else str(i + 1)
        p = sp.product
        letter_to_pid[letter] = p.id
        products_ctx.append({
            "letter": letter, "title": p.title, "category": p.category,
            "price": p.price, "rating": p.rating, "reviewCount": p.review_count,
            "longTermReviewRatio": p.long_term_review_ratio,
            "recentSalesCount": p.recent_sales_count,
            "cues": p.cue_summary or {},
        })
    context = {
        "userValues": {
            "summary": (state_summary or {}).get("oneSentenceSummary", ""),
            "chips": [c.get("label") for c in (state_summary or {}).get("chips", [])],
        },
        "products": products_ctx,
    }

    out: dict = {}
    try:
        raw = await provider.generate_json(
            [LLMMessage(role="user", content=render_user_context(context))],
            task="card_rationale", context=context,
        )
        for card in (raw or {}).get("cards", []):
            pid = letter_to_pid.get(card.get("letter"))
            if pid:
                out[pid] = {
                    "reason": (card.get("reason") or "").strip(),
                    "matched": [m for m in (card.get("matched") or []) if isinstance(m, str)][:2],
                    "weak": [w for w in (card.get("weak") or []) if isinstance(w, str)][:2],
                }
    except Exception:  # noqa: BLE001 — 폴백으로 강등
        out = {}

    for sp in scored:  # 누락 상품은 사실 기반 폴백 (카드가 비지 않게)
        if sp.product.id not in out or not out[sp.product.id]["reason"]:
            out[sp.product.id] = _fallback_card(sp.product)
    return out


def _fallback_card(p: models.Product) -> dict:
    """LLM 실패 시 상품 사실 기반 최소 설명."""
    ltr = round((p.long_term_review_ratio or 0) * 100)
    matched = []
    if ltr >= 30:
        matched.append(f"한달사용 리뷰 비율이 {ltr}%로 높은 편이에요")
    if (p.rating or 0) >= 4.5:
        matched.append(f"평점 {p.rating}로 만족도가 높아요")
    if not matched:
        matched.append("말씀하신 기준에 무난하게 맞는 편이에요")
    return {"reason": matched[0], "matched": matched[:2], "weak": []}


def _strip_markdown(text: str) -> str:
    """Chat bubbles render plain text — remove markdown the LLM may emit anyway."""
    import re

    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    return text.strip()


def close_text(product: models.Product | None) -> str:
    if product is None:
        return "결정을 도와드려서 기뻤어요. 필요하시면 언제든 다시 찾아주세요."
    return (
        f"'{product.title}'(으)로 결정하셨네요. 좋은 선택이에요! "
        "이번 대화에서 제가 이해한 기준은 오른쪽 패널에 남아 있으니, 다르게 이해한 부분이 있었다면 알려주세요."
    )

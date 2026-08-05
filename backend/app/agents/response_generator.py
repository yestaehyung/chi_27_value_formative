"""Korean agent responses (spec §18, §24, §36 — hedged, never definitive about the user).

Templates below are the deterministic fallback (and the mock provider's output).
When a real LLM provider is configured, `generate_reply` rewrites the template
grounded on conversation context, product data, and the preference state.
"""
from app.db import models
from app.llm.prompts import AGENT_REPLY_SYSTEM, render_user_context
from app.llm.provider import LLMMessage, LLMProvider
from app.products.search import ScoredProduct

def clarify_text(category: str | None) -> str:
    if category is None:
        return (
            "어떤 상품을 찾고 계세요? 쓰실 분(본인/선물), 용도, 대략의 예산을 "
            "알려주시면 더 잘 찾아드릴 수 있어요."
        )
    return "어떤 분이 쓰실 물건인가요? 용도나 예산도 알려주시면 후보를 더 잘 좁힐 수 있어요."


def recommend_text(scored: list[ScoredProduct]) -> str:
    """챗 버블 초안 — 상품 개별 설명은 카드가 하므로(③ 역할 분리), 여기선 '왜 이 조합인지'
    비교 관점만 안내한다. 상품별 나열은 카드가 하므로 중복하지 않는다."""
    n = len(scored)
    return (
        f"말씀해주신 기준에 맞춰 서로 다른 방향의 상품 {n}가지를 골라봤어요. "
        "가격·신뢰·특별함처럼 강조점이 다른 후보들이라, 어떤 쪽이 더 끌리는지 보시면 "
        "기준을 더 정확히 잡아드릴 수 있어요.\n\n"
        "각 카드의 설명을 보고 좋아요·싫어요로 반응해주시면 돼요."
    )


def near_miss_text(scored: list[ScoredProduct]) -> str:
    """전 후보가 제약 위반일 때의 정직 초안 (② 부분 정직, 2026-07-07) — 조건에 맞는
    상품의 부재를 먼저 알리고, 근접 대안이 어떤 점에서 다른지는 카드(weak)가 보여주며,
    다음 방향(조건 완화/다른 방향)은 사용자가 정한다. mock 출력 겸 실패 폴백."""
    if not scored:
        return (
            "말씀하신 조건에 맞는 상품을 지금 카탈로그에서는 찾지 못했어요. "
            "조건을 조금 넓혀볼까요, 아니면 다른 종류의 상품을 찾아볼까요?"
        )
    n = len(scored)
    return (
        f"말씀하신 조건에 딱 맞는 상품은 지금 카탈로그에서 찾지 못했어요. "
        f"대신 가장 가까운 후보 {n}가지를 보여드릴게요 — 각 카드에 조건과 다른 점을 "
        "표시해두었어요. 조건을 조금 넓혀볼까요, 아니면 다른 방향으로 찾아볼까요?"
    )


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


def detail_text(p: models.Product, prof: dict | None = None) -> str:
    """자세히 클릭에 대한 결정론 초안 (mock 출력 겸 실패 폴백) — 상품 사실 + 프로필
    (오프라인 enrichment의 keyAttributes/caveats)로 설명하고, 무엇이 궁금한지 묻는다.
    질문이 핵심: 탐색 클릭의 의미를 시스템이 추측하는 대신 사용자가 직접 말하게 한다."""
    lines = [f"'{p.title}'에 대해 더 알려드릴게요."]
    facts = []
    if p.price is not None:
        facts.append(f"가격 {p.price:,}원")
    if p.rating:
        facts.append(f"평점 {p.rating}")
    if p.review_count:
        facts.append(f"리뷰 {p.review_count:,}개")
    if facts:
        lines.append(" · ".join(facts))
    if prof:
        if prof.get("profile"):
            lines.append(str(prof["profile"]))
        attrs = prof.get("keyAttributes") or []
        if attrs:
            lines.append("주요 특징: " + ", ".join(str(a) for a in attrs[:5]))
        caveats = prof.get("caveats") or []
        if caveats:
            lines.append("참고할 점: " + " / ".join(str(c) for c in caveats[:2]))
    elif p.description:
        lines.append(p.description[:200])
    lines.append("이 상품에서 어떤 점이 궁금하신가요? 그냥 둘러보신 거라도 편하게 말씀해 주세요.")
    return "\n\n".join(lines)


def conflict_text(conflict: models.PreferenceConflict) -> str:
    base = conflict.explanation_for_user or "말씀해주신 기준 사이에 충돌이 있는 것 같아요."
    return f"기준이 바뀐 것 같아요.\n\n{base}\n\n어느 쪽을 우선할지 알려주세요."


async def generate_reply(
    provider: LLMProvider,
    action: str,
    template_text: str,
    recent_turns: list[models.Turn],
    products: list[models.Product],
    state_summary: dict | None,
    conflict_explanation: str | None = None,
    must_ask_question: str | None = None,
    previously_shown: list[models.Product] | None = None,
    recommendation_note: dict | None = None,
) -> str:
    """LLM-grounded reply; falls back to the deterministic template on mock/error."""
    if provider.name == "mock":
        return template_text
    from app.products import profiles

    # 직전 노출 셋 — 이게 없으면 "앞서 보여드린 상품" 이야기가 전부 추측이 된다
    # (2026-07-03 live: 남성 2/3 세트를 "전부 여성용으로 골랐다"고 허위 진술).
    # 제목+정체 필드만 — 과거 주장의 근거로 충분하고 토큰을 아낀다.
    prev_products = []
    for p in previously_shown or []:
        entry: dict = {"title": p.title}
        prof = profiles.get(p.id)
        if prof:
            entry["productType"] = prof.get("productType")
            entry["audience"] = prof.get("audience")
        prev_products.append(entry)
    context = {
        "recentDialogue": [
            {"role": t.role, "content": t.content} for t in recent_turns[-8:]
        ],
        "decidedAction": action,
        "mustAskQuestion": must_ask_question,
        "previouslyShownProducts": prev_products,
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
        "recommendationNote": recommendation_note,
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


async def rerank_by_intent(
    provider: LLMProvider,
    scored: list[ScoredProduct],
    intent_context: dict,
) -> tuple[list[ScoredProduct], dict[str, dict], dict[str, str]]:
    """사용자 가치·동기로 후보를 재정렬 (LLM4Rerank WWW'25식 Goal-기반 listwise rerank).
    임베딩이 추려준 후보(scored, 임베딩 순)를, 추출된 의도(intent_context)에 맞춰 순위를 다시 매긴다.

    intent_context = {scenario, recentUtterances, topics[{label,description,quotes}],
                      values(TCV5 raw), motivations(raw)}  — 점수→자연어 하드코딩 변환 안 함.
    반환: (재정렬된 scored, {productId: {reason,matched,weak}}, {productId: 제외 이유}).
    제외는 **명시 exclude:true만** 인정 — ranking 누락은 아래 append-back으로 살아나며
    제외가 아니다(생략≠제외; 노출 억제는 반드시 명시 채널로만, 2026-07-07 ② 부분 정직).
    mock/실패 시 입력 순서 그대로 + 빈 제외 셋 + 사실기반 폴백 카드 (재현성).
    """
    if not scored:
        return scored, {}, {}

    from app.products import profiles

    by_index = {i: sp for i, sp in enumerate(scored)}
    candidates = []
    for i, sp in enumerate(scored):
        p = sp.product
        cand = {
            "index": i, "title": p.title, "category": p.category,
            "price": p.price, "rating": p.rating, "reviewCount": p.review_count,
            "longTermReviewRatio": p.long_term_review_ratio,
            "priceCue": (p.cue_summary or {}).get("priceCue"),
        }
        prof = profiles.get(p.id)
        if prof:
            # 정규화 프로필 (오프라인 LLM enrichment) — 제약 대조의 직접 손잡이.
            # raw description 대신: 판단 재료는 늘고 토큰은 준다.
            cand.update({
                "productType": prof.get("productType"),
                "audience": prof.get("audience"),
                "keyAttributes": prof.get("keyAttributes") or [],
                "caveats": prof.get("caveats") or [],
            })
        else:  # 프로필 없는 풀(seed/, seed_naver/) — 기존 산문 유지
            cand["description"] = p.description
        candidates.append(cand)
    context = {**intent_context, "candidates": candidates}

    order: list[int] = []
    card_texts: dict[str, dict] = {}
    excluded: dict[str, str] = {}
    try:
        raw = await provider.generate_json(
            [LLMMessage(role="user", content=render_user_context(context))],
            task="rerank", context=context,
            # 집행 레이어는 최대 결정론 — temp 0.1에서도 전멸 풀(준수후보 0)의 exclude
            # 판정이 런마다 뒤집혔다 (2026-07-07 eval r7: 동일 입력 1.0↔0.0).
            temperature=0.0,
        )
        for item in (raw or {}).get("ranking", []):
            idx = item.get("index")
            if idx in by_index and idx not in order:
                order.append(idx)
                pid = by_index[idx].product.id
                card_texts[pid] = {
                    "reason": (item.get("reason") or "").strip(),
                    "matched": [m for m in (item.get("matched") or []) if isinstance(m, str)][:2],
                    "weak": [w for w in (item.get("weak") or []) if isinstance(w, str)][:2],
                }
                if item.get("exclude") is True:
                    excluded[pid] = (item.get("excludeReason") or "").strip()
    except Exception:  # noqa: BLE001 — 폴백: 입력 순서 유지, 제외 없음
        order = []
        excluded = {}

    # 누락된 후보는 원래(임베딩) 순서로 뒤에 붙임 (재현성·완전성; 제외 아님)
    for i in range(len(scored)):
        if i not in order:
            order.append(i)
    reranked = [by_index[i] for i in order]

    # 카드텍스트 누락분은 사실기반 폴백 (카드가 비지 않게)
    for sp in reranked:
        if sp.product.id not in card_texts or not card_texts[sp.product.id]["reason"]:
            card_texts[sp.product.id] = _fallback_card(sp.product)
    return reranked, card_texts, excluded


_FALLBACK_SUGGESTIONS = {
    "clarify": ["네, 그게 중요해요", "아니요, 그건 아니에요", "잘 모르겠어요"],
    "recommend": ["더 저렴한 건 없나요?", "사실 디자인도 중요해요", "오래 쓰는 게 우선이에요"],
    "answer": ["다른 기준으로 비교해줘", "이걸로 정할게요", "더 보여줄 수 있나요?"],
    # 자세히 클릭 후 — "그냥 둘러봤어요"가 핵심 칩: 호기심 클릭을 명시적으로 캡처해
    # 시스템이 추측할 여지를 없앤다.
    "detail": ["가격이 적당한지 궁금해요", "기능·사양이 궁금해요", "그냥 둘러봤어요"],
}
_FALLBACK_DEFAULT = ["좀 더 추천해줘", "가격이 가장 중요해요", "잘 모르겠어요"]


async def generate_reply_suggestions(
    provider: LLMProvider,
    action: str,
    agent_reply: str,
    state_summary: dict | None,
) -> list[str]:
    """입력창 위 '답변 칩' 생성 — 방금 에이전트 말에 이어지는 사용자 1인칭 후보 3개.
    대화 맥락(에이전트 응답)+가치요약 기반. 실패/mock-빈 시 액션별 정적 폴백."""
    fallback = _FALLBACK_SUGGESTIONS.get(action, _FALLBACK_DEFAULT)
    if provider.name == "mock":
        return fallback  # mock은 핸들러가 같은 값 — 호출 절약
    context = {
        "action": action,
        "agentReply": (agent_reply or "")[:500],
        "userValues": {
            "summary": (state_summary or {}).get("oneSentenceSummary", ""),
            "chips": [c.get("label") for c in (state_summary or {}).get("chips", [])],
        },
    }
    try:
        raw = await provider.generate_json(
            [LLMMessage(role="user", content=render_user_context(context))],
            task="reply_suggestion", context=context,
        )
        sug = [s.strip() for s in (raw or {}).get("suggestions", [])
               if isinstance(s, str) and s.strip()]
        return sug[:3] if sug else fallback
    except Exception:  # noqa: BLE001
        return fallback


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
    """말풍선이 **렌더하지 못하는** 문법만 제거한다.

    2026-08-06 이전에는 마크다운을 전부 지웠다(말풍선이 평문 렌더였으므로). 지금은
    프론트 `StructuredText`가 불릿·번호 목록·표·굵게를 렌더하므로 그 넷은 남긴다 —
    비교나 조건 정리처럼 구조가 도움이 되는 답변을 표·목록으로 낼 수 있어야 한다.

    남는 제거 대상은 렌더러가 다루지 않는 것들이다. 지우지 않으면 참가자 화면에
    '### 요약'이나 백틱이 글자 그대로 노출된다.
    """
    import re

    text = text.replace("__", "").replace("`", "")
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)   # 제목
    text = re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE)     # 인용
    return text.strip()


def close_text(product: models.Product | None) -> str:
    if product is None:
        return "결정을 도와드려서 기뻤어요. 필요하시면 언제든 다시 찾아주세요."
    return (
        f"'{product.title}'(으)로 결정하셨네요. 좋은 선택이에요! "
        "이번 대화에서 제가 이해한 기준이 다르게 느껴진 부분이 있었다면 알려주세요."
    )

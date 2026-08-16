"""Korean agent responses (spec §18, §24, §36 — hedged, never definitive about the user).

Templates below are the deterministic fallback (and the mock provider's output).
When a real LLM provider is configured, `generate_reply` rewrites the template
grounded on conversation context, product data, and the preference state.
"""
from app.core.locale import L, is_en, product_display_price, product_display_title, usd
from app.db import models
from app.llm.prompts import AGENT_REPLY_SYSTEM, render_user_context
from app.llm.provider import LLMMessage, LLMProvider
from app.products.search import ScoredProduct

def clarify_text(category: str | None) -> str:
    if category is None:
        return L(
            "어떤 상품을 찾고 계세요? 쓰실 분(본인/선물), 용도, 대략의 예산을 "
            "알려주시면 더 잘 찾아드릴 수 있어요.",
            "What are you looking for? Telling me who it's for (yourself or a gift), "
            "how it will be used, and a rough budget will help me find better options.",
        )
    return L(
        "어떤 분이 쓰실 물건인가요? 용도나 예산도 알려주시면 후보를 더 잘 좁힐 수 있어요.",
        "Who will be using it? Sharing the use case or budget will help me narrow things down.",
    )


def recommend_text(scored: list[ScoredProduct]) -> str:
    """챗 버블 초안 — 상품 개별 설명은 카드가 하므로(③ 역할 분리), 여기선 '왜 이 조합인지'
    비교 관점만 안내한다. 상품별 나열은 카드가 하므로 중복하지 않는다."""
    n = len(scored)
    return L(
        f"말씀해주신 기준에 맞춰 서로 다른 방향의 상품 {n}가지를 골라봤어요. "
        "가격·신뢰·특별함처럼 강조점이 다른 후보들이라, 어떤 쪽이 더 끌리는지 보시면 "
        "기준을 더 정확히 잡아드릴 수 있어요.\n\n"
        "각 카드의 설명을 보고 좋아요·싫어요로 반응해주시면 돼요.",
        f"Based on what you told me, I picked {n} options that each take a different angle — "
        "some lean toward price, others toward reliability or something distinctive. "
        "Seeing which one appeals to you will help me sharpen the criteria.\n\n"
        "Take a look at each card and react with like or dislike.",
    )


def empty_handed_text(blocking_criteria: list[str]) -> str:
    """준수 후보 0(행렬의 사실)일 때의 빈손 초안 — 카드를 보여주지 않고, 어떤 기준이
    후보를 전멸시켰는지 밝힌 뒤 다음 방향(조건 완화 / 근접 후보 보기)을 사용자가 고르게
    한다. 날조된 세트보다 정확한 빈손이 낫다(fail-loud)."""
    if is_en():
        why = ""
        if blocking_criteria:
            crits = "' and '".join(blocking_criteria[:2])
            why = f" In particular, I couldn't find candidates that satisfy '{crits}'."
        return (
            "I couldn't find any product in the catalog that meets all of your conditions." + why +
            " Would you like to relax a condition, or shall I show the closest matches instead?"
        )
    why = ""
    if blocking_criteria:
        crits = "'와 '".join(blocking_criteria[:2])
        why = f" 특히 '{crits}' 기준을 만족하는 후보를 찾지 못했어요."
    return (
        "말씀하신 조건을 모두 만족하는 상품을 지금 카탈로그에서는 찾지 못했어요." + why +
        " 조건을 조금 넓혀보시겠어요? 아니면 조건에 가장 가까운 후보라도 보여드릴까요?"
    )


def near_miss_text(scored: list[ScoredProduct]) -> str:
    """전 후보가 제약 위반일 때의 정직 초안 (② 부분 정직, 2026-07-07) — 조건에 맞는
    상품의 부재를 먼저 알리고, 근접 대안이 어떤 점에서 다른지는 카드(weak)가 보여주며,
    다음 방향(조건 완화/다른 방향)은 사용자가 정한다. mock 출력 겸 실패 폴백."""
    if not scored:
        return L(
            "말씀하신 조건에 맞는 상품을 지금 카탈로그에서는 찾지 못했어요. "
            "조건을 조금 넓혀볼까요, 아니면 다른 종류의 상품을 찾아볼까요?",
            "I couldn't find a product in the catalog that matches your conditions. "
            "Shall we relax them a little, or look at a different kind of product?",
        )
    n = len(scored)
    return L(
        f"말씀하신 조건에 딱 맞는 상품은 지금 카탈로그에서 찾지 못했어요. "
        f"대신 가장 가까운 후보 {n}가지를 보여드릴게요 — 각 카드에 조건과 다른 점을 "
        "표시해두었어요. 조건을 조금 넓혀볼까요, 아니면 다른 방향으로 찾아볼까요?",
        f"I couldn't find products that exactly match your conditions, so here are the {n} "
        "closest candidates — each card notes where it falls short. Shall we relax a "
        "condition, or try a different direction?",
    )


def explain_text(products: list[models.Product]) -> str:
    if not products:
        return L("조금 더 구체적으로 어떤 점이 궁금하신지 알려주시면 비교해드릴게요.",
                 "Let me know what you're curious about and I'll compare the options for you.")
    lines = [L("최근 보여드린 후보를 기준으로 비교해드릴게요.",
               "Here's a comparison of the recently shown candidates."), ""]
    for p in products:
        ltr = f"{round((p.long_term_review_ratio or 0) * 100)}%"
        lines.append(L(
            f"- {p.title}: 평점 {p.rating}, 리뷰 {p.review_count:,}개, "
            f"한달사용 리뷰 비율 {ltr}, 셀러 등급 {p.seller_grade}.",
            f"- {p.title}: rating {p.rating}, {p.review_count:,} reviews, "
            f"{ltr} long-term-use reviews, seller grade {p.seller_grade}.",
        ))
    best = max(products, key=lambda p: p.long_term_review_ratio or 0)
    lines.append("")
    lines.append(L(
        f"오래 쓰는 관점에서는 한달사용 리뷰 비율이 가장 높은 '{best.title}' 쪽이 "
        "오래 써도 괜찮을 가능성이 높아 보여요. 다만 이건 리뷰만 본 거라, 직접 기준을 알려주시면 더 정확해져요.",
        f"For long-term use, '{best.title}' looks most promising given its long-term-use "
        "review ratio — though that's only from reviews, so telling me your own criteria will make this sharper.",
    ))
    return "\n".join(lines)


def detail_text(p: models.Product, prof: dict | None = None) -> str:
    """자세히 클릭에 대한 결정론 초안 (mock 출력 겸 실패 폴백) — 상품 사실 + 프로필
    (오프라인 enrichment의 keyAttributes/caveats)로 설명하고, 무엇이 궁금한지 묻는다.
    질문이 핵심: 탐색 클릭의 의미를 시스템이 추측하는 대신 사용자가 직접 말하게 한다."""
    lines = [L(f"'{p.title}'에 대해 더 알려드릴게요.",
               f"Here's more about '{product_display_title(p)}'.")]
    facts = []
    if p.price is not None:
        facts.append(L(f"가격 {p.price:,}원", f"priced at {product_display_price(p)}"))
    if p.rating:
        facts.append(L(f"평점 {p.rating}", f"rating {p.rating}"))
    if p.review_count:
        facts.append(L(f"리뷰 {p.review_count:,}개", f"{p.review_count:,} reviews"))
    if facts:
        lines.append(" · ".join(facts))
    if prof:
        if prof.get("profile"):
            lines.append(str(prof["profile"]))
        attrs = prof.get("keyAttributes") or []
        if attrs:
            lines.append(L("주요 특징: ", "Key attributes: ") + ", ".join(str(a) for a in attrs[:5]))
        caveats = prof.get("caveats") or []
        if caveats:
            lines.append(L("참고할 점: ", "Worth noting: ") + " / ".join(str(c) for c in caveats[:2]))
    elif p.description:
        lines.append(p.description[:200])
    lines.append(L("이 상품에서 어떤 점이 궁금하신가요? 그냥 둘러보신 거라도 편하게 말씀해 주세요.",
                   "What would you like to know about this product? If you were just browsing, that's fine too."))
    return "\n\n".join(lines)


def conflict_text(conflict: models.PreferenceConflict) -> str:
    base = conflict.explanation_for_user or L(
        "말씀해주신 기준 사이에 충돌이 있는 것 같아요.",
        "Some of your criteria seem to be in tension with each other.")
    return L(f"기준이 바뀐 것 같아요.\n\n{base}\n\n어느 쪽을 우선할지 알려주세요.",
             f"It looks like your criteria may have shifted.\n\n{base}\n\nWhich direction should take priority?")


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
        entry: dict = {"title": product_display_title(p)}
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
                # EN 모드는 가격을 $ 문자열로 선계산해 싣는다 — 모델이 KRW를 암산
                # 변환하다 틀리는 것을 막고, 응답은 이 값을 그대로 인용하면 된다.
                "title": product_display_title(p),
                "price": product_display_price(p) if is_en() else p.price,
                "rating": p.rating,
                "reviewCount": p.review_count,
                "longTermReviewRatio": p.long_term_review_ratio,
                "recentSalesCount": p.recent_sales_count,
                "sellerGrade": p.seller_grade,
                "deliveryFee": usd(p.delivery_fee) if is_en() and p.delivery_fee else p.delivery_fee,
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
        reply_system = AGENT_REPLY_SYSTEM
        if is_en():
            reply_system += ("\n\n[참가자 화면 언어]\n모든 응답을 자연스러운 영어로 쓴다"
                             " (hedged tone: \"it seems\", \"you might\")."
                             " draftTemplate이 영어면 그 사실 정보를 유지하며 다듬는다."
                             " 가격은 컨텍스트에 이미 $ 문자열로 주어져 있다 — 그대로"
                             " 인용하고, KRW 금액을 새로 계산하거나 언급하지 않는다.")
        messages = [
            LLMMessage(role="system", content=reply_system),
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
) -> tuple[list[ScoredProduct], dict[str, dict], dict[str, str], dict]:
    """판정 행렬 기반 listwise rerank (2026-08-15 — categorical-over-scalar를 rerank에 적용).

    LLM 출력 계약: 후보×기준 판정 행렬(verdicts) → 순위(order) → 상위 8개 카드(cards).
    결론(순위·카드)이 판정(행렬)에서 유도되게 해 복합 조건 부분 준수·허위 이유를 막는다.
    코드는 기준 내용을 모른다 — 행렬의 구조적 귀결만 집행한다:
    hard 기준(constraint·avoidance·statedConstraintsNote)의 "vio" 셀 → 노출 배제(excluded),
    preference·context의 "vio" → 순위에만 반영(배제 아님), "unk" → 배제 아님.

    반환: (재정렬 scored, {pid: {reason,matched,weak}}, {pid: 위반 내용},
           행렬 진단 {nearMissRequested, vioCounts, verdicts}).
    구 스키마("ranking" + 명시 exclude)는 폴백으로 계속 파싱한다(스텁·구모델 안전망).
    mock/실패 시 입력 순서 그대로 + 빈 제외 셋 + 사실기반 폴백 카드 (재현성).
    """
    matrix: dict = {"nearMissRequested": False, "vioCounts": {}, "verdicts": {}}
    if not scored:
        return scored, {}, {}, matrix

    from app.products import profiles

    by_index = {i: sp for i, sp in enumerate(scored)}
    candidates = []
    for i, sp in enumerate(scored):
        p = sp.product
        cand = {
            # EN 모드는 영어 원제목 — 카드 필드가 영어 어휘에 그라운딩되게 한다
            "index": i, "title": product_display_title(p), "category": p.category,
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

    # 행렬 셀의 키(cid) 부여 — hard cid의 "vio"만 배제로 이어진다 (기준 내용은 코드 무관)
    criteria = [dict(c) for c in (intent_context.get("criteria") or [])]
    for ci, c in enumerate(criteria):
        c["cid"] = f"c{ci + 1}"
    hard_cids = {c["cid"] for c in criteria if c.get("kind") in ("constraint", "avoidance")}
    label_by_cid = {c["cid"]: (c.get("label") or c["cid"]) for c in criteria}
    if (intent_context.get("statedConstraintsNote") or "").strip():
        hard_cids.add("note")
        label_by_cid["note"] = L("직접 말씀하신 조건", "your stated conditions")
    matrix["criterionLabels"] = label_by_cid  # 노출 셋의 unk 집계(확인 불가 고지)에 쓰인다
    context = {**intent_context, "criteria": criteria, "candidates": candidates}

    def _parse_card(item: dict) -> dict:
        return {
            "reason": (item.get("reason") or "").strip(),
            "matched": [m for m in (item.get("matched") or []) if isinstance(m, str)][:2],
            "weak": [w for w in (item.get("weak") or []) if isinstance(w, str)][:2],
        }

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
        raw = raw or {}
        if "order" in raw or "verdicts" in raw:
            matrix["nearMissRequested"] = raw.get("nearMissRequested") is True
            for v in raw.get("verdicts") or []:
                idx = v.get("index") if isinstance(v, dict) else None
                if idx not in by_index:
                    continue
                cells = v.get("cells") if isinstance(v.get("cells"), dict) else {}
                pid = by_index[idx].product.id
                matrix["verdicts"][pid] = cells
                vio_cids = [cid for cid, val in cells.items()
                            if val == "vio" and cid in hard_cids]
                if vio_cids:
                    note = (v.get("vioNote") or "").strip() or ", ".join(
                        label_by_cid.get(cid, cid) for cid in vio_cids)
                    excluded[pid] = note
                    for cid in vio_cids:
                        klabel = label_by_cid.get(cid, cid)
                        matrix["vioCounts"][klabel] = matrix["vioCounts"].get(klabel, 0) + 1
            for idx in raw.get("order") or []:
                if idx in by_index and idx not in order:
                    order.append(idx)
            for item in raw.get("cards") or []:
                idx = item.get("index") if isinstance(item, dict) else None
                if idx in by_index:
                    card_texts[by_index[idx].product.id] = _parse_card(item)
        else:
            # 구 스키마 폴백 — 명시 exclude:true만 제외로 인정 (2026-07-07 계약)
            for item in raw.get("ranking", []):
                idx = item.get("index")
                if idx in by_index and idx not in order:
                    order.append(idx)
                    pid = by_index[idx].product.id
                    card_texts[pid] = _parse_card(item)
                    if item.get("exclude") is True:
                        excluded[pid] = (item.get("excludeReason") or "").strip()
    except Exception:  # noqa: BLE001 — 폴백: 입력 순서 유지, 제외 없음
        order = []
        excluded = {}
        matrix = {"nearMissRequested": False, "vioCounts": {}, "verdicts": {}}

    # 누락된 후보는 원래(임베딩) 순서로 뒤에 붙임 (재현성·완전성; 제외 아님)
    for i in range(len(scored)):
        if i not in order:
            order.append(i)
    reranked = [by_index[i] for i in order]

    # 카드텍스트 누락분은 사실기반 폴백 (카드가 비지 않게)
    for sp in reranked:
        if sp.product.id not in card_texts or not card_texts[sp.product.id]["reason"]:
            card_texts[sp.product.id] = _fallback_card(sp.product)
    return reranked, card_texts, excluded, matrix


_FALLBACK_SUGGESTIONS = {
    "clarify": [L("네, 그게 중요해요", "Yes, that matters to me"),
                L("아니요, 그건 아니에요", "No, not really"),
                L("잘 모르겠어요", "I'm not sure")],
    "recommend": [L("더 저렴한 건 없나요?", "Anything cheaper?"),
                  L("사실 디자인도 중요해요", "Design matters to me too"),
                  L("오래 쓰는 게 우선이에요", "Durability comes first")],
    "answer": [L("다른 기준으로 비교해줘", "Compare them on other criteria"),
               L("이걸로 정할게요", "I'll go with this one"),
               L("더 보여줄 수 있나요?", "Can you show me more?")],
    # 자세히 클릭 후 — "그냥 둘러봤어요"가 핵심 칩: 호기심 클릭을 명시적으로 캡처해
    # 시스템이 추측할 여지를 없앤다.
    "detail": [L("가격이 적당한지 궁금해요", "Is the price reasonable?"),
               L("기능·사양이 궁금해요", "Tell me about the specs"),
               L("그냥 둘러봤어요", "Just browsing")],
}
_FALLBACK_DEFAULT = [L("좀 더 추천해줘", "Show me more options"),
                     L("가격이 가장 중요해요", "Price matters most"),
                     L("잘 모르겠어요", "I'm not sure")]


async def generate_reply_suggestions(
    provider: LLMProvider,
    action: str,
    agent_reply: str,
    state_summary: dict | None,
    recent_user_utterances: list[str] | None = None,
) -> list[str]:
    """입력창 위 '답변 칩' 생성 — 방금 에이전트 말에 이어지는 사용자 1인칭 후보 3개.
    대화 맥락(에이전트 응답)+가치요약 기반. 사용자가 이미 밝힌 조건(발화 원문)을 실어
    극성 뒤집힌 제안("RGB 없음" 요청에 "RGB도 있었으면")을 막는다. 실패/mock-빈 시 폴백."""
    fallback = _FALLBACK_SUGGESTIONS.get(action, _FALLBACK_DEFAULT)
    if provider.name == "mock":
        return fallback  # mock은 핸들러가 같은 값 — 호출 절약
    context = {
        "action": action,
        "agentReply": (agent_reply or "")[:500],
        "userStatedSoFar": [u[:200] for u in (recent_user_utterances or [])[-5:]],
        "userValues": {
            "summary": (state_summary or {}).get("oneSentenceSummary", ""),
            # 칩 라벨은 설계상 극성 없는 문구 — type(avoid 등)을 함께 싣지 않으면
            # 회피 기준을 원한다고 제안하는 극성 역전이 생긴다 (2026-08-15 RGB 사례)
            "chips": [
                {"label": c.get("label"), "type": c.get("type")}
                for c in (state_summary or {}).get("chips", [])
            ],
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
        matched.append(L(f"한달사용 리뷰 비율이 {ltr}%로 높은 편이에요",
                         f"{ltr}% of reviews come after a month of use"))
    if (p.rating or 0) >= 4.5:
        matched.append(L(f"평점 {p.rating}로 만족도가 높아요", f"Rated {p.rating} by buyers"))
    if not matched:
        matched.append(L("말씀하신 기준에 무난하게 맞는 편이에요", "A reasonable fit for your criteria"))
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
        return L("결정을 도와드려서 기뻤어요. 필요하시면 언제든 다시 찾아주세요.",
                 "Glad I could help you decide. Come back anytime!")
    return (
        L(f"'{product.title}'(으)로 결정하셨네요. 좋은 선택이에요! "
          "이번 대화에서 제가 이해한 기준이 다르게 느껴진 부분이 있었다면 알려주세요.",
          f"You've decided on '{product.title}' — great choice! "
          "If any of the criteria I picked up felt off during this conversation, let me know.")
    )

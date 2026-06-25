"""Deterministic rule engine backing MockLLMProvider (spec §27).

Implements keyword-driven Korean shopping-dialogue understanding so the full
demo (gift smartwatch scenario, spec §24) runs end-to-end without an LLM API.
Each function mirrors the JSON contract of the corresponding pipeline stage,
so a real LLM provider can replace it without touching callers.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Canonical topic labels (single source of truth for rules below)
# ---------------------------------------------------------------------------
T_GIFT_SPORT = "운동 좋아하는 친구에게 맞는 선물"
T_GIFT_GENERIC = "선물 받는 사람에게 적절한 상품"
T_BRAND_UNKNOWN = "브랜드를 잘 몰라 실패 확률이 낮은 선택을 원함"
T_LOW_PRICE = "가격이 낮을수록 좋음"
T_VALUE_FOR_MONEY = "가격 대비 효용 중시"
T_NOT_TOO_CHEAP = "선물로 너무 저렴해 보이지 않기"
T_LONG_TERM_TRUST = "장기 사용 신뢰가 필요함"
T_DISTINCTIVE = "흔하지 않은 선물의 특별함"
T_SELLER_TRUST = "셀러와 브랜드 신뢰가 필요함"
T_SAFE_CHOICE = "실패 가능성이 낮은 안전한 선택 선호"
T_BATTERY = "배터리 지속시간이 중요함"
T_WATERPROOF = "방수 기능 필요"
T_DESIGN = "디자인과 취향 적합"
T_PRICE_BURDEN = "가격 부담 줄이기"

GIFT_CONTEXT_LABELS = {T_GIFT_SPORT, T_GIFT_GENERIC}


def _has(text: str, *kws: str) -> bool:
    return any(k in text for k in kws)


def _topic(label, description, explicitness, confidence, priority, evidence,
           kind="preference", implied_hard_constraint=None, implied_avoidance=None,
           price_min=None, price_max=None):
    # M1: 계약상 원본은 confidenceLevel 범주 — 기존 숫자 인자에서 레벨을 파생해
    # 양쪽 다 내보낸다 (merge는 레벨 우선, 숫자는 폴백).
    level = ("directly_stated" if confidence >= 0.8
             else "strong_inference" if confidence >= 0.55 else "weak_inference")
    return {
        "label": label,
        "description": description,
        "explicitness": explicitness,
        "confidence": confidence,
        "confidenceLevel": level,
        "priority": priority,
        "kind": kind,  # preference | constraint | avoidance | context
        "impliedHardConstraint": implied_hard_constraint,
        "impliedAvoidance": implied_avoidance,
        "priceMin": price_min,
        "priceMax": price_max,
        "sourceEvidence": evidence,
    }


# ---------------------------------------------------------------------------
# Stage 1 — topic extraction (spec §15.1)
# ---------------------------------------------------------------------------
def _is_negative_cheap_remark(text: str) -> bool:
    return _has(text, "저렴해 보이", "싸 보이", "싸보이") and _has(
        text, "좀 그래", "싫", "별로", "그렇", "않", "안 ", "애매"
    )


def _topics_from_turn(turn: dict) -> list[dict]:
    text = turn.get("content", "")
    ev = [{"type": "turn", "id": turn["id"], "quoteOrSummary": text}]
    out: list[dict] = []

    gift = _has(text, "선물", "에게 줄", "친구 줄", "친구에게", "엄마", "아버지", "부모님")
    sporty = _has(text, "운동", "스포츠", "러닝", "헬스", "피트니스")
    neg_cheap = _is_negative_cheap_remark(text)

    if gift and sporty:
        out.append(_topic(
            T_GIFT_SPORT,
            "수령자(운동을 좋아하는 친구)의 생활양식에 맞는 선물을 원한다.",
            "explicit", 0.85, "high", ev, kind="context",
            implied_hard_constraint="운동 기능이 있어야 함",
        ))
    elif gift:
        out.append(_topic(
            T_GIFT_GENERIC,
            "선물 맥락에서 수령자에게 적절한 상품을 원한다.",
            "explicit", 0.8, "high", ev, kind="context",
        ))

    if _has(text, "브랜드") and _has(text, "몰라", "모르", "잘 모"):
        out.append(_topic(
            T_BRAND_UNKNOWN,
            "브랜드 지식이 부족해 실패 확률이 낮은 안전한 추천 기준이 필요하다.",
            "explicit", 0.75, "medium", ev,
        ))

    if neg_cheap:
        out.append(_topic(
            T_NOT_TOO_CHEAP,
            "단순 최저가보다 선물로 보았을 때 적절한 가격대와 체면을 중요하게 본다.",
            "implicit", 0.86, "high", ev, kind="avoidance",
            implied_avoidance="초저가로 보이는 상품",
        ))
    elif (
        _has(text, "저렴한 게 좋", "저렴한게 좋", "싼 게 좋", "싼게 좋", "최저가", "가격이 낮", "저렴할수록", "쌀수록")
        or (_has(text, "저렴", "싸게", "싼 ") and _has(text, "좋아요", "좋겠", "좋긴", "좋아"))
    ):
        out.append(_topic(
            T_LOW_PRICE,
            "가능하면 가격이 낮은 상품을 선호한다고 말했다.",
            "explicit", 0.75, "high", ev,
        ))

    if _has(text, "가성비"):
        out.append(_topic(
            T_VALUE_FOR_MONEY,
            "가격 대비 효용을 중요하게 본다.",
            "explicit", 0.7, "medium", ev,
        ))

    from app.products.scoring import parse_price_range

    lo, hi = parse_price_range(text)
    if (lo is not None or hi is not None) and _has(
        text, "이하", "이내", "안에", "안으로", "넘지", "까지", "예산", "아래",
        "이상", "사이", "에서", "부터", "원대",
    ):
        # mock은 LLM 대역: 발화를 숫자로 풀어 priceMin/priceMax로 방출(문자열 아님).
        if lo and hi:
            label = f"가격 {lo // 10000}~{hi // 10000}만원"
        elif hi:
            label = f"가격 {hi // 10000}만원 이하"
        else:
            label = f"가격 {lo // 10000}만원 이상"
        out.append(_topic(
            label,
            "사용자가 가격대를 제시했다.",
            "explicit", 0.9, "must_have", ev, kind="constraint",
            price_min=lo, price_max=hi,
        ))

    if _has(text, "오래 쓰", "오래 써", "한달사용", "한 달 사용", "장기", "오래 사용"):
        out.append(_topic(
            T_LONG_TERM_TRUST,
            "오래 써도 문제없다는 장기 사용 신뢰가 필요하다.",
            "implicit", 0.7, "high", ev,
        ))

    if _has(text, "AS", "에이에스", "환불", "교환") or _has(text, "불안", "걱정", "실패"):
        out.append(_topic(
            T_SAFE_CHOICE,
            "실패 가능성이 낮고 안심할 수 있는 선택을 원한다.",
            "implicit", 0.7, "medium", ev,
        ))

    if _has(text, "배터리"):
        out.append(_topic(T_BATTERY, "배터리 지속시간이 중요한 기준이다.", "explicit", 0.75, "medium", ev))

    if _has(text, "방수", "수영"):
        out.append(_topic(T_WATERPROOF, "방수 기능이 필요하다.", "explicit", 0.8, "high", ev,
                          kind="constraint", implied_hard_constraint="방수 기능이 있어야 함"))

    if _has(text, "디자인", "예쁜", "예쁘", "이쁜"):
        out.append(_topic(T_DESIGN, "디자인과 취향 적합이 중요한 기준이다.", "explicit", 0.65, "medium", ev))

    if _has(text, "흔하", "흔해", "흔한"):
        out.append(_topic(
            T_DISTINCTIVE,
            "흔한 상품보다 선물로서 특별해 보이는 상품을 원한다.",
            "implicit", 0.7, "medium", ev, kind="avoidance",
            implied_avoidance="너무 흔한 인기 상품",
        ))

    return out


def _topics_from_feedback(fb: dict) -> list[dict]:
    text = fb.get("reasonText") or ""
    code = fb.get("reasonCode")
    valence = fb.get("valence")
    quote = f"{fb.get('type')} on {fb.get('productTitle', fb.get('productId'))}" + (f' — "{text}"' if text else "")
    ev = [{"type": "feedback", "id": fb["id"], "quoteOrSummary": quote}]
    cues = fb.get("productCues") or {}
    out: list[dict] = []

    if valence == "negative":
        if code == "too_cheap_looking" or _has(text, "저렴해 보이", "싸 보이", "싸보이"):
            out.append(_topic(
                T_NOT_TOO_CHEAP,
                "단순 최저가보다 선물로 보았을 때 적절한 가격대와 체면을 중요하게 본다.",
                "implicit", 0.86, "high", ev, kind="avoidance",
                implied_avoidance="초저가로 보이는 상품",
            ))
        if code == "too_common" or _has(text, "흔하", "흔해", "흔한"):
            out.append(_topic(
                T_DISTINCTIVE,
                "흔한 상품보다 선물로서 특별해 보이는 상품을 원한다.",
                "latent", 0.7, "medium", ev, kind="avoidance",
                implied_avoidance="너무 흔한 인기 상품",
            ))
        if code == "not_trustworthy" or _has(text, "신뢰", "믿음", "못 믿", "믿을"):
            out.append(_topic(
                T_SELLER_TRUST,
                "셀러 등급과 브랜드 신뢰가 낮으면 불안해한다.",
                "implicit", 0.7, "high", ev,
            ))
        if code == "low_long_term_reviews" or _has(text, "한달", "한 달", "오래 쓴 리뷰", "장기"):
            out.append(_topic(
                T_LONG_TERM_TRUST,
                "오래 써도 문제없다는 장기 사용 신뢰가 필요하다.",
                "implicit", 0.72, "high", ev,
            ))
        if code == "too_expensive" or _has(text, "비싸", "부담"):
            out.append(_topic(
                T_PRICE_BURDEN,
                "예산을 크게 넘는 상품은 부담스러워한다.",
                "explicit", 0.7, "high", ev, kind="avoidance",
                implied_avoidance="예산을 크게 넘는 상품",
            ))
        if code == "bad_design" or _has(text, "디자인"):
            out.append(_topic(T_DESIGN, "디자인과 취향 적합이 중요한 기준이다.", "implicit", 0.6, "medium", ev))
    elif valence == "positive":
        ltr = fb.get("longTermReviewRatio")
        if (ltr is not None and ltr >= 0.3) or cues.get("trustCue") == "high":
            out.append(_topic(
                T_LONG_TERM_TRUST,
                "장기 사용 리뷰가 많은 상품에 긍정적으로 반응했다.",
                "latent", 0.55, "medium",
                [{"type": "product_cue", "id": fb["id"],
                  "quoteOrSummary": f"긍정 반응 상품의 한달사용 리뷰 비율이 높음 ({ltr})"}],
            ))

    return out


def topic_extraction(ctx: dict) -> dict:
    topics: list[dict] = []
    for turn in ctx.get("turns", []):
        if turn.get("role") in ("user", "user_agent"):
            topics.extend(_topics_from_turn(turn))
    for fb in ctx.get("feedback", []):
        topics.extend(_topics_from_feedback(fb))
    # dedupe by label within one extraction batch (merge evidence)
    by_label: dict[str, dict] = {}
    for t in topics:
        if t["label"] in by_label:
            by_label[t["label"]]["sourceEvidence"].extend(t["sourceEvidence"])
        else:
            by_label[t["label"]] = t
    return {"topics": list(by_label.values())}


# ---------------------------------------------------------------------------
# Stage 2 — 6-anchor mapping (spec §15.2)
# ---------------------------------------------------------------------------
ANCHOR_TABLE: dict[str, list[tuple[str, float, str, str]]] = {
    T_GIFT_SPORT: [
        ("Conditional", 0.85, "confirmed", "수령자와 선물이라는 사용 맥락이 분명히 드러났다."),
        ("Social", 0.7, "inferred", "타인에게 주는 선물이라는 관계 맥락이 있다."),
        ("Functional", 0.65, "inferred", "운동 기능 적합성이 필요하다."),
    ],
    T_GIFT_GENERIC: [
        ("Conditional", 0.8, "confirmed", "선물이라는 사용 맥락이 판단 기준을 바꾼다."),
        ("Social", 0.65, "inferred", "수령자와의 관계 적절성이 작동한다."),
    ],
    T_BRAND_UNKNOWN: [
        ("Epistemic", 0.7, "confirmed", "브랜드 정보가 부족해 비교·학습이 필요하다."),
        ("Emotional", 0.6, "inferred", "실패에 대한 불안을 줄이려는 신호가 있다."),
    ],
    T_LOW_PRICE: [
        ("Functional", 0.8, "confirmed", "가격 대비 효용을 직접 언급했다."),
    ],
    T_VALUE_FOR_MONEY: [
        ("Functional", 0.85, "confirmed", "가성비를 직접 언급했다."),
    ],
    T_NOT_TOO_CHEAP: [
        ("Social", 0.9, "confirmed", "선물의 인상과 관계적 적절성을 중요하게 보고 있다."),
        ("Conditional", 0.75, "confirmed", "선물이라는 사용 맥락이 가격 판단 기준을 바꾸고 있다."),
        ("Emotional", 0.45, "inferred", "수령자가 부정적으로 느낄 가능성을 피하려는 신호가 있다."),
    ],
    T_LONG_TERM_TRUST: [
        ("Emotional", 0.75, "inferred", "오래 써도 문제없다는 안심이 필요하다."),
        ("Functional", 0.6, "inferred", "내구성과 품질 지속성이 관련된다."),
    ],
    T_DISTINCTIVE: [
        ("Social", 0.7, "inferred", "흔한 선물은 관계적 인상이 약하다고 본다."),
        ("Emotional", 0.5, "inferred", "특별한 선물이 주는 긍정적 감정을 원한다."),
        ("Epistemic", 0.4, "weak", "남다른 것을 탐색하려는 신호."),
    ],
    T_SELLER_TRUST: [
        ("Emotional", 0.75, "inferred", "셀러 신뢰로 실패 불안을 줄이려 한다."),
        ("Epistemic", 0.45, "weak", "신뢰 단서를 탐색하고 있다."),
    ],
    T_SAFE_CHOICE: [
        ("Emotional", 0.8, "confirmed", "실패 회피와 안심을 직접 언급했다."),
        ("Epistemic", 0.4, "inferred", "불확실성 해소가 필요하다."),
    ],
    T_BATTERY: [("Functional", 0.8, "confirmed", "배터리 스펙을 직접 언급했다.")],
    T_WATERPROOF: [("Functional", 0.8, "confirmed", "방수 기능을 직접 언급했다.")],
    T_DESIGN: [
        ("Emotional", 0.55, "inferred", "디자인이 주는 긍정적 감정을 원한다."),
        ("Social", 0.45, "weak", "타인에게 보이는 인상이 일부 작동한다."),
    ],
    T_PRICE_BURDEN: [
        ("Functional", 0.6, "confirmed", "지출 부담을 직접 언급했다."),
        ("Conditional", 0.4, "inferred", "예산이라는 맥락 제약이 있다."),
    ],
}


def anchor_mapping(ctx: dict) -> dict:
    mappings = []
    for t in ctx.get("topics", []):
        label = t["label"]
        rows = ANCHOR_TABLE.get(label)
        if rows is None and label.startswith("예산"):
            rows = [
                ("Functional", 0.6, "confirmed", "예산 제약을 직접 언급했다."),
                ("Conditional", 0.45, "inferred", "구매 맥락의 제약이다."),
            ]
        if rows is None:
            rows = [("Functional", 0.5, "weak", "명시적 근거가 부족해 약하게 추론했다.")]
        strength_by_conf = {"confirmed": "high", "inferred": "medium", "weak": "low"}
        mappings.append({
            "topicLabel": label,
            "anchors": [
                {"anchor": a, "score": s, "confidence": c, "rationale": r,
                 "evidenceStrength": strength_by_conf.get(c, "medium"),
                 "decisionImpact": "high" if s >= 0.75 else ("medium" if s >= 0.5 else "low"),
                 "temporalStatus": "emerging",
                 "evidence": [e["quoteOrSummary"] for e in t.get("sourceEvidence", [])][:2]}
                for (a, s, c, r) in rows
            ],
        })
    return {"mappings": mappings}


# ---------------------------------------------------------------------------
# Stage 3 — conceptualization (spec §15.3)
# ---------------------------------------------------------------------------
CONCEPT_TABLE: dict[str, list[tuple[str, str]]] = {
    T_NOT_TOO_CHEAP: [("선물의 체면", "gift_social_appropriateness"),
                      ("가격 하한", "price_floor"),
                      ("사회적 적절성", "social_appropriateness")],
    T_GIFT_SPORT: [("수령자 생활양식 적합", "recipient_lifestyle_fit"),
                   ("선물 맥락", "gift_context")],
    T_GIFT_GENERIC: [("선물 맥락", "gift_context"),
                     ("사회적 적절성", "social_appropriateness")],
    T_BRAND_UNKNOWN: [("실패 회피", "failure_avoidance"),
                      ("탐색 지원 필요", "guidance_need")],
    T_LOW_PRICE: [("가격 민감도", "price_sensitivity")],
    T_VALUE_FOR_MONEY: [("가성비", "value_for_money")],
    T_LONG_TERM_TRUST: [("장기 사용 신뢰", "long_term_trust"),
                        ("리뷰 신뢰성", "review_credibility")],
    T_DISTINCTIVE: [("선물의 특별함", "gift_distinctiveness"),
                    ("차별성", "anti_mainstream")],
    T_SELLER_TRUST: [("셀러 신뢰", "seller_trust"), ("실패 회피", "failure_avoidance")],
    T_SAFE_CHOICE: [("실패 회피", "failure_avoidance"), ("안심", "reassurance")],
    T_BATTERY: [("핵심 스펙 충족", "core_spec_fit")],
    T_WATERPROOF: [("핵심 스펙 충족", "core_spec_fit")],
    T_DESIGN: [("취향 적합", "taste_fit")],
    T_PRICE_BURDEN: [("예산 제약", "budget_cap")],
}


def conceptualization(ctx: dict) -> dict:
    out = []
    for t in ctx.get("topics", []):
        label = t["label"]
        rows = CONCEPT_TABLE.get(label)
        if rows is None and label.startswith("예산"):
            rows = [("예산 제약", "budget_cap")]
        if rows is None:
            rows = [(label, label)]
        out.append({
            "topicLabel": label,
            "concepts": [{"label": cl, "normalizedLabel": nl, "aliases": []} for cl, nl in rows],
        })
    return {"concepts": out}


# ---------------------------------------------------------------------------
# Stage 4 — relation classification (spec §15.4)
# ---------------------------------------------------------------------------
def relation_classification(ctx: dict) -> dict:
    labels = set(ctx.get("topicLabels", []))
    relations = []

    def add(src, tgt, rtype, strength, rationale, causal_evidence=None):
        if src in labels and tgt in labels and src != tgt:
            rel = {
                "sourceTopicLabel": src, "targetTopicLabel": tgt,
                "type": rtype, "strength": strength, "rationale": rationale,
            }
            if causal_evidence is not None:  # 인과 타입(MOTIVATES/REFINES) 증거 수준 (D4/M1)
                rel["causalEvidence"] = causal_evidence
            relations.append(rel)

    for gift_label in GIFT_CONTEXT_LABELS:
        add(gift_label, T_NOT_TOO_CHEAP, "MOTIVATES", 0.9,
            "선물 상황이기 때문에 단순 최저가보다 사회적으로 적절한 가격대가 중요해졌다.",
            causal_evidence="stated_cause")  # "선물인데" — 사용자가 인과를 직접 언어화
        add(gift_label, T_DISTINCTIVE, "MOTIVATES", 0.7,
            "선물 맥락이 흔하지 않은 특별함을 중요하게 만들었다.",
            causal_evidence="strong_inference")
    add(T_LOW_PRICE, T_NOT_TOO_CHEAP, "CONFLICTS_WITH", 0.84,
        "초기에는 낮은 가격을 선호하는 것으로 추론했으나, 이후 너무 저렴해 보이는 상품을 선물로 부적절하다고 거절했다.")
    add(T_BRAND_UNKNOWN, T_LONG_TERM_TRUST, "MOTIVATES", 0.6,
        "브랜드를 모르기 때문에 장기 사용 리뷰 같은 신뢰 단서가 더 중요해졌다.",
        causal_evidence="strong_inference")
    add(T_BRAND_UNKNOWN, T_SAFE_CHOICE, "MOTIVATES", 0.6,
        "브랜드 지식 부족이 실패 회피 성향을 강화한다.", causal_evidence="weak")
    add(T_LONG_TERM_TRUST, T_SAFE_CHOICE, "SUPPORTS", 0.6,
        "장기 사용 신뢰와 실패 회피는 서로를 강화한다.")
    add(T_SELLER_TRUST, T_SAFE_CHOICE, "SUPPORTS", 0.55,
        "셀러 신뢰는 실패 회피 기준을 뒷받침한다.")
    add(T_NOT_TOO_CHEAP, T_LOW_PRICE, "REVISES", 0.7,
        "가격 선호의 적용 범위를 '너무 저렴해 보이지 않는 선'으로 수정한다.")
    return {"relations": relations}


# ---------------------------------------------------------------------------
# Conflict detection (spec §17, recall-first)
# ---------------------------------------------------------------------------
PRICE_CONFLICT_RESOLUTIONS = [
    {
        "id": "accept_new_priority",
        "label": "최저가보다 선물로 적절한 가격대와 신뢰도를 우선하기",
        "action": "accept_new",
        "resultingStatePreview": "중간 이상 가격대, 리뷰/셀러 신뢰도가 높은 상품을 우선 추천합니다.",
    },
    {
        "id": "keep_price_priority",
        "label": "가격이 여전히 가장 중요하다고 유지하기",
        "action": "keep_old",
        "resultingStatePreview": "예산 내 저가 상품을 계속 우선 추천합니다.",
    },
    {
        "id": "merge_price_cap_and_gift_appropriateness",
        "label": "가격 상한은 유지하되 너무 저렴한 상품은 제외하기",
        "action": "merge",
        "resultingStatePreview": "예산 상한 안에서 너무 저렴해 보이는 상품은 제외합니다.",
    },
    {
        "id": "manual_edit",
        "label": "직접 수정하기",
        "action": "manual_edit",
        "resultingStatePreview": "기준을 직접 수정합니다.",
    },
]


def conflict_detection(ctx: dict) -> dict:
    existing = {t["label"]: t for t in ctx.get("existingTopics", [])}
    new = {t["label"]: t for t in ctx.get("newTopics", [])}
    conflicts = []

    # direct: low-price preference vs gift price floor (either arrival order)
    if T_LOW_PRICE in existing and T_NOT_TOO_CHEAP in new:
        conflicts.append({
            "oldTopicLabel": T_LOW_PRICE,
            "newTopicLabel": T_NOT_TOO_CHEAP,
            "label": "direct_conflict",
            "severityScore": 0.84,
            "conflictType": "priority_shift",
            "oldAssumption": "가격이 낮을수록 좋음",
            "newSignal": "선물인데 너무 저렴해 보이면 싫음",
            "explanationForUser": (
                "처음에는 가격을 가장 중요하게 본다고 이해했는데, 방금 피드백을 보면 "
                "선물로 보았을 때 적절한 가격대와 신뢰도가 더 중요한 것 같아요."
            ),
            "explanationForResearcher": (
                "기존 '최저가 선호' 가설(explicit)과 새 '선물 가격 하한' 신호(too_cheap_looking 피드백)가 "
                "우선순위 충돌. WIMHF 관점에서 chosen-rejected pair의 가격/신뢰 cue 차이와 일치."
            ),
            "suggestedResolutions": PRICE_CONFLICT_RESOLUTIONS,
        })
    if T_NOT_TOO_CHEAP in existing and T_LOW_PRICE in new:
        conflicts.append({
            "oldTopicLabel": T_NOT_TOO_CHEAP,
            "newTopicLabel": T_LOW_PRICE,
            "label": "direct_conflict",
            "severityScore": 0.8,
            "conflictType": "contradiction",
            "oldAssumption": "선물로 너무 저렴해 보이지 않는 것이 중요함",
            "newSignal": "가격이 낮을수록 좋다고 말함",
            "explanationForUser": (
                "앞서는 너무 저렴해 보이지 않는 것이 중요하다고 이해했는데, "
                "방금은 저렴한 쪽을 선호한다고 말씀하셨어요. 어느 쪽을 우선할까요?"
            ),
            "explanationForResearcher": "가격 하한 topic과 최저가 선호 topic의 양방향 충돌.",
            "suggestedResolutions": PRICE_CONFLICT_RESOLUTIONS,
        })

    # ambiguous: popularity-ish preference vs distinctiveness (recall-first)
    popularity_labels = [l for l in existing if ("인기" in l or "판매" in l)]
    if popularity_labels and T_DISTINCTIVE in new:
        conflicts.append({
            "oldTopicLabel": popularity_labels[0],
            "newTopicLabel": T_DISTINCTIVE,
            "label": "ambiguous_conflict",
            "severityScore": 0.55,
            "conflictType": "scope_change",
            "oldAssumption": popularity_labels[0],
            "newSignal": "너무 흔한 상품은 선물로 애매하다고 함",
            "explanationForUser": "인기 있는 상품이 좋다고 이해했는데, 너무 흔한 건 선물로 애매하다고 하셔서 확인하고 싶어요.",
            "explanationForResearcher": "인기 선호와 차별성 선호의 적용 범위 충돌 가능성.",
            "suggestedResolutions": [
                {"id": "accept_distinctive", "label": "흔하지 않은 상품을 우선하기", "action": "accept_new",
                 "resultingStatePreview": "판매량보다 차별성이 있는 상품을 우선 추천합니다."},
                {"id": "keep_popular", "label": "검증된 인기 상품을 유지하기", "action": "keep_old",
                 "resultingStatePreview": "리뷰가 많은 인기 상품을 계속 우선 추천합니다."},
            ],
        })

    # ambiguous: budget burden vs premium gift appropriateness
    if T_PRICE_BURDEN in new and T_NOT_TOO_CHEAP in existing:
        conflicts.append({
            "oldTopicLabel": T_NOT_TOO_CHEAP,
            "newTopicLabel": T_PRICE_BURDEN,
            "label": "ambiguous_conflict",
            "severityScore": 0.5,
            "conflictType": "scope_change",
            "oldAssumption": "선물로 너무 저렴해 보이지 않는 것이 중요함",
            "newSignal": "너무 비싼 상품은 부담스러움",
            "explanationForUser": "너무 저렴해 보이는 것도, 너무 비싼 것도 피하고 싶으신 것 같아요. 중간 가격대를 우선할까요?",
            "explanationForResearcher": "가격 하한과 상한이 동시에 생겨 적정 가격 구간(scope)으로 좁혀짐.",
            "suggestedResolutions": [
                {"id": "mid_price_band", "label": "네, 중간 가격대를 우선해주세요", "action": "merge",
                 "resultingStatePreview": "너무 저렴하지도, 너무 비싸지도 않은 가격대를 우선합니다."},
                {"id": "keep_as_is", "label": "아니요, 지금 기준 그대로 둘게요", "action": "keep_old",
                 "resultingStatePreview": "기존 기준을 유지합니다."},
            ],
        })

    return {"conflicts": conflicts}


# ---------------------------------------------------------------------------
# Turn intent classification (PSCon seed taxonomy, spec §6.3)
# ---------------------------------------------------------------------------
def intent_classification(ctx: dict) -> dict:
    text = ctx.get("content", "")
    intents: list[str] = []
    if _has(text, "찾고 있", "추천해", "필요해", "사려고", "사고 싶", "보여줘", "보여주"):
        intents.append("reveal")
    if _has(text, "로 할게", "으로 할게", "결정했", "구매할게", "이걸로", "주문할게"):
        intents.append("accept")
    if _has(text, "싫", "별로", "아니에요", "거절"):
        intents.append("reject")
    if "?" in text or _has(text, "뭐가", "어떤 게", "어떤게", "차이", "어때", "괜찮을까", "궁금", "알려줘", "어떨까"):
        intents.append("inquire")
    if _has(text, "말고", "대신", "바꿔", "다시 추천", "다른 걸"):
        intents.append("revise")
    if _has(text, "좋긴 해요", "좋겠", "이면 좋", "중요", "선호", "좋아요", "신경"):
        intents.append("interpret")
    if not intents:
        intents.append("chitchat")
    return {"intents": list(dict.fromkeys(intents))}


# ---------------------------------------------------------------------------
# Chosen-rejected pair: inferred hidden reason (spec §10)
# ---------------------------------------------------------------------------
def pair_hidden_reason(ctx: dict) -> dict:
    reason = ctx.get("userReasonText") or ""
    diff = ctx.get("diff") or {}
    parts: list[str] = []
    if _has(reason, "저렴해 보이", "싸 보이", "싸보이"):
        parts.append("선물의 사회적 적절성과 장기 사용 신뢰가 최저가보다 중요하게 작동했다")
    if _has(reason, "흔하", "흔해", "흔한"):
        parts.append("흔하지 않은 선물의 특별함이 인기·판매량보다 중요하게 작동했다")
    if _has(reason, "비싸", "부담"):
        parts.append("예산 상한이 프리미엄 신호보다 우선했다")
    if not parts:
        if (diff.get("longTermReviewRatioDiff") or 0) > 0.15:
            parts.append("장기 사용 신뢰(한달사용 리뷰)가 선택을 갈랐다")
        if "chosen product has more trusted seller grade" in (diff.get("cueDifferences") or []):
            parts.append("셀러 신뢰 기반 실패 회피가 작동했다")
        if diff.get("chosenMoreExpensive"):
            parts.append("더 비싸더라도 신뢰·적절성 단서가 있는 쪽을 선택했다")
    if not parts:
        parts.append("상품 단서 차이로는 단일 요인을 특정하기 어렵다")
    return {"inferredHiddenReason": ". ".join(parts) + "."}


# ---------------------------------------------------------------------------
# WIMHF-style feature mining (spec §11)
# ---------------------------------------------------------------------------
def feature_mining(ctx: dict) -> dict:
    pairs = ctx.get("pairs", [])
    total = max(len(pairs), 1)

    def matches(pair, key):
        d = pair.get("productDiff") or {}
        reason = pair.get("userReasonText") or ""
        if key == "long_term_trust":
            return (d.get("longTermReviewRatioDiff") or 0) > 0.15
        if key == "gift_distinctiveness":
            return _has(reason, "흔하", "흔해", "흔한") or (
                "rejected product is more popular" in " ".join(d.get("cueDifferences", []))
                and d.get("chosenMoreExpensive")
            )
        if key == "seller_trust":
            return "chosen product has more trusted seller grade" in (d.get("cueDifferences") or [])
        if key == "gift_price_floor":
            return bool(d.get("chosenMoreExpensive")) and _has(reason, "저렴", "싸")
        return False

    feature_defs = [
        ("long_term_trust", "장기 사용 신뢰",
         "사용자는 리뷰 수가 적더라도 한달사용(장기) 리뷰 비율이 높은 상품을 일관되게 선택했다.",
         0.35, [("Emotional", 0.7), ("Functional", 0.5)], "refine_existing_concept", "장기 사용 신뢰"),
        ("gift_distinctiveness", "흔하지 않은 선물의 특별함",
         "사용자는 인기 많고 흔한 상품보다, 선물로 보았을 때 덜 흔하고 더 특별해 보이는 상품을 선호했다.",
         0.8, [("Social", 0.7), ("Emotional", 0.5)], "new_concept", "선물의 특별함"),
        ("seller_trust", "셀러 신뢰 기반 실패 회피",
         "사용자는 셀러 등급이 높은 상품을 선택해 실패 가능성을 줄이려 했다.",
         0.5, [("Emotional", 0.75), ("Epistemic", 0.4)], "refine_existing_concept", "셀러 신뢰"),
        ("gift_price_floor", "선물 가격 하한(체면 가격대)",
         "사용자는 더 저렴한 상품 대신, 선물로 가벼워 보이지 않는 가격대의 상품을 선택했다.",
         0.45, [("Social", 0.85), ("Conditional", 0.6)], "new_concept", "선물의 체면"),
    ]

    features = []
    for key, label, desc, novelty, anchors, action, concept_label in feature_defs:
        matched = [p for p in pairs if matches(p, key)]
        if not matched:
            continue
        coverage = round(len(matched) / total, 2)
        consistency = 1.0  # rule-matched pairs are consistent by construction
        interpretability = 0.85
        predictiveness = round(0.4 * coverage + 0.3 * consistency + 0.2 * novelty + 0.1 * interpretability, 2)
        features.append({
            "key": key,
            "label": label,
            "description": desc,
            "sourcePairIds": [p["id"] for p in matched],
            "examplePairs": [
                {"pairId": p["id"],
                 "shortExplanation": (p.get("productDiff") or {}).get("naturalLanguageSummary", "")}
                for p in matched[:3]
            ],
            "candidateAnchorMappings": [
                {"anchor": a, "score": s, "confidence": "inferred",
                 "rationale": f"pair 패턴에서 {label} 신호가 반복 관찰됨"}
                for a, s in anchors
            ],
            "noveltyScore": novelty,
            "coverageScore": coverage,
            "predictivenessScore": predictiveness,
            "interpretabilityScore": interpretability,
            "suggestedOntologyAction": action,
            "suggestedConceptLabel": concept_label,
        })
    return {"features": features}


# ---------------------------------------------------------------------------
# Feature clustering (이론모듈 §9.4 Step 4)
# ---------------------------------------------------------------------------
CLUSTER_RULES = [
    {
        "label": "선물의 리스크 회피",
        "description": "선물 이후 실패(저렴해 보임, 고장, 배송/AS 문제)를 피하려는 상위 가치",
        "members": ["장기 사용 신뢰", "셀러 신뢰 기반 실패 회피", "선물 가격 하한(체면 가격대)"],
        "scenarioDistribution": {"gift_for_other": "high", "high_involvement": "medium"},
    },
    {
        "label": "선물의 차별성 추구",
        "description": "흔하지 않고 특별해 보이는 선물을 원하는 상위 가치",
        "members": ["흔하지 않은 선물의 특별함", "선물 가격 하한(체면 가격대)"],
        "scenarioDistribution": {"gift_for_other": "high", "taste_identity": "medium"},
    },
]


def feature_clustering(ctx: dict) -> dict:
    labels = {f.get("label") for f in ctx.get("features", [])}
    clusters = []
    for rule in CLUSTER_RULES:
        members = [m for m in rule["members"] if m in labels]
        if len(members) >= 2:
            clusters.append({
                "label": rule["label"],
                "description": rule["description"],
                "memberFeatureLabels": members,
                "scenarioDistribution": rule["scenarioDistribution"],
            })
    return {"clusters": clusters}


# ---------------------------------------------------------------------------
# SME translation (이론모듈 §14.3)
# ---------------------------------------------------------------------------
SME_ACTION_TABLE = {
    "선물의 체면": (["적정 가격대 포지셔닝", "선물 패키지 옵션 강조", "고급스러운 상품 사진 우선 노출"],
                "성의 있어 보이는 합리적 선물로 포지셔닝"),
    "사회적 적절성": (["수신자별 추천 문구 구성", "선물 후기 노출"], "받는 사람이 좋아하는 선물로 포지셔닝"),
    "장기 사용 신뢰": (["한달사용 리뷰를 상세페이지 상단에 노출", "AS/교환 정책 강조", "내구성 정보 추가"],
                  "오래 쓰는 선물로 포지셔닝"),
    "리뷰 신뢰성": (["장기 사용 리뷰 필터 제공", "리뷰 사진 우선 노출"], "검증된 선택으로 포지셔닝"),
    "실패 회피": (["교환/환불 정책 명시", "배송 안정성 강조", "셀러 등급 노출"], "안심 구매로 포지셔닝"),
    "셀러 신뢰": (["셀러 등급/연차 노출", "공식 스토어 인증 강조"], "믿을 수 있는 판매처로 포지셔닝"),
    "선물의 특별함": (["희소성/한정판 요소 강조", "기프트 큐레이션 구성", "디자인 차별점 부각"],
                 "흔하지 않은 특별한 선물로 포지셔닝"),
    "차별성": (["덜 대중적인 컬러/모델 추천", "개성 표현 중심 상세페이지"], "나만의 선택으로 포지셔닝"),
    "수령자 생활양식 적합": (["사용 장면 중심 상세페이지 구성", "용도별 추천 가이드"], "받는 사람의 생활에 맞는 선물로 포지셔닝"),
    "가격 민감도": (["가격 비교보다 value-for-money 설명", "할인 사유 명시"], "납득 가능한 가치로 포지셔닝"),
    "예산 제약": (["예산대별 추천 구성", "배송비 포함 총액 표시"], "예산 안의 최선으로 포지셔닝"),
}


def sme_translation(ctx: dict) -> dict:
    out = []
    for c in ctx.get("concepts", []):
        label = c.get("label", "")
        match = next((v for k, v in SME_ACTION_TABLE.items() if k in label), None)
        if match is None:
            match = (["관련 evidence 기반 상세페이지 보완"], f"'{label}' 기준에 맞는 상품으로 포지셔닝")
        out.append({"conceptLabel": label, "actions": match[0], "positioning": match[1]})
    return {"translations": out}


def motivation_detection(ctx: dict) -> dict:
    """설문 문항 rubric 기반 동기 신호 (M8) — mock은 cue 매칭 + 극성 검사로 결정론 재현."""
    from app.agents.motivation import MOTIVATION_SPEC

    text = ctx.get("content", "")
    signals = []
    for dim, spec in MOTIVATION_SPEC.items():
        hit = next((c for c in spec["cues"] if c in text), None)
        if not hit:
            continue
        if dim == "BargainValue" and _is_negative_cheap_remark(text):
            continue  # 극성 검사: 저렴함 *회피*는 득템 동기의 증거가 아니다
        signals.append({"dim": dim, "level": "suggests", "quote": hit})
    return {"signals": signals}


def judge_causal_relation(ctx: dict) -> dict:
    """인과 주장 judge (M5) — mock은 builder의 증거 수준을 그대로 인정한다."""
    level = ctx.get("causalEvidence")
    if level == "stated_cause":
        return {"verdict": "supported", "supportedLevel": "stated_cause",
                "reason": "인용에 인과 표지가 직접 등장한다."}
    if level == "strong_inference":
        return {"verdict": "supported", "supportedLevel": "strong_inference",
                "reason": "맥락상 강한 추론으로 지지된다."}
    return {"verdict": "downgrade", "supportedLevel": "weak",
            "reason": "동시출현 이상의 근거가 없다."}


def persona_profile(ctx: dict) -> dict:
    """persona×scenario GT 도출 (합성 테스트) — mock은 시나리오 조건부 고정 프로필 (테스트 결정론).

    가치·동기는 상황의 산물이므로 mock도 시나리오에 따라 다른 GT를 내야
    상황 조건부 경로(주입→세션별 GT)가 테스트에서 구별 가능하다.
    """
    sid = (ctx.get("scenario") or {}).get("id") or "gift_for_other"
    if sid == "gift_for_other":
        return {
            "valueLevels": {"Functional": "present", "Social": "dominant", "Emotional": "present",
                            "Epistemic": "trace", "Conditional": "present"},
            "motivationLevels": {"Adventure": "low", "Gratification": "low", "Role": "high",
                                 "BargainValue": "medium", "SocialShopping": "low",
                                 "Idea": "low", "Utilitarian": "medium"},
            "hiddenIntentions": ["받는 사람 앞에서 체면이 깎이지 않을 선물인지 조용히 따진다",
                                 "포장과 브랜드 인상이 값어치를 말해주길 바란다"],
            "personaDistinction": "선물 상황에서도 실리 습관이 남아 가격 대비를 끝까지 살핀다",
            "matchRationale": "서사의 '관계를 중시한다'는 대목이 선물 상황에서 Social을 키운다",
        }
    return {
        "valueLevels": {"Functional": "dominant", "Social": "present", "Emotional": "present",
                        "Epistemic": "trace", "Conditional": "present"},
        "motivationLevels": {"Adventure": "low", "Gratification": "low", "Role": "low",
                             "BargainValue": "high", "SocialShopping": "low",
                             "Idea": "low", "Utilitarian": "high"},
        "hiddenIntentions": ["실리를 중시해 가격 대비 내구성을 조용히 따진다",
                             "지인에게 흠 잡히지 않을 무난한 품질을 원한다"],
        "personaDistinction": "같은 상황의 평균 소비자보다 브랜드보다 내구 연한을 먼저 본다",
        "matchRationale": "서사의 '아껴 쓰는 습관' 대목이 자기용 구매에서 Functional을 키운다",
    }


def scenario_match(ctx: dict) -> dict:
    """persona→시나리오 캐스팅 (합성 풀 확장용) — mock은 첫 시나리오 고정 (결정론)."""
    scenarios = ctx.get("scenarios") or []
    sid = scenarios[0]["id"] if scenarios else "gift_for_other"
    return {
        "scenarioId": sid,
        "speechStyle": "짧고 실리적, 이유를 잘 말하지 않음",
        "matchReason": "서사의 실리 추구 표현과 가장 맞는 상황이다",
    }


def user_agent_utterance(ctx: dict) -> dict:
    """가상 사용자 발화 (합성 테스트) — mock은 2턴 뒤 첫 상품 구매로 수렴."""
    history = ctx.get("history") or []
    shown = ctx.get("shownProducts") or []
    user_turns = sum(1 for h in history if h.get("role") == "user")
    if user_turns == 0:
        need = (ctx.get("scenario") or {}).get("initialUserNeed", "스마트워치 추천해 주세요.")
        return {"utterance": need, "action": "continue", "purchaseProductId": None}
    if user_turns >= 2 and shown:
        pid = shown[0]["id"]
        return {"utterance": "그걸로 할게요.", "action": "purchase", "purchaseProductId": pid}
    return {"utterance": "가성비 좋은 걸로 보여주세요. 너무 비싼 건 부담돼요.",
            "action": "continue", "purchaseProductId": None}


def user_agent_reaction(ctx: dict) -> dict:
    """가상 사용자 상품 반응 (합성 테스트) — mock은 초저가 dislike(이유 생략) + 첫 상품 like."""
    products = ctx.get("products") or []
    reactions = []
    for p in products:
        if (p.get("cueSummary") or {}).get("priceCue") == "very_low":
            reactions.append({"productId": p["id"], "type": "dislike", "reasonText": None})
        elif not reactions:
            reactions.append({"productId": p["id"], "type": "like", "reasonText": None})
    return {"reactions": reactions}


def card_rationale(ctx: dict) -> dict:
    """결정론적 카드 설명 — 테스트/데모용. 상품 데이터로 간단한 가치 연결 문구를 만든다.
    (실 provider는 prompts.card_rationale로 LLM 생성; mock은 재현성 위해 규칙.)"""
    cards = []
    for p in ctx.get("products", []):
        letter = p.get("letter", "?")
        ltr = round((p.get("longTermReviewRatio") or 0) * 100)
        rating = p.get("rating") or 0
        cue = p.get("cues") or {}
        matched, weak = [], []
        if ltr >= 30:
            matched.append(f"한달사용 리뷰 비율이 {ltr}%로 높아 오래 써도 괜찮을 가능성이 커요")
        if rating >= 4.5:
            matched.append(f"평점이 {rating}로 높은 편이에요")
        if cue.get("priceCue") in ("very_low", "low"):
            matched.append("가격 부담이 적은 편이에요")
        elif cue.get("priceCue") in ("high", "very_high"):
            weak.append("가격대가 높은 편이에요")
        if cue.get("trustCue") == "low":
            weak.append("리뷰·신뢰 단서는 약한 편이에요")
        if not matched:
            matched.append("기준에 무난하게 맞는 편이에요")
        cards.append({
            "letter": letter,
            "reason": matched[0],
            "matched": matched[:2],
            "weak": weak[:2],
        })
    return {"cards": cards}


def rerank(ctx: dict) -> dict:
    """결정론적 rerank — 입력 후보 순서를 그대로 유지(임베딩 순서 = 폴백과 동일).
    각 후보에 간단한 사실 기반 카드텍스트를 붙인다. (실 provider는 가치·동기로 재정렬.)"""
    ranking = []
    for c in ctx.get("candidates", []):
        ltr = round((c.get("longTermReviewRatio") or 0) * 100)
        rating = c.get("rating") or 0
        matched = []
        if ltr >= 30:
            matched.append(f"한달사용 리뷰 비율이 {ltr}%로 높은 편이에요")
        if rating >= 4.5:
            matched.append(f"평점이 {rating}로 높은 편이에요")
        if not matched:
            matched.append("기준에 무난하게 맞는 편이에요")
        ranking.append({
            "index": c.get("index"),
            "reason": matched[0],
            "matched": matched[:2],
            "weak": [],
        })
    return {"ranking": ranking}


def reply_suggestion(ctx: dict) -> dict:
    """결정론적 답변 칩 — 액션별 기본값 (테스트/폴백용; 실 provider는 LLM 생성)."""
    action = ctx.get("action") or ""
    if action == "clarify":
        sug = ["네, 그게 중요해요", "아니요, 그건 아니에요", "잘 모르겠어요"]
    elif action == "recommend":
        sug = ["더 저렴한 건 없나요?", "사실 디자인도 중요해요", "오래 쓰는 게 우선이에요"]
    elif action == "explain":
        sug = ["다른 기준으로 비교해줘", "이걸로 정할게요", "더 보여줄 수 있나요?"]
    else:
        sug = ["좀 더 추천해줘", "가격이 가장 중요해요", "잘 모르겠어요"]
    return {"suggestions": sug}


def state_summary(ctx: dict) -> dict:
    """결정론 요약 — 칩 라벨 조합(B1). 실 provider는 LLM이 trade-off 문장을 생성한다.
    이 mock이 곧 §36 hedged 계약이자 LLM 실패 시의 폴백 형태."""
    labels = [l for l in (ctx.get("labels") or []) if l][:3]
    if not labels:
        return {"summary": "아직 기준을 파악하는 중이에요. 원하시는 조건을 자유롭게 말씀해 주세요."}
    head = ", ".join(labels)
    return {"summary": f"지금은 '{head}'을(를) 더 중요하게 보시는 것 같아요. 맞는지 확인해 주세요."}


def generic_text(_prompt: str) -> str:
    return "확인했어요. 제가 이해한 기준이 맞는지 오른쪽 패널에서 확인해 주세요."


TASK_HANDLERS = {
    "topic_extraction": topic_extraction,
    "anchor_mapping": anchor_mapping,
    "conceptualization": conceptualization,
    "relation_classification": relation_classification,
    "conflict_detection": conflict_detection,
    "intent_classification": intent_classification,
    "motivation_detection": motivation_detection,
    "judge_causal_relation": judge_causal_relation,
    "persona_profile": persona_profile,
    "scenario_match": scenario_match,
    "user_agent_utterance": user_agent_utterance,
    "user_agent_reaction": user_agent_reaction,
    "pair_hidden_reason": pair_hidden_reason,
    "feature_mining": feature_mining,
    "feature_clustering": feature_clustering,
    "sme_translation": sme_translation,
    "card_rationale": card_rationale,
    "reply_suggestion": reply_suggestion,
    "rerank": rerank,
    "state_summary": state_summary,
}

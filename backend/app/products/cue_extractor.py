"""Derive ProductCueSummary (spec §6.1) from raw product fields when missing.

priceCue는 절대 금액이 아니라 **카테고리 내 상대 위치**가 의미를 가진다
(노트북의 40만원은 저가, 스마트워치의 40만원은 고가). category_prices가
주어지면 분위수(20/40/60/80%) 기준으로, 없으면 절대 금액 폴백을 쓴다.
"""


def _quantile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(int(q * len(sorted_vals)), len(sorted_vals) - 1)
    return sorted_vals[idx]


def build_cue_summary(item: dict, category_prices: list[int] | None = None) -> dict:
    price = item.get("price") or 0
    if category_prices and len(category_prices) >= 4:
        sp = sorted(category_prices)
        if price <= _quantile(sp, 0.2):
            price_cue = "very_low"
        elif price <= _quantile(sp, 0.4):
            price_cue = "low"
        elif price <= _quantile(sp, 0.6):
            price_cue = "mid"
        elif price <= _quantile(sp, 0.8):
            price_cue = "high"
        else:
            price_cue = "very_high"
    elif price < 50000:
        price_cue = "very_low"
    elif price < 100000:
        price_cue = "low"
    elif price < 180000:
        price_cue = "mid"
    elif price < 500000:
        price_cue = "high"
    else:
        price_cue = "very_high"

    ltr = item.get("longTermReviewRatio") or 0
    rating = item.get("rating") or 0
    n_reviews = item.get("reviewCount") or 0
    # 신뢰 신호: 평점 + 리뷰 수(검증된 규모) 기반 — NAVER/Amazon 공통 (Amazon엔 한달리뷰 ltr이 없음).
    # ltr(NAVER)이 있으면 상향 보너스로만 사용. 가공 없이 메타 필드 그대로.
    if (rating >= 4.5 and n_reviews >= 200) or (ltr >= 0.3 and rating >= 4.6):
        trust_cue = "high"
    elif rating < 3.8 or n_reviews < 20:
        trust_cue = "low"
    else:
        trust_cue = "medium"

    sales = item.get("recentSalesCount") or 0
    if sales >= 8000:
        popularity = "very_popular"
    elif sales >= 3000:
        popularity = "popular"
    elif sales >= 1000:
        popularity = "moderate"
    else:
        popularity = "niche"

    grade = item.get("sellerGrade") or ""
    if grade in ("프리미엄", "플래티넘", "빅파워", "파워"):
        seller_cue = "trusted"
    elif grade in ("새싹", "씨앗"):
        seller_cue = "new_or_low_grade"
    else:
        seller_cue = "normal"

    novelty = "common" if popularity in ("popular", "very_popular") else "distinctive"
    return {
        "priceCue": price_cue,
        "trustCue": trust_cue,
        "popularityCue": popularity,
        "sellerCue": seller_cue,
        "noveltyCue": novelty,
    }

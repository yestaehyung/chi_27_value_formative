"""Deterministic ProductDiff builder (spec §10, §11 Phase B)."""
from app.db import models

GRADE_RANK = {"씨앗": 0, "새싹": 1, "파워": 2, "빅파워": 3, "프리미엄": 4, "플래티넘": 5}
TRUSTED = {"파워", "빅파워", "프리미엄", "플래티넘"}


def build_product_diff(chosen: models.Product, rejected: models.Product) -> dict:
    price_diff = (chosen.price or 0) - (rejected.price or 0)
    ltr_diff = round((chosen.long_term_review_ratio or 0) - (rejected.long_term_review_ratio or 0), 2)
    cue_differences: list[str] = []

    if ltr_diff > 0.1:
        cue_differences.append("chosen product has higher long-term review ratio")
    elif ltr_diff < -0.1:
        cue_differences.append("rejected product has higher long-term review ratio")

    cg, rgr = chosen.seller_grade or "", rejected.seller_grade or ""
    seller_grade_diff = None
    if cg != rgr:
        seller_grade_diff = f"chosen seller is {cg}, rejected seller is {rgr}"
        if GRADE_RANK.get(cg, 0) > GRADE_RANK.get(rgr, 0):
            cue_differences.append("chosen product has more trusted seller grade")

    if (rejected.recent_sales_count or 0) > (chosen.recent_sales_count or 0) * 2:
        cue_differences.append("rejected product is more popular")
    if price_diff > 0:
        cue_differences.append("rejected product is cheaper")

    summary_parts = []
    if price_diff > 0:
        summary_parts.append("더 저렴")
    if (rejected.recent_sales_count or 0) > (chosen.recent_sales_count or 0):
        summary_parts.append("인기가 많은")
    rejected_desc = "하고 ".join(summary_parts) + " 상품" if summary_parts else "다른 상품"

    chosen_traits = []
    if ltr_diff > 0.1:
        chosen_traits.append("장기 사용 리뷰")
    if GRADE_RANK.get(cg, 0) > GRADE_RANK.get(rgr, 0):
        chosen_traits.append("셀러 신뢰도")
    chosen_desc = "와 ".join(chosen_traits) + "가 높은 상품" if chosen_traits else "상품"

    natural = f"사용자는 {rejected_desc}보다, {chosen_desc}을 선택했다."

    return {
        "priceDiff": price_diff,
        "chosenMoreExpensive": price_diff > 0,
        "ratingDiff": round((chosen.rating or 0) - (rejected.rating or 0), 2),
        "reviewCountDiff": (chosen.review_count or 0) - (rejected.review_count or 0),
        "longTermReviewRatioDiff": ltr_diff,
        "recentSalesDiff": (chosen.recent_sales_count or 0) - (rejected.recent_sales_count or 0),
        "sellerGradeDiff": seller_grade_diff,
        "brandDiff": None if chosen.brand == rejected.brand else f"{chosen.brand} vs {rejected.brand}",
        "categoryDiff": None if chosen.category == rejected.category else f"{chosen.category} vs {rejected.category}",
        "cueDifferences": cue_differences,
        "naturalLanguageSummary": natural,
    }

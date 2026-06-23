"""Product scoring (spec §14.2) + hidden-intention fit rules + rationale strings."""
from app.db import models

PRICE_CUE_ORDER = ["very_low", "low", "mid", "high", "very_high"]


def _char_bigrams(s: str) -> set[str]:
    s = "".join(ch for ch in s if ch.isalnum())
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) >= 2 else set()


def text_relevance(product: models.Product, query: str) -> float:
    """토큰 일치 + 문자 bigram 겹침(한국어 조사/띄어쓰기 변형에 강건)."""
    if not query:
        return 0.5
    hay = f"{product.title} {product.category or ''} {product.brand or ''} {product.description or ''}"
    tokens = [t for t in query.replace(",", " ").split() if len(t) >= 2]
    token_score = (sum(1 for t in tokens if t in hay) / len(tokens)) if tokens else 0.0
    qb, hb = _char_bigrams(query), _char_bigrams(hay)
    bigram_score = len(qb & hb) / len(qb) if qb else 0.0
    base = max(token_score, bigram_score * 0.85)
    if product.category and product.category in query:
        base = max(base, 0.9)
    return min(base + 0.1, 1.0)


def parse_budget_won(text: str) -> int | None:
    """예산 표현 파싱: 'N만원', 'N만 원', 'N십만원', 'N원'(4자리 이상), 'N만원대'."""
    import re

    m = re.search(r"(\d+(?:\.\d+)?)\s*십\s*만\s*원", text)
    if m:
        return int(float(m.group(1)) * 100000)
    m = re.search(r"(\d+(?:\.\d+)?)\s*만\s*원", text)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r"(\d{4,})\s*원", text.replace(",", ""))
    if m:
        return int(m.group(1))
    return None


def hard_constraint_match(product: models.Product, hard_constraints: list[str]) -> float:
    """1.0 if all known constraints pass, 0.0 if a known constraint fails."""
    attrs = product.attributes or {}
    for c in hard_constraints:
        if "운동" in c and not (attrs.get("gps") or attrs.get("style") in ("sport", "performance") or attrs.get("heartRate")):
            return 0.0
        if "방수" in c and not attrs.get("waterproof"):
            return 0.0
        if "예산" in c:
            budget = parse_budget_won(c)
            if budget and product.price and product.price > budget:
                return 0.0
    return 1.0


def trust_score(product: models.Product) -> float:
    cue = product.cue_summary or {}
    s = {"low": 0.2, "medium": 0.5, "high": 0.9}.get(cue.get("trustCue", "medium"), 0.5)
    if cue.get("sellerCue") == "trusted":
        s = min(1.0, s + 0.1)
    return s


def popularity_score(product: models.Product) -> float:
    return {"niche": 0.3, "moderate": 0.5, "popular": 0.7, "very_popular": 0.9}.get(
        (product.cue_summary or {}).get("popularityCue", "moderate"), 0.5
    )


def hidden_intention_fit(product: models.Product, topic_labels: list[str], avoidances: list[str]) -> tuple[float, list[str], list[str]]:
    """Returns (fit score 0-1, matched rationale strings, weak rationale strings). Spec §14.2 rules."""
    cue = product.cue_summary or {}
    attrs = product.attributes or {}
    ltr = product.long_term_review_ratio or 0
    matched: list[str] = []
    weak: list[str] = []
    score = 0.5
    labels = " | ".join(topic_labels)

    if "장기 사용" in labels:
        if ltr >= 0.3:
            score += 0.15
            matched.append("한달사용 리뷰 비율이 높아 장기 사용 신뢰 기준에 맞습니다.")
        else:
            score -= 0.1
            weak.append("한달사용(장기) 리뷰 비율이 낮은 편입니다.")

    if "저렴해 보이지 않기" in labels or "체면" in labels:
        if cue.get("priceCue") == "very_low":
            score -= 0.25
            weak.append("가격대가 매우 낮아 선물로 가벼워 보일 수 있습니다.")
        elif cue.get("priceCue") in ("mid", "high"):
            score += 0.15
            matched.append("선물로 가벼워 보이지 않는 가격대입니다.")
        if cue.get("sellerCue") == "trusted":
            score += 0.05
            matched.append("셀러 신뢰 등급이 높습니다.")

    if "특별함" in labels or "흔하지 않은" in labels:
        if cue.get("popularityCue") == "very_popular":
            score -= 0.15
            weak.append("최근 판매수가 많아 특별한 선물 느낌은 약할 수 있습니다.")
        elif cue.get("noveltyCue") == "distinctive":
            score += 0.1
            matched.append("흔하지 않은 모델이라 선물로 특별해 보일 수 있습니다.")

    if "가성비" in labels or "가격이 낮을수록" in labels:
        if cue.get("priceCue") in ("very_low", "low") and (product.rating or 0) >= 4.4:
            score += 0.15
            matched.append("가격이 낮으면서 평점이 높아 가성비 기준에 맞습니다.")

    if "운동" in labels or "친구에게 맞는 선물" in labels:
        if attrs.get("gps") or attrs.get("style") in ("sport", "performance"):
            score += 0.12
            matched.append("운동 기능(GPS/스포츠 특화)이 분명한 모델입니다.")
        elif not attrs.get("heartRate"):
            weak.append("운동 특화 기능이 분명하지 않습니다.")

    if "신뢰" in labels or "실패" in labels or "브랜드를 잘 몰라" in labels:
        if cue.get("sellerCue") == "trusted" and cue.get("trustCue") == "high":
            score += 0.1
            matched.append("리뷰·셀러 신뢰 단서가 강해 실패 확률이 낮은 선택입니다.")
        elif cue.get("sellerCue") == "new_or_low_grade":
            score -= 0.1
            weak.append("셀러 등급이 낮아 신뢰 단서가 약합니다.")

    if "배터리" in labels and attrs.get("batteryDays"):
        if attrs["batteryDays"] >= 7:
            score += 0.08
            matched.append(f"배터리가 약 {attrs['batteryDays']}일 지속됩니다.")
        else:
            weak.append(f"배터리 지속시간이 {attrs['batteryDays']}일로 짧은 편입니다.")

    if "디자인" in labels or "취향" in labels:
        if attrs.get("style") in ("fashion", "premium") or attrs.get("limitedColor"):
            score += 0.08
            matched.append("디자인 차별 요소가 있는 모델입니다.")

    for avoid in avoidances:
        if "초저가" in avoid and cue.get("priceCue") == "very_low":
            score -= 0.3
            weak.append("'초저가로 보이는 상품 제외' 기준에 걸립니다.")
        if "흔한" in avoid and cue.get("popularityCue") == "very_popular":
            score -= 0.2
        if "예산" in avoid and cue.get("priceCue") in ("high", "very_high"):
            score -= 0.1
            weak.append("예산 부담 기준에서 가격이 높은 편입니다.")
        if "셀러" in avoid and cue.get("sellerCue") == "new_or_low_grade":
            score -= 0.2

    return max(0.0, min(1.0, score)), matched, weak


def compute_product_score(product: models.Product, query: str, hard_constraints: list[str],
                          soft_preferences: list[str], topic_labels: list[str],
                          avoidances: list[str], text_rel: float | None = None) -> tuple[float, list[str], list[str]]:
    """finalScore per spec §14.2. Returns (score, matched, weak).

    text_rel: 외부에서 계산한 적합도(키워드+임베딩 하이브리드)를 주입한다.
    None이면 키워드 적합도만 사용(기존 동작 — mock/테스트 경로).
    """
    # 랭킹 = 사용자 의도(가치) 매칭 위주. 2026-06-23 정리:
    #   - 예산(hard_constraint)은 search.py에서 이미 '필터'로 처리(비보완적 스크리닝,
    #     Payne/Bettman/Johnson) → 점수항으로 중복 계산 안 함(통과품은 다 1.0이라 죽은 항).
    #   - trust/popularity 제거: TCV5 가치·동기 어디에도 근거 없는 일반 커머스 상수였음
    #     (이론 기반 원칙 위배). '신뢰' 가치가 필요하면 anchor(Functional/Emotional) 경로로
    #     반영되고, 리뷰·평점은 카드에 정보로 노출(사용자 판단). 순위엔 안 씀.
    # 남는 항은 모두 의도-매칭: 의미 적합도(임베딩 우선) + soft/fit(topic↔상품 가치 매칭).
    tr = text_rel if text_rel is not None else text_relevance(product, query)
    fit, matched, weak = hidden_intention_fit(product, topic_labels, avoidances)
    soft = 0.5
    if soft_preferences:
        soft_fit, _, _ = hidden_intention_fit(product, soft_preferences, [])
        soft = soft_fit
    score = 0.6 * tr + 0.2 * soft + 0.2 * fit
    return score, matched, weak

"""Keyword search + scoring + trade-off sampler (spec §14, §29)."""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session as DbSession

from app.db import models
from app.products import search_index
from app.products.scoring import compute_product_score, hard_constraint_match, text_relevance
from app.products.tag_filter import required_tags, tag_constraint_ok


@dataclass
class ScoredProduct:
    product: models.Product
    score: float
    matched: list[str] = field(default_factory=list)
    weak: list[str] = field(default_factory=list)
    bucket: str = "balanced"
    relevance: float = 0.0  # 질의 적합도(text_relevance) — trade-off floor 게이트에 사용
    probe_anchor: str | None = None  # 진단적 trade-off: 이 후보가 검증하는 가설 축


# 질의 적합도 하한 — trade-off 다양화가 관련 없는 상품을 버킷에 채우는 것을 막는다 (§14.3 보강).
# detect_category 하드필터에 의존하지 않고, 사용자의 실제 발화↔제목 적합도로 거른다.
# 절대 임계가 아니라 "이번 질의의 최고 적합도 대비 상대값"을 쓴다 — 대화체 질의
# ("나 맥북 사고 싶어, 지금 고장났음")는 불용어가 token_score를 희석해 적합도가 통째로
# 낮아지므로, 고정 임계는 관련 상품까지 잘라낸다(→ 빈 풀 폴백 → 오프도메인 누수). (2026-06-16)
REL_FLOOR_MIN = 0.20   # 바닥 — 이보다 낮으면 사실상 무관
REL_FLOOR_RATIO = 0.5  # 이번 질의 최고 적합도의 비율

# 진단 후보 규칙: 불확실한 anchor 가설을 검증할 수 있는 상품 cue (active learning식 자극 설계)
# 예: Social 가설이 추론 상태면 초저가 상품을 노출 — 싫어하면 체면 가설 확인, 좋아하면 기각
# 진단 후보 규칙 — trait(TCV5) 가설 검증용 (motivation 층은 대화 프로브로 별도 확인)
PROBE_RULES = {
    "Social": lambda p: (p.cue_summary or {}).get("priceCue") == "very_low",
    "Emotional": lambda p: (p.cue_summary or {}).get("trustCue") == "low"
    or (p.long_term_review_ratio or 0) < 0.1,
    "Epistemic": lambda p: (p.cue_summary or {}).get("noveltyCue") == "distinctive",
    "Conditional": lambda p: (p.attributes or {}).get("style") == "basic",
    "Functional": lambda p: (p.rating or 0) >= 4.7,
}


CATEGORY_KEYWORDS = {
    "스마트워치": ["스마트워치", "워치", "스마트 워치", "스마트밴드"],
    "러닝화": ["러닝화", "운동화", "런닝화", "신발"],
    "노트북": ["노트북", "랩탑", "laptop"],
    "무선이어폰": ["이어폰", "무선이어폰", "이어버드", "버즈"],
    "여행용 캐리어": ["캐리어", "여행가방", "수트케이스", "여행 가방"],
    "사무용 의자": ["의자", "오피스체어", "오피스 체어", "사무용의자"],
    "향수": ["향수", "퍼퓸", "오드퍼퓸", "오드뚜왈렛"],
}


def detect_category(text: str) -> str | None:
    for category, kws in CATEGORY_KEYWORDS.items():
        if any(k in text for k in kws):
            return category
    return None


def assign_bucket(p: models.Product) -> str:
    """TradeoffBucket per spec §14.3. Order matters: it spreads the seed catalog
    across distinct buckets so the recommendation set surfaces real trade-offs
    (e.g. A=low price/popular, B=high trust/long-term, C=gift package/premium)."""
    cue = p.cue_summary or {}
    attrs = p.attributes or {}
    if attrs.get("giftPackage") or attrs.get("style") in ("fashion", "premium") or attrs.get("limitedColor"):
        return "design_or_identity"
    if cue.get("priceCue") in ("very_low", "low") and cue.get("popularityCue") in ("popular", "very_popular"):
        return "low_price_popular"
    if (p.long_term_review_ratio or 0) >= 0.3 and cue.get("trustCue") == "high":
        return "high_trust_long_term"
    if cue.get("sellerCue") == "trusted" and (p.delivery_fee or 0) == 0:
        return "seller_reliable"
    if cue.get("noveltyCue") == "distinctive":
        return "novel_or_distinctive"
    return "balanced"


def search_products(
    db: DbSession,
    query: str,
    category: str | None,
    hard_constraints: list[str],
    soft_preferences: list[str],
    topic_labels: list[str],
    avoidances: list[str],
    top_k: int = 3,
    diversify_by_tradeoff: bool = True,
    diagnostic_anchor: str | None = None,
) -> list[ScoredProduct]:
    # 1) BM25(FTS5) retrieve — 전체 스캔 대체(카탈로그 확장 대비). 매칭 없으면 카테고리/전체 폴백.
    ids = search_index.retrieve(db, query, n=200, category=category)
    if ids:
        pm = {p.id: p for p in db.query(models.Product).filter(models.Product.id.in_(ids)).all()}
        candidates = [pm[i] for i in ids if i in pm]
    else:
        q = db.query(models.Product)
        if category:
            q = q.filter(models.Product.category == category)
        candidates = q.all() or db.query(models.Product).all()

    # 2) 이미지 있는 상품 우선 (없으면 전체 유지 — 데모/테스트 동작 보존)
    with_image = [p for p in candidates if p.image_url]
    if with_image:
        candidates = with_image

    # 3) 하드 제약(예산 가격·데모 속성) 유지 — 가격 숫자비교 보존
    passing = [p for p in candidates if hard_constraint_match(p, hard_constraints) > 0]
    if passing:
        candidates = passing

    # 4) 태그 모순 필터 — 사용자 요구 태그의 반대극만 가진 상품 제외(없으면 소프트 통과)
    required = required_tags(query)
    tag_pass = [p for p in candidates if tag_constraint_ok(p.tags or [], required)]
    if tag_pass:
        candidates = tag_pass

    # 5) 점수 = 키워드 적합도 + 태그 부합 가점 → 기존 trade-off 랭킹 (후보는 BM25가 확보)
    scored = []
    for p in candidates:
        rel = text_relevance(p, query)
        if required and p.tags:
            rel = min(1.0, rel + 0.1 * len(set(p.tags) & set(required)))
        score, matched, weak = compute_product_score(
            p, query, hard_constraints, soft_preferences, topic_labels, avoidances, text_rel=rel
        )
        scored.append(ScoredProduct(product=p, score=score, matched=matched, weak=weak,
                                    bucket=assign_bucket(p), relevance=rel))
    ranked = apply_diversity_rerank(sorted(scored, key=lambda x: x.score, reverse=True))

    if not diversify_by_tradeoff:
        return ranked[:top_k]
    return select_tradeoff_set(ranked, top_k, diagnostic_anchor)


def apply_diversity_rerank(ranked: list[ScoredProduct]) -> list[ScoredProduct]:
    """finalScore의 diversityScore(0.05) 항 구현 (spec §14.2) — MMR식 greedy.
    이미 뽑힌 상위 후보와 브랜드/버킷이 겹치면 0.05 한도 내에서 점수를 깎아
    같은 브랜드·같은 trade-off 방향이 결과를 독점하지 않게 한다."""
    result: list[ScoredProduct] = []
    remaining = list(ranked)
    seen_brands: set[str] = set()
    seen_buckets: set[str] = set()
    while remaining:
        best, best_adj = None, float("-inf")
        for sp in remaining:
            penalty = 0.0
            if sp.product.brand and sp.product.brand in seen_brands:
                penalty += 0.03
            if sp.bucket in seen_buckets:
                penalty += 0.02
            adj = sp.score - penalty
            if adj > best_adj:
                best, best_adj = sp, adj
        result.append(best)
        remaining.remove(best)
        if best.product.brand:
            seen_brands.add(best.product.brand)
        seen_buckets.add(best.bucket)
    return result


def select_tradeoff_set(
    ranked: list[ScoredProduct],
    top_k: int = 3,
    diagnostic_anchor: str | None = None,
) -> list[ScoredProduct]:
    """Pick top candidates from distinct trade-off buckets so the set deliberately
    surfaces tensions (price vs trust vs distinctiveness) that elicit hidden intentions.

    diagnostic_anchor가 주어지면, 그 가설을 검증하는 진단 후보가 결과에 반드시
    포함되게 한다 — 단 슬롯을 추가로 뺏지 않고 **가장 약한 멤버와 교체**한다.
    이렇게 해야 핵심 trade-off 3종(저가/신뢰/프리미엄) 다양성을 유지하면서도
    추천을 active learning의 질의로 쓸 수 있다 (hidden intention 강화 ⓐ)."""
    # 0) 질의 적합도 floor — 관련도 낮은 상품이 trade-off 버킷을 채우지 않게 한다.
    #    관련 상품이 하나도 없으면(우리가 안 가진 카테고리 등) 점수 상위로 폴백해 빈 응답을 막는다.
    top_rel = max((sp.relevance for sp in ranked), default=0.0)
    floor = max(REL_FLOOR_MIN, top_rel * REL_FLOOR_RATIO)
    pool = [sp for sp in ranked if sp.relevance >= floor] or ranked[:top_k]

    # 1) 버킷 다양성 기준으로 top_k 선정
    chosen: list[ScoredProduct] = []
    used_buckets: set[str] = set()
    for sp in pool:
        if sp.bucket not in used_buckets:
            chosen.append(sp)
            used_buckets.add(sp.bucket)
        if len(chosen) >= top_k:
            break
    for sp in pool:  # 버킷이 부족하면 점수순으로 채움
        if len(chosen) >= top_k:
            break
        if sp not in chosen:
            chosen.append(sp)

    # 2) 진단 후보가 이미 포함됐으면 태그만, 아니면 가장 약한 멤버와 교체
    rule = PROBE_RULES.get(diagnostic_anchor or "")
    if rule is not None:
        in_set = next((sp for sp in chosen if rule(sp.product)), None)
        if in_set is not None:
            in_set.probe_anchor = diagnostic_anchor
        else:
            probe = next((sp for sp in pool if rule(sp.product) and sp not in chosen), None)
            if probe is not None:
                weakest = min(chosen, key=lambda x: x.score)
                chosen[chosen.index(weakest)] = probe
                probe.probe_anchor = diagnostic_anchor
    return chosen

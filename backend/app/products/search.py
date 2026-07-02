"""Keyword search + scoring + trade-off sampler (spec §14, §29)."""
from dataclasses import dataclass

from sqlalchemy.orm import Session as DbSession

from app.db import models
from app.products import search_index
from app.products.scoring import compute_product_score, hard_constraint_match, price_in_range, text_relevance
from app.products.tag_filter import required_tags, tag_constraint_ok


@dataclass
class ScoredProduct:
    product: models.Product
    score: float
    bucket: str = "balanced"
    relevance: float = 0.0  # 질의 적합도(text_relevance) — trade-off floor 게이트에 사용


# 질의 적합도 하한 — trade-off 다양화가 관련 없는 상품을 버킷에 채우는 것을 막는다 (§14.3 보강).
# detect_category 하드필터에 의존하지 않고, 사용자의 실제 발화↔제목 적합도로 거른다.
# 절대 임계가 아니라 "이번 질의의 최고 적합도 대비 상대값"을 쓴다 — 대화체 질의
# ("나 맥북 사고 싶어, 지금 고장났음")는 불용어가 token_score를 희석해 적합도가 통째로
# 낮아지므로, 고정 임계는 관련 상품까지 잘라낸다(→ 빈 풀 폴백 → 오프도메인 누수). (2026-06-16)


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
    price_min: int | None = None,
    price_max: int | None = None,
    top_k: int = 3,
    return_pool: bool = False,
    pool_size: int = 15,
) -> list[ScoredProduct]:
    # 1) retrieve — 의미 임베딩 우선, 실패/비활성(mock·테스트) 시 BM25(FTS5)로 폴백.
    #    임베딩이 의미를 보고(예: "운동용 이어폰"↔"러닝 이어버드"), BM25는 글자 trigram만 본다.
    from app.products import embeddings

    # 임베딩 retrieve는 (id, 코사인 유사도)를 받아 유사도를 랭킹에 반영한다.
    # 비활성/미로드(mock·테스트) 시 BM25 폴백 — 그땐 유사도 없음(sim_by_id 빈 dict).
    sim_by_id: dict[str, float] = {}
    scored_ids = embeddings.retrieve_scored(query, n=200)
    if scored_ids is not None:
        sim_by_id = {pid: sim for pid, sim in scored_ids}
        ids = [pid for pid, _ in scored_ids]
    else:
        ids = search_index.retrieve(db, query, n=200)
    if ids:
        pm = {p.id: p for p in db.query(models.Product).filter(models.Product.id.in_(ids)).all()}
        candidates = [pm[i] for i in ids if i in pm]
        if not candidates:  # retrieve id가 DB와 불일치(재시드/스테일 캐시) → 빈 추천 방지, 전체 폴백
            candidates = db.query(models.Product).all()
        # 카테고리 하드필터 제거(2026-06-23): detect_category가 발화 속 동반 언급
        # (예: "노트북이랑 같이 쓸 모니터")을 잘못 집어, 의미검색이 올린 정답을 지웠다.
        # 카테고리는 임베딩/BM25 의미 적합도 + LLM rerank가 자연히 처리한다.
    else:
        candidates = db.query(models.Product).all()

    # 2) 이미지 있는 상품 우선 (없으면 전체 유지 — 데모/테스트 동작 보존)
    with_image = [p for p in candidates if p.image_url]
    if with_image:
        candidates = with_image

    # 3) 하드 제약 — 데모 속성(hard_constraint_match) + 구조화 예산(price_in_range, 산수)
    passing = [p for p in candidates
               if hard_constraint_match(p, hard_constraints) > 0
               and price_in_range(p, price_min, price_max)]
    if passing:
        candidates = passing

    # 4) 태그 모순 필터 — 사용자 요구 태그의 반대극만 가진 상품 제외(없으면 소프트 통과)
    required = required_tags(query)
    tag_pass = [p for p in candidates if tag_constraint_ok(p.tags or [], required)]
    if tag_pass:
        candidates = tag_pass

    # 5) 점수 = 질의 적합도(임베딩 유사도 우선) + 태그 가점. 랭킹은 value-blind(2026-07-01):
    #    가치·의도는 추천을 강제하지 않고 피드백에서 passive하게 추론한다. 임베딩 없으면(mock) 키워드 적합도.
    scored = []
    for p in candidates:
        sim = sim_by_id.get(p.id)
        rel = sim if sim is not None else text_relevance(p, query)
        if required and p.tags:
            rel = min(1.0, rel + 0.1 * len(set(p.tags) & set(required)))
        score = compute_product_score(p, query, text_rel=rel)
        scored.append(ScoredProduct(product=p, score=score,
                                    bucket=assign_bucket(p), relevance=rel))
    ranked = apply_diversity_rerank(sorted(scored, key=lambda x: x.score, reverse=True))

    if return_pool:  # LLM rerank용 상위 후보 풀(점수순). 노출 셋 확정은 rerank(LLM)가 한다.
        return ranked[:pool_size]
    return ranked[:top_k]


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


# select_tradeoff_set은 2026-07-02 제거 — 노출 셋 확정은 rerank(LLM)가 한다.
# 셋의 대비(강점이 서로 다른 3개 = 수동 관측 도구)는 rerank 프롬프트의 구성 원칙으로 이동,
# mock rerank는 결정론 priceCue 스프레드로 같은 계약을 지킨다. 옛 버킷 규칙은 아마존 풀에서
# 88%가 단일 버킷(novel_or_distinctive)으로 형해화됐고, 희소 버킷 후보를 rerank 순위 깊은
# 곳에서 승격시켜 제약 위반품(유선 이어폰)을 노출시키는 부작용만 남겼다.
# assign_bucket/bucket은 풀 단계 MMR(apply_diversity_rerank)용으로만 유지.

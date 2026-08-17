"""Product retrieval: embedding/BM25 retrieve → filters → value-blind relevance rank.
노출 셋 확정(제약 집행 + 보완적 3개 구성)은 recommender의 LLM rerank가 한다 (spec §14, §29)."""
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
    bucket: str = "balanced"  # apply_diversity_rerank의 브랜드/버킷 중복 감점에 사용


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


def blend_relevance(lex: float, sim: float | None, alpha: float) -> float:
    """하이브리드 적합도 — rel = α·어휘 + (1-α)·코사인 (2026-07-06).

    두 신호 모두 [0,1]이라 정규화 없이 섞는다 (KGGen식 raw BM25 합산의 스케일 문제 없음).
    어휘 팔(text_relevance)은 타입 명사·카테고리명 정확 일치에 강해, dense 검색의 타입
    취약성(Sciavolino et al. EMNLP'21 — F2 크로스 카테고리 오염)을 보정한다.
    α=0 → 코사인 단독(기존 동작) / sim 없음(임베딩 비활성·mock) → 어휘 단독(기존 폴백)."""
    if sim is None:
        return lex
    if alpha <= 0:
        return sim
    return alpha * lex + (1 - alpha) * sim


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
    alpha: float | None = None,
) -> list[ScoredProduct]:
    # 1) retrieve — 의미 임베딩 우선, 실패/비활성(mock·테스트) 시 BM25(FTS5)로 폴백.
    #    임베딩이 의미를 보고(예: "운동용 이어폰"↔"러닝 이어버드"), BM25는 글자 trigram만 본다.
    from app.core.config import settings
    from app.products import embeddings

    if alpha is None:
        alpha = settings.hybrid_alpha

    # 임베딩 retrieve는 (id, 코사인 유사도)를 받아 유사도를 랭킹에 반영한다.
    # 비활성/미로드(mock·테스트) 시 BM25 폴백 — 그땐 유사도 없음(sim_by_id 빈 dict).
    # α>0(하이브리드): 후보 = 임베딩 top-200 ∪ BM25 top-200 — 어휘로만 잡히는 정답
    # (정확한 카테고리명·속성어 일치)이 임베딩 컷에서 탈락하지 않게 한다.
    sim_by_id: dict[str, float] = {}
    bm25_ids: list[str] = search_index.retrieve(db, query, n=200) if alpha > 0 else []
    scored_ids = (
        embeddings.retrieve_scored(query, n=200, include_ids=set(bm25_ids))
        if bm25_ids else embeddings.retrieve_scored(query, n=200)  # α=0: 기존 호출 그대로
    )
    if scored_ids is not None:
        sim_by_id = {pid: sim for pid, sim in scored_ids}
        ids = [pid for pid, _ in scored_ids]  # 임베딩 top-200 순 + (union 시) BM25-only 후미
    else:
        ids = bm25_ids or search_index.retrieve(db, query, n=200)
    if ids:
        pm = {p.id: p for p in db.query(models.Product).filter(models.Product.id.in_(ids)).all()}
        candidates = [pm[i] for i in ids if i in pm]
    else:
        candidates = []
    # 카테고리 하드필터 (2026-08-18 복원): category 인자는 이제 발화 추측(detect_category,
    # 2026-06-23 제거 사유)이 아니라 **세션의 과제 카테고리(참가자가 고른 DB 사실)**다.
    # 검색은 절대 이 카테고리를 넘지 않는다 — 전역 임베딩 top-200이 타 카테고리로 쏠리면
    # ('사무실용 편한 바지' → 사무용 의자 5개, 라이브 실측) 그대로 풀에 들어가기 때문.
    # 부족해도 타 카테고리로 채우지 않고, 해당 카테고리 전체에서 다시 고른다.
    if category:
        in_cat = [p for p in candidates if p.category == category]
        if not in_cat:
            in_cat = db.query(models.Product).filter(models.Product.category == category).all()
        candidates = in_cat
    elif not candidates:  # category 미지정(자유 대화·데모) — 기존 전체 폴백 유지
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

    # 5) 점수 = 질의 적합도(blend_relevance: α·어휘 + (1-α)·코사인) + 태그 가점.
    #    랭킹은 value-blind(2026-07-01): 가치·의도는 추천을 강제하지 않고 피드백에서
    #    passive하게 추론한다. α=0이면 코사인 단독(기존), 임베딩 없으면(mock) 어휘 단독.
    scored = []
    for p in candidates:
        sim = sim_by_id.get(p.id)
        lex = text_relevance(p, query) if (sim is None or alpha > 0) else 0.0
        rel = blend_relevance(lex, sim, alpha)
        if required and p.tags:
            rel = min(1.0, rel + 0.1 * len(set(p.tags) & set(required)))
        score = compute_product_score(p, query, text_rel=rel)
        scored.append(ScoredProduct(product=p, score=score, bucket=assign_bucket(p)))
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

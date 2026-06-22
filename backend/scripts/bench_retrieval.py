"""BM25(FTS5 trigram) vs OpenAI embedding retrieval — side-by-side on our catalog.

Single variable changed: retrieval method. Both sides index the SAME Korean product
text (title + tags + description + category) and the SAME Korean query — no translation.
Prints top-K from each method so we can eyeball which surfaces more sensible products.

Run from backend/:  PYTHONPATH=. .venv/bin/python scripts/bench_retrieval.py
"""
import json
import sys

from app.core.config import BACKEND_DIR
from app.db.database import SessionLocal
from app.db import models
from app.products import search_index, embeddings

TOP_K = 6

# LLM 생성 검색용 서술 (scripts/generate_product_descriptions.py 산출)
_DESC_PATH = BACKEND_DIR / "seed_naver" / "product_descriptions.json"
_GEN_DESC = json.loads(_DESC_PATH.read_text(encoding="utf-8")) if _DESC_PATH.exists() else {}

# 실제 스터디에서 나올 법한 질의들 (한국어, 대화체 포함)
QUERIES = [
    "운동할 때 쓸 수 있는 가성비 좋은 무선 이어폰",
    "선물로 줄 브랜드 있는 이어폰",
    "조용한 노이즈캔슬링 이어폰",
    "러닝할 때 흘러내리지 않는 이어폰",
]


def product_doc(p: models.Product) -> str:
    """임베딩/BM25 텍스트. 생성 서술(있으면)을 포함해 빈약한 제목을 보강."""
    tags = " ".join(p.tags or [])
    gen = _GEN_DESC.get(p.id, "")
    cat_path = (p.attributes or {}).get("categoryPath", "")
    return f"{p.title or ''} {gen} {tags} {cat_path} {p.category or ''}".strip()


def bm25_topk(db, query: str, k: int) -> list[str]:
    return search_index.retrieve(db, query, n=k, category=None)


def embed_topk(db, query: str, products: list, k: int) -> list[str]:
    qv = embeddings.query_vector(query)
    if qv is None:
        return []
    scored = []
    for p in products:
        pv = embeddings.product_vector(p.id)
        if pv is not None:
            scored.append((embeddings.cosine(qv, pv), p.id))
    scored.sort(reverse=True)
    return [pid for _, pid in scored[:k]]


def main() -> None:
    db = SessionLocal()
    try:
        if not embeddings.enabled():
            print("✗ embeddings 비활성 — VC_LLM_PROVIDER != mock 이고 OPENAI_API_KEY 필요")
            sys.exit(1)

        products = db.query(models.Product).all()
        title_by_id = {p.id: p.title for p in products}
        print(f"상품 {len(products)}개 임베딩 생성 중 (OpenAI 3-small, 1회)...")

        # embeddings.ensure_product_vectors는 "title category brand"만 씀 →
        # BM25와 같은 텍스트(태그·설명 포함)로 맞추기 위해 직접 임베딩한다.
        items = [(p.id, product_doc(p)) for p in products]
        vecs = embeddings._embed([t for _, t in items])
        if vecs is None:
            print("✗ 상품 임베딩 실패")
            sys.exit(1)
        embeddings._product_vectors.update({pid: v for (pid, _), v in zip(items, vecs)})
        embeddings._loaded = True
        print(f"  완료 ({len(vecs)}개 벡터)\n")

        # FTS 인덱스 보장
        search_index.build_index(db)

        for q in QUERIES:
            print("=" * 78)
            print(f"질의: {q}")
            print("-" * 78)
            bm = bm25_topk(db, q, TOP_K)
            em = embed_topk(db, q, products, TOP_K)
            print(f"{'BM25 trigram':<38} | {'OpenAI 임베딩':<38}")
            print(f"{'-'*38} | {'-'*38}")
            for i in range(TOP_K):
                left = title_by_id.get(bm[i], "")[:36] if i < len(bm) else ""
                right = title_by_id.get(em[i], "")[:36] if i < len(em) else ""
                print(f"{left:<38} | {right:<38}")
            print()
    finally:
        db.close()


if __name__ == "__main__":
    main()

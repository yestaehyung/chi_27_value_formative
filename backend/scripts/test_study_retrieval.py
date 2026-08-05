"""본실험 3과제 카테고리의 검색 품질 점검 (2026-07-28).

새로 넣은 카테고리(책상·데스크체어)가 실제로 검색되는지, 그리고 과제 간 누수가 없는지를
본다. 검사하는 것은 두 가지다:

  ① 적중  — 해당 과제 질의가 그 카테고리 상품을 올리는가
  ② 누수  — 다른 과제 카테고리가 섞여 들어오는가 (예: 책상 질의에 스피커)

②가 중요한 이유: 본실험은 3과제 within-subjects다. 한 과제의 후보 풀에 다른 과제 상품이
섞이면 그 자체가 통제되지 않은 변인이고, 참가자가 "왜 이게 나오지" 하고 이탈한다.

임베딩 캐시가 로드돼야 의미검색이 돈다 — 없으면 BM25(FTS5)로 폴백하므로 결과가 달라진다.
어느 경로로 돌았는지 함께 출력한다.

  cd backend && PYTHONPATH=. .venv/bin/python scripts/test_study_retrieval.py
"""
import asyncio
import collections
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("VC_SEED_DIR", str(BACKEND / "seed_amazon"))
os.environ.setdefault("VC_DB_PATH", str(BACKEND / "amazon_ko.db"))

from app.db.database import SessionLocal  # noqa: E402
from app.db import models  # noqa: E402
from app.products import embeddings  # noqa: E402
from app.products.search import search_products  # noqa: E402

#: (질의, 기대 카테고리) — 과제별 대표 질의. 자연스러운 한국어 발화 형태로 둔다.
CASES: list[tuple[str, set[str]]] = [
    ("재택근무용 책상 추천해줘", {"책상"}),
    ("높이 조절되는 스탠딩 데스크", {"책상"}),
    ("좁은 방에 들어가는 작은 책상", {"책상"}),
    ("오래 앉아도 허리 안 아픈 의자", {"데스크체어"}),
    ("메쉬 소재 사무용 의자", {"데스크체어"}),
    ("캠핑 갈 때 쓸 방수 블루투스 스피커", {"블루투스 스피커"}),
    ("음질 좋은 휴대용 스피커", {"블루투스 스피커"}),
    ("여름에 입을 시원한 반팔 티셔츠", {"티셔츠"}),
    ("무난한 기본 티셔츠", {"티셔츠"}),
    # 경계 사례 — 책상과 의자는 한 과제라 서로 섞여도 무방하지만, 어느 쪽이 올라오는지 본다.
    ("홈오피스 꾸미려는데 뭐가 좋을까", {"책상", "데스크체어"}),
]

POOL = 15   # 리랭커에 넘어가는 후보 수와 같은 크기로 본다 (recommender는 30을 쓰지만
            # 여기서는 상위 적중률을 보는 게 목적이라 좁게 잡는다)


def main() -> None:
    db = SessionLocal()
    try:
        products = db.query(models.Product).all()
        by_cat = collections.Counter(p.category for p in products)
        print(f"DB 상품 {len(products):,}개 · 카테고리 {len(by_cat)}종")
        print("  " + " · ".join(f"{c}={n:,}" for c, n in by_cat.most_common(8)))

        embeddings.ensure_product_vectors(products)
        mode = "임베딩(의미검색)" if embeddings.loaded() else "BM25 폴백(임베딩 미로드)"
        print(f"검색 경로: {mode}\n")

        hits = 0
        for query, expect in CASES:
            pool = search_products(db, query, category=None, hard_constraints=[],
                                   return_pool=True, pool_size=POOL)
            cats = collections.Counter(sp.product.category for sp in pool)
            n_ok = sum(n for c, n in cats.items() if c in expect)
            ok = n_ok >= POOL // 2
            hits += ok
            top = pool[0].product if pool else None
            print(f"{'OK ' if ok else '실패'} {query}")
            print(f"     기대 {'/'.join(sorted(expect))} — 상위{POOL} 중 {n_ok}개 적중")
            print(f"     분포: " + " · ".join(f"{c}={n}" for c, n in cats.most_common()))
            if top:
                print(f"     1위: [{top.category}] {top.title[:52]}")
            print()
        print(f"=== {hits}/{len(CASES)} 통과 (상위{POOL}의 절반 이상이 기대 카테고리) ===")
    finally:
        db.close()


if __name__ == "__main__":
    main()

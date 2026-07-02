"""임베딩 retrieval 품질 진단 — 시나리오별 쿼리(발화+카테고리)로 top-N을 뽑아
카테고리 앵커가 얼마나 잘 되는지(오프카테고리 누수)를 측정한다.

value-blind 랭킹(2026-07-01) 이후 retrieve 품질이 후보 풀 품질의 거의 전부이므로,
임베딩 텍스트/쿼리 구성을 바꿀 때 before/after를 재보는 **재사용 진단 도구**다.

  cd backend && PYTHONPATH=. .venv/bin/python scripts/diag_retrieval_quality.py

VC_SEED_DIR/VC_DB_PATH 기본 seed_amazon/amazon_ko.db (실행 서버와 동일 풀).
임베딩 활성 필요(provider!=mock + OPENAI_API_KEY) — 쿼리 5개 임베딩 호출.
"""
import os
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("VC_SEED_DIR", str(BACKEND / "seed_amazon"))
os.environ.setdefault("VC_DB_PATH", str(BACKEND / "amazon_ko.db"))

from app.products import embeddings  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db import models  # noqa: E402

# (발화, 카테고리 토큰=타깃) — 실제 시스템 쿼리 = 발화 + 시나리오 카테고리
CASES = [
    ("출장이랑 여행 다닐 때 들고 쓸 가벼운 노트북 찾고 있어요", "노트북"),
    ("운동 좋아하는 친구에게 줄 무선 이어폰 찾고 있어요", "무선이어폰"),
    ("남들과 잘 안 겹치는 원피스 찾고 있어요", "원피스"),
    ("처음 사보는데 그림 그리기 좋은 태블릿 찾아요", "태블릿"),
    ("몇 년 입을 겨울 코트 신중하게 고르고 싶어요", "코트"),
]
N = 50
POOL = 15


def main():
    db = SessionLocal()
    products = db.query(models.Product).all()
    embeddings.ensure_product_vectors(products)
    if not embeddings.enabled() or not embeddings.loaded():
        print("embeddings 비활성/미로드 (provider=mock 이거나 OPENAI_API_KEY 없음)")
        return
    pm = {p.id: p for p in products}
    print(f"pool={len(products)}  N={N}  rerank_pool=top-{POOL}\n")
    print(f"{'타깃':8} {'top1':>6} {'타깃@풀':>9} {'첫누수':>6}  top-50 분포")
    for utt, cat in CASES:
        q = f"{utt} {cat}"
        scored = embeddings.retrieve_scored(q, n=N)
        target_pool = sum(1 for pid, _ in scored[:POOL] if pm[pid].category == cat)
        first_leak = next((r for r, (pid, _) in enumerate(scored, 1) if pm[pid].category != cat), None)
        dist = Counter(pm[pid].category or "?" for pid, _ in scored)
        print(f"{cat:8} {scored[0][1]:.3f} {target_pool:>6}/{POOL} {str(first_leak):>6}  {dict(dist.most_common())}")


if __name__ == "__main__":
    main()

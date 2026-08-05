"""상품 벡터 캐시 재생성 — seed_dir/product_vectors.json.gz.

풀을 바꾼 뒤(증보·정리) 마지막에 한 번 돌린다. `embeddings.ensure_product_vectors`가
증분이라 캐시에 있는 id는 재사용하고 새 id만 임베딩하며, 현재 상품 집합에 없는 벡터는
prune해 다시 쓴다. 서버를 띄우지 않고 이 작업만 하기 위한 스크립트다
(서버 기동은 DB 시딩·FTS 인덱스까지 함께 돌아 무겁다).

임베딩은 OpenAI로 나간다(embeddings.py에 엔드포인트 고정) — SDS 서버는 생성 모델만
서빙하므로 여기에는 쓸 수 없다. 차원이 다르면 기존 캐시와 호환되지 않아 전량
재임베딩이 되므로 모델을 바꾸지 않는다.

  cd backend && VC_SEED_DIR=seed_amazon PYTHONPATH=. .venv/bin/python scripts/rebuild_vectors.py
"""
import gzip
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
# DB를 건드리지 않는다 — 시드 파일만 읽어 벡터를 만든다.
os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_vec_"), "x.db"))
os.environ.setdefault("VC_SEED_DIR", "seed_amazon")

logging.basicConfig(level=logging.INFO, format="%(message)s")

from app.core.config import settings  # noqa: E402
from app.products import embeddings  # noqa: E402


class P:
    """embeddings._product_text가 기대하는 최소 형태의 상품 객체."""

    def __init__(self, d: dict):
        self.id = d["id"]
        self.title = d.get("title") or ""
        self.category = d.get("category")
        self.description = d.get("description") or ""
        self.tags = d.get("tags") or []
        self.attributes = d.get("attributes") or {}
        self.brand = d.get("brand")
        self.price = d.get("price")


def main() -> None:
    seed = settings.seed_dir
    products = [P(d) for d in json.loads((seed / "products.json").read_text(encoding="utf-8"))]
    cache = seed / "product_vectors.json.gz"
    before = 0
    if cache.exists():
        before = len(json.loads(gzip.decompress(cache.read_bytes()).decode("utf-8")))

    if not embeddings.enabled():
        print("임베딩이 비활성이다 — OPENAI_API_KEY / VC_EMBEDDINGS 설정을 확인하라.")
        raise SystemExit(1)

    print(f"seed_dir={seed}\n상품 {len(products):,}개 · 기존 캐시 {before:,}개 → 임베딩 시작")
    embeddings.ensure_product_vectors(products)

    after = json.loads(gzip.decompress(cache.read_bytes()).decode("utf-8"))
    size_mb = cache.stat().st_size / 1024 ** 2
    print(f"\n완료 — 벡터 {len(after):,}개 · {size_mb:.1f} MB")
    missing = {p.id for p in products} - set(after)
    if missing:
        # 임베딩 호출이 실패하면 조용히 일부만 남는다 — 반드시 드러나야 한다.
        print(f"⚠️ 벡터가 없는 상품 {len(missing):,}개 — 임베딩 호출이 실패했을 수 있다. 재실행하라.")
        raise SystemExit(1)
    if size_mb >= 95:
        print("⚠️ GitHub 100MB 한도에 근접 — 커밋 전에 풀을 줄여야 한다.")


if __name__ == "__main__":
    main()

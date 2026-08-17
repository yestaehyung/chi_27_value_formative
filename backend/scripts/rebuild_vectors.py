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
import hashlib
import json
import logging
import math
import os
import sys
import tempfile
from datetime import datetime, timezone
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _validate_reusable_cache(seed: Path, cache: Path, seed_manifest: dict) -> None:
    """Do not reuse same-ID vectors built from a different text recipe/model."""
    if not cache.exists() or not seed_manifest.get("embeddingRecipe"):
        return
    vector_manifest_path = seed / "product_vectors.manifest.json"
    if not vector_manifest_path.exists():
        raise RuntimeError(
            f"{cache} exists without product_vectors.manifest.json; refusing to reuse unknown vectors"
        )
    vector_manifest = _read_json(vector_manifest_path)
    expected = {
        "productsSha256": seed_manifest.get("productsSha256"),
        "embeddingRecipe": seed_manifest.get("embeddingRecipe"),
        "embeddingModel": settings.embedding_model,
        "embeddingDimensions": seed_manifest.get("embeddingDimensions"),
    }
    mismatches = {
        key: (value, vector_manifest.get(key))
        for key, value in expected.items()
        if value is not None and vector_manifest.get(key) != value
    }
    if mismatches or vector_manifest.get("vectorCacheSha256") != sha256(cache):
        raise RuntimeError(
            "existing vector cache does not match this seed recipe; move it aside and rerun "
            f"for a fresh cache (mismatches={mismatches})"
        )


def main() -> None:
    seed = settings.seed_dir
    products_path = seed / "products.json"
    products = [P(d) for d in json.loads(products_path.read_text(encoding="utf-8"))]
    cache = seed / "product_vectors.json.gz"
    seed_manifest = _read_json(seed / "manifest.json")
    _validate_reusable_cache(seed, cache, seed_manifest)
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
    product_ids = {p.id for p in products}
    missing = product_ids - set(after)
    extra = set(after) - product_ids
    if missing or extra:
        # 임베딩 호출이 실패하면 조용히 일부만 남는다 — 반드시 드러나야 한다.
        print(
            f"⚠️ 벡터 id 불일치 — missing={len(missing):,}, extra={len(extra):,}; 재실행하라."
        )
        raise SystemExit(1)
    bad_vectors = [
        pid
        for pid, vector in after.items()
        if len(vector) != embeddings._DIM or not all(math.isfinite(value) for value in vector)
    ]
    if bad_vectors:
        print(f"⚠️ 차원/유한성 검증 실패 벡터 {len(bad_vectors):,}개")
        raise SystemExit(1)

    vector_manifest = {
        "schemaVersion": "valuecommit-product-vectors/v1",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "productsSha256": seed_manifest.get("productsSha256") or sha256(products_path),
        "productCount": len(products),
        "vectorCount": len(after),
        "locale": seed_manifest.get("locale"),
        "embeddingRecipe": seed_manifest.get("embeddingRecipe") or "legacy-product-text",
        "embeddingModel": settings.embedding_model,
        "embeddingDimensions": embeddings._DIM,
        "vectorCacheSha256": sha256(cache),
    }
    manifest_path = seed / "product_vectors.manifest.json"
    tmp_manifest = manifest_path.with_suffix(".tmp")
    tmp_manifest.write_text(json.dumps(vector_manifest, indent=2) + "\n", encoding="utf-8")
    tmp_manifest.replace(manifest_path)
    print(f"manifest={manifest_path}")
    if size_mb >= 95:
        print("⚠️ GitHub 100MB 한도에 근접 — 커밋 전에 풀을 줄여야 한다.")


if __name__ == "__main__":
    main()

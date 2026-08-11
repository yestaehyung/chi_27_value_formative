#!/usr/bin/env python3
"""신규 27,596개의 문서 벡터를 embeddingText 벡터로 교체 (2026-08-11).

같은 모델·차원(text-embedding-3-small · 1536)으로 오늘 임베딩이 두 번 돌았다:
  ① rebuild_vectors.py — 폴백 조성(한국어 제목+설명+태그) → seed_amazon_full 캐시
  ② embed_hybrid_amazon_retrieval_profiles.py — 프로필 embeddingText → f32 샤드
②가 설계상 우수하다(시각 특징 포함 — 의류 "빨간 후드티"류 질의에 유리, 8/7 플랜의
검색 전용 조립문). 같은 임베딩 공간이라 문서 벡터만 바꿔치기해도 쿼리와 호환된다.

기존 16,943개 벡터(정체성 조성)는 그대로 두고, 신규 id만 ②로 덮는다.
샤드는 manifest의 sha256으로 검증 후 읽는다. 출력은 기존 캐시 형식
(gzip JSON, 6자리 반올림, 정규화)을 유지한다.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import struct
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
RUN = BACKEND / "data/amazon_retrieval_vectors/hybrid-real-six-adult-v1-20260811"
CACHE = BACKEND / "seed_amazon_full/product_vectors.json.gz"


def load_shards() -> dict[str, list[float]]:
    manifest = json.loads((RUN / "manifest.json").read_text())
    dim = manifest["dimensions"]
    out: dict[str, list[float]] = {}
    for shard in manifest["shards"]:
        vec_path, ids_path = RUN / shard["vectorFile"], RUN / shard["idsFile"]
        for path, key in ((vec_path, "vectorSha256"), (ids_path, "idsSha256")):
            got = hashlib.sha256(path.read_bytes()).hexdigest()
            if got != shard[key]:
                raise SystemExit(f"sha256 불일치: {path.name}")
        ids = json.loads(ids_path.read_text())
        raw = vec_path.read_bytes()
        assert len(raw) == len(ids) * dim * 4, f"{vec_path.name} 크기 불일치"
        for i, pid in enumerate(ids):
            vec = list(struct.unpack_from(f"<{dim}f", raw, i * dim * 4))
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out[pid] = [round(v / norm, 6) for v in vec]
    return out


def main() -> None:
    cache = json.loads(gzip.decompress(CACHE.read_bytes()))
    new_vecs = load_shards()
    before = len(cache)
    missing = [pid for pid in new_vecs if pid not in cache]
    if missing:
        raise SystemExit(f"캐시에 없는 id {len(missing)}개 — 병합 순서 오류")
    cache.update(new_vecs)
    assert len(cache) == before, "교체인데 개수가 변했다"
    CACHE.write_bytes(gzip.compress(json.dumps(cache).encode(), 6))
    print(f"교체 완료 — 총 {len(cache):,}개 중 {len(new_vecs):,}개를 embeddingText 벡터로")
    print(f"캐시 크기: {CACHE.stat().st_size / 2**20:.1f} MiB")


if __name__ == "__main__":
    main()

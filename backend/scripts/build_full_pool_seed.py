#!/usr/bin/env python3
"""본실험 전량 풀 시드 빌드 (2026-08-11) — GitHub를 거치지 않는 볼륨 배포용.

seed_amazon(16,943, git 추적)은 그대로 두고, 여기에 real-six-adult-v3 카탈로그
30,000개 중 **한국어 멀티모달 프로필이 완성된 27,596개**를 합쳐 별도 디렉터리
`seed_amazon_full/`(gitignore)에 시드를 만든다. 총 44,539개 · 10카테고리.

왜 별도 디렉터리인가: 벡터 캐시가 ~200MB로 GitHub 100MB 한도를 넘는다. 이
시드는 git이 아니라 Railway 볼륨(/data/seed_amazon)으로 올라가고, 서버는
VC_SEED_DIR로 그 위치를 가리킨다.

신규 상품의 한국어화: 카탈로그 원문은 영어다. 프로필의 titleToDisplayKo /
descriptionToDisplayKo 를 title/description 으로 쓰고, 원문 제목은
attributes.titleEn 에 보존한다. derivedFeatures 는 tags(정식 라벨 채널 — FTS
색인·임베딩 폴백 텍스트에 들어감)로, visualFeatures 는 attributes 에 둔다.
프로필이 영구 실패한 2,404개는 **제외** — 영어 카드가 참가자에게 노출되는
것을 막는다 (2026-08-11 결정).

신규 상품은 product_profiles.json 에 넣지 않는다 — 임베딩 조성이 상품 단위로
폴백(제목+설명+tags+카테고리, 전부 한국어)하고, rerank 후보도 설명 원문을
쓴다. 검색은 카테고리 필터 안에서 돌므로 산문 교차 누수(2026-07-02 진단)의
영향 범위가 없다.

사용:
    .venv/bin/python scripts/build_full_pool_seed.py            # → seed_amazon_full/
이후 벡터: VC_SEED_DIR=$PWD/seed_amazon_full .venv/bin/python scripts/rebuild_vectors.py
"""
from __future__ import annotations

import gzip
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SEED = BACKEND / "seed_amazon"
OUT = BACKEND / "seed_amazon_full"
CATALOG = BACKEND / "data/amazon_source_catalog/real-six-adult-v3-20260810/products.json"
PROFILE_RUNS = [  # 뒤가 이김 — v2-retry 는 v1 실패분의 재시도
    BACKEND / "data/amazon_retrieval_profiles/hybrid-real-six-adult-v1-20260810/profiles.jsonl",
    BACKEND / "data/amazon_retrieval_profiles/hybrid-real-six-adult-v2-retry-20260811/profiles.jsonl",
]


def load_profiles() -> dict[str, dict]:
    """완성(completed) 프로필만 id→profile 로. 재시도 런이 앞선 실패를 덮는다."""
    done: dict[str, dict] = {}
    for path in PROFILE_RUNS:
        with path.open() as f:
            for line in f:
                rec = json.loads(line)
                if rec.get("status") == "completed" and rec.get("profile"):
                    done[rec["id"]] = rec["profile"]
    return done


def main() -> None:
    existing = json.loads((SEED / "products.json").read_text())
    existing_ids = {p["id"] for p in existing}
    catalog = json.loads(CATALOG.read_text())
    profiles = load_profiles()

    merged, skipped_no_profile, skipped_dup = list(existing), 0, 0
    empty_ko = 0
    for p in catalog:
        if p["id"] in existing_ids:
            skipped_dup += 1
            continue
        prof = profiles.get(p["id"])
        if prof is None:
            skipped_no_profile += 1
            continue
        title_ko = (prof.get("titleToDisplayKo") or "").strip()
        desc_ko = (prof.get("descriptionToDisplayKo") or "").strip()
        if not title_ko:
            empty_ko += 1
            continue
        item = dict(p)
        item["title"] = title_ko
        item["description"] = desc_ko or p.get("description") or ""
        item["tags"] = list(prof.get("derivedFeatures") or [])
        attrs = dict(p.get("attributes") or {})
        attrs["titleEn"] = p.get("title") or ""
        if prof.get("visualFeatures"):
            attrs["visualFeatures"] = list(prof["visualFeatures"])
        item["attributes"] = attrs
        merged.append(item)

    OUT.mkdir(exist_ok=True)
    (OUT / "products.json").write_text(json.dumps(merged, ensure_ascii=False))
    # 프로필/컨셉/시나리오는 기존 것 그대로 — 신규 상품은 runtime 프로필 없이 폴백.
    for name in ("product_profiles.json", "concepts.json", "scenarios.json"):
        shutil.copy2(SEED / name, OUT / name)
    # 벡터 캐시는 기존 16,943개를 출발점으로 복사 — rebuild_vectors 가 신규분만 증분 임베딩.
    shutil.copy2(SEED / "product_vectors.json.gz", OUT / "product_vectors.json.gz")

    cats = Counter(x["category"] for x in merged)
    print(f"병합 완료 → {OUT / 'products.json'}")
    print(f"  기존 {len(existing):,} + 신규 {len(merged) - len(existing):,} = 총 {len(merged):,}")
    print(f"  제외: 프로필 없음 {skipped_no_profile:,} · 한국어 제목 빈값 {empty_ko:,} · 중복 {skipped_dup:,}")
    for k, v in cats.most_common():
        print(f"  {v:6,}  {k}")
    if len(cats) != 10:
        print(f"경고: 카테고리 {len(cats)}개 (10개 기대)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

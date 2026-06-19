"""라벨 병합 — seed/labels/*.json 을 products_stratified.json 에 합쳐 products_stratified.labeled.json 생성.

라벨링 표준(2026-06-17): 구조화 신호 = tags(고정 vocab). attributes 는 메타(categoryId/domain)만
유지하고 라벨러가 뱉은 자유형 attribute 키는 폐기(일관성). description = 라벨러 shortDesc.
사용: .venv/bin/python scripts/merge_labels.py
"""
import glob
import json
import os
from pathlib import Path

SEED = Path(__file__).resolve().parents[1] / "seed"
SRC = SEED / "products_stratified.json"
OUT = SEED / "products_stratified.labeled.json"
KEEP_ATTR = {"categoryId", "domain"}


def main() -> None:
    prods = json.loads(SRC.read_text(encoding="utf-8"))
    labels: dict[str, dict] = {}
    for f in glob.glob(str(SEED / "labels" / "*.json")):
        if os.path.basename(f).startswith(("_", "build_")):
            continue
        for x in json.loads(Path(f).read_text(encoding="utf-8")):
            labels[x["id"]] = x

    merged = 0
    for p in prods:
        a = p.get("attributes") or {}
        p["attributes"] = {k: a[k] for k in KEEP_ATTR if k in a}  # 메타만 (자유키 폐기)
        lb = labels.get(p["id"])
        p["tags"] = (lb.get("tags") if lb else None) or []
        if lb:
            if lb.get("shortDesc"):
                p["description"] = lb["shortDesc"]
            if "offCategory" in lb:  # 라벨러의 카테고리 진위 판정 (정화에서 사용)
                p["offCategory"] = bool(lb["offCategory"])
            merged += 1
    OUT.write_text(json.dumps(prods, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"merged {merged}/{len(prods)} labels → {OUT}")


if __name__ == "__main__":
    main()

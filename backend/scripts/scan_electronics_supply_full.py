"""meta_Electronics 전체를 1회 통과하며 전자 카테고리별 확정 공급량을 센다 (2026-07-28).

왜 전체 통과인가: 부분 스캔 + 바이트 비례 외삽이 블루투스 스피커에서 3,588개를 예측했는데
실제는 2,318개였다(35% 과대). 이 메타 파일은 랜덤 순서가 아니라 카테고리별로 뭉쳐 있어서
앞부분 표본이 대표성을 갖지 못한다. **이 데이터셋에서는 외삽하지 말고 끝까지 읽어야 한다.**

게이트는 본실험 수집과 동일하게 맞춘다 (augment_amazon_main_study.py):
    가격 파싱 가능 + 이미지 존재 + 리뷰 MIN_REVIEWS(기본 10)개 이상
게이트 통과분이 곧 "풀에 넣을 수 있는 수"다.

액세서리 제목 필터도 동일하게 적용한다 — 안 걸면 케이스·거치대가 본품으로 잡혀 공급량이
부풀려진다.

  cd backend && PYTHONPATH=. .venv/bin/python scripts/scan_electronics_supply_full.py
"""
import collections
import json
import os
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
HF = ""
for line in (BACKEND / ".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("HF_API_TOKEN="):
        HF = line.split("=", 1)[1].strip().strip('"')
BASE = "https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/resolve/main/raw/meta_categories"
MIN_REVIEWS = int(os.environ.get("MIN_REVIEWS", "10"))

#: 기존 seed_amazon 전자 카테고리 + 후보군. leaf 노드로 매칭.
KINDS: dict[str, set[str]] = {
    "모니터": {"Monitors", "Computer Monitors"},
    "블루투스 스피커": {"Portable Bluetooth Speakers"},
    "태블릿": {"Tablets"},
    "노트북": {"Traditional Laptops", "2 in 1 Laptops", "Gaming Laptops", "Laptops"},
    "무선이어폰": {"Earbud Headphones", "In-Ear Headphones"},
    "헤드폰": {"Over-Ear Headphones", "On-Ear Headphones"},
    "스마트워치": {"Smartwatches", "Smart Watches"},
    "키보드·마우스": {"Keyboards", "Mice", "Gaming Keyboards", "Gaming Mice"},
    "컴퓨터 스피커": {"Computer Speakers"},
    "웹캠": {"Webcams"},
    "외장 하드·SSD": {"External Hard Drives", "External Solid State Drives"},
}
JUNK = ("case", "cover", "protector", "band", "strap", "replacement", "charger",
        "cable", "adapter", "stand", "mount", "skin", "sticker", "hub", "sleeve",
        "earpad", "ear pad", "cushion", "tips", "hook")


def parse_price(p):
    if not p:
        return None
    try:
        v = float(str(p).replace("$", "").replace(",", "").split()[0])
        return v if v > 0 else None
    except Exception:  # noqa: BLE001
        return None


def has_image(images):
    return any(im.get("large") or im.get("hi_res") or im.get("thumb") for im in (images or []))


def main() -> None:
    node_to_label = {n: lab for lab, nodes in KINDS.items() for n in nodes}
    sub = collections.Counter()       # 노드 매칭 (액세서리 제외 전)
    junked = collections.Counter()    # 제목 필터로 탈락
    priced = collections.Counter()    # 가격+이미지 통과
    final = collections.Counter()     # + 리뷰 게이트 통과
    disc = collections.Counter()      # leaf에 'monitor' 포함된 노드 발견용

    req = urllib.request.Request(f"{BASE}/meta_Electronics.jsonl",
                                 headers={"Authorization": f"Bearer {HF}"} if HF else {})
    resp = urllib.request.urlopen(req, timeout=600)
    n = 0
    for raw in resp:
        n += 1
        try:
            r = json.loads(raw)
        except Exception:  # noqa: BLE001
            continue
        cats = r.get("categories") or []
        if not cats:
            continue
        leaf = str(cats[-1]).strip()
        if "monitor" in leaf.lower():
            disc[leaf] += 1
        label = node_to_label.get(leaf)
        if label is None:
            continue
        sub[label] += 1
        if any(j in (r.get("title") or "").lower() for j in JUNK):
            junked[label] += 1
            continue
        if parse_price(r.get("price")) is None or not has_image(r.get("images")):
            continue
        priced[label] += 1
        if (r.get("rating_number") or 0) >= MIN_REVIEWS:
            final[label] += 1
        if n % 400000 == 0:
            print(f"  {n:,}줄 · 모니터={final['모니터']:,} 스피커={final['블루투스 스피커']:,}", flush=True)

    print(f"\n=== meta_Electronics 전체 {n:,}줄 · 리뷰 게이트 {MIN_REVIEWS}+ ===")
    print(f"{'카테고리':<16}{'노드매칭':>9}{'액세서리':>9}{'가격+이미지':>11}{'최종':>9}")
    for label in sorted(KINDS, key=lambda k: -final[k]):
        print(f"{label:<16}{sub[label]:>9,}{junked[label]:>9,}{priced[label]:>11,}{final[label]:>9,}")
    print(f"\n=== leaf 이름에 'monitor' 포함된 노드 (정의 누락 확인용) ===")
    for leaf, c in disc.most_common(10):
        mark = "★" if leaf in node_to_label else " "
        print(f"  {mark} {leaf[:44]:44} {c:,}")


if __name__ == "__main__":
    main()

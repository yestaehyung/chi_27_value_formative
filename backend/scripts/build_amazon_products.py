"""Amazon Reviews 2023 메타데이터를 스트리밍하며 우리 시나리오와 겹치는 서브카테고리만 뽑아
seed_amazon/products.json 으로 빌드한다 (영어 풀로 전환). 통째 다운로드 X — 충분히 모이면 조기중단.

cue_summary/벡터는 seed_loader/startup이 자동 생성하므로 raw 필드만 만든다.

  cd backend && PYTHONPATH=. .venv/bin/python scripts/build_amazon_products.py            # 기본 N=120/서브카
  cd backend && N_PER=20 LINE_CAP=80000 .venv/bin/python scripts/build_amazon_products.py # 빠른 검증
"""
import json
import os
import re
import shutil
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
OUT = BACKEND / "seed_amazon"
HF = ""
for line in (BACKEND / ".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("HF_API_TOKEN="):
        HF = line.split("=", 1)[1].strip().strip('"')

BASE = "https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/resolve/main/raw/meta_categories"
N_PER = int(os.environ.get("N_PER", "120"))
LINE_CAP = int(os.environ.get("LINE_CAP", "700000"))   # 파일당 최대 스캔 라인(다운로드 상한)

def _leaf_in(cats, names):
    return bool(cats) and str(cats[-1]).strip() in names


# 우리 라벨 → (amazon 파일, 매칭 predicate(title_lower, categories_list)).
# Electronics는 categories 경로(leaf)가 채워져 있어 정밀 매칭 / Fashion은 categories가 비어 title 정규식.
SUBCATS = {
    "Tablet": ("meta_Electronics",
        lambda t, c: _leaf_in(c, {"Tablets"})),
    "Laptop": ("meta_Electronics",
        lambda t, c: "Laptops" in (c or []) and _leaf_in(c, {"Traditional Laptops", "2 in 1 Laptops", "Gaming Laptops", "Laptops"})),
    "Wireless Earphones": ("meta_Electronics",
        lambda t, c: _leaf_in(c, {"Earbud Headphones", "In-Ear Headphones"}) and not any(x in t for x in
            ["skin", "case", "cover", "cushion", "ear pad", "tips", "replacement", "sticker"])),
    # Clothing은 categories가 0% 비어있고 leaf가 정밀("Dresses"/"Coats, Jackets & Vests") → 경로 노드 매칭.
    "Dress": ("meta_Clothing_Shoes_and_Jewelry",
        lambda t, c: "Dresses" in (c or [])),
    "Coat": ("meta_Clothing_Shoes_and_Jewelry",
        lambda t, c: any(n in (c or []) for n in ["Coats, Jackets & Vests", "Jackets & Coats"])),
}
FILES = sorted({v[0] for v in SUBCATS.values()})


def parse_price(p):
    if not p:
        return None
    try:
        v = float(str(p).replace("$", "").replace(",", "").split()[0])
        return round(v) if v > 0 else None
    except Exception:  # noqa: BLE001
        return None


def first_image(images):
    for im in images or []:
        u = im.get("large") or im.get("hi_res") or im.get("thumb")
        if u:
            return u
    return None


def map_item(r, label):
    asin = r.get("parent_asin") or r.get("asin")
    desc = " ".join(r.get("features") or []) + " " + " ".join(r.get("description") or [])
    return {
        "id": f"amz_{asin}",
        "title": (r.get("title") or "").strip(),
        "category": label,
        "brand": r.get("store"),
        "price": parse_price(r.get("price")),
        "deliveryFee": 0,
        "discountRate": 0,
        "rating": r.get("average_rating") or 0,
        "reviewCount": r.get("rating_number") or 0,
        "longTermReviewRatio": 0,                       # Amazon 메타에 없음
        "recentSalesCount": r.get("rating_number") or 0,  # 인기 프록시(리뷰수)
        "sellerName": r.get("store"),
        "sellerGrade": None, "sellerYears": None,
        "imageUrl": first_image(r.get("images")),
        "productUrl": f"https://www.amazon.com/dp/{asin}",
        "attributes": {"asin": asin, "amazonCategory": r.get("main_category")},
        "tags": [],
        "description": desc.strip()[:600],
    }


def stream(url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {HF}"} if HF else {})
    return urllib.request.urlopen(req, timeout=180)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    collected = {label: [] for label in SUBCATS}
    for fname in FILES:
        subs = {lab: spec for lab, spec in SUBCATS.items() if spec[0] == fname}
        if all(len(collected[lab]) >= N_PER for lab in subs):
            continue
        print(f"[stream] {fname} … (목표 {[lab for lab in subs]})", flush=True)
        seen_ids = {p["id"] for lab in collected for p in collected[lab]}
        n_lines = 0
        try:
            for raw in stream(f"{BASE}/{fname}.jsonl"):
                n_lines += 1
                if n_lines > LINE_CAP or all(len(collected[lab]) >= N_PER for lab in subs):
                    break
                try:
                    r = json.loads(raw)
                except Exception:  # noqa: BLE001
                    continue
                price = parse_price(r.get("price"))
                if price is None or not first_image(r.get("images")):
                    continue
                title_l = (r.get("title") or "").lower()
                cats = r.get("categories") or []
                for lab, (_, pred) in subs.items():
                    if len(collected[lab]) >= N_PER:
                        continue
                    if pred(title_l, cats):
                        item = map_item(r, lab)
                        if item["id"] in seen_ids or not item["title"]:
                            break
                        seen_ids.add(item["id"])
                        collected[lab].append(item)
                        break
                if n_lines % 50000 == 0:
                    print(f"   {n_lines} lines · " + " ".join(f"{lab}={len(collected[lab])}" for lab in subs), flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"   stream error: {type(e).__name__} {str(e)[:120]}", flush=True)
        print(f"   done {fname}: " + " ".join(f"{lab}={len(collected[lab])}" for lab in subs), flush=True)

    products = [p for lab in collected for p in collected[lab]]
    (OUT / "products.json").write_text(json.dumps(products, ensure_ascii=False, indent=1), encoding="utf-8")
    # 기동에 필요한 보조 파일: concepts는 복사, scenarios는 5개 영어(카테고리 정합)
    shutil.copy(BACKEND / "seed" / "concepts.json", OUT / "concepts.json")
    scenarios = [
        {"id": "first_time_tablet", "title": "First tablet", "targetCategory": "Tablet", "recipient": "self",
         "context": "first-time purchase (criteria not yet formed)", "offered": True, "studyOrder": 1,
         "initialUserNeed": "I'm buying a tablet for the first time and not sure what to look for.",
         "groundTruthHiddenIntentions": []},
        {"id": "taste_dress", "title": "Taste/identity dress", "targetCategory": "Dress", "recipient": "self",
         "context": "taste / self-expression", "offered": True, "studyOrder": 2,
         "initialUserNeed": "I'm looking for a dress that doesn't look too common.",
         "groundTruthHiddenIntentions": []},
        {"id": "travel_laptop", "title": "Travel/business laptop", "targetCategory": "Laptop", "recipient": "self",
         "context": "specific situation (business trip / travel)", "offered": True, "studyOrder": 3,
         "initialUserNeed": "I need a laptop I can carry around for business trips and travel.",
         "groundTruthHiddenIntentions": []},
        {"id": "gift_earphones", "title": "Gift earphones", "targetCategory": "Wireless Earphones", "recipient": "a friend who likes working out",
         "context": "gift", "offered": True, "studyOrder": 4,
         "initialUserNeed": "I'm looking for wireless earphones as a gift for a friend who works out. I don't know brands well.",
         "groundTruthHiddenIntentions": []},
        {"id": "high_involvement_coat", "title": "High-involvement coat", "targetCategory": "Coat", "recipient": "self",
         "context": "high involvement", "offered": True, "studyOrder": 5,
         "initialUserNeed": "I want to carefully choose a winter coat I can wear for years.",
         "groundTruthHiddenIntentions": []},
    ]
    (OUT / "scenarios.json").write_text(json.dumps(scenarios, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n완료 — {len(products)}개 상품 → {OUT}/products.json")
    from collections import Counter
    print("카테고리별:", dict(Counter(p["category"] for p in products)))
    print("concepts.json 복사 + scenarios.json(영어 5개) 생성.")
    print("기동: VC_SEED_DIR=seed_amazon (벡터는 첫 startup에서 자동 생성)")


if __name__ == "__main__":
    main()

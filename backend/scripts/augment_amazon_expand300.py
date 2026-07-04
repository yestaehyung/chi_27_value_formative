"""seed_amazon 전 카테고리 300 증량 + 남성 의류 쿼터 (2026-07-04).

배경: 실제 formative study 테스트에서 반바지 등 남성 의류 추천이 계속 같은 상품으로
반복 — 원인 중 데이터 측: (1) 카테고리 깊이 120이 얕고 (2) 수집이 여성 편중이었다.
해법: 모든 카테고리를 300으로 올리되, 남녀 공용 의류는 **남성("Men" 경로 노드) 최소
쿼터**를 강제해 수집한다. 아동(Boys/Girls/Baby) 경로는 제외(성인 스터디).

구조: augment_amazon_* 계열의 통합판 — 파일별 KINDS에 per-kind goal(신규 수)과
men_min(남성 버킷)을 두고, 남성 아이템은 남성 버킷 우선, 나머지는 free 버킷.
기존 id는 스킵(재실행 = 증분). 이후 단계는 동일: profiles(증분) → embed(증분,
.json.gz 캐시) → 커밋 → VC_SEED_UPSERT=1 1회.

  cd backend && VC_LLM_PROVIDER=deepseek VC_DEEPSEEK_MODEL=deepseek-v4-flash VC_DEEPSEEK_THINKING=off \
      PYTHONPATH=. .venv/bin/python scripts/augment_amazon_expand300.py
"""
import asyncio
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_aug_"), "x.db"))

from app.llm.provider import LLMMessage, get_provider  # noqa: E402

OUT = BACKEND / "seed_amazon"
HF = ""
for line in (BACKEND / ".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("HF_API_TOKEN="):
        HF = line.split("=", 1)[1].strip().strip('"')
BASE = "https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/resolve/main/raw/meta_categories"

RATE = float(os.environ.get("USDKRW", "1350"))
CONC = int(os.environ.get("CONC", "8"))
MIN_REVIEWS = int(os.environ.get("MIN_REVIEWS", "30"))
CLOTHING_CAP = int(os.environ.get("CLOTHING_CAP", "30000000"))     # 사실상 전체 스캔
ELECTRONICS_CAP = int(os.environ.get("ELECTRONICS_CAP", "12000000"))

CLOTH_JUNK = ("costume", "cosplay", "halloween")
ELEC_JUNK = ("case", "cover", "protector", "band", "strap", "replacement", "charger",
             "cable", "adapter", "stand", "mount", "skin", "sticker", "hub", "sleeve",
             "earpad", "ear pad", "cushion", "tips", "hook")
KID_NODES = {"Boys", "Girls", "Baby", "Baby Boys", "Baby Girls"}

# 파일별: 라벨 → {nodes, goal(신규 목표), men_min(남성 최소; 0=성별 무관)}
# goal은 "현재 수 → 300"의 부족분 (2026-07-04 기준: 의류 120, 코트 180, 전자大 120, 전자新 60).
PLAN: dict[str, dict[str, dict]] = {
    "meta_Clothing_Shoes_and_Jewelry": {
        "티셔츠": {"nodes": {"T-Shirts"}, "goal": 180, "men_min": 90},
        "셔츠·블라우스": {"nodes": {"Blouses & Button-Down Shirts", "Casual Button-Down Shirts", "Dress Shirts"}, "goal": 180, "men_min": 90},
        "청바지": {"nodes": {"Jeans"}, "goal": 180, "men_min": 90},
        "바지": {"nodes": {"Pants", "Casual Pants"}, "goal": 180, "men_min": 90},
        "반바지": {"nodes": {"Shorts", "Cargo Shorts"}, "goal": 180, "men_min": 90},
        "니트·스웨터": {"nodes": {"Sweaters", "Pullovers", "Cardigans"}, "goal": 180, "men_min": 90},
        "후드·맨투맨": {"nodes": {"Fashion Hoodies & Sweatshirts", "Sweatshirts & Hoodies", "Hoodies & Sweatshirts"}, "goal": 180, "men_min": 90},
        "샌들": {"nodes": {"Sandals"}, "goal": 180, "men_min": 90},
        "수영복": {"nodes": {"Swimsuits & Cover Ups", "Swim Trunks", "Board Shorts", "Rash Guards"}, "goal": 180, "men_min": 60},
        "선글라스": {"nodes": {"Sunglasses"}, "goal": 180, "men_min": 90},
        "원피스": {"nodes": {"Dresses"}, "goal": 180, "men_min": 0},
        "스커트": {"nodes": {"Skirts"}, "goal": 180, "men_min": 0},
        "코트": {"nodes": {"Coats, Jackets & Vests", "Jackets & Coats"}, "goal": 120, "men_min": 60},
    },
    "meta_Electronics": {
        "태블릿": {"nodes": {"Tablets"}, "goal": 180, "men_min": 0},
        "노트북": {"nodes": {"Traditional Laptops", "2 in 1 Laptops", "Gaming Laptops", "Laptops"}, "goal": 180, "men_min": 0},
        "무선이어폰": {"nodes": {"Earbud Headphones", "In-Ear Headphones"}, "goal": 180, "men_min": 0},
        "스마트워치": {"nodes": {"Smartwatches", "Smart Watches"}, "goal": 240, "men_min": 0},
        "헤드폰": {"nodes": {"Over-Ear Headphones", "On-Ear Headphones"}, "goal": 240, "men_min": 0},
        "블루투스 스피커": {"nodes": {"Portable Bluetooth Speakers", "Bluetooth Speakers"}, "goal": 240, "men_min": 0},
        "모니터": {"nodes": {"Monitors", "Computer Monitors"}, "goal": 240, "men_min": 0},
        "키보드·마우스": {"nodes": {"Keyboards", "Mice", "Gaming Keyboards", "Gaming Mice"}, "goal": 240, "men_min": 0},
    },
}


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


def map_item(r, label: str) -> dict:
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
        "longTermReviewRatio": 0,
        "recentSalesCount": r.get("rating_number") or 0,
        "sellerName": r.get("store"),
        "sellerGrade": None, "sellerYears": None,
        "imageUrl": first_image(r.get("images")),
        "productUrl": f"https://www.amazon.com/dp/{asin}",
        "attributes": {"asin": asin, "amazonCategory": r.get("main_category")},
        "tags": [],
        "description": desc.strip()[:600],
    }


def collect_file(fname: str, kinds: dict, junk: tuple, cap: int, existing_ids: set) -> list[dict]:
    men = {k: [] for k in kinds}     # 남성 버킷 (men_min)
    free = {k: [] for k in kinds}    # 자유 버킷 (goal - men_min)
    def full(k):
        return len(men[k]) >= kinds[k]["men_min"] and len(free[k]) >= kinds[k]["goal"] - kinds[k]["men_min"]

    req = urllib.request.Request(f"{BASE}/{fname}.jsonl",
                                 headers={"Authorization": f"Bearer {HF}"} if HF else {})
    resp = urllib.request.urlopen(req, timeout=300)
    n = 0
    for raw in resp:
        n += 1
        if n > cap or all(full(k) for k in kinds):
            break
        try:
            r = json.loads(raw)
        except Exception:  # noqa: BLE001
            continue
        if parse_price(r.get("price")) is None or not first_image(r.get("images")):
            continue
        if (r.get("rating_number") or 0) < MIN_REVIEWS:
            continue
        title_l = (r.get("title") or "").lower()
        if any(j in title_l for j in junk):
            continue
        cset = set(r.get("categories") or [])
        if cset & KID_NODES:
            continue
        kind = next((k for k, spec in kinds.items() if cset & spec["nodes"]), None)
        if kind is None or full(kind):
            continue
        item = map_item(r, kind)
        if not item["title"] or item["id"] in existing_ids:
            continue
        is_men = "Men" in cset
        spec = kinds[kind]
        if is_men and len(men[kind]) < spec["men_min"]:
            bucket = men[kind]
        elif len(free[kind]) < spec["goal"] - spec["men_min"]:
            bucket = free[kind]
        else:
            continue
        existing_ids.add(item["id"])
        bucket.append(item)
        if n % 500000 == 0:
            done = sum(len(men[k]) + len(free[k]) for k in kinds)
            total = sum(kinds[k]["goal"] for k in kinds)
            print(f"  [{fname}] {n:,} lines · {done}/{total}", flush=True)
    got = [x for k in kinds for x in men[k] + free[k]]
    print(f"[{fname}] 수집 완료({n:,} lines): " +
          " ".join(f"{k}={len(men[k])+len(free[k])}(남{len(men[k])})" for k in kinds), flush=True)
    return got


async def koreanize_one(provider, sem, p, counter, total):
    msg = ("다음 아마존 상품을 한국 쇼핑앱 스타일로 가공해. JSON만 출력:\n"
           '{"titleFull": "자연스러운 한국어 번역 제목(브랜드·모델 유지)",'
           ' "title": "카드용 간결한 이름 — 브랜드+제품유형+핵심스펙 1~2개, 25자 내외",'
           ' "description": "1~2문장 한국어 설명"}\n'
           f"제목: {p.get('title', '')}\n설명: {(p.get('description') or '')[:400]}")
    out = {}
    async with sem:
        try:
            out = await provider.generate_json([LLMMessage(role="user", content=msg)], task=None)
        except Exception:  # noqa: BLE001
            out = {}
    if isinstance(out, dict) and out.get("title"):
        p["attributes"]["titleEn"] = p["title"]
        p["attributes"]["titleFull"] = str(out.get("titleFull") or out["title"]).strip()
        p["title"] = str(out["title"]).strip()
        if out.get("description"):
            p["description"] = str(out["description"]).strip()[:600]
    if isinstance(p.get("price"), (int, float)) and p["price"]:
        p["price"] = round(p["price"] * RATE / 100) * 100
    counter[0] += 1
    if counter[0] % 100 == 0:
        print(f"  {counter[0]}/{total} koreanized", flush=True)


async def main():
    products = json.loads((OUT / "products.json").read_text(encoding="utf-8"))
    existing_ids = {p["id"] for p in products}
    print(f"기존 풀: {len(products)}개 — 전 카테고리 300 증량 시작 (남성 쿼터 포함)")

    new_items: list[dict] = []
    new_items += collect_file("meta_Clothing_Shoes_and_Jewelry",
                              PLAN["meta_Clothing_Shoes_and_Jewelry"], CLOTH_JUNK,
                              CLOTHING_CAP, existing_ids)
    new_items += collect_file("meta_Electronics",
                              PLAN["meta_Electronics"], ELEC_JUNK,
                              ELECTRONICS_CAP, existing_ids)
    if not new_items:
        print("수집 0개 — 중단"); return

    print(f"번역 시작: {len(new_items)}개")
    provider = get_provider()
    sem = asyncio.Semaphore(CONC)
    counter = [0]
    await asyncio.gather(*(koreanize_one(provider, sem, p, counter, len(new_items)) for p in new_items))

    products.extend(new_items)
    (OUT / "products.json").write_text(json.dumps(products, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n완료 — +{len(new_items)}개 → 총 {len(products)}개")


if __name__ == "__main__":
    asyncio.run(main())

"""seed_amazon 350 복구 소보충 — junk 정리(63개 제거) 후 미달 5종 채움 (2026-07-06).
강화된 junk 필터 적용 (산업/직업용 + 노벨티 조크). 스테이징 없이 직접 병합."""
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

CLOTH_JUNK = ("costume", "cosplay", "halloween", "jewelry making", "charm only", "diy",
              "scrub", "coverall", "hi-vis", "high visibility", "safety", "workwear",
              "work jean", "work pant", "carpenter", "flame resistant", "fire resistant",
              "uniform", "nurse", "medical",
              "funny", "novelty", "gag gift", "sarcas", "joke", "grandpa", "grandma",
              "papa ", " ever shirt", "best dad", "best mom", "retirement gift",
              "for mom", "for dad", "mom gift", "dad gift", "gift for", "mama", "daddy",
              "teacher", "sister", "brother", "daughter", "husband", "wife",
              "girlfriend", "boyfriend", "auntie", "birthday", "anniversary",
              "graduation", "wedding gift", "생일", "기념일", "졸업", "퇴직")
ELEC_JUNK = ("case", "cover", "protector", "band", "strap", "replacement", "charger",
             "cable", "adapter", "stand", "mount", "skin", "sticker", "hub", "sleeve",
             "earpad", "ear pad", "cushion", "tips", "hook")
KID_NODES = {"Boys", "Girls", "Baby", "Baby Boys", "Baby Girls"}

# 파일별: 라벨 → {nodes, goal(신규 목표), men_min(남성 최소; 0=성별 무관)}
# goal은 "현재 수 → 300"의 부족분 (2026-07-04 기준: 의류 120, 코트 180, 전자大 120, 전자新 60).
PLAN: dict[str, dict[str, dict]] = {
    "meta_Clothing_Shoes_and_Jewelry": {
        "티셔츠": {"nodes": {"T-Shirts"}, "goal": 9, "men_min": 0},
        "주얼리": {"nodes": {"Necklaces", "Earrings", "Bracelets", "Rings", "Pendants"}, "goal": 15, "men_min": 0},
        "지갑": {"nodes": {"Wallets", "Wallets, Card Cases & Money Organizers", "Card Cases"}, "goal": 8, "men_min": 0},
        "양말": {"nodes": {"Socks", "Casual Socks", "Athletic Socks", "Dress Socks", "Socks & Hosiery"}, "goal": 4, "men_min": 0, "max_usd": 40},
        "모자·캡": {"nodes": {"Baseball Caps", "Beanies & Knit Hats", "Sun Hats", "Bucket Hats", "Hats & Caps"}, "goal": 7, "men_min": 0, "max_usd": 40},
        "스카프·머플러": {"nodes": {"Scarves", "Fashion Scarves", "Cold Weather Scarves & Wraps", "Scarves & Wraps"}, "goal": 5, "men_min": 0, "max_usd": 40},
    },
    "meta_Home_and_Kitchen": {
        "텀블러·머그": {"nodes": {"Mugs", "Travel Mugs", "Tumblers & Water Glasses", "Insulated Tumblers"}, "goal": 59, "men_min": 0, "max_usd": 40},
        "캔들·디퓨저": {"nodes": {"Candles", "Scented Candles", "Jar Candles", "Essential Oil Diffusers", "Aromatherapy Diffusers"}, "goal": 59, "men_min": 0, "max_usd": 40},
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
    print(f"기존 풀: {len(products)}개 — 350 복구 보충")

    new_items: list[dict] = []
    new_items += collect_file("meta_Clothing_Shoes_and_Jewelry",
                              PLAN["meta_Clothing_Shoes_and_Jewelry"], CLOTH_JUNK,
                              CLOTHING_CAP, existing_ids)
    new_items += collect_file("meta_Home_and_Kitchen", PLAN["meta_Home_and_Kitchen"], CLOTH_JUNK,
                              CLOTHING_CAP, existing_ids)
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

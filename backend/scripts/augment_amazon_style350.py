"""seed_amazon 전 카테고리 350 증량 + 의류 스타일 다양성 쿼터 (2026-07-06).

사용자 요청: "옷의 경우 다양한 스타일이 있어야" + "전 카테고리 최소 350".
의류 13종의 +50은 스타일 버킷(캐주얼/포멀·드레시/스포츠/빈티지·클래식/패턴·프린트,
제목 키워드)로 나눠 수집해 스타일 스펙트럼을 강제하고, 버킷 미달분은 스필오버로
채워 350을 보장한다(스타일은 선호, 총량은 보장). 남성 쿼터·아동 제외·$40 상한
(캐주얼 선물 5종)·액세서리 필터(전자)는 기존 규칙 유지.

  cd backend && VC_LLM_PROVIDER=deepseek VC_DEEPSEEK_MODEL=deepseek-v4-flash VC_DEEPSEEK_THINKING=off \
      PYTHONPATH=. .venv/bin/python scripts/augment_amazon_style350.py
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

GOAL = int(os.environ.get("GOAL", "50"))          # 카테고리당 신규 (300 → 350)
RATE = float(os.environ.get("USDKRW", "1350"))
CONC = int(os.environ.get("CONC", "8"))
MIN_REVIEWS = int(os.environ.get("MIN_REVIEWS", "30"))
CAPS = {"meta_Clothing_Shoes_and_Jewelry": 10000000,
        "meta_Electronics": 12000000,
        "meta_Home_and_Kitchen": 6000000}

# 2026-07-06 보강: 산업/직업용(작업복·스크럽·안전장구)과 노벨티 조크 문구 상품 제외
# (formative 테스트에서 '사수 선물'에 안전 우의·Best Grandpa Ever 티셔츠가 노출된 사고)
CLOTH_JUNK = ("costume", "cosplay", "halloween", "jewelry making", "charm only", "diy",
              "scrub", "coverall", "hi-vis", "high visibility", "safety", "workwear",
              "work jean", "work pant", "carpenter", "flame resistant", "fire resistant",
              "uniform", "nurse", "medical",
              "funny", "novelty", "gag gift", "sarcas", "joke", "grandpa", "grandma",
              "papa ", " ever shirt", "best dad", "best mom", "retirement gift")
ELEC_JUNK = ("case", "cover", "protector", "band", "strap", "replacement", "charger",
             "cable", "adapter", "stand", "mount", "skin", "sticker", "hub", "sleeve",
             "earpad", "ear pad", "cushion", "tips", "hook")
KID_NODES = {"Boys", "Girls", "Baby", "Baby Boys", "Baby Girls"}

# 스타일 버킷 (의류 전용) — 제목 키워드, 버킷당 5개 선호 수집
STYLES: dict[str, tuple] = {
    "casual": ("casual", "everyday", "relaxed"),
    "formal": ("dress ", "formal", "elegant", "office", "business", "dressy"),
    "sport": ("sport", "athletic", "running", "workout", "active", "gym", "performance"),
    "vintage": ("vintage", "retro", "classic"),
    "pattern": ("floral", "print", "pattern", "graphic", "striped", "plaid", "leopard", "tie dye"),
}
STYLE_Q = 5   # 스타일 버킷당
MEN_Q = 15    # 남녀 공용 의류 남성 버킷

CLOTHING_STYLED = {"코트", "원피스", "티셔츠", "셔츠·블라우스", "청바지", "바지", "반바지",
                   "스커트", "니트·스웨터", "후드·맨투맨", "샌들", "수영복", "선글라스"}
WOMEN_ONLY = {"원피스", "스커트"}

PLAN: dict[str, dict[str, dict]] = {
    "meta_Clothing_Shoes_and_Jewelry": {
        "티셔츠": {"nodes": {"T-Shirts"}},
        "셔츠·블라우스": {"nodes": {"Blouses & Button-Down Shirts", "Casual Button-Down Shirts", "Dress Shirts"}},
        "청바지": {"nodes": {"Jeans"}},
        "바지": {"nodes": {"Pants", "Casual Pants"}},
        "반바지": {"nodes": {"Shorts", "Cargo Shorts"}},
        "니트·스웨터": {"nodes": {"Sweaters", "Pullovers", "Cardigans"}},
        "후드·맨투맨": {"nodes": {"Fashion Hoodies & Sweatshirts", "Sweatshirts & Hoodies", "Hoodies & Sweatshirts"}},
        "샌들": {"nodes": {"Sandals"}},
        "수영복": {"nodes": {"Swimsuits & Cover Ups", "Swim Trunks", "Board Shorts", "Rash Guards"}},
        "선글라스": {"nodes": {"Sunglasses"}},
        "원피스": {"nodes": {"Dresses"}},
        "스커트": {"nodes": {"Skirts"}},
        "코트": {"nodes": {"Coats, Jackets & Vests", "Jackets & Coats"}},
        "시계": {"nodes": {"Wrist Watches"}},
        "주얼리": {"nodes": {"Necklaces", "Earrings", "Bracelets", "Rings", "Pendants"}},
        "가방·핸드백": {"nodes": {"Shoulder Bags", "Totes", "Crossbody Bags", "Satchels", "Top-Handle Bags", "Hobo Bags"}},
        "지갑": {"nodes": {"Wallets", "Wallets, Card Cases & Money Organizers", "Card Cases"}},
        "양말": {"nodes": {"Socks", "Casual Socks", "Athletic Socks", "Dress Socks", "Socks & Hosiery"}, "max_usd": 40},
        "모자·캡": {"nodes": {"Baseball Caps", "Beanies & Knit Hats", "Sun Hats", "Bucket Hats", "Hats & Caps"}, "max_usd": 40},
        "스카프·머플러": {"nodes": {"Scarves", "Fashion Scarves", "Cold Weather Scarves & Wraps", "Scarves & Wraps"}, "max_usd": 40},
    },
    "meta_Electronics": {
        "태블릿": {"nodes": {"Tablets"}},
        "노트북": {"nodes": {"Traditional Laptops", "2 in 1 Laptops", "Gaming Laptops", "Laptops"}},
        "무선이어폰": {"nodes": {"Earbud Headphones", "In-Ear Headphones"}},
        "스마트워치": {"nodes": {"Smartwatches", "Smart Watches"}},
        "헤드폰": {"nodes": {"Over-Ear Headphones", "On-Ear Headphones"}},
        "블루투스 스피커": {"nodes": {"Portable Bluetooth Speakers", "Bluetooth Speakers"}},
        "모니터": {"nodes": {"Monitors", "Computer Monitors"}},
        "키보드·마우스": {"nodes": {"Keyboards", "Mice", "Gaming Keyboards", "Gaming Mice"}},
    },
    "meta_Home_and_Kitchen": {
        "텀블러·머그": {"nodes": {"Mugs", "Travel Mugs", "Tumblers & Water Glasses", "Insulated Tumblers"}, "max_usd": 40},
        "캔들·디퓨저": {"nodes": {"Candles", "Scented Candles", "Jar Candles", "Essential Oil Diffusers", "Aromatherapy Diffusers"}, "max_usd": 40},
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


def detect_style(title_l: str) -> str | None:
    for s, kws in STYLES.items():
        if any(k in title_l for k in kws):
            return s
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
    picked = {k: [] for k in kinds}                 # 확정 (men+style+free)
    men_n = {k: 0 for k in kinds}
    style_n = {k: {s: 0 for s in STYLES} for k in kinds}
    spill = {k: [] for k in kinds}                  # 스필오버 (버킷 초과분, 350 보장용)

    def need_more(k):
        return len(picked[k]) < GOAL or len(spill[k]) < GOAL

    req = urllib.request.Request(f"{BASE}/{fname}.jsonl",
                                 headers={"Authorization": f"Bearer {HF}"} if HF else {})
    resp = urllib.request.urlopen(req, timeout=300)
    n = 0
    for raw in resp:
        n += 1
        if n > cap or not any(need_more(k) for k in kinds):
            break
        try:
            r = json.loads(raw)
        except Exception:  # noqa: BLE001
            continue
        price = parse_price(r.get("price"))
        if price is None or not first_image(r.get("images")):
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
        if kind is None:
            continue
        cap_usd = kinds[kind].get("max_usd")
        if cap_usd and price > cap_usd:
            continue
        item = map_item(r, kind)
        if not item["title"] or item["id"] in existing_ids:
            continue

        styled = kind in CLOTHING_STYLED
        men_min = 0 if (not styled or kind in WOMEN_ONLY) else MEN_Q
        is_men = "Men" in cset
        style = detect_style(title_l) if styled else None
        free_cap = GOAL - men_min - (STYLE_Q * len(STYLES) if styled else 0)

        placed = False
        if len(picked[kind]) < GOAL:
            if is_men and men_n[kind] < men_min:
                men_n[kind] += 1; placed = True
            elif style and style_n[kind][style] < STYLE_Q:
                style_n[kind][style] += 1; placed = True
            elif sum(1 for _ in picked[kind]) - men_n[kind] - sum(style_n[kind].values()) < max(free_cap, 0):
                placed = True
        if placed:
            existing_ids.add(item["id"])
            picked[kind].append(item)
        elif len(spill[kind]) < GOAL:
            existing_ids.add(item["id"])
            spill[kind].append(item)
        if n % 1000000 == 0:
            done = sum(len(v) for v in picked.values())
            print(f"  [{fname}] {n:,} lines · picked {done}/{GOAL*len(kinds)}", flush=True)

    out = []
    for k in kinds:
        merged = picked[k] + spill[k][: GOAL - len(picked[k])]   # 스필오버로 350 보장
        out += merged
        if k in CLOTHING_STYLED:
            print(f"  {k}: {len(merged)} (남{men_n[k]}, 스타일 {dict(style_n[k])})", flush=True)
        else:
            print(f"  {k}: {len(merged)}", flush=True)
    print(f"[{fname}] 수집 완료({n:,} lines): 총 {len(out)}", flush=True)
    return out


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
    print(f"기존 풀: {len(products)}개 — 전 카테고리 350 증량 (의류 스타일 버킷)")

    new_items: list[dict] = []
    for fname, kinds in PLAN.items():
        new_items += collect_file(fname, kinds, ELEC_JUNK if fname == "meta_Electronics" else CLOTH_JUNK,
                                  CAPS[fname], existing_ids)
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

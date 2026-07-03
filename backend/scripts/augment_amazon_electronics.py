"""seed_amazon 전자제품 증보 — 스마트워치·헤드폰·스피커·모니터·키보드마우스 (2026-07-03).
전자가 태블릿·노트북·이어폰뿐이라 확장 — 스마트워치는 데모 시나리오(선물 스마트워치)의
도메인이기도 하다. meta_Electronics 스트리밍, 액세서리(케이스·스트랩·충전기) 제목 필터 추가.

augment_amazon_summer.py와 같은 계열(넷째) — Clothing 메타를 스트리밍하며 카테고리
경로 노드로 정밀 필터(제목 정규식 아님), 가격+이미지+리뷰 30+만 수집, 신규만 번역·축약.

파이프라인 정합(중요):
- 레코드 형태는 기존과 동일: title(간결 카드명) / attributes.titleEn / attributes.titleFull /
  USD→KRW 100원 반올림 / category ∈ 5종 전자 라벨.
- 이후 단계: build_product_profiles.py(증분) → 로컬 임베딩 갱신 → 커밋 → VC_SEED_UPSERT=1 1회.
  ※ 프로필을 먼저 만들어야 임베딩 텍스트가 정체성-필드 구성으로 들어간다.

  cd backend && VC_LLM_PROVIDER=deepseek VC_DEEPSEEK_MODEL=deepseek-v4-flash VC_DEEPSEEK_THINKING=off \
      N_EACH=60 LINE_CAP=3000000 PYTHONPATH=. \
      .venv/bin/python scripts/augment_amazon_electronics.py
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

N_EACH = int(os.environ.get("N_EACH", "60"))
LINE_CAP = int(os.environ.get("LINE_CAP", "3000000"))
RATE = float(os.environ.get("USDKRW", "1350"))
CONC = int(os.environ.get("CONC", "8"))
MIN_REVIEWS = int(os.environ.get("MIN_REVIEWS", "30"))

# 전자는 액세서리(케이스·밴드·충전기…)가 본품 카테고리 인근에 다량 섞인다 — 제목으로 제외.
JUNK_HINTS = ("case", "cover", "protector", "band", "strap", "replacement", "charger",
              "cable", "adapter", "stand", "mount", "skin", "sticker", "hub", "sleeve",
              "earpad", "ear pad", "cushion", "tips", "hook")

# 카테고리 경로 노드 매칭 (정밀) — 노드명 변형은 합집합 (없는 노드명은 안 걸릴 뿐).
KINDS: dict[str, dict] = {
    "스마트워치": {"nodes": {"Smartwatches", "Smart Watches"}},
    "헤드폰": {"nodes": {"Over-Ear Headphones", "On-Ear Headphones"}},
    "블루투스 스피커": {"nodes": {"Portable Bluetooth Speakers", "Bluetooth Speakers"}},
    "모니터": {"nodes": {"Monitors", "Computer Monitors"}},
    "키보드·마우스": {"nodes": {"Keyboards", "Mice", "Gaming Keyboards", "Gaming Mice"}},
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


def classify(title_l: str, cats: list) -> str | None:
    if any(j in title_l for j in JUNK_HINTS):
        return None
    cset = set(cats or [])
    for label, spec in KINDS.items():
        if cset & spec["nodes"]:
            return label
    return None


def map_item(r, label: str) -> dict:
    asin = r.get("parent_asin") or r.get("asin")
    desc = " ".join(r.get("features") or []) + " " + " ".join(r.get("description") or [])
    return {
        "id": f"amz_{asin}",
        "title": (r.get("title") or "").strip(),   # 번역 단계에서 교체
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


def collect(existing_ids: set) -> list[dict]:
    got: dict[str, list] = {k: [] for k in KINDS}
    req = urllib.request.Request(f"{BASE}/meta_Electronics.jsonl",
                                 headers={"Authorization": f"Bearer {HF}"} if HF else {})
    resp = urllib.request.urlopen(req, timeout=300)
    n = 0
    for raw in resp:
        n += 1
        if n > LINE_CAP or all(len(v) >= N_EACH for v in got.values()):
            break
        try:
            r = json.loads(raw)
        except Exception:  # noqa: BLE001
            continue
        if parse_price(r.get("price")) is None or not first_image(r.get("images")):
            continue
        if (r.get("rating_number") or 0) < MIN_REVIEWS:
            continue
        kind = classify((r.get("title") or "").lower(), r.get("categories") or [])
        if kind is None or len(got[kind]) >= N_EACH:
            continue
        item = map_item(r, kind)
        if not item["title"] or item["id"] in existing_ids:
            continue
        existing_ids.add(item["id"])
        got[kind].append(item)
        if n % 100000 == 0:
            print(f"  {n:,} lines · " + " ".join(f"{k}={len(v)}" for k, v in got.items()), flush=True)
    print(f"수집 완료({n:,} lines): " + " ".join(f"{k}={len(v)}" for k, v in got.items()), flush=True)
    return [x for v in got.values() for x in v]


async def koreanize_one(provider, sem, p, counter):
    """번역+카드명 축약을 한 호출로 — 기존 필드 규약(titleEn/titleFull/title) 유지."""
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
    if counter[0] % 20 == 0:
        print(f"  {counter[0]} koreanized", flush=True)


async def main():
    products = json.loads((OUT / "products.json").read_text(encoding="utf-8"))
    existing_ids = {p["id"] for p in products}
    print(f"기존 풀: {len(products)}개 — 전자 5종 증보 시작 (각 {N_EACH})")

    new_items = collect(existing_ids)
    if not new_items:
        print("수집 0개 — 중단"); return

    provider = get_provider()
    sem = asyncio.Semaphore(CONC)
    counter = [0]
    await asyncio.gather(*(koreanize_one(provider, sem, p, counter) for p in new_items))

    products.extend(new_items)
    (OUT / "products.json").write_text(json.dumps(products, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n완료 — +{len(new_items)}개 → 총 {len(products)}개 ({OUT}/products.json)")
    print("다음 단계:")
    print("  1) PYTHONPATH=. .venv/bin/python scripts/build_product_profiles.py   # 신규만 증분")
    print("  2) 로컬 임베딩 갱신 → product_vectors.json 커밋 → VC_SEED_UPSERT=1 1회 배포")


if __name__ == "__main__":
    asyncio.run(main())

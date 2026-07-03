"""seed_amazon 여성 아우터 증보 — '여성 울 코트' 공급 격차(1/600, 2026-07-03 진단) 해소.

S5(큰맘 먹고 사는 겨울 코트)에서 여성 참가자가 울을 선호하면 카탈로그 전체에 후보가
1개(Caitefaso)뿐이라 비교 자체가 불가능했다 (시나리오의 hiddenIntentionMechanism이
'후보 비교'인데 비교 대상이 없음). NAVER 풀의 build_womens_outerwear.py(97개)와 같은
계열의 Amazon판 — 여성 코트류를 울 우선으로 추가 샘플링해 기존 600개에 증분한다.

파이프라인 정합(중요):
- 신규 아이템만 번역/축약 (enrich_amazon_korean·shorten_amazon_titles는 전체 대상이라 재실행 금지).
- 레코드 형태는 기존과 동일: title(간결 카드명) / attributes.titleEn(영어 원제) /
  attributes.titleFull(긴 한국어 번역) / USD→KRW 100원 반올림 / category="코트".
- 이후 단계: build_product_profiles.py(증분 — 신규 id만 프로필 생성)를 돌린 뒤 서버를
  재기동하면 ensure_product_vectors가 신규 id만 임베딩한다(기존 600개 캐시 유지).
  ※ 프로필을 먼저 만들어야 임베딩 텍스트가 정체성-필드 구성으로 들어간다.

  cd backend && VC_LLM_PROVIDER=deepseek VC_DEEPSEEK_MODEL=deepseek-v4-flash VC_DEEPSEEK_THINKING=off \
      N_WOOL=40 N_COAT=20 LINE_CAP=1200000 PYTHONPATH=. \
      .venv/bin/python scripts/augment_amazon_womens_outerwear.py
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

N_WOOL = int(os.environ.get("N_WOOL", "40"))      # 울(제목/카테고리에 wool) 여성 코트
N_COAT = int(os.environ.get("N_COAT", "20"))      # 울 아닌 클래식 여성 코트(트렌치·오버코트 등) — 비교 대비군
LINE_CAP = int(os.environ.get("LINE_CAP", "1200000"))
RATE = float(os.environ.get("USDKRW", "1350"))
CONC = int(os.environ.get("CONC", "8"))
MIN_REVIEWS = int(os.environ.get("MIN_REVIEWS", "30"))  # 품질 하한 — 기존 풀과 유사한 신뢰 신호 확보

CLASSIC_HINTS = ("trench", "overcoat", "pea coat", "peacoat", "long coat", "wrap coat", "dress coat")
JUNK_HINTS = ("costume", "cosplay", "halloween")
# 'Wool & Pea Coats' leaf에 faux fur·fleece가 섞여 있음(2026-07-03 스캔) —
# 카테고리 기반 울 판정은 제목의 상반 소재가 없을 때만.
NOT_WOOL_MATERIALS = ("faux fur", "fleece", "down ", "puffer", "leather", "denim")


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
    """여성 코트류를 wool / classic 으로 분류. 해당 없음 → None."""
    if "Women" not in (cats or []):
        return None
    if not any(n in (cats or []) for n in ("Coats, Jackets & Vests", "Jackets & Coats")):
        return None
    if any(j in title_l for j in JUNK_HINTS):
        return None
    if "wool" in title_l:
        return "wool"
    if any("wool" in str(x).lower() for x in cats or []) \
            and not any(m in title_l for m in NOT_WOOL_MATERIALS):
        return "wool"  # Wool & Pea Coats leaf — 상반 소재 명시 없으면 피코트류로 인정
    if any(h in title_l for h in CLASSIC_HINTS):
        return "classic"
    return None


def map_item(r) -> dict:
    asin = r.get("parent_asin") or r.get("asin")
    desc = " ".join(r.get("features") or []) + " " + " ".join(r.get("description") or [])
    return {
        "id": f"amz_{asin}",
        "title": (r.get("title") or "").strip(),   # 번역 단계에서 교체
        "category": "코트",
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
    got = {"wool": [], "classic": []}
    goal = {"wool": N_WOOL, "classic": N_COAT}
    req = urllib.request.Request(f"{BASE}/meta_Clothing_Shoes_and_Jewelry.jsonl",
                                 headers={"Authorization": f"Bearer {HF}"} if HF else {})
    resp = urllib.request.urlopen(req, timeout=300)
    n = 0
    for raw in resp:
        n += 1
        if n > LINE_CAP or all(len(got[k]) >= goal[k] for k in got):
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
        if kind is None or len(got[kind]) >= goal[kind]:
            continue
        item = map_item(r)
        if not item["title"] or item["id"] in existing_ids:
            continue
        existing_ids.add(item["id"])
        got[kind].append(item)
        if n % 100000 == 0:
            print(f"  {n:,} lines · wool={len(got['wool'])} classic={len(got['classic'])}", flush=True)
    print(f"수집 완료({n:,} lines): wool={len(got['wool'])} classic={len(got['classic'])}", flush=True)
    return got["wool"] + got["classic"]


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
    if counter[0] % 10 == 0:
        print(f"  {counter[0]} koreanized", flush=True)


async def main():
    products = json.loads((OUT / "products.json").read_text(encoding="utf-8"))
    existing_ids = {p["id"] for p in products}
    print(f"기존 풀: {len(products)}개 — 여성 아우터 증보 시작 (wool {N_WOOL} + classic {N_COAT})")

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
    print("  2) 서버 재기동 → ensure_product_vectors가 신규 id만 임베딩")


if __name__ == "__main__":
    asyncio.run(main())

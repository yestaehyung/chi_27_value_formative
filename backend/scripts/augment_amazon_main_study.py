"""본실험(main study) 3개 과제 카테고리 증보 — 블루투스 스피커 / 티셔츠 / 홈오피스 책상·데스크체어.

배경: 본실험은 3조건 between-subjects × 3카테고리 within-subjects다. 세 과제의 **풀 깊이가
다르면** 과제 간 차이가 '카테고리 특성' 때문인지 '풀이 얕아서'인지 구분되지 않는다. 그래서
이 스크립트의 핵심 목표는 개수를 늘리는 것이 아니라 **세 과제의 깊이를 같게 맞추는 것**이다.

공급 실측(`scan_study_supply.py`, 2026-07-28, MIN_REVIEWS=10 기준 추정):
    블루투스 스피커  ~3,588   ← 병목. 파일을 끝까지 읽어야 이만큼 나온다.
    티셔츠          ~100,000+ (남아돔)
    홈오피스 책상    ~4,500 / 데스크체어 ~2,700

따라서 **스피커를 먼저 상한까지 수집해 N을 확정하고, 나머지를 N에 맞춘다** (아래 main 참조).
기존 풀에 이미 있는 개수를 차감하므로 재실행해도 목표 총량을 넘지 않는다.

리뷰 게이트는 30이 아니라 **10**이다 (2026-07-28 결정). 30은 인기 상품 편향을 만들어
"덜 알려진 것을 원한다"는 축(TCV Social/Emotional)을 표현할 상품이 풀에서 사라진다 —
숨은 기준을 관측하는 것이 연구 목적이므로 그 축을 죽이면 안 된다. 10이면 유령 리스팅은
여전히 걸러지면서 풀이 22% 커진다.

파이프라인 정합(중요) — augment_amazon_electronics.py와 동일:
- 레코드 형태: title(간결 카드명) / attributes.titleEn / attributes.titleFull /
  USD→KRW 100원 반올림 / category ∈ 아래 KINDS 라벨.
- 이후 단계: build_product_profiles.py(증분) → 임베딩 갱신 → 커밋/배포.
  ※ 프로필을 먼저 만들어야 임베딩 텍스트가 정체성-필드 구성으로 들어간다.

  cd backend && VC_LLM_PROVIDER=deepseek VC_DEEPSEEK_MODEL=deepseek-v4-flash \
      CONC=64 PYTHONPATH=. .venv/bin/python scripts/augment_amazon_main_study.py
"""
import asyncio
import json
import os
import re
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
CONC = int(os.environ.get("CONC", "64"))
MIN_REVIEWS = int(os.environ.get("MIN_REVIEWS", "10"))
#: 스피커 수집 상한. 0이면 무제한(파일 끝까지) — 상한이 곧 세 과제의 공통 목표가 된다.
#: collect()에 넘길 때는 UNLIMITED(-1)로 바꾼다. quotas의 0은 "이미 충족 → 건너뛰기"라는
#: 다른 뜻이므로(2·3단계가 max(목표-기존, 0)으로 그렇게 쓴다) 두 의미를 겹치면 안 된다.
BT_CAP = int(os.environ.get("BT_CAP", "0"))
UNLIMITED = -1
#: 디버그용 줄 제한. 0이면 무제한.
LINE_CAP = int(os.environ.get("LINE_CAP", "0"))

#: 카테고리 → (메타 파일, leaf 노드 집합). leaf(경로 마지막)로만 매칭한다 —
#: 상위 경로로 매칭하면 액세서리 하위노드까지 딸려온다.
KINDS: dict[str, dict] = {
    # "Bluetooth Speakers"는 방어적으로 넣어둔 별칭이었으나 meta_Electronics 40만 줄 스캔에서
    # 0건 — 존재하지 않는 노드다(2026-07-28 측정). 사실상 단일 노드이며 그게 정확한 정의다.
    # 다른 speaker 노드는 다른 제품군이다: Coaxial=자동차 부품, Bookshelf/Floorstanding=홈오디오
    # (블루투스 아님), Mounts/Repair/Grills=부속품. 넓히면 과제 정의가 "스피커"로 바뀐다.
    "블루투스 스피커": {
        "file": "meta_Electronics",
        "nodes": {"Portable Bluetooth Speakers"},
    },
    "티셔츠": {
        "file": "meta_Clothing_Shoes_and_Jewelry",
        "nodes": {"T-Shirts"},
    },
    "책상": {
        "file": "meta_Home_and_Kitchen",
        "nodes": {"Home Office Desks", "Desks"},
    },
    "데스크체어": {
        "file": "meta_Home_and_Kitchen",
        "nodes": {"Home Office Desk Chairs", "Desk Chairs", "Home Office Chairs"},
    },
}

#: 전자 — 본품 인근에 액세서리가 대량으로 섞인다.
#
#: 2026-08-06 실측(`diagnose_junk_filter.py`, meta_Electronics 1.61M줄 전수)으로 두 가지가 드러났다:
#:   (1) 부분 문자열 매칭이 본품을 죽인다 — `stand`가 "Auto **Stand**by"를,
#:       `band`가 "Neck**band** Speaker"를 잡아냈다. 단독탈락 기준 93개가 순수 오탐이었다.
#:   (2) 액세서리는 "<부속품> for <제품>" 어순을 갖고, 본품 번들은 "<제품> with <부속품>"이다.
#:       ("Hard Travel Case **for** JBL" = 액세서리 / "JBL Speaker Bundle **with** Carry Case" = 본품)
#: 그래서 단어경계로 찾되, 매칭 위치가 'speaker' 뒤이거나 'with' 뒤면 본품으로 살린다.
JUNK_ELECTRONICS = ("case", "cover", "protector", "band", "strap", "replacement", "charger",
                    "cable", "adapter", "stand", "mount", "skin", "sticker", "hub", "sleeve",
                    "earpad", "ear pad", "cushion", "tips", "hook")
#: 단어경계 매칭. "standby"/"neckband"/"showcase" 같은 합성어에 걸리지 않는다.
_JUNK_RE = re.compile(r"\b(" + "|".join(re.escape(j) for j in JUNK_ELECTRONICS) + r")\b")
#: 본품 번들 신호 — 이 어휘가 부속품 단어 **앞**에 오면 부속품이 아니라 구성품이다.
_BUNDLE_RE = re.compile(r"\b(with|bundle|includes?|included|built-?in|plus)\b")


def is_accessory(title_l: str) -> bool:
    """액세서리면 True. 단어경계 + 어순으로 판정한다 (위 주석의 (1)(2))."""
    m = _JUNK_RE.search(title_l)
    if m is None:
        return False
    head = title_l[:m.start()]
    # 부속품 단어 앞에 제품명이나 번들 신호가 이미 나왔으면 본품이다.
    if "speaker" in head or _BUNDLE_RE.search(head):
        return False
    return True
#: 가구 — 노드 필터가 대부분 걸러주므로 명백한 부속품 어휘만 좁게 잡는다.
#: ("cushion" 같은 일반어를 넣으면 "Cushioned Office Chair" 같은 본품이 탈락한다.)
JUNK_FURNITURE = ("slipcover", "chair mat", "caster", "armrest pad", "seat cushion",
                  "replacement", "chair pad", "desk pad", "floor mat")
#: 의류 — 아동 경로 제외. 성인 대상 연구이므로 아동복이 섞이면 과제가 오염된다.
KIDS_PATH = ("Boys", "Girls", "Baby", "Kids", "Toddler", "Infant", "Children")


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


def classify(title_l: str, cats: list, wanted: dict[str, dict]) -> str | None:
    """leaf 노드로 카테고리를 정하고, 카테고리별 부속품/아동 필터를 적용한다."""
    if not cats:
        return None
    leaf = str(cats[-1]).strip()
    for label, spec in wanted.items():
        if leaf not in spec["nodes"]:
            continue
        if label == "블루투스 스피커" and is_accessory(title_l):
            return None
        if label in ("책상", "데스크체어") and any(j in title_l for j in JUNK_FURNITURE):
            return None
        if label == "티셔츠" and any(k in cats for k in KIDS_PATH):
            return None
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


def collect(fname: str, quotas: dict[str, int], existing_ids: set) -> dict[str, list]:
    """meta 파일 하나를 스트리밍하며 quotas만큼 모은다. quota 0 이하는 무제한."""
    wanted = {k: v for k, v in KINDS.items() if v["file"] == fname and quotas.get(k, 0) != 0}
    if not wanted:
        return {}
    got: dict[str, list] = {k: [] for k in wanted}

    def done() -> bool:
        return all(0 < quotas[k] <= len(got[k]) for k in wanted)

    req = urllib.request.Request(f"{BASE}/{fname}.jsonl",
                                 headers={"Authorization": f"Bearer {HF}"} if HF else {})
    resp = urllib.request.urlopen(req, timeout=300)
    n = 0
    for raw in resp:
        n += 1
        if (LINE_CAP and n > LINE_CAP) or done():
            break
        try:
            r = json.loads(raw)
        except Exception:  # noqa: BLE001
            continue
        if parse_price(r.get("price")) is None or not first_image(r.get("images")):
            continue
        if (r.get("rating_number") or 0) < MIN_REVIEWS:
            continue
        kind = classify((r.get("title") or "").lower(), r.get("categories") or [], wanted)
        if kind is None:
            continue
        if 0 < quotas[kind] <= len(got[kind]):
            continue
        item = map_item(r, kind)
        if not item["title"] or item["id"] in existing_ids:
            continue
        existing_ids.add(item["id"])
        got[kind].append(item)
        if n % 200000 == 0:
            print(f"  {fname} {n:,}줄 · " + " ".join(f"{k}={len(v)}" for k, v in got.items()), flush=True)
    print(f"  {fname} 완료({n:,}줄): " + " ".join(f"{k}={len(v)}" for k, v in got.items()), flush=True)
    return got


async def koreanize_one(provider, sem, p, counter, total):
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
    if counter[0] % 200 == 0:
        print(f"  번역 {counter[0]:,}/{total:,}", flush=True)


def save(products: list[dict], new_items: list[dict]) -> None:
    products.extend(new_items)
    (OUT / "products.json").write_text(
        json.dumps(products, ensure_ascii=False, indent=1), encoding="utf-8")


async def main():
    products = json.loads((OUT / "products.json").read_text(encoding="utf-8"))
    existing_ids = {p["id"] for p in products}
    have = {k: sum(1 for p in products if p.get("category") == k) for k in KINDS}
    print(f"기존 풀: {len(products):,}개 · 대상 카테고리 현황 " +
          " ".join(f"{k}={v}" for k, v in have.items()))

    # 카테고리별로 **각자의 공급 한계까지** 모은다 (2026-08-06 방침 변경).
    #
    # 이전에는 병목(스피커)에 맞춰 세 과제 깊이를 균일하게 잘랐다. 그런데 실측 결과 스피커의
    # 절대 상한이 2,859개(가격+이미지 있는 전량)로 확정됐고, 거기에 나머지를 맞추면 공급이
    # 남는 카테고리까지 인위적으로 버리게 된다. 깊이 균일보다 각 카테고리의 추천 다양성을
    # 택한다 — 과제 간 비교 시 풀 깊이 차이를 공변량으로 기록해 두면 된다.
    #
    # 티셔츠만 상한이 필요하다: 공급이 10만+라 무제한으로 두면 벡터 캐시가
    # product_vectors.json.gz의 GitHub 100MB 한도(개당 4,752 B → 약 21,000개)를 넘어
    # 배포가 깨진다. 다른 셋이 실측된 뒤 여유가 남으면 이 값을 올려 재실행하면 된다
    # (기존 id는 건너뛰므로 증분).
    tshirt_cap = int(os.environ.get("TSHIRT_CAP", "10000"))
    print(f"\n[1/3] 블루투스 스피커 수집 (무제한, 리뷰 {MIN_REVIEWS}+ · 실측 상한 ~2,859)")
    bt = collect("meta_Electronics", {"블루투스 스피커": BT_CAP or UNLIMITED}, existing_ids)
    bt_new = bt.get("블루투스 스피커", [])
    print(f"→ 블루투스 스피커 {have['블루투스 스피커']:,} + 신규 {len(bt_new):,}"
          f" = {have['블루투스 스피커'] + len(bt_new):,}")

    ts_goal = max(tshirt_cap - have["티셔츠"], 0)
    print(f"\n[2/3] 티셔츠 수집 (상한 {tshirt_cap:,} − 기존 {have['티셔츠']:,} = {ts_goal:,})")
    ts = collect("meta_Clothing_Shoes_and_Jewelry", {"티셔츠": ts_goal}, existing_ids)

    print("\n[3/3] 홈오피스 수집 (책상·데스크체어 각각 무제한 — 실제 공급을 이번 패스로 실측)")
    hk = collect("meta_Home_and_Kitchen",
                 {"책상": UNLIMITED, "데스크체어": UNLIMITED}, existing_ids)

    new_items = bt_new + [x for v in ts.values() for x in v] + [x for v in hk.values() for x in v]
    if not new_items:
        print("수집 0개 — 중단")
        return

    print(f"\n한국어 가공 {len(new_items):,}건 (CONC={CONC})")
    provider = get_provider()
    sem = asyncio.Semaphore(CONC)
    counter = [0]
    await asyncio.gather(*(koreanize_one(provider, sem, p, counter, len(new_items))
                           for p in new_items))

    save(products, new_items)
    final = {k: sum(1 for p in products if p.get("category") == k) for k in KINDS}
    print(f"\n완료 — +{len(new_items):,}개 → 총 {len(products):,}개")
    print("  카테고리별 최종 깊이 (균일하지 않은 것이 의도된 설계 — 위 주석 참조):")
    for k in KINDS:
        print(f"    {k:14s} {final[k]:>7,}")
    # 벡터 캐시가 GitHub 100MB 한도를 넘으면 배포가 깨진다 — 여기서 미리 경고한다.
    VEC_B = 4752  # gz 기준 개당 실측 (11,478개 = 52.0 MB, 2026-08-06)
    est_mb = len(products) * VEC_B / 1024 ** 2
    print(f"\n  예상 product_vectors.json.gz ≈ {est_mb:.0f} MB "
          f"({'OK' if est_mb < 95 else '⚠️ GitHub 100MB 한도 초과 — TSHIRT_CAP을 낮춰 재구성 필요'})")
    print("\n다음 단계:")
    print("  1) PYTHONPATH=. .venv/bin/python scripts/build_product_profiles.py   # 신규만 증분")
    print("  2) 임베딩 갱신 → product_vectors 재생성")
    print("  3) 새 카테고리(책상·데스크체어)용 시나리오 추가 — seed_amazon/scenarios.json")


if __name__ == "__main__":
    asyncio.run(main())

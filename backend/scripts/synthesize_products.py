"""합성 상품 생성 (속성 그리드 방식) — 각 카테고리를 목표 개수까지 채운다.

다양성 문제 해결: "기존 제목 회피"(확장 불가)가 아니라 **속성 그리드 사전 분배**.
각 상품에 서로 다른 속성 조합(서로소 스텝 인덱싱)을 배정 → LLM은 그 속성으로 제목만
생성 → 구조적으로 안 겹침. 과거 제목을 안 봐도 됨 → 수백 개로 무한 확장.

가치 트레이드오프: 숫자 필드(가격·평점·리뷰·장기리뷰)는 코드가 4프로필로 제어
(LLM이 숫자 지어내면 비현실적). 속성 그리드는 '무엇'(다양성), 프로필은 '가치 긴장'.

이미지 없음(합의). cueSummary는 seed_loader가 자동 생성. id=syn_ 접두사. 결정론적.

사용:
  PYTHONPATH=. .venv/bin/python scripts/synthesize_products.py --target 50 --limit-cat 노트북
  PYTHONPATH=. .venv/bin/python scripts/synthesize_products.py --target 50
  PYTHONPATH=. .venv/bin/python scripts/synthesize_products.py --apply
"""
import argparse
import asyncio
import json
import shutil
import sqlite3
from collections import Counter

from app.core.config import BACKEND_DIR, settings
from app.llm.provider import LLMMessage, get_provider

SEED = BACKEND_DIR / "seed_naver" / "products.json"
OUT = BACKEND_DIR / "seed_naver" / "synthetic_products.json"

# 카테고리별 가격대 (저/중/고, 원) — 실덤프 분포 기반
PRICE_BANDS = {
    "무선이어폰": (15000, 60000, 250000), "헤드셋·헤드폰": (20000, 80000, 250000),
    "노트북": (450000, 900000, 2200000), "모니터": (150000, 350000, 900000),
    "태블릿": (200000, 600000, 1400000), "키보드·마우스": (15000, 60000, 180000),
    "원피스": (20000, 60000, 200000), "니트·가디건": (25000, 70000, 200000),
    "코트·패딩·자켓": (50000, 150000, 450000), "티셔츠·셔츠": (12000, 35000, 90000),
    "팬츠·바지": (15000, 40000, 120000),
}

# 가상 브랜드 풀 (실존 베끼지 않음). 카테고리 무관 공용 + 패션/전자 구분.
BRANDS_TECH = ["루미테크","노바사운드","데일리텍","맥스플로우","제닉스","코어웨이","에버North","사운드웨이","큐브릭","넥스원"]
BRANDS_FASHION = ["모먼트","데일리핏","러비드","오브제","코지룸","에이블린","무드앤","폴앤","리니크","세느"]

# 카테고리별 속성 축 (그리드). 마지막 "_brands"는 브랜드 풀 선택.
GRIDS = {
    "무선이어폰": {"형태":["커널형","오픈형","골전도","반오픈형"],"기능":["노이즈캔슬링","주변음허용","방수 IPX5","고음질 코덱","저지연 게이밍"],"용도":["일상","운동·러닝","통화·회의","음악감상"],"색":["블랙","화이트","크림","민트"]},
    "헤드셋·헤드폰": {"형태":["오버이어","온이어"],"기능":["노이즈캔슬링","무선","유선 모니터링","게이밍 7.1"],"용도":["음악감상","게이밍","스튜디오","사무·재택"],"색":["블랙","화이트","그레이","베이지"]},
    "노트북": {"용도":["사무·문서","게이밍","크리에이터·영상편집","대학생·인강","코딩·개발","휴대·이동"],"화면":["13인치","14인치","15.6인치","16인치"],"칩":["인텔 i5","인텔 i7","인텔 Ultra5","라이젠5","라이젠7"],"특징":["초경량","고주사율","올데이 배터리","메탈 바디","터치스크린"],"색":["실버","스페이스그레이","화이트","네이비"]},
    "모니터": {"크기":["24인치","27인치","32인치","34인치 울트라와이드"],"패널":["IPS","VA","OLED"],"해상도":["FHD","QHD","4K UHD"],"용도":["사무·문서","디자인·영상","게이밍","개발·코딩"],"특징":["아이케어 플리커프리","고주사율 144Hz","HDR","높이조절 스탠드"]},
    "태블릿": {"크기":["8인치","10인치","11인치","12.9인치"],"용도":["필기·학습","그림·드로잉","영상·미디어","사무·문서"],"특징":["펜 지원","고주사율","경량","대용량 배터리"],"칩":["보급형","미드레인지","고성능"],"색":["스페이스그레이","실버","그래파이트"]},
    "키보드·마우스": {"구성":["키보드","마우스","키보드+마우스 세트"],"방식":["기계식","멤브레인","무접점","무선 슬림"],"특징":["저소음","RGB 백라이트","인체공학","컴팩트 텐키리스"],"용도":["사무","게이밍","코딩","휴대"]},
    "원피스": {"길이":["미니","미디","롱"],"핏":["A라인","슬림","루즈"],"소재":["코튼","쉬폰","니트","린넨"],"스타일":["데일리캐주얼","오피스룩","페미닌","유니크 디자인"],"계절":["봄가을","여름","간절기"]},
    "니트·가디건": {"종류":["라운드넥 니트","브이넥 니트","가디건","터틀넥 니트"],"핏":["슬림","오버핏","레귤러"],"소재":["울 혼방","코튼","캐시미어 터치","아크릴"],"두께":["얇은 봄가을용","두꺼운 겨울용"],"색":["아이보리","그레이","네이비","브라운"]},
    "코트·패딩·자켓": {"종류":["싱글 코트","더블 코트","숏패딩","롱패딩","블레이저"],"소재":["울 혼방","구스다운","폴리 충전재","코듀로이"],"핏":["슬림","오버핏","레귤러"],"용도":["출퇴근","데일리","포멀"],"색":["블랙","카멜","차콜","베이지"]},
    "티셔츠·셔츠": {"종류":["반팔 티셔츠","긴팔 티셔츠","셔츠","맨투맨"],"핏":["슬림","오버핏","레귤러"],"소재":["코튼","옥스포드","링클프리","기모"],"스타일":["베이직","캐주얼","오피스"],"색":["화이트","블랙","네이비","베이지"]},
    "팬츠·바지": {"종류":["슬랙스","청바지","와이드팬츠","조거팬츠","치노팬츠"],"핏":["슬림","스트레이트","와이드","테이퍼드"],"소재":["코튼","데님","린넨","기모"],"용도":["오피스","데일리","운동·라운지"],"색":["블랙","네이비","베이지","그레이"]},
}

PROFILES = {
    "value":   {"band":0,"rating":4.3,"reviews":250,"ltr":0.15,"sales":400,"delivery":0,"desc":"가격이 낮은 가성비형"},
    "premium": {"band":2,"rating":4.8,"reviews":900,"ltr":0.40,"sales":300,"delivery":0,"desc":"고가·고품질, 신뢰도 높음"},
    "novel":   {"band":1,"rating":4.5,"reviews":80, "ltr":0.20,"sales":60, "delivery":3000,"desc":"개성·차별화 디자인 중가"},
    "balanced":{"band":1,"rating":4.6,"reviews":450,"ltr":0.28,"sales":250,"delivery":0,"desc":"가격·품질 균형 중가"},
}
PROFILE_MIX = ["value","balanced","premium","novel"]


def price_for(cat, band_idx, jitter):
    lo, mid, hi = PRICE_BANDS[cat]
    base = [lo, mid, hi][band_idx]
    return int(round(base * (1.0 + ((jitter % 7) - 3) * 0.05) / 1000) * 1000)


def _coprime_step(j, n):
    """축 길이 n과 서로소인 스텝 — (i*step)%n이 모든 값을 순회하게 한다.
    (j*2+1)이 n의 배수면 수렴(예: step=5, n=5 → 항상 0). 서로소가 될 때까지 +1."""
    from math import gcd
    step = j * 2 + 1
    while gcd(step, n) != 1:
        step += 1
    return step


def attrs_for(cat, i):
    """속성 그리드에서 i번째 조합 — 축마다 서로소 스텝으로 분배(모든 값 순회, 겹침 최소)."""
    grid = GRIDS[cat]
    keys = list(grid.keys())
    return {k: grid[k][(i * _coprime_step(j, len(grid[k]))) % len(grid[k])]
            for j, k in enumerate(keys)}


SYSTEM = """너는 한국 온라인 쇼핑몰의 현실적인 상품 제목을 만든다.
주어진 브랜드명과 속성들을 **모두 자연스럽게 반영**한 제목 1개를 만들어라.

규칙:
1. 주어진 가상 브랜드명을 그대로 쓴다 (실존 브랜드 베끼지 말 것).
2. 속성(용도·형태·소재·색 등)을 제목에 녹인다 — 단 어색하게 나열하지 말고 실제 상품명처럼.
3. 가치 프로필(가성비/프리미엄/디자인/균형)의 느낌을 살린다.
4. 태그는 속성에서 뽑은 한국어 키워드 4~6개.
5. JSON으로만: {"title":"...","tags":["...","..."]}"""


async def gen_one(provider, cat, profile_key, i):
    prof = PROFILES[profile_key]
    grid_attrs = attrs_for(cat, i)
    brands = BRANDS_FASHION if cat in ("원피스","니트·가디건","코트·패딩·자켓","티셔츠·셔츠","팬츠·바지") else BRANDS_TECH
    brand = brands[i % len(brands)]
    ctx = {"카테고리":cat, "브랜드":brand, "속성":grid_attrs, "가치프로필":prof["desc"]}
    try:
        out = await provider.generate_json(
            [LLMMessage(role="system",content=SYSTEM),
             LLMMessage(role="user",content=json.dumps(ctx,ensure_ascii=False))],
            task="synthesize_product", context=ctx)
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ {cat}/{profile_key}#{i}: {type(e).__name__}")
        return None
    title = (out or {}).get("title")
    if not title:
        return None
    price = price_for(cat, prof["band"], i)
    return {
        "id": f"syn_{cat}_{profile_key}_{i}".replace("·","_").replace("/","_"),
        "title": title.strip(), "category": cat, "brand": brand,
        "price": price, "listPrice": int(price*1.15), "discountRate": 0.13,
        "deliveryFee": prof["delivery"], "rating": prof["rating"],
        "reviewCount": prof["reviews"] + (i % 5)*17, "longTermReviewRatio": prof["ltr"],
        "recentSalesCount": prof["sales"] + (i % 4)*23,
        "sellerName": None, "sellerGrade": None, "sellerYears": None,
        "imageUrl": None, "productUrl": None,
        "attributes": {"domain":"synthetic","synthetic":True,"valueProfile":profile_key,"gridAttrs":grid_attrs},
        "description": None, "tags": (out or {}).get("tags") or [], "cueSummary": None,
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=50)
    ap.add_argument("--limit-cat", type=str, default=None)
    ap.add_argument("--concurrency", type=int, default=12)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--regen", action="store_true", help="기존 합성품 무시하고 새로(그리드)")
    args = ap.parse_args()

    products = json.loads(SEED.read_text(encoding="utf-8"))
    # 실상품만 카운트 (합성 제외)
    real = [p for p in products if not (p.get("attributes") or {}).get("synthetic")]
    cur = Counter(p["category"] for p in real)

    if args.apply:
        if not OUT.exists():
            print("✗ synthetic_products.json 없음"); return
        syn = json.loads(OUT.read_text(encoding="utf-8"))
        # seed에서 기존 합성품 제거 후 새 합성품으로 교체 (regen 반영)
        base = [p for p in products if not (p.get("attributes") or {}).get("synthetic")]
        merged = base + syn
        shutil.copy(SEED, SEED.with_suffix(".json.presyn.bak"))
        SEED.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ seed: 실 {len(base)} + 합성 {len(syn)} = {len(merged)}, 백업 .presyn.bak")
        from app.products.cue_extractor import build_cue_summary
        pbc = {}
        for it in merged:
            if it.get("price"): pbc.setdefault(it.get("category",""),[]).append(it["price"])
        db = sqlite3.connect(settings.db_path); c = db.cursor()
        # 기존 합성품 DB 삭제 후 재삽입
        c.execute("DELETE FROM products WHERE json_extract(attributes,'$.synthetic')=1")
        c.execute("SELECT id FROM products"); have={r[0] for r in c.fetchall()}
        ins=0
        for it in syn:
            if it["id"] in have: continue
            cue = it.get("cueSummary") or build_cue_summary(it, pbc.get(it.get("category","")))
            c.execute("""INSERT INTO products (id,title,category,brand,price,list_price,discount_rate,
                delivery_fee,rating,review_count,long_term_review_ratio,recent_sales_count,
                image_url,product_url,attributes,tags,description,cue_summary)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
                it["id"],it["title"],it["category"],it.get("brand"),it.get("price"),
                it.get("listPrice"),it.get("discountRate"),it.get("deliveryFee"),it.get("rating"),
                it.get("reviewCount"),it.get("longTermReviewRatio"),it.get("recentSalesCount"),
                None,None,json.dumps(it.get("attributes") or {},ensure_ascii=False),
                json.dumps(it.get("tags") or [],ensure_ascii=False),it.get("description"),
                json.dumps(cue,ensure_ascii=False)))
            ins+=1
        db.commit(); db.close()
        print(f"✓ DB: 기존 합성 삭제 후 {ins}개 재삽입")
        return

    if settings.llm_provider == "mock":
        print("✗ mock — 실제 provider 필요"); return
    provider = get_provider()
    print(f"provider={provider.name}, model={getattr(provider,'model','?')}")

    cats = [args.limit_cat] if args.limit_cat else list(PRICE_BANDS.keys())
    existing = {} if args.regen else ({s["id"]:s for s in json.loads(OUT.read_text(encoding="utf-8"))} if OUT.exists() else {})

    spec = []
    for cat in cats:
        need = max(0, args.target - cur.get(cat,0))
        for i in range(need):
            profile = PROFILE_MIX[i % len(PROFILE_MIX)]
            sid = f"syn_{cat}_{profile}_{i}".replace("·","_").replace("/","_")
            if sid not in existing:
                spec.append((cat, profile, i))
    print(f"생성 대상 {len(spec)}개 (목표 {args.target}/카테고리, regen={args.regen})\n")

    sem = asyncio.Semaphore(args.concurrency)
    results = dict(existing); done=0
    async def work(s):
        nonlocal done
        cat,profile,i = s
        async with sem:
            r = await gen_one(provider,cat,profile,i)
            if r: results[r["id"]]=r
            done+=1
            if done%25==0 or done==len(spec):
                print(f"  진행 {done}/{len(spec)}")
                OUT.write_text(json.dumps(list(results.values()),ensure_ascii=False,indent=2),encoding="utf-8")
    await asyncio.gather(*(work(s) for s in spec))
    OUT.write_text(json.dumps(list(results.values()),ensure_ascii=False,indent=2),encoding="utf-8")

    titles = [s["title"] for s in results.values()]
    print(f"\n완료 → {OUT} (총 {len(results)}개, 고유제목 {len(set(titles))})")


if __name__ == "__main__":
    asyncio.run(main())

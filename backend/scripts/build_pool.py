"""범용 상품 풀 빌더 (패션 전반 + 전자기기) — build_womens_outerwear.py의 일반화.

설계: 카테고리는 *제한*이 아니라 *청소/라벨 신호*. 추천은 카테고리 하드필터를 안 쓰므로
(의미검색+LLM rerank) 풀은 넓게 간다. 단계:
  candidates  [recall] 13개 세부 카테고리 제목 그물로 후보 폭넓게 (구매수 top, 가격대 다양)
  verify      [clean]  네이버 API category path → category1 ∈ {패션의류,패션잡화,디지털/가전}만
              통과(쓰레기/오분류 제거) + tags(제목∩vocab)·gender·garment·image 라벨
  merge       풀에 병합 / verify_pool  실 로더+FTS+임베딩으로 검색 검증

제목 정규식은 후보 *발견*(recall)에만, *분류/청소*는 API가 한다(테니스화 "코트" 등 누수 차단).
numpy 미설치 → duckdb .df() 금지. 원본 gz 직접 스트리밍.
"""
import json
import sys
import time
import urllib.error
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # app.* / 형제 스크립트 import

BASE = "/Users/notaehyeong/Develop/naver_value_evaluation"
PRODUCT = f"{BASE}/part-00000-8f9dcd63-f196-4e6f-918c-c42a5150f1f1-c000.csv.gz"
PURCHASE = f"{BASE}/part-00000-a577f368-2a11-454b-b4be-fcb00e45e690-c000.csv.gz"
REVIEW = f"{BASE}/part-00000-1679696e-3725-4c99-9637-124f7d0a33ed-c000.csv.gz"
OPT = r"delim='\t', header=false, all_varchar=true, ignore_errors=true, quote=''"

ROOT = Path(__file__).resolve().parents[1]
CAND_OUT = ROOT / "data" / "pool_candidates.json"
POOL_OUT = ROOT / "seed" / "products_pool.json"
TAG_VOCAB = json.loads((ROOT / "config" / "tag_taxonomy.json").read_text(encoding="utf-8"))

# 도메인 게이트 — API category1이 이 중 하나면 통과(패션 전반 + 전자기기), 나머지·쓰레기는 탈락.
DOMAIN_OK = {"패션의류", "패션잡화", "디지털/가전"}

# leaf 게이트 — 도메인만으론 "노트북 백팩"(패션잡화)이 새므로, API 세부 leaf(category4)가
# 그 카테고리의 핵심 품목이어야 통과. (제목-분류의 액세서리 오분류 차단)
LEAF_OK = {
    "무선이어폰": ["블루투스이어폰", "이어셋", "버즈", "에어팟"],
    "헤드셋·헤드폰": ["헤드셋", "헤드폰"],
    "노트북": ["노트북"],
    "태블릿": ["태블릿"],
    "키보드·마우스": ["키보드", "마우스"],
    "모니터": ["모니터"],
    "원피스": ["원피스"],
    "니트·가디건": ["니트", "가디건", "스웨터", "풀오버"],
    "코트·패딩·자켓": ["코트", "패딩", "재킷", "점퍼", "야상", "무스탕", "파카", "베스트", "아우터", "플리스"],
    "팬츠·바지": ["팬츠", "바지", "청바지", "슬랙스", "레깅스", "조거"],
    "티셔츠·셔츠": ["티셔츠", "셔츠", "블라우스", "맨투맨", "후드"],
    "잠옷·홈웨어": ["잠옷", "파자마", "홈웨어", "실내복", "언더웨어"],
    "수영복·래쉬가드": ["수영복", "래쉬가드", "비치", "비키니", "스윔"],
}
# leaf에 이게 들어가면 액세서리/부속 → 탈락 (마우스패드·셀렉터·백팩 등)
LEAF_ACCESSORY = ["패드", "케이스", "파우치", "백팩", "가방", "허브", "보조배터리", "거치", "브라켓",
                  "스탠드", "케이블", "어댑터", "액세서리", "필름", "단품", "셀렉터", "분배기",
                  "브리프케이스", "마운트", "쿨러", "스킨", "커버", "받침", "청소", "무전기", "슬리퍼"]
JUNK_TITLE = ["나눔", "정체를 알 수 없", "단체 모임", "문구 티", "중고"]


def _leaf_accept(category: str, leaf: str) -> bool:
    if any(a in leaf for a in LEAF_ACCESSORY):
        return False
    return any(s in leaf for s in LEAF_OK.get(category, []))

# 후보 *발견*용 세부 카테고리 그물 (name, include, exclude). 분류는 API가 확정.
TAXONOMY = [
    ("무선이어폰", r"이어폰|에어팟|갤럭시버즈|버즈프로|블루투스이어폰", r"이어팁|이어캡|행거|줄걸이"),
    ("헤드셋·헤드폰", r"헤드셋|헤드폰", r"거치|행거"),
    ("노트북", r"노트북|갤럭시북|맥북", r"슬리브|쿨러|키스킨|받침|파우치"),
    ("태블릿", r"태블릿|갤럭시탭|아이패드", r"필름|케이스|펜슬팁"),
    ("키보드·마우스", r"키보드|마우스", r"패드|손목|장갑"),
    ("모니터", r"모니터", r"받침|암|거치|청소"),
    ("원피스", r"원피스", r"수영복|강아지|애견|커튼"),
    ("니트·가디건", r"니트|가디건|카디건|스웨터", r"보풀|제거기"),
    ("코트·패딩·자켓", r"코트|패딩|자켓|재킷|점퍼|야상|무스탕|아우터|파카", r"레인코트|마스코트|테니스|침대|차량"),
    ("팬츠·바지", r"팬츠|바지|청바지|슬랙스|레깅스|조거", r"보정|복대"),
    ("티셔츠·셔츠", r"티셔츠|반팔|긴팔|맨투맨|후드|셔츠|블라우스", r"강아지"),
    ("잠옷·홈웨어", r"잠옷|파자마|홈웨어|실내복|수면바지", r"강아지"),
    ("수영복·래쉬가드", r"수영복|래쉬가드|비치웨어|보드숏", r"강아지"),
]
GLOBAL_EXCLUDE = (r"라부부|피규어|팝마트|인형|키링|스티커|굿즈|장난감|뱃지|배지|파우치|케이스|커버|거치|받침|"
                  r"스탠드|클리너|청소|충전기|어댑터|케이블|보호필름|강화유리|필름|액정|젠더|악세|액세서리|장패드")
ALL_INCLUDE = "|".join(set("|".join(inc for _, inc, _ in TAXONOMY).split("|")))

import re  # noqa: E402

_GLOBAL = re.compile(GLOBAL_EXCLUDE)
_COMPILED = [(name, re.compile(inc), re.compile(exc) if exc else None) for name, inc, exc in TAXONOMY]


def classify(title: str) -> str | None:
    """제목을 세부 카테고리로 (recall 분류; 최종 도메인 확정은 API)."""
    if _GLOBAL.search(title):
        return None
    for name, inc, exc in _COMPILED:
        if inc.search(title) and not (exc and exc.search(title)):
            return name
    return None


def candidates(pmin: int, pmax: int, per_cat: int) -> None:
    """[recall] 13개 세부 카테고리에서 구매수 top per_cat씩 → 후보 (가치큐 포함)."""
    sql = f"""
      WITH prod AS (
        SELECT column2 AS cat, any_value(column4) AS title, any_value(column3) AS categoryId
        FROM read_csv('{PRODUCT}', {OPT})
        WHERE column8='판매중' AND column2 IS NOT NULL AND column2<>'NULL'
          AND regexp_matches(column4, '{ALL_INCLUDE}') AND NOT regexp_matches(column4, '{GLOBAL_EXCLUDE}')
        GROUP BY column2),
      price AS (
        SELECT column02 AS cat, median(TRY_CAST(column09 AS BIGINT)) AS price,
               median(TRY_CAST(column20 AS BIGINT)) AS delivery_fee,
               avg(CASE WHEN TRY_CAST(column09 AS BIGINT)>0
                        THEN TRY_CAST(column11 AS BIGINT)*1.0/TRY_CAST(column09 AS BIGINT) END) AS discount_rate,
               count(*) AS sales
        FROM read_csv('{PURCHASE}', {OPT})
        WHERE TRY_CAST(column09 AS BIGINT)>0 AND column02 IS NOT NULL AND column02<>'NULL'
        GROUP BY column02),
      rev AS (
        SELECT column02 AS cat, avg(TRY_CAST(column14 AS DOUBLE)) AS rating, count(*) AS reviews,
               sum(CASE WHEN column07='한달사용' THEN 1 ELSE 0 END)*1.0/count(*) AS ltr
        FROM read_csv('{REVIEW}', {OPT})
        WHERE column16='정상' AND column02 IS NOT NULL AND column02<>'NULL'
        GROUP BY column02)
      SELECT p.cat, p.title, p.categoryId, pr.price, pr.delivery_fee, pr.discount_rate, pr.sales,
             r.rating, r.reviews, r.ltr
      FROM prod p JOIN price pr USING(cat) LEFT JOIN rev r USING(cat)
      WHERE pr.price BETWEEN {pmin} AND {pmax}
      ORDER BY pr.sales DESC
    """
    print(f"스캔 중(원본 gz)… 가격 {pmin:,}~{pmax:,}원, 13개 카테고리 제목 그물")
    rows = duckdb.connect().execute(sql).fetchall()
    buckets: dict[str, list] = {}
    for (cat, title, categoryId, price, dfee, drate, sales, rating, reviews, ltr) in rows:
        name = classify(title or "")
        if not name:
            continue
        buckets.setdefault(name, []).append({
            "id": f"nv_{cat}", "cat": cat, "title": title, "categoryId": categoryId, "guessCategory": name,
            "price": int(price) if price is not None else None,
            "deliveryFee": int(dfee) if dfee is not None else None,
            "discountRate": round(drate, 3) if drate is not None else None,
            "rating": round(rating, 2) if rating is not None else None,
            "reviewCount": int(reviews) if reviews is not None else None,
            "longTermReviewRatio": round(ltr, 3) if ltr is not None else None,
            "recentSalesCount": int(sales or 0),
            "productUrl": f"https://search.shopping.naver.com/catalog/{cat}",
        })
    out = []
    for name, _, _ in TAXONOMY:
        items = sorted(buckets.get(name, []), key=lambda x: x["recentSalesCount"], reverse=True)[:per_cat]
        out.extend(items)
        print(f"  {name:14} {len(items):>4}개 선정 / {len(buckets.get(name, [])):>5} 가용")
    CAND_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n총 후보 {len(out)}개 → {CAND_OUT.name}")


def _derive_tags(title: str, category: str) -> list[str]:
    """제목에 그대로 등장하는 vocab 태그만 (환각 없음). 카테고리별 vocab은 tag_taxonomy.json."""
    return [t for t in TAG_VOCAB.get(category, []) if isinstance(t, str) and t in title]


def verify(sleep: float = 0.12) -> None:
    """[clean] 후보를 API 검색→ category1 ∈ DOMAIN_OK만 통과 + tags/gender/garment/image 라벨.
    멱등/재개 — 이미 결과에 있는 id는 건너뛴다(중간 끊겨도 이어서)."""
    from enrich_naver_images import best_match, category_path, clean_query, search

    cands = json.loads(CAND_OUT.read_text(encoding="utf-8"))
    kept = json.loads(POOL_OUT.read_text(encoding="utf-8")) if POOL_OUT.exists() else []
    done = {p["id"] for p in kept}
    cats = {}
    todo = [c for c in cands if c["id"] not in done]
    print(f"API 청소: 후보 {len(cands)} · 이미 {len(done)} · 처리 {len(todo)}")
    dropped = errored = 0
    for i, c in enumerate(todo, 1):
        try:
            items = search(clean_query(c["title"]))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print("  429 — sleep 5s"); time.sleep(5); continue
            errored += 1; continue
        except Exception:  # noqa: BLE001
            errored += 1; continue
        m = best_match(items, c)
        leaf = (m or {}).get("category4") or (m or {}).get("category3") or ""
        if (m and m.get("category1") in DOMAIN_OK and _leaf_accept(c["guessCategory"], leaf)
                and not any(j in c["title"] for j in JUNK_TITLE)):
            cat = c["guessCategory"]
            path = category_path(m)
            tags = _derive_tags(c["title"], cat)
            attrs = {"categoryId": c["categoryId"], "domain": m.get("category1"),
                     "categoryPath": path, "garmentType": m.get("category4")}
            if m.get("category2") in ("여성의류", "남성의류"):
                attrs["gender"] = "여성" if m["category2"] == "여성의류" else "남성"
            lprice = int(m["lprice"]) if str(m.get("lprice", "")).isdigit() else None
            if lprice:
                attrs["lowestPrice"] = lprice
            kept.append({
                "id": c["id"], "title": c["title"], "category": cat,
                "brand": (m.get("brand") or m.get("maker") or None),
                "price": c["price"], "deliveryFee": c["deliveryFee"], "discountRate": c["discountRate"],
                "rating": c["rating"], "reviewCount": c["reviewCount"],
                "longTermReviewRatio": c["longTermReviewRatio"], "recentSalesCount": c["recentSalesCount"],
                "sellerName": m.get("mallName"), "sellerGrade": None, "sellerYears": None,
                "imageUrl": m.get("image") or None, "productUrl": m.get("link") or c["productUrl"],
                "attributes": attrs, "tags": tags, "description": None,
            })
            cats[cat] = cats.get(cat, 0) + 1
        else:
            dropped += 1
        if i % 50 == 0:
            print(f"  {i}/{len(todo)} · 통과누적 {len(kept)} 탈락 {dropped} 에러 {errored}")
            POOL_OUT.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(sleep)
    POOL_OUT.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n통과 {len(kept)} · 탈락 {dropped} · 에러 {errored} → {POOL_OUT.name}")
    from collections import Counter
    print("카테고리 분포:", dict(Counter(p["category"] for p in kept).most_common()))


POOL_FILE = ROOT / "seed_naver" / "products.json"  # 스터디 풀 (VC_SEED_DIR=seed_naver)
WOMENS = ROOT / "seed" / "products_womens_outer.json"
DESC_FILE = ROOT / "seed_naver" / "product_descriptions.json"
VEC_CACHE = ROOT / "seed_naver" / "product_vectors.json"


def apply_descriptions() -> None:
    """generate_product_descriptions.py가 만든 {id:설명}을 풀에 반영 + 벡터 캐시 무효화.
    설명이 임베딩 텍스트에 들어가므로(embeddings._product_text), 반영 후엔 재임베딩이 필요하다."""
    desc = json.loads(DESC_FILE.read_text(encoding="utf-8"))
    pool = json.loads(POOL_FILE.read_text(encoding="utf-8"))
    n = 0
    for p in pool:
        d = desc.get(p["id"])
        if d:
            p["description"] = d
            n += 1
    POOL_FILE.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding="utf-8")
    if VEC_CACHE.exists():
        VEC_CACHE.unlink()  # 설명 반영됨 → 다음 verify_pool이 설명 포함해 전량 재임베딩
    miss = [p["title"][:30] for p in pool if not p.get("description")][:5]
    print(f"설명 반영 {n}/{len(pool)} → {POOL_FILE.name} · 벡터 캐시 무효화(재임베딩 대기)")
    if miss:
        print(f"설명 없는 {len(pool)-n}개 (샘플): {miss}")


def reclean() -> None:
    """[clean v2] 이미 검증된 products_pool.json을 저장된 API leaf로 재청소 (추가 API 없음).
    제목-분류가 통과시킨 액세서리(노트북 백팩·모니터 스피커 등)·정크를 leaf 게이트로 제거."""
    from collections import Counter
    d = json.loads(POOL_OUT.read_text(encoding="utf-8"))
    out = []
    for p in d:
        leaf = (p.get("attributes", {}).get("categoryPath") or "").split(" > ")[-1]
        if any(j in p["title"] for j in JUNK_TITLE):
            continue
        if _leaf_accept(p["category"], leaf):
            out.append(p)
    POOL_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"재청소: {len(d)} → {len(out)} (제거 {len(d) - len(out)}) → {POOL_OUT.name}")
    print("카테고리 분포:", dict(Counter(p["category"] for p in out).most_common()))


def merge_pool(cap_per_cat: int, target: int) -> None:
    """[F-④a] 검증된 풀 + 여성 아우터를 카테고리별 cap으로 균형 맞춰 ~target개로 → seed_naver/products.json.
    풀을 교체한다(백업 보존). id 중복은 검증본이 이긴다."""
    from collections import defaultdict
    verified = json.loads(POOL_OUT.read_text(encoding="utf-8"))
    womens = json.loads(WOMENS.read_text(encoding="utf-8")) if WOMENS.exists() else []
    by_id = {p["id"]: p for p in verified}
    for p in womens:  # 여성 아우터 보존(검증본에 없으면 추가)
        by_id.setdefault(p["id"], p)
    # 카테고리별 cap (구매수 상위 우선) → 균형
    buckets: dict[str, list] = defaultdict(list)
    for p in by_id.values():
        buckets[p.get("category", "기타")].append(p)
    pool = []
    for cat, items in buckets.items():
        items.sort(key=lambda x: x.get("recentSalesCount") or 0, reverse=True)
        pool.extend(items[:cap_per_cat])
    pool.sort(key=lambda x: x.get("recentSalesCount") or 0, reverse=True)
    pool = pool[:target]
    bak = POOL_FILE.with_name("products.json.bak_pre_pool_v2")
    if not bak.exists():
        bak.write_text(POOL_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    POOL_FILE.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding="utf-8")
    from collections import Counter
    print(f"풀 {len(pool)}개 → {POOL_FILE.name} (백업 {bak.name})")
    print("카테고리 분포:", dict(Counter(p["category"] for p in pool).most_common()))


def verify_pool() -> None:
    """[F-④b] 실 로더+FTS+임베딩으로 새 풀 검색 검증 — 여러 카테고리 질의가 맞게 나오나.
    VC_SEED_DIR=seed_naver 로 실행."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db import models
    from app.db.database import Base
    from app.products import embeddings, search_index
    from app.products.search import search_products
    from app.products.seed_loader import load_seed_products

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    n = load_seed_products(db)
    search_index.build_index(db)
    embeddings.ensure_product_vectors(db.query(models.Product).all())
    mode = "임베딩" if (embeddings.enabled() and embeddings._loaded) else "BM25"
    print(f"풀 {n}개 + FTS + 벡터({mode}).")
    for q in ["겨울 코트 추천", "무선 이어폰 가성비", "사무용 노트북", "운동할 때 입을 반팔", "게이밍 모니터"]:
        pool = search_products(db, query=q, category=None, hard_constraints=[], soft_preferences=[],
                               topic_labels=[], avoidances=[], return_pool=True, pool_size=5)
        print(f"\nQ={q!r}")
        for sp in pool[:3]:
            print(f"   [{sp.product.category}] {(sp.product.price or 0):>8,}원 · {sp.product.tags} | {sp.product.title[:30]}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "candidates"
    if mode == "candidates":
        pmin = int(sys.argv[2]) if len(sys.argv) > 2 else 10000
        pmax = int(sys.argv[3]) if len(sys.argv) > 3 else 500000
        per_cat = int(sys.argv[4]) if len(sys.argv) > 4 else 280
        candidates(pmin, pmax, per_cat)
    elif mode == "verify":
        verify()
    elif mode == "reclean":
        reclean()
    elif mode == "apply_desc":
        apply_descriptions()
    elif mode == "merge":
        cap = int(sys.argv[2]) if len(sys.argv) > 2 else 200
        target = int(sys.argv[3]) if len(sys.argv) > 3 else 2000
        merge_pool(cap, target)
    elif mode == "verify_pool":
        verify_pool()

"""여성 아우터 상품 풀 빌더 (F: 데이터 풀 확장).

문제: 현재 풀에 여성 코트/아우터가 ~0개 → "코트 추천"이 실패(로직 아닌 데이터 공백).
해법: 원본 덤프(가치큐: 구매수·평점·한달사용비율) + 네이버 API category-path(gender·garment
      구조화 신호)를 합쳐 깨끗한 여성 아우터만 담는다. 제목 정규식은 *후보 발견*에만 쓰고,
      *분류*는 API path가 한다(테니스화 "올코트"는 path가 운동화라 자동 탈락 — 검증됨).

단계:
  probe                스키마 검증(컬럼 매핑 눈으로 확인)
  candidates           [F-①] dump narrow(아우터 제목)+가격/구매/리뷰 조인 → 후보 JSON
  verify               [F-②] 후보를 API 검색→ category2=여성의류 & category3=아우터 게이트 + enrich

numpy 미설치 → duckdb .df() 금지, fetchall만. /tmp 파생물은 재부팅 소실 → 원본 gz 직접 스트리밍.
"""
import json
import sys
from pathlib import Path

import duckdb

BASE = "/Users/notaehyeong/Develop/naver_value_evaluation"
PRODUCT = f"{BASE}/part-00000-8f9dcd63-f196-4e6f-918c-c42a5150f1f1-c000.csv.gz"   # 9col:  c2=cat c3=categoryId c4=title c8=status
PURCHASE = f"{BASE}/part-00000-a577f368-2a11-454b-b4be-fcb00e45e690-c000.csv.gz"  # 26col: c02=cat c09=정가 c11=할인 c20=배송비
REVIEW = f"{BASE}/part-00000-1679696e-3725-4c99-9637-124f7d0a33ed-c000.csv.gz"    # 18col: c02=cat c07=한달사용 c14=평점 c16=정상
OPT = r"delim='\t', header=false, all_varchar=true, ignore_errors=true, quote=''"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # app.* import 가능하게 (verify_pool)

DATA = Path(__file__).resolve().parents[1] / "data"
CAND_OUT = DATA / "outer_candidates.json"
VERIFY_OUT = Path(__file__).resolve().parents[1] / "seed" / "products_womens_outer.json"

# 아우터 후보 *발견*용(분류 아님 — API path가 분류). recall 위주로 넓게, 명백한 누수만 미리 깎는다.
OUTER_RE = "코트|패딩|자켓|재킷|점퍼|야상|트렌치|플리스|후리스|무스탕|아우터|파카|블루종|더플|뽀글|숏패딩|롱패딩|바람막이"
OUTER_NOISE = "테니스|골프|운동화|스니커즈|반려|강아지|애견|고양이|차량|매트|침대|코트지|마스코트|스킨앤코트|키링|인형|커버|케이스|거치"


def probe(path: str, name: str, n: int = 2) -> None:
    rows = duckdb.connect().execute(f"SELECT * FROM read_csv('{path}', {OPT}) LIMIT {n}").fetchall()
    print(f"\n=== {name} : {len(rows[0]) if rows else 0} columns ===")
    for ri, r in enumerate(rows):
        print(f"  -- row {ri} --")
        for i, v in enumerate(r):
            print(f"    col{i:>2}: {(v[:50] if isinstance(v, str) else v)!r}")


def candidates(pmin: int, pmax: int, limit: int) -> None:
    """[F-①] 아우터 제목 후보 + 가격(pmin~pmax)/구매/리뷰 조인 → 구매수 top-limit 후보."""
    sql = f"""
      WITH prod AS (
        SELECT column2 AS cat, any_value(column4) AS title, any_value(column3) AS categoryId
        FROM read_csv('{PRODUCT}', {OPT})
        WHERE column8='판매중' AND column2 IS NOT NULL AND column2<>'NULL'
          AND regexp_matches(column4, '{OUTER_RE}') AND NOT regexp_matches(column4, '{OUTER_NOISE}')
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
      LIMIT {limit}
    """
    print(f"스캔 중(원본 gz 직접)… 가격 {pmin:,}~{pmax:,}원 · 아우터 제목 후보 top {limit} (구매수순)")
    rows = duckdb.connect().execute(sql).fetchall()
    out = []
    for (cat, title, categoryId, price, dfee, drate, sales, rating, reviews, ltr) in rows:
        out.append({
            "id": f"nv_{cat}", "cat": cat, "title": title, "categoryId": categoryId,
            "price": int(price) if price is not None else None,
            "deliveryFee": int(dfee) if dfee is not None else None,
            "discountRate": round(drate, 3) if drate is not None else None,
            "rating": round(rating, 2) if rating is not None else None,
            "reviewCount": int(reviews) if reviews is not None else None,
            "longTermReviewRatio": round(ltr, 3) if ltr is not None else None,
            "recentSalesCount": int(sales or 0),
            "productUrl": f"https://search.shopping.naver.com/catalog/{cat}",
        })
    DATA.mkdir(exist_ok=True)
    CAND_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n후보 {len(out)}개 → {CAND_OUT}")
    for it in out[:12]:
        print(f"   {(it['price'] or 0):>8,}원 · 구매 {it['recentSalesCount']:>5} · ⭐{it['rating']} "
              f"· 리뷰 {it['reviewCount'] or 0:>5} · 장기 {it['longTermReviewRatio']} | {it['title'][:34]}")


LABELS_OUT = Path(__file__).resolve().parents[1] / "seed" / "labels" / "여성아우터.json"
POOL_CATEGORY = "코트·패딩·자켓"  # 풀/taxonomy 키와 일치 (garmentType는 attributes+태그로 보존)

# 라벨 도출 — gender+garment는 API가 확정했으니(garmentType), 남은 태그는 garmentType+제목 키워드로.
GARMENT_TAG = {  # API category4 → vocab garment 태그
    "기타코트": "코트", "롱코트": "코트", "숏코트": "코트", "트렌치코트": "코트", "레인코트": "코트", "코트": "코트",
    "재킷": "자켓", "레더재킷": "자켓", "무스탕": "자켓", "후드집업": "점퍼", "패딩": "패딩", "베스트": None,
}
MATERIALS = ["캐시미어", "양모", "울", "트위드", "플리스", "후리스", "덕다운", "구스", "웰론", "벨벳",
             "코듀로이", "데님", "무스탕", "퀼팅", "뽀글", "나일론"]
WARM_KW = ["패딩", "무스탕", "양모", "울", "플리스", "후리스", "웰론", "덕다운", "구스", "기모", "푸퍼",
           "캐시미어", "뽀글", "다운", "웜", "방한"]
LIGHT_KW = ["경량", "초경량", "라이트", "바람막이", "윈드브레이커", "윈드"]
FORMAL_KW = ["트위드", "테일러", "벨벳", "포멀", "정장", "자켓팬츠"]
CASUAL_KW = ["후드", "집업", "바람막이", "플리스", "후리스", "데님", "캐주얼", "뽀글", "조거"]


def _derive_label(p: dict) -> dict:
    """제목+garmentType에서 vocab 태그/attributes/shortDesc 도출 (제목 근거만, 환각 없음)."""
    title = p["title"]
    g = (p.get("attributes") or {}).get("garmentType") or p.get("category") or ""
    tags: list[str] = []
    garment = GARMENT_TAG.get(g)
    if garment:
        tags.append(garment)
    # 길이 — garmentType 우선, 없으면 제목
    if g == "롱코트" or "롱" in title or "맥시" in title:
        tags.append("롱")
    elif g == "숏코트" or "숏" in title or "크롭" in title:
        tags.append("숏")
    if any(k in title for k in WARM_KW) or garment == "패딩":
        tags.append("방한")
    if any(k in title for k in LIGHT_KW):
        tags.append("경량")
    if any(k in title for k in FORMAL_KW):
        tags.append("포멀")
    if any(k in title for k in CASUAL_KW):
        tags.append("캐주얼")
    if "데일리" in title:
        tags.append("데일리")
    tags = list(dict.fromkeys(tags))  # 중복 제거, 순서 보존

    attrs: dict = {}
    material = next((m for m in MATERIALS if m in title), None)
    if material:
        attrs["material"] = material
    if "롱" in tags:
        attrs["length"] = "롱"
    elif "숏" in tags:
        attrs["length"] = "숏"
    desc = (f"{material} 소재의 " if material else "") + f"여성 {garment or g or '아우터'}이다."
    return {"id": p["id"], "tags": tags, "attributes": attrs, "shortDesc": desc}


def label() -> None:
    """[F-③] rule-based 라벨링 — products_womens_outer.json에 tags/description/category 병합 +
    seed/labels/여성아우터.json(리뷰용) 기록. gender+garment는 API가 확정, 나머지만 도출."""
    prods = json.loads(VERIFY_OUT.read_text(encoding="utf-8"))
    labels = [_derive_label(p) for p in prods]
    by_id = {lb["id"]: lb for lb in labels}
    for p in prods:
        lb = by_id[p["id"]]
        attrs = dict(p.get("attributes") or {})
        attrs.update(lb["attributes"])  # material/length 보강 (categoryId/categoryPath/gender/garmentType 유지)
        p["attributes"] = attrs
        p["tags"] = lb["tags"]
        p["description"] = lb["shortDesc"]
        p["category"] = POOL_CATEGORY  # garmentType이 아니라 풀/taxonomy 키로 통일
    VERIFY_OUT.write_text(json.dumps(prods, ensure_ascii=False, indent=2), encoding="utf-8")
    LABELS_OUT.write_text(json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8")
    from collections import Counter
    tagc = Counter(t for lb in labels for t in lb["tags"])
    empty = [lb["id"] for lb in labels if not lb["tags"]]
    print(f"라벨링 {len(labels)}개 → {VERIFY_OUT.name} (병합) + {LABELS_OUT.name}")
    print("태그 분포:", dict(tagc.most_common()))
    print(f"빈 태그: {len(empty)}개")
    for p in prods[:8]:
        print(f"   {p['tags']} | {p['title'][:38]}")


def verify(limit: int = 0, sleep: float = 0.12) -> None:
    """[F-②] 후보를 네이버 API 검색 → best_match(Jaccard≥0.3) → category2=여성의류 & category3=아우터
    게이트만 통과 + image/categoryPath/lowestPrice enrich. 매칭 실패/타카테고리는 탈락(정밀도 우선)."""
    import time
    import urllib.error

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from enrich_naver_images import best_match, category_path, clean_query, search  # 검증된 로직 재사용

    cands = json.loads(CAND_OUT.read_text(encoding="utf-8"))
    if limit:
        cands = cands[:limit]
    kept: list[dict] = []
    dropped = errored = 0
    garments: dict[str, int] = {}
    print(f"API 게이트: 후보 {len(cands)}개 → category2=여성의류 & category3=아우터 통과만")
    for i, c in enumerate(cands, 1):
        try:
            items = search(clean_query(c["title"]))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print("  429 rate limit — sleep 5s"); time.sleep(5); continue
            errored += 1; continue
        except Exception:  # noqa: BLE001
            errored += 1; continue
        m = best_match(items, c)
        if m and m.get("category1") == "패션의류" and m.get("category2") == "여성의류" and m.get("category3") == "아우터":
            g = m.get("category4") or "기타"
            garments[g] = garments.get(g, 0) + 1
            lprice = int(m["lprice"]) if str(m.get("lprice", "")).isdigit() else None
            kept.append({
                "id": c["id"], "title": c["title"], "category": g,
                "brand": (m.get("brand") or m.get("maker") or None),
                "price": c["price"], "deliveryFee": c["deliveryFee"], "discountRate": c["discountRate"],
                "rating": c["rating"], "reviewCount": c["reviewCount"],
                "longTermReviewRatio": c["longTermReviewRatio"], "recentSalesCount": c["recentSalesCount"],
                "sellerName": m.get("mallName"), "sellerGrade": None, "sellerYears": None,
                "imageUrl": m.get("image") or None, "productUrl": m.get("link") or c["productUrl"],
                "attributes": {
                    "categoryId": c["categoryId"], "domain": "의류", "gender": "여성", "garmentType": g,
                    "categoryPath": category_path(m), "lowestPrice": lprice,
                },
                "description": None,
            })
        else:
            dropped += 1
        if i % 25 == 0:
            print(f"  {i}/{len(cands)} · 통과 {len(kept)} 탈락 {dropped} 에러 {errored}")
            VERIFY_OUT.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(sleep)
    VERIFY_OUT.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n통과 {len(kept)} · 탈락 {dropped} · 에러 {errored} → {VERIFY_OUT.name}")
    print("garment 분포:", dict(sorted(garments.items(), key=lambda x: -x[1])))
    for it in kept[:10]:
        print(f"   {(it['price'] or 0):>8,}원 · {it['attributes']['categoryPath']} | {it['title'][:30]}")


POOL_FILE = Path(__file__).resolve().parents[1] / "seed_naver" / "products.json"  # 스터디 풀 (VC_SEED_DIR=seed_naver)


def merge_pool() -> None:
    """[F-④a] 라벨링된 여성 아우터를 스터디 풀(seed_naver/products.json)에 병합 (백업·중복스킵)."""
    pool = json.loads(POOL_FILE.read_text(encoding="utf-8"))
    new = json.loads(VERIFY_OUT.read_text(encoding="utf-8"))
    new_ids = {p["id"] for p in new}
    # 중복 id(같은 catalogId)는 *교체* — 검증+라벨링된 깨끗한 버전이 이긴다(오분류 교정).
    kept = [p for p in pool if p["id"] not in new_ids]
    replaced = len(pool) - len(kept)
    bak = POOL_FILE.with_name("products.json.bak_pre_womens_outer")
    if not bak.exists():  # 원본 보존 — 재실행해도 첫 백업(원본 509)을 덮어쓰지 않음
        bak.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding="utf-8")
    merged = kept + new
    POOL_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    bands = {"5~10만": 0, "10~20만": 0, "20~40만": 0}
    for p in new:
        pr = p.get("price") or 0
        if pr < 100000: bands["5~10만"] += 1
        elif pr < 200000: bands["10~20만"] += 1
        else: bands["20~40만"] += 1
    print(f"풀 {len(kept)}(유지) + 여성아우터 {len(new)}(교체 {replaced}) = {len(merged)} → {POOL_FILE.name}")
    print(f"백업: {bak.name} · 여성아우터 가격대 분포: {bands}")


def verify_pool() -> None:
    """[F-④b] 실 로더+FTS+임베딩으로 새 풀을 적재하고 '코트' 질의에 여성 코트가 노출되는지 검증.
    라이브와 같은 의미검색 경로(.env가 deepseek+OPENAI_KEY → enabled). 새 상품만 증분 임베딩하며
    seed_naver/product_vectors.json 캐시를 pre-warm한다.
    실행: VC_SEED_DIR=seed_naver .venv/bin/python scripts/build_womens_outerwear.py verify_pool"""
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
    embeddings.ensure_product_vectors(db.query(models.Product).all())  # 증분: 새 상품만 임베딩 + 캐시 pre-warm
    mode = "임베딩(의미검색)" if (embeddings.enabled() and embeddings._loaded) else "BM25 폴백"
    print(f"풀 적재 {n}개 + FTS + 벡터. retrieve 경로: {mode}.")

    for q, pmin, pmax in [("코트 추천해줘", None, None), ("여성 코트", 100000, 200000), ("따뜻한 겨울 코트", None, None)]:
        pool = search_products(db, query=q, category=None, hard_constraints=[], soft_preferences=[],
                               topic_labels=[], avoidances=[], price_min=pmin, price_max=pmax,
                               return_pool=True, pool_size=10)
        womens = [sp for sp in pool if (sp.product.attributes or {}).get("gender") == "여성"]
        print(f"\nQ={q!r} band={pmin}~{pmax} → 풀 {len(pool)}개 중 여성아우터 {len(womens)}개")
        for sp in pool[:5]:
            g = (sp.product.attributes or {}).get("gender", "-")
            print(f"   [{g}] {(sp.product.price or 0):>8,}원 · {sp.product.tags} | {sp.product.title[:30]}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if mode == "probe":
        probe(PRODUCT, "PRODUCT"); probe(PURCHASE, "PURCHASE"); probe(REVIEW, "REVIEW")
    elif mode == "candidates":
        pmin = int(sys.argv[2]) if len(sys.argv) > 2 else 50000
        pmax = int(sys.argv[3]) if len(sys.argv) > 3 else 400000
        limit = int(sys.argv[4]) if len(sys.argv) > 4 else 800
        candidates(pmin, pmax, limit)
    elif mode == "verify":
        verify(limit=int(sys.argv[2]) if len(sys.argv) > 2 else 0)
    elif mode == "label":
        label()
    elif mode == "merge":
        merge_pool()
    elif mode == "verify_pool":
        verify_pool()

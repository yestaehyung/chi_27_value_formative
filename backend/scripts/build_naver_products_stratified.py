"""세부 카테고리 stratified 샘플러 — products_stratified.json 생성 (안전: products.json 안 건드림).

build_naver_products.py가 "도메인(전자기기/의류)별 구매수 top-300"이라 이어폰 과대표·코트 공백이
생겼다. 여기서는 **세부 카테고리(무선이어폰/노트북/원피스/니트/코트…)별로 구매수 상위 N개**를 뽑아
카테고리 다양성을 확보한다(각 카테고리 내 품질=구매수 상위 유지). niche 주입은 하지 않는다.

키워드 분류는 brittle하므로 (1) 전역 제외어(피규어·키링·파우치 등 액세서리/굿즈),
(2) 카테고리별 정밀 제외, (3) 가격 하한으로 노이즈를 거른다. (근본해법은 NAVER API category1~4
기반 라벨링 — 다른 세션 enrich와 합류 시 교체 가능.)
"""
import json
import re
from pathlib import Path

import duckdb

SRC = {"f1": "/tmp/nv/s1.tsv", "f2": "/tmp/nv/s2.tsv", "f4": "/tmp/nv/s4.tsv"}
PER_CATEGORY = 50
MIN_PRICE = 3000  # 옵션가/부속 artifact 제거
OUT = Path(__file__).resolve().parents[1] / "seed" / "products_stratified.json"
OPT = "delim='\t', header=false, all_varchar=true, ignore_errors=true, quote=''"

# 모든 카테고리에 적용되는 제외 (피규어·캐릭터굿즈·액세서리류)
GLOBAL_EXCLUDE = r"라부부|피규어|팝마트|인형|키링|스티커|소품|굿즈|장난감|카드|뱃지|배지|파우치|케이스|커버|거치|받침|스탠드|클리너|청소|충전기|어댑터|케이블|보호필름|강화유리|필름|액정|스킨|젠더|악세|액세서리|워시|가글|잠금|데스크매트|장패드|미니마우스|미키"

# (카테고리명, 도메인, include, 추가 exclude). 순서 = 우선순위(첫 매칭).
TAXONOMY = [
    ("무선이어폰", "전자기기", r"이어폰|에어팟|갤럭시버즈|버즈프로|블루투스이어폰",
     r"백|가방|이어팁|이어캡|잭|행거|줄"),
    ("헤드셋·헤드폰", "전자기기", r"헤드셋|헤드폰", r"옷|신발|우비|안경"),
    ("노트북", "전자기기", r"노트북|갤럭시북|맥북",
     r"슬리브|가방|쿨러|키스킨|HDD|메모리|비타민|영양제|프로그램|건강|받침|마우스|패드"),
    ("태블릿", "전자기기", r"태블릿|갤럭시탭|아이패드", r"펜|키보드|충전"),
    ("키보드·마우스", "전자기기", r"키보드|마우스", r"패드|손목|장갑|디즈니|원피스"),
    ("모니터", "전자기기", r"모니터",
     r"에어|측정|이산화탄소|온습도|경보|혈압|cctv|베이비|아기|차량|혈당|심박"),
    ("원피스", "의류", r"원피스", r"수영복|강아지|애견"),
    ("니트·가디건", "의류", r"니트|가디건|카디건|스웨터",
     r"보풀|제거기|팬츠|바지|장갑|모자|양말|치마|스커트"),
    ("코트·패딩·자켓", "의류", r"코트|패딩|자켓|재킷|점퍼|야상",
     r"레인코트|마스코트|스킨앤코트|트리코트|테니스|우비|우의|침대|매트|강아지|반려|차량|마우스"),
    ("팬츠·바지", "의류", r"팬츠|바지|청바지|슬랙스|레깅스|조거", r"보정|복대|강아지"),
    ("티셔츠·셔츠", "의류", r"티셔츠|반팔|긴팔|맨투맨|후드|셔츠|블라우스", r"강아지"),
    ("잠옷·홈웨어", "의류", r"잠옷|파자마|홈웨어|실내복|수면바지", r"강아지"),
    ("수영복·래쉬가드", "의류", r"수영복|래쉬가드|비치웨어|보드숏", r"강아지"),
]

_GLOBAL = re.compile(GLOBAL_EXCLUDE)


def classify(title: str):
    if _GLOBAL.search(title):
        return None, None
    for name, domain, inc, exc in TAXONOMY:
        if re.search(inc, title) and not (exc and re.search(exc, title)):
            return name, domain
    return None, None


def main() -> None:
    con = duckdb.connect()
    rows = con.execute(f"""
      WITH prod AS (
        SELECT column2 AS cat, any_value(column4) AS title, any_value(column3) AS categoryId
        FROM read_csv('{SRC['f1']}', {OPT})
        WHERE column8='판매중' AND column2 IS NOT NULL AND column2<>'NULL' GROUP BY column2),
      price AS (
        SELECT column02 AS cat, median(TRY_CAST(column09 AS BIGINT)) AS price,
               median(TRY_CAST(column20 AS BIGINT)) AS delivery_fee,
               avg(CASE WHEN TRY_CAST(column09 AS BIGINT)>0
                        THEN TRY_CAST(column11 AS BIGINT)*1.0/TRY_CAST(column09 AS BIGINT) END) AS discount_rate,
               count(*) AS sales
        FROM read_csv('{SRC['f4']}', {OPT})
        WHERE TRY_CAST(column09 AS BIGINT)>0 AND column02 IS NOT NULL AND column02<>'NULL' GROUP BY column02),
      rev AS (
        SELECT column02 AS cat, avg(TRY_CAST(column14 AS DOUBLE)) AS rating, count(*) AS reviews,
               sum(CASE WHEN column07='한달사용' THEN 1 ELSE 0 END)*1.0/count(*) AS ltr
        FROM read_csv('{SRC['f2']}', {OPT})
        WHERE column16='정상' AND column02 IS NOT NULL AND column02<>'NULL' GROUP BY column02)
      SELECT p.cat, p.title, p.categoryId, pr.price, pr.delivery_fee, pr.discount_rate, pr.sales,
             r.rating, r.reviews, r.ltr
      FROM prod p JOIN price pr USING(cat) LEFT JOIN rev r USING(cat)
      WHERE pr.price >= {MIN_PRICE}
    """).fetchall()
    print(f"join된 후보(판매중+구매기록+정가>={MIN_PRICE}): {len(rows):,}개")

    buckets: dict[str, list] = {}
    for (cat, title, categoryId, price, dfee, drate, sales, rating, reviews, ltr) in rows:
        name, domain = classify(title or "")
        if not name:
            continue
        buckets.setdefault(name, []).append(
            dict(cat=cat, title=title, categoryId=categoryId, domain=domain, price=price,
                 dfee=dfee, drate=drate, sales=sales or 0, rating=rating, reviews=reviews, ltr=ltr))

    products = []
    for name, _, _, _ in TAXONOMY:
        items = sorted(buckets.get(name, []), key=lambda x: x["sales"], reverse=True)[:PER_CATEGORY]
        print(f"\n━ {name}  ({len(items)}개 선정 / {len(buckets.get(name, []))} 가용)")
        for it in items[:3]:
            print(f"    {int(it['price']):>8,}원 · 구매 {it['sales']:>5} · ⭐{it['rating']} | {it['title'][:38]}")
        for it in items:
            products.append({
                "id": f"nv_{it['cat']}", "title": it["title"], "category": name, "brand": None,
                "price": int(it["price"]) if it["price"] is not None else None,
                "deliveryFee": int(it["dfee"]) if it["dfee"] is not None else None,
                "discountRate": round(it["drate"], 3) if it["drate"] is not None else None,
                "rating": round(it["rating"], 2) if it["rating"] is not None else None,
                "reviewCount": int(it["reviews"]) if it["reviews"] is not None else None,
                "longTermReviewRatio": round(it["ltr"], 3) if it["ltr"] is not None else None,
                "recentSalesCount": int(it["sales"]),
                "sellerName": None, "sellerGrade": None, "sellerYears": None, "imageUrl": None,
                "productUrl": f"https://search.shopping.naver.com/catalog/{it['cat']}",
                "attributes": {"categoryId": it["categoryId"], "domain": it["domain"]},
                "description": None,
            })

    OUT.write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n총 {len(products)}개 → {OUT}")


if __name__ == "__main__":
    main()

"""Build seed/products_naver.json from the real NAVER Smart Store dumps.

ETL (offline, one-shot): read 4 headerless TSV dumps, join on the 19-digit
catalogId, aggregate price/rating/reviews/popularity, filter to 전자(기기)+의류,
sample N per domain, emit products.json (existing schema). NO LLM enrichment yet
(brand/attributes left empty by design — see docs/plans/2026-06-16-...-design.md).

Column maps (header=false → DuckDB names; width depends on #cols per file):
  File1 catalog (9col):  c2=catalogId c3=categoryId c4=title c8=status
  File2 review  (18col): c02=catalogId c07=type(일반/한달사용) c14=score(1-5) c16=pubstat
  File4 purchase(26col): c02=catalogId c09=정가(list) c11=할인 c20=배송비

Default reads the bounded samples in /tmp/nv (fast). For the full run, point
SRC at the .csv.gz files directly (DuckDB streams gz).
"""
import json
from pathlib import Path

import duckdb

# --- config ----------------------------------------------------------------
SRC = {                       # swap to the .csv.gz paths for the full run
    "f1": "/tmp/nv/s1.tsv",
    "f2": "/tmp/nv/s2.tsv",
    "f4": "/tmp/nv/s4.tsv",
}
N_PER_DOMAIN = 300
OUT = Path(__file__).resolve().parents[1] / "seed" / "products_naver.json"

DEVICE = "스마트워치|갤럭시워치|애플워치|이어폰|에어팟|갤럭시버즈|버즈프로|헤드폰|헤드셋|노트북|태블릿|아이패드|갤럭시탭"
DEVICE_EXCLUDE = "필름|케이스|강화유리|보호|거치대|충전|스트랩|케이블|어댑터|파우치|그립|스탠드|받침|커버|클리너|젠더|독|홀더|악세|액세서리|터치펜|펜슬|HDD|하드디스크|메모리|클렌징|스킨"
CLOTH = "티셔츠|반팔|긴팔|맨투맨|후드|니트|가디건|카디건|셔츠|블라우스|원피스|스커트|바지|청바지|슬랙스|팬츠|레깅스|조거|자켓|재킷|코트|패딩|점퍼|잠옷|파자마|수영복|트레이닝복"

OPT = "delim='\t', header=false, all_varchar=true, ignore_errors=true, quote=''"


def main() -> None:
    con = duckdb.connect()
    con.execute(f"""
    CREATE TEMP VIEW prod AS
      SELECT column2 AS cat, any_value(column4) AS title, any_value(column3) AS categoryId
      FROM read_csv('{SRC['f1']}', {OPT})
      WHERE column8='판매중' AND column2 IS NOT NULL AND column2<>'NULL' GROUP BY column2;

    CREATE TEMP VIEW price AS
      SELECT column02 AS cat,
             median(TRY_CAST(column09 AS BIGINT))                         AS price,
             median(TRY_CAST(column20 AS BIGINT))                         AS delivery_fee,
             avg(CASE WHEN TRY_CAST(column09 AS BIGINT)>0
                      THEN TRY_CAST(column11 AS BIGINT)*1.0/TRY_CAST(column09 AS BIGINT) END) AS discount_rate,
             count(*)                                                     AS sales
      FROM read_csv('{SRC['f4']}', {OPT})
      WHERE TRY_CAST(column09 AS BIGINT)>0 AND column02 IS NOT NULL AND column02<>'NULL'
      GROUP BY column02;

    CREATE TEMP VIEW rev AS
      SELECT column02 AS cat,
             avg(TRY_CAST(column14 AS DOUBLE))                            AS rating,
             count(*)                                                     AS reviews,
             sum(CASE WHEN column07='한달사용' THEN 1 ELSE 0 END)*1.0/count(*) AS ltr_ratio
      FROM read_csv('{SRC['f2']}', {OPT})
      WHERE column16='정상' AND column02 IS NOT NULL AND column02<>'NULL' GROUP BY column02;

    CREATE TEMP VIEW joined AS
      SELECT p.cat, p.title, p.categoryId,
             pr.price, pr.delivery_fee, pr.discount_rate, pr.sales,
             r.rating, r.reviews, r.ltr_ratio,
             CASE
               WHEN regexp_matches(p.title, '{DEVICE}')
                    AND NOT regexp_matches(p.title, '{DEVICE_EXCLUDE}') THEN '전자기기'
               WHEN regexp_matches(p.title, '{CLOTH}')                  THEN '의류'
             END AS domain
      FROM prod p JOIN price pr USING(cat) LEFT JOIN rev r USING(cat);
    """)

    rows = con.execute(f"""
      WITH ranked AS (
        SELECT *, row_number() OVER (PARTITION BY domain ORDER BY sales DESC) rn
        FROM joined WHERE domain IS NOT NULL
      )
      SELECT cat, title, categoryId, domain, price, delivery_fee, discount_rate,
             sales, rating, reviews, ltr_ratio
      FROM ranked WHERE rn <= {N_PER_DOMAIN}
    """).fetchall()

    products = []
    for (cat, title, categoryId, domain, price, dfee, drate, sales,
         rating, reviews, ltr) in rows:
        products.append({
            "id": f"nv_{cat}",
            "title": title,
            "category": domain,                         # domain-level (priceCue relativity)
            "brand": None,                              # no enrichment yet
            "price": int(price) if price is not None else None,
            "deliveryFee": int(dfee) if dfee is not None else None,
            "discountRate": round(drate, 3) if drate is not None else None,
            "rating": round(rating, 2) if rating is not None else None,
            "reviewCount": int(reviews) if reviews is not None else None,
            "longTermReviewRatio": round(ltr, 3) if ltr is not None else None,
            "recentSalesCount": int(sales) if sales is not None else None,
            "sellerName": None, "sellerGrade": None, "sellerYears": None,
            "imageUrl": None,
            "productUrl": f"https://search.shopping.naver.com/catalog/{cat}",
            "attributes": {"categoryId": categoryId, "domain": domain},
            "description": None,                        # no generated copy yet
            # cueSummary omitted → seed_loader derives it (category-relative price)
        })

    OUT.write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- report ---
    by = {}
    for p in products:
        by[p["category"]] = by.get(p["category"], 0) + 1
    print(f"wrote {len(products)} products → {OUT}")
    print("도메인별:", by, "\n")
    print(f"{'도메인':>6} | {'정가':>8} | {'배송':>5} | {'판매':>6} | {'평점':>4} | {'리뷰':>6} | {'한달%':>5} | 상품명")
    print("-" * 110)
    for dom in ("전자기기", "의류"):
        shown = [p for p in products if p["category"] == dom][:8]
        for p in shown:
            pr = f"{p['price']:,}" if p['price'] else "-"
            df = f"{p['deliveryFee']:,}" if p['deliveryFee'] else "0"
            rt = f"{p['rating']:.2f}" if p['rating'] else " -"
            rv = f"{p['reviewCount']:,}" if p['reviewCount'] else "-"
            lt = f"{p['longTermReviewRatio']*100:.0f}%" if p['longTermReviewRatio'] is not None else "-"
            print(f"{dom:>6} | {pr:>8} | {df:>5} | {p['recentSalesCount']:>6,} | {rt:>4} | {rv:>6} | {lt:>5} | {p['title'][:34]}")


if __name__ == "__main__":
    main()

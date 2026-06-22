"""노이즈 상품 제거 — 리퍼/중고 + 잔존 오분류 + 전자 가격매핑오류.

가격은 임의 교정하지 않는다(검증 안 된 수식). 명백한 매핑 오류(lowest>price*3, 전자)는
'제거'만 한다. 제거된 자리는 별도로 합성 상품으로 채운다(remove → synthesize 파이프라인).

원본 비파괴: seed_naver/products.json 백업(.prenoise.bak), DB 동기 삭제.
사용: PYTHONPATH=. .venv/bin/python scripts/remove_noise_products.py [--apply]
"""
import argparse
import json
import shutil
import sqlite3
from collections import Counter

from app.core.config import BACKEND_DIR, settings

SEED = BACKEND_DIR / "seed_naver" / "products.json"

USED_KW = ["중고", "리퍼", "[리퍼]", "A급", "B급", "단순개봉", "개조", "미개봉"]
MISCAT_KW = ["CCTV", "사이니지", "DID", "랜덤발송", "공동구매", "공구", "렌탈", "렌트",
             "대여", "임대", "패키지", "드로잉", "전자칠판", "뇌새김", "야외스냅", "셀프웨딩"]
ELEC = {"노트북", "태블릿", "모니터"}
# 패션 노이즈(잠옷·아기·임부·옷본 등)는 키워드가 아니라 LLM 재분류로 거른다
# (scripts/reclassify_categories.py) — "패턴"=무늬 vs 옷본 같은 모호함을 키워드론 못 가림.


def removal_reason(p: dict) -> str | None:
    t = p.get("title") or ""
    cat = p.get("category")
    price = p.get("price")
    low = (p.get("attributes") or {}).get("lowestPrice")
    for k in USED_KW:
        if k in t:
            return f"used/refurb~'{k}'"
    for k in MISCAT_KW:
        if k in t:
            return f"miscat~'{k}'"
    if cat in ELEC and low and price and low > price * 3:
        return f"price_error(low={low}>price={price}*3)"
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    products = json.loads(SEED.read_text(encoding="utf-8"))
    keep, drop = [], []
    for p in products:
        r = removal_reason(p)
        (drop if r else keep).append((p, r))

    print(f"전체 {len(products)} → 유지 {len(keep)}, 제거 {len(drop)}\n")
    by_reason = Counter(r.split("~")[0].split("(")[0] for _, r in drop)
    print("=== 제거 사유별 ===")
    for reason, n in by_reason.most_common():
        print(f"  {reason:<18} {n}")
    print("\n=== 제거 후 카테고리별 잔존 ===")
    kept_cat = Counter(p["category"] for p, _ in keep)
    for c, n in sorted(kept_cat.items(), key=lambda x: -x[1]):
        print(f"  {c:<16} {n}")
    print("\n=== 제거 샘플 (20개) ===")
    for p, r in drop[:20]:
        print(f"  [{r}] {p['title'][:44]}")

    if not args.apply:
        print("\n(dry-run — 적용하려면 --apply)")
        return

    kept_products = [p for p, _ in keep]
    keep_ids = {p["id"] for p in kept_products}
    shutil.copy(SEED, SEED.with_suffix(".json.prenoise.bak"))
    SEED.write_text(json.dumps(kept_products, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ seed 갱신 ({len(kept_products)}개), 백업 .prenoise.bak")

    db = sqlite3.connect(settings.db_path)
    cur = db.cursor()
    cur.execute("SELECT id FROM products")
    allids = {r[0] for r in cur.fetchall()}
    todel = allids - keep_ids
    cur.executemany("DELETE FROM products WHERE id=?", [(i,) for i in todel])
    db.commit()
    db.close()
    print(f"✓ DB 삭제 {len(todel)}개 (남은 {len(keep_ids)})")


if __name__ == "__main__":
    main()

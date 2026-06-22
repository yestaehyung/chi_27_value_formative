"""상품 풀 정리 — 시나리오에 쓰이는 카테고리만 남기고 노이즈 제거 (formative study WoZ).

제거 대상:
  1) 시나리오(+관련 묶음)에 안 속하는 category 전체 (잠옷·수영복·페인트·기저귀 등)
  2) 카테고리 내 용도 이탈 — categoryPath/제목 기반 (무전기 이어폰, 노트북 액세서리 등)

원본 비파괴: seed_naver/products.json 은 백업 후 덮어쓰기. nv_study.db 도 동기 삭제.
사용: PYTHONPATH=. .venv/bin/python scripts/clean_product_pool.py [--apply]
      (--apply 없으면 dry-run: 무엇이 지워질지만 출력)
"""
import argparse
import json
import shutil
import sqlite3
from pathlib import Path

from app.core.config import BACKEND_DIR, settings

SEED = BACKEND_DIR / "seed_naver" / "products.json"

# 시나리오가 쓰는 category + 관련 묶음(코디/이어폰묶음). 풀의 실제 category 값 기준.
KEEP_CATEGORIES = {
    # 전자
    "무선이어폰", "헤드셋·헤드폰", "노트북", "모니터", "태블릿", "키보드·마우스",
    # 패션 (원피스/니트/코트 시나리오 + 코디 묶음)
    "원피스", "니트·가디건", "코트·패딩·자켓", "티셔츠·셔츠", "팬츠·바지",
}

# 카테고리 내 용도 이탈 — categoryPath에 이 토큰이 있으면 제거 (예: 무전기 액세서리)
DROP_IF_PATH_CONTAINS = ["무전기", "공유기", "케이블", "어댑터", "충전기", "거치대"]

# 제목 기반 노이즈 (액세서리·부품 — 본 상품이 아님)
DROP_IF_TITLE_CONTAINS = [
    "펜촉", "펜팁", "USB 허브", "USB허브", "멀티허브", "멀티포트", "인터넷선", "인터넷연결선",
    "랜케이블", "공유기", "브라켓", "거치대", "받침대", "선택기", "마우스 반지", "리모컨 마우스 반지",
    "노트북 백팩", "노트북백팩", "노트북 가방", "파우치", "보호필름", "강화유리", "키스킨", "키캡",
    "속지", "플래너", "단어장", "스케줄", "다이어리",
]


def should_keep(p: dict) -> tuple[bool, str]:
    cat = p.get("category")
    if cat not in KEEP_CATEGORIES:
        return False, f"category={cat!r} (시나리오 무관)"
    title = p.get("title") or ""
    cpath = (p.get("attributes") or {}).get("categoryPath") or ""
    for tok in DROP_IF_PATH_CONTAINS:
        if tok in cpath:
            return False, f"categoryPath~'{tok}'"
    for tok in DROP_IF_TITLE_CONTAINS:
        if tok in title:
            return False, f"title~'{tok}'"
    return True, ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제 적용(없으면 dry-run)")
    args = ap.parse_args()

    products = json.loads(SEED.read_text(encoding="utf-8"))
    keep, drop = [], []
    for p in products:
        ok, reason = should_keep(p)
        (keep if ok else drop).append((p, reason))

    print(f"전체 {len(products)} → 유지 {len(keep)}, 제거 {len(drop)}\n")

    # 카테고리별 유지 현황
    from collections import Counter
    kept_cats = Counter(p["category"] for p, _ in keep)
    print("=== 유지된 카테고리 ===")
    for c, n in kept_cats.most_common():
        print(f"  {c:<16} {n}")

    print(f"\n=== 제거 샘플 (처음 25개) ===")
    for p, reason in drop[:25]:
        print(f"  [{reason}] {p['title'][:45]}")
    if len(drop) > 25:
        print(f"  ... 외 {len(drop)-25}개")

    if not args.apply:
        print("\n(dry-run — 실제 적용하려면 --apply)")
        return

    kept_products = [p for p, _ in keep]
    keep_ids = {p["id"] for p in kept_products}

    # 1) seed 백업 + 덮어쓰기
    shutil.copy(SEED, SEED.with_suffix(".json.prebclean.bak"))
    SEED.write_text(json.dumps(kept_products, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ seed 갱신 ({len(kept_products)}개), 백업 .prebclean.bak")

    # 2) DB 동기 삭제 (products + 관련 임프레션은 세션 데이터라 보존 — FK 없음, 고아 무해)
    db = sqlite3.connect(settings.db_path)
    cur = db.cursor()
    cur.execute("SELECT id FROM products")
    all_ids = {r[0] for r in cur.fetchall()}
    to_del = all_ids - keep_ids
    cur.executemany("DELETE FROM products WHERE id = ?", [(i,) for i in to_del])
    db.commit()
    print(f"✓ DB products 삭제 {len(to_del)}개 (남은 {len(keep_ids)})")
    db.close()
    print("\n⚠️ 서버 재시작 필요 (FTS 인덱스 재구축 + 임베딩 캐시 갱신).")


if __name__ == "__main__":
    main()

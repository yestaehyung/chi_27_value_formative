"""상품 카테고리 LLM 재분류 — 네이버 원본 분류의 오류를 우리 시나리오 체계로 정정.

네이버 덤프 category는 부정확하다(무전기 이어폰이 무선이어폰에, 헤드셋에 이어폰 혼입 등).
LLM이 title + categoryPath를 보고 우리의 고정 카테고리 체계 중 하나로 재분류한다.
어느 것에도 안 맞으면 "OTHER"(→ 제외 후보).

description 생성과 동일 패턴: DeepSeek, 배치, resume, 사실 기반(제목/경로만).
사용: PYTHONPATH=. .venv/bin/python scripts/reclassify_categories.py --limit 5   # 검증
      PYTHONPATH=. .venv/bin/python scripts/reclassify_categories.py              # 전체
      PYTHONPATH=. .venv/bin/python scripts/reclassify_categories.py --apply      # seed+DB 반영
"""
import argparse
import asyncio
import json
import shutil
import sqlite3
from pathlib import Path

from app.core.config import BACKEND_DIR, settings
from app.llm.provider import LLMMessage, get_provider

SEED = BACKEND_DIR / "seed_naver" / "products.json"
OUT = BACKEND_DIR / "seed_naver" / "category_reclassified.json"

# 고정 카테고리 체계 (시나리오 10개 + 관련 묶음). 풀 category 값과 동일 표기.
CATEGORIES = [
    "무선이어폰", "헤드셋·헤드폰", "노트북", "모니터", "태블릿", "키보드·마우스",
    "원피스", "니트·가디건", "코트·패딩·자켓", "티셔츠·셔츠", "팬츠·바지",
]

SYSTEM = f"""너는 쇼핑 상품을 정해진 카테고리 체계로 분류하는 분류기다.
상품의 제목과 원본 카테고리경로를 보고, 아래 목록 중 **정확히 하나**를 고른다.

카테고리 목록:
{chr(10).join(f"- {c}" for c in CATEGORIES)}

규칙:
1. 제목과 경로의 실제 제품 본질로 판단한다. (예: '무전기 리시버 이어폰'은 일반 무선이어폰이
   아니므로 OTHER. '게이밍 헤드셋'은 헤드셋·헤드폰. '마우스패드'는 키보드·마우스 아님 → OTHER.)
2. 이어폰(귀에 꽂는 것)과 헤드셋·헤드폰(머리에 쓰는 것)을 구분한다.
3. 액세서리·부품·소모품(케이스, 거치대, 패드, 필름 등)은 본 제품이 아니므로 OTHER.
4. 목록 어디에도 명확히 안 맞으면 "OTHER".
5. JSON으로만 답한다: {{"category": "<목록 중 하나 또는 OTHER>", "reason": "<짧은 근거>"}}"""


async def classify_one(provider, p: dict) -> dict | None:
    ctx = {
        "제목": p.get("title"),
        "원본카테고리경로": (p.get("attributes") or {}).get("categoryPath") or p.get("category"),
        "현재카테고리": p.get("category"),
    }
    try:
        out = await provider.generate_json(
            [LLMMessage(role="system", content=SYSTEM),
             LLMMessage(role="user", content=json.dumps(ctx, ensure_ascii=False))],
            task="category_classification", context=ctx,
        )
        cat = (out or {}).get("category")
        if cat in CATEGORIES or cat == "OTHER":
            return {"category": cat, "reason": (out or {}).get("reason", "")}
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ {p['id']}: {type(e).__name__}: {str(e)[:50]}")
    return None


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--apply", action="store_true", help="결과를 seed+DB에 반영")
    args = ap.parse_args()

    products = json.loads(SEED.read_text(encoding="utf-8"))

    # --apply: 이미 생성된 결과를 seed+DB에 반영하고 종료
    if args.apply:
        if not OUT.exists():
            print("✗ category_reclassified.json 없음 — 먼저 분류 실행")
            return
        result = json.loads(OUT.read_text(encoding="utf-8"))
        changed = [(p, result[p["id"]]["category"]) for p in products
                   if p["id"] in result and result[p["id"]]["category"] != p["category"]]
        others = [pid for pid, r in result.items() if r["category"] == "OTHER"]
        print(f"변경 {len(changed)}개, OTHER(제외후보) {len(others)}개")
        for p, newcat in changed[:30]:
            print(f"  {p['category']:<12} → {newcat:<12} | {p['title'][:40]}")
        if len(changed) > 30:
            print(f"  ... 외 {len(changed)-30}개")

        # seed 백업 + 갱신 (OTHER는 제외, 나머지는 category 교체)
        shutil.copy(SEED, SEED.with_suffix(".json.precat.bak"))
        kept = []
        for p in products:
            r = result.get(p["id"])
            if r is None:
                kept.append(p); continue
            if r["category"] == "OTHER":
                continue  # 제외
            p["category"] = r["category"]
            kept.append(p)
        SEED.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n✓ seed 갱신 ({len(kept)}개, OTHER {len(products)-len(kept)}개 제외), 백업 .precat.bak")

        # DB 반영
        keep_ids = {p["id"] for p in kept}
        db = sqlite3.connect(settings.db_path); cur = db.cursor()
        for p in kept:
            cur.execute("UPDATE products SET category=? WHERE id=?", (p["category"], p["id"]))
        cur.execute("SELECT id FROM products"); allids = {r[0] for r in cur.fetchall()}
        for i in allids - keep_ids:
            cur.execute("DELETE FROM products WHERE id=?", (i,))
        db.commit(); db.close()
        print(f"✓ DB 갱신 + OTHER {len(allids-keep_ids)}개 삭제")
        print("\n⚠️ 서버 재시작 필요 (FTS·임베딩 캐시 재구축). 옛 product_vectors.json 삭제 권장.")
        return

    # 분류 실행
    if settings.llm_provider == "mock":
        print("✗ mock — 실제 provider 필요"); return
    provider = get_provider()
    print(f"provider={provider.name}, model={getattr(provider,'model','?')}")

    existing = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    todo = [p for p in products if p["id"] not in existing]
    if args.limit:
        todo = todo[:args.limit]
    print(f"분류 대상 {len(todo)}개 (전체 {len(products)}, 기존 {len(existing)})\n")

    sem = asyncio.Semaphore(args.concurrency)
    results = dict(existing)
    done = 0

    async def work(p):
        nonlocal done
        async with sem:
            r = await classify_one(provider, p)
            if r:
                results[p["id"]] = r
            done += 1
            if done % 20 == 0 or done == len(todo):
                print(f"  진행 {done}/{len(todo)}")
                OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    await asyncio.gather(*(work(p) for p in todo))
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    # 요약
    from collections import Counter
    by_id = {p["id"]: p for p in products}
    changes = Counter()
    for pid, r in results.items():
        old = by_id.get(pid, {}).get("category")
        if r["category"] != old:
            changes[f"{old} → {r['category']}"] += 1
    print(f"\n완료 → {OUT} ({len(results)}개)")
    print("\n=== 변경 요약 (상위 15) ===")
    for k, n in changes.most_common(15):
        print(f"  {n:>3}  {k}")


if __name__ == "__main__":
    asyncio.run(main())

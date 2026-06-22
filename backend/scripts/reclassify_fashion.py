"""패션 카테고리 LLM 재분류 — 잠옷·아기·임부·옷본 등을 OTHER로 거른다.

키워드 블랙리스트의 한계("패턴"=무늬 vs 옷본 구분 불가, 오제거)를 피하려 LLM이 판단한다.
대상: 실(synthetic 아님) 패션 5개 카테고리만. 전자/이어폰/합성품은 건드리지 않는다.

사용:
  PYTHONPATH=. .venv/bin/python scripts/reclassify_fashion.py            # 분류(검토)
  PYTHONPATH=. .venv/bin/python scripts/reclassify_fashion.py --apply    # seed+DB 반영
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
OUT = BACKEND_DIR / "seed_naver" / "fashion_reclassified.json"

FASHION = ["원피스", "니트·가디건", "코트·패딩·자켓", "티셔츠·셔츠", "팬츠·바지"]

SYSTEM = f"""너는 의류 상품을 분류하는 분류기다. 상품 제목·카테고리경로를 보고
아래 일상 의류 카테고리 중 하나를 고르거나, 해당 없으면 "OTHER"를 고른다.

카테고리:
{chr(10).join(f"- {c}" for c in FASHION)}

OTHER로 보내야 하는 것 (formative study의 일상복 시나리오와 무관):
- 잠옷·홈웨어·라운지웨어·파자마·란제리·슬립웨어
- 아기·유아·아동·키즈 의류
- 임부복·임산부·수유복
- 수영복·래쉬가드·비치웨어
- 옷본·패턴 도안·재단 도안 (옷을 만드는 종이/파일. 단, '무늬·프린트 패턴'은 정상 의류이니 OTHER 아님)
- 코스튬·할로윈·웨딩드레스 같은 특수 의상
- 반려동물 의류

규칙:
1. 제목의 '패턴'이 옷 무늬(체크·플로럴 등)면 정상 의류, '도안/옷본/재단'이면 OTHER.
2. 일반 성인 일상복(데일리/오피스/캐주얼)이면 해당 카테고리 유지.
3. JSON으로만: {{"category":"<카테고리 또는 OTHER>","reason":"<짧은 근거>"}}"""


async def classify(provider, p):
    ctx = {"제목": p.get("title"),
           "카테고리경로": (p.get("attributes") or {}).get("categoryPath") or p.get("category"),
           "현재카테고리": p.get("category")}
    try:
        out = await provider.generate_json(
            [LLMMessage(role="system", content=SYSTEM),
             LLMMessage(role="user", content=json.dumps(ctx, ensure_ascii=False))],
            task="fashion_classification", context=ctx)
        cat = (out or {}).get("category")
        if cat in FASHION or cat == "OTHER":
            return {"category": cat, "reason": (out or {}).get("reason", "")}
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ {p['id']}: {type(e).__name__}")
    return None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--concurrency", type=int, default=12)
    args = ap.parse_args()

    products = json.loads(SEED.read_text(encoding="utf-8"))
    # 대상: 실(합성 아님) 패션만
    targets = [p for p in products
               if p.get("category") in FASHION
               and not (p.get("attributes") or {}).get("synthetic")]

    if args.apply:
        if not OUT.exists():
            print("✗ fashion_reclassified.json 없음 — 먼저 분류"); return
        result = json.loads(OUT.read_text(encoding="utf-8"))
        others = [pid for pid, r in result.items() if r["category"] == "OTHER"]
        changed = [(p, result[p["id"]]["category"]) for p in products
                   if p["id"] in result and result[p["id"]]["category"] not in ("OTHER", p["category"])]
        print(f"OTHER(제외) {len(others)}개, 카테고리 변경 {len(changed)}개")

        shutil.copy(SEED, SEED.with_suffix(".json.prefashion.bak"))
        kept = []
        for p in products:
            r = result.get(p["id"])
            if r is None:
                kept.append(p); continue
            if r["category"] == "OTHER":
                continue
            p["category"] = r["category"]
            kept.append(p)
        SEED.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ seed {len(products)}→{len(kept)} (OTHER {len(products)-len(kept)} 제외), 백업 .prefashion.bak")

        keep_ids = {p["id"] for p in kept}
        db = sqlite3.connect(settings.db_path); cur = db.cursor()
        for p in kept:
            cur.execute("UPDATE products SET category=? WHERE id=?", (p["category"], p["id"]))
        cur.execute("SELECT id FROM products"); allids = {r[0] for r in cur.fetchall()}
        for i in allids - keep_ids:
            cur.execute("DELETE FROM products WHERE id=?", (i,))
        db.commit(); db.close()
        print(f"✓ DB OTHER {len(allids-keep_ids)}개 삭제")
        return

    if settings.llm_provider == "mock":
        print("✗ mock — 실제 provider 필요"); return
    provider = get_provider()
    print(f"provider={provider.name}, model={getattr(provider,'model','?')}")
    print(f"대상: 실 패션 {len(targets)}개\n")

    sem = asyncio.Semaphore(args.concurrency)
    results = {}
    done = 0
    async def work(p):
        nonlocal done
        async with sem:
            r = await classify(provider, p)
            if r:
                results[p["id"]] = r
            done += 1
            if done % 25 == 0 or done == len(targets):
                print(f"  진행 {done}/{len(targets)}")
                OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    await asyncio.gather(*(work(p) for p in targets))
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    # 요약
    by_id = {p["id"]: p for p in products}
    others = [(by_id[pid]["category"], by_id[pid]["title"]) for pid, r in results.items() if r["category"] == "OTHER"]
    changed = [(by_id[pid]["category"], r["category"], by_id[pid]["title"]) for pid, r in results.items()
               if r["category"] not in ("OTHER", by_id[pid]["category"])]
    print(f"\n완료 → {OUT}")
    print(f"OTHER(제외후보) {len(others)}개, 카테고리 변경 {len(changed)}개")
    print(f"\n=== OTHER 분포 ===")
    for c, n in Counter(c for c, _ in others).most_common():
        print(f"  {c}: {n}")
    print(f"\n=== OTHER 샘플 (20개) ===")
    for c, t in others[:20]:
        print(f"  [{c}] {t[:46]}")
    if changed:
        print(f"\n=== 카테고리 변경 ===")
        for old, new, t in changed[:15]:
            print(f"  {old} → {new} | {t[:40]}")


if __name__ == "__main__":
    asyncio.run(main())

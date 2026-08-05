"""본실험 상품 풀 정리 — 중복·부속품·카테고리 불일치 제거 (2026-08-06).

임베딩 **전에** 돌려야 한다. 임베딩은 id 키 캐시라 자동 무효화가 없고, 지울 상품까지
임베딩하면 그만큼이 낭비된다.

무엇을 지우고 무엇을 남기는가 — 실측(17,850개)에 근거한 세 갈래다:

  ① 중복 (343개)  같은 제목이 두 번 이상. 판매자가 같은 상품을 여러 번 올린 것이라
     추천에 나란히 뜨면 "선택지 3개인데 둘이 같은 상품"이 된다. 첫 항목만 남긴다.

  ② 부속품 (80개)  프로필의 productType이 배터리·케이스·거치대 등을 가리키는 것.
     제목 정규식이 아니라 **오프라인 LLM이 매긴 productType**을 근거로 삼는다 —
     제목 매칭은 "Speaker with Carrying Case"(본품)와 "Case for Speaker"(부속품)를
     구분하지 못해 2026-08-06 진단에서 본품 321개를 오탈락시켰던 전력이 있다.

  ③ 카테고리 불일치 (483개)  productType에 그 카테고리의 핵심어가 없는 것.
     예: 스피커 풀의 "LED 라이트"(JW Speaker는 조명 브랜드다), "블루투스 비니 모자",
     책상 풀의 "파일 캐비닛", 체어 풀의 "바 스툴".

**가격 이상치는 지우지 않는다.** 처음엔 '중앙값 12배 초과'를 후보로 잡았는데, 실물을
보니 Devialet Phantom(445만) · B&O Beosound Balance(371만) · Herman Miller 에어론(236만)
같은 **정상 프리미엄 제품**이 대부분이었다. 이들을 지우면 "덜 알려진 것/좋은 것을 원한다"는
축(TCV Social·Emotional)을 표현할 상품이 풀에서 사라진다 — 숨은 기준을 관측하는 것이
연구 목적이므로 그 축을 죽이면 안 된다. (MIN_REVIEWS를 30→10으로 낮춘 것과 같은 이유다.)
진짜 가격 오류로 보이는 것(JBL Flip3 374만원 등)은 개별 검수 대상으로 남기고 로그에만 남긴다.

  cd backend && PYTHONPATH=. .venv/bin/python scripts/clean_study_pool.py          # 예행 (기본)
  cd backend && APPLY=1 PYTHONPATH=. .venv/bin/python scripts/clean_study_pool.py  # 실제 적용
"""
import collections
import json
import os
import statistics
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SEED = BACKEND / "seed_amazon"
APPLY = os.environ.get("APPLY") == "1"

#: 카테고리별로 productType에 반드시 들어 있어야 하는 핵심어 (하나라도 포함되면 통과).
EXPECT: dict[str, tuple[str, ...]] = {
    "블루투스 스피커": ("스피커",),
    "티셔츠": ("티", "셔츠"),
    "책상": ("책상", "데스크", "테이블"),
    "데스크체어": ("의자", "체어"),
}
#: productType이 이걸 담고 있으면 부속품 — 본품이 아니다.
ACCESSORY = ("배터리", "케이스", "커버", "거치대", "받침", "충전기", "케이블",
             "어댑터", "스탠드", "마운트", "부품", "교체", "쿠션")


def main() -> None:
    products = json.loads((SEED / "products.json").read_text(encoding="utf-8"))
    raw = json.loads((SEED / "product_profiles.json").read_text(encoding="utf-8"))
    profiles = raw if isinstance(raw, dict) else {p["id"]: p for p in raw}

    drop: dict[str, str] = {}          # id → 사유
    seen_titles: dict[tuple[str, str], str] = {}

    for p in products:
        cat, pid = p.get("category"), p["id"]
        key = (cat, p["title"].strip())
        if key in seen_titles:
            drop[pid] = "중복"
            continue
        seen_titles[key] = pid

        ptype = (profiles.get(pid) or {}).get("productType") or ""
        if any(a in ptype for a in ACCESSORY):
            drop[pid] = f"부속품({ptype})"
        elif cat in EXPECT and not any(k in ptype for k in EXPECT[cat]):
            drop[pid] = f"불일치({ptype})"

    kept = [p for p in products if p["id"] not in drop]

    print(f"{'':16s}{'현재':>8s}{'제거':>8s}{'남음':>8s}")
    by_cat = collections.Counter(p["category"] for p in products)
    kept_cat = collections.Counter(p["category"] for p in kept)
    for cat in by_cat:
        print(f"{cat:16s}{by_cat[cat]:>8,}{by_cat[cat]-kept_cat[cat]:>8,}{kept_cat[cat]:>8,}")
    print(f"{'합계':16s}{len(products):>8,}{len(drop):>8,}{len(kept):>8,}")

    reasons = collections.Counter(r.split("(")[0] for r in drop.values())
    print("\n사유별: " + " · ".join(f"{k} {v:,}" for k, v in reasons.most_common()))

    # 가격 오류 후보 — 지우지 않고 눈으로 볼 수 있게 남긴다 (위 docstring 참조).
    print("\n[검수 대상] 가격 오류로 보이는 것 — 자동 삭제하지 않음:")
    by = collections.defaultdict(list)
    for p in kept:
        by[p["category"]].append(p)
    for cat, items in by.items():
        med = statistics.median([p["price"] for p in items])
        top = sorted([p for p in items if p["price"] > med * 12], key=lambda x: -x["price"])
        if top:
            print(f"  {cat} (중앙 {int(med):,}원, 12배 초과 {len(top)}개) — 상위 3:")
            for p in top[:3]:
                print(f"      {int(p['price']):>9,}  {p['title'][:58]}")

    est = len(kept) * 4752 / 1024 ** 2
    print(f"\n예상 product_vectors.json.gz ≈ {est:.0f} MB "
          f"({'OK' if est < 95 else '⚠️ GitHub 100MB 한도 초과'})")

    if not APPLY:
        print("\n예행 모드 — 파일을 쓰지 않았다. 적용하려면 APPLY=1")
        return

    (SEED / "products.json").write_text(
        json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
    kept_ids = {p["id"] for p in kept}
    (SEED / "product_profiles.json").write_text(
        json.dumps({k: v for k, v in profiles.items() if k in kept_ids},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    # 무엇을 왜 지웠는지 남긴다 — 나중에 "이 상품 왜 없지"를 추적할 수 있어야 한다.
    (BACKEND / "data" / "pool_cleanup.json").write_text(
        json.dumps({"dropped": drop, "keptTotal": len(kept)}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"\n적용 완료 — products.json {len(kept):,}개 · 사유 로그 data/pool_cleanup.json")


if __name__ == "__main__":
    main()

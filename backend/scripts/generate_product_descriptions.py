"""상품 검색용 서술 생성 (DeepSeek) — 임베딩 retrieval 품질 향상용.

제목이 빈약하거나 모호한 상품("게이밍 이어폰 N1")도 용도·특징·가격대가 담긴
한국어 서술로 정규화해, 의미 임베딩이 더 정확히 매칭하게 한다.

설계 원칙:
  - 사실 기반(hallucination 가드): 주어진 title/categoryPath/tags/가격으로만 서술.
    배터리·방수·블루투스 버전 등 주어지지 않은 사양은 절대 지어내지 않는다.
  - 검색용(B1 가치단서 아님): 용도·형태·특징·가격대 중심. 가치(TCV) 단서는 별도 단계.
  - 재현성: 결과를 seed_naver/product_descriptions.json 에 저장(원본 비파괴).
    같은 입력 → 같은 프롬프트·모델. 재실행 시 이미 생성된 건 건너뛴다(resume).

사용:
  PYTHONPATH=. .venv/bin/python scripts/generate_product_descriptions.py --limit 5   # 검증
  PYTHONPATH=. .venv/bin/python scripts/generate_product_descriptions.py              # 전체(resume)
"""
import argparse
import asyncio
import json
from pathlib import Path

from app.core.config import settings, BACKEND_DIR
from app.llm.provider import LLMMessage, get_provider

SEED = BACKEND_DIR / "seed_naver" / "products.json"
OUT = BACKEND_DIR / "seed_naver" / "product_descriptions.json"

SYSTEM = """너는 쇼핑몰 상품의 '검색용 서술'을 작성하는 도우미다.
주어진 상품 정보로 한국어 2~3문장 서술을 쓴다. 이 서술은 사용자의 가치 기준
(내구성·신뢰·가성비·브랜드·용도 등)과 의미 매칭되도록 쓰인다.

두 종류를 모두 담아라:
(A) 용도·형태·구성: 어떤 상황에 쓰는지, 형태(오픈형/커널형 등), 주요 기능.
(B) 객관적 신뢰 단서: 리뷰 수, 한 달 이상 사용 후기 비율, 평점, 브랜드를 자연스럽게 서술.

규칙:
1. 주어진 정보로만 작성한다. 배터리·방수·음질 수치 등 주어지지 않은 사양은 지어내지 마라.
2. **가치를 단정하지 말고 '단서'만 서술한다.** ("내구성이 좋은 제품" X →
   "한 달 이상 사용 후기가 많은 편" O). 가치 판단은 사용자 몫이다.
3. 객관 단서는 자연어로 풀어라. 예: 리뷰 많으면 "리뷰가 많이 쌓인 편",
   한 달 후기 비율 높으면 "오래 쓴 후기가 많은 편", 평점 높으면 "평점이 높은 편",
   브랜드 있으면 브랜드명 언급. 수치가 낮거나 적으면 그 점도 솔직히("리뷰가 적은 편").
4. 마케팅 과장("최고의","혁신적인") 금지. 담백하게.
5. JSON으로만 답한다: {"description": "..."}"""


def price_band(price: int | None) -> str:
    if not price:
        return "가격 정보 없음"
    if price < 20000:
        return "저가형(2만원 미만)"
    if price < 50000:
        return "중저가(2~5만원)"
    if price < 100000:
        return "중급가(5~10만원)"
    return "고가형(10만원 이상)"


def _review_hint(n: int | None) -> str:
    if not n:
        return "리뷰 정보 없음"
    if n >= 1000:
        return f"리뷰 {n:,}개 (매우 많음)"
    if n >= 300:
        return f"리뷰 {n:,}개 (많은 편)"
    if n >= 50:
        return f"리뷰 {n}개 (보통)"
    return f"리뷰 {n}개 (적은 편)"


def _ltr_hint(r: float | None) -> str:
    pct = round((r or 0) * 100)
    if pct >= 30:
        return f"한 달 이상 사용 후기 비율 {pct}% (높은 편)"
    if pct >= 15:
        return f"한 달 이상 사용 후기 비율 {pct}% (보통)"
    return f"한 달 이상 사용 후기 비율 {pct}% (낮은 편)"


def build_context(p: dict) -> dict:
    return {
        "제목": p.get("title"),
        "카테고리경로": (p.get("attributes") or {}).get("categoryPath") or p.get("category"),
        "태그": p.get("tags") or [],
        "가격대": price_band(p.get("price")),
        # 객관적 신뢰 단서 (B) — 가진 숫자만, 자연어 힌트 동반
        "브랜드": p.get("brand") or "정보 없음",
        "리뷰": _review_hint(p.get("reviewCount")),
        "장기사용후기": _ltr_hint(p.get("longTermReviewRatio")),
        "평점": f"{p.get('rating')} (높은 편)" if (p.get("rating") or 0) >= 4.6
                else (f"{p.get('rating')}" if p.get("rating") else "정보 없음"),
    }


async def generate_one(provider, p: dict) -> str | None:
    ctx = build_context(p)
    user = json.dumps(ctx, ensure_ascii=False)
    try:
        out = await provider.generate_json(
            [LLMMessage(role="system", content=SYSTEM),
             LLMMessage(role="user", content=user)],
            task="product_description", context=ctx,
        )
        desc = (out or {}).get("description")
        return desc.strip() if isinstance(desc, str) and desc.strip() else None
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ {p['id']}: {type(e).__name__}: {str(e)[:60]}")
        return None


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="N개만 처리(0=전체)")
    ap.add_argument("--concurrency", type=int, default=8, help="동시 요청 수")
    ap.add_argument("--force", action="store_true", help="기존 결과 무시하고 재생성")
    args = ap.parse_args()

    if settings.llm_provider == "mock":
        print("✗ VC_LLM_PROVIDER=mock — 실제 provider 필요 (deepseek 권장)")
        return
    provider = get_provider()
    print(f"provider={provider.name}, model={getattr(provider,'model','?')}")

    products = json.loads(SEED.read_text(encoding="utf-8"))
    existing: dict = {}
    if OUT.exists() and not args.force:
        existing = json.loads(OUT.read_text(encoding="utf-8"))
        print(f"기존 {len(existing)}개 발견 → resume (이미 된 건 건너뜀)")

    todo = [p for p in products if p["id"] not in existing]
    if args.limit:
        todo = todo[:args.limit]
    print(f"처리 대상: {len(todo)}개 (전체 {len(products)})\n")

    sem = asyncio.Semaphore(args.concurrency)
    results: dict = dict(existing)
    done = 0

    async def work(p):
        nonlocal done
        async with sem:
            desc = await generate_one(provider, p)
            if desc:
                results[p["id"]] = desc
            done += 1
            if done % 20 == 0 or done == len(todo):
                print(f"  진행 {done}/{len(todo)} (성공 {len(results)-len(existing)})")
                OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    await asyncio.gather(*(work(p) for p in todo))
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n완료 → {OUT}  (총 {len(results)}개)")

    # 샘플 미리보기
    print("\n=== 샘플 5개 ===")
    for p in todo[:5]:
        d = results.get(p["id"], "(실패)")
        print(f"· {p['title'][:40]}\n    → {d}\n")


if __name__ == "__main__":
    asyncio.run(main())

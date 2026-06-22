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
주어진 상품 정보(제목·카테고리·태그·가격)만으로 한국어 1~2문장 서술을 쓴다.

규칙:
1. 주어진 정보로만 작성한다. 배터리 지속시간, 방수 등급, 블루투스 버전, 음질 수치 등
   주어지지 않은 사양은 절대 추측하거나 지어내지 마라.
2. 용도·형태·주요 특징·가격대를 자연스럽게 녹인다. (예: "러닝·운동용 골전도 무선 이어폰, 저가형")
3. 마케팅 과장("최고의", "혁신적인") 없이 담백하게 쓴다.
4. 제목에 모델명·브랜드가 있으면 포함한다.
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


def build_context(p: dict) -> dict:
    return {
        "제목": p.get("title"),
        "카테고리경로": (p.get("attributes") or {}).get("categoryPath") or p.get("category"),
        "태그": p.get("tags") or [],
        "가격대": price_band(p.get("price")),
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

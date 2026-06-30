"""seed_amazon 상품 제목을 카드용 간결한 한국어 이름으로 재생성(DeepSeek flash).
영어 원제목(attributes.titleEn)에서 브랜드+제품유형+핵심스펙만 뽑아 ~25자. 긴 한국어 제목은
attributes.titleFull로 보존. 그 뒤 product_vectors 캐시를 비워 다음 startup이 간결 제목으로 재임베딩.

  cd backend && VC_LLM_PROVIDER=deepseek VC_DEEPSEEK_MODEL=deepseek-v4-flash VC_DEEPSEEK_THINKING=off \
      CONC=8 PYTHONPATH=. .venv/bin/python scripts/shorten_amazon_titles.py
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_short_"), "x.db"))

from app.llm.provider import LLMMessage, get_provider  # noqa: E402

OUT = BACKEND / "seed_amazon"
CONC = int(os.environ.get("CONC", "8"))


async def shorten_one(provider, sem, p, counter):
    src = (p.get("attributes") or {}).get("titleEn") or p.get("title") or ""
    msg = ("다음 아마존 상품명을 한국 쇼핑앱 카드에 들어갈 간결한 한국어 이름으로 줄여줘. "
           "브랜드 + 제품 유형 + 핵심 스펙 1~2개만 남기고, 마케팅 문구·반복·불필요한 키워드는 제거. "
           "25자 내외. JSON만: {\"title\": \"...\"}\n"
           f"상품명: {src}")
    out = {}
    async with sem:
        try:
            out = await provider.generate_json([LLMMessage(role="user", content=msg)], task=None)
        except Exception:  # noqa: BLE001
            out = {}
    if isinstance(out, dict) and out.get("title"):
        p.setdefault("attributes", {})["titleFull"] = p.get("title")   # 긴 제목 보존
        p["title"] = str(out["title"]).strip()
    counter[0] += 1
    if counter[0] % 50 == 0:
        print(f"  {counter[0]} shortened", flush=True)


async def main():
    products = json.loads((OUT / "products.json").read_text(encoding="utf-8"))
    provider = get_provider()
    print(f"[shorten] {len(products)} products · model={getattr(provider, 'model', '?')} · conc={CONC}", flush=True)
    sem = asyncio.Semaphore(CONC)
    counter = [0]
    await asyncio.gather(*(shorten_one(provider, sem, p, counter) for p in products))
    (OUT / "products.json").write_text(json.dumps(products, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "product_vectors.json").unlink(missing_ok=True)   # 간결 제목으로 재임베딩
    print("\n샘플:")
    for p in products[:6]:
        print(f"  {p['title']}")
    print(f"\n완료 — {len(products)}개 제목 간결화; 벡터 캐시 삭제(재임베딩).")


if __name__ == "__main__":
    asyncio.run(main())

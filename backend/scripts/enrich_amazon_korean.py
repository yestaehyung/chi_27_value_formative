"""seed_amazon 풀을 한국어 study용으로 가공: 상품 제목·설명 한국어 번역(DeepSeek flash) +
가격 USD→KRW + 카테고리 한국어 + 시나리오 5개 한국어. 그 뒤 product_vectors 캐시를 비워
다음 startup이 한국어 텍스트로 재임베딩하게 한다.

  cd backend && VC_LLM_PROVIDER=deepseek VC_DEEPSEEK_MODEL=deepseek-v4-flash VC_DEEPSEEK_THINKING=off \
      USDKRW=1350 CONC=8 PYTHONPATH=. .venv/bin/python scripts/enrich_amazon_korean.py
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_enr_"), "x.db"))

from app.llm.provider import LLMMessage, get_provider  # noqa: E402

OUT = BACKEND / "seed_amazon"
RATE = float(os.environ.get("USDKRW", "1350"))
CONC = int(os.environ.get("CONC", "8"))
CAT_KO = {"Tablet": "태블릿", "Laptop": "노트북", "Wireless Earphones": "무선이어폰",
          "Dress": "원피스", "Coat": "코트"}

MECH = {
    "S1": "구매 경험이 부족해 판단 기준이 명확하지 않기 때문에, 대화 중 정보 탐색과 비교를 통해 기준이 형성됨",
    "S2": "미적 취향이나 자기표현과 관련된 기준은 직접 언어화하기 어렵기 때문에, 예시 선호나 비교 반응을 통해 드러남",
    "S3": "구매 또는 사용 맥락에 따라 기준이 달라지기 때문에, 상황을 구체화하는 과정에서 필요한 조건이 드러남",
    "S4": "선택의 기준이 자신보다 받는 사람에게 있기 때문에, 관계와 상황을 고려하는 과정에서 숨은 기준이 드러남",
    "S5": "고려해야 할 조건이 많고 우선순위가 처음부터 분명하지 않기 때문에, 후보 비교를 통해 중요한 조건과 타협 가능한 조건이 구분됨",
}
SCENARIOS_KO = [
    {"id": "first_time_tablet", "title": "처음 사보는 태블릿", "targetCategory": "태블릿", "recipient": "본인",
     "context": "처음 구매하는 제품군 (판단 기준 미형성)", "offered": True, "studyOrder": 1, "hiddenIntentionMechanism": MECH["S1"],
     "initialUserNeed": "태블릿을 처음 사보는데, 뭘 보고 골라야 할지 잘 모르겠어요.", "groundTruthHiddenIntentions": []},
    {"id": "taste_dress", "title": "취향 중심 원피스", "targetCategory": "원피스", "recipient": "본인",
     "context": "취향/정체성 중심 구매", "offered": True, "studyOrder": 2, "hiddenIntentionMechanism": MECH["S2"],
     "initialUserNeed": "남들과 잘 안 겹치는 원피스를 찾고 있어요.", "groundTruthHiddenIntentions": []},
    {"id": "travel_laptop", "title": "출장·여행용 노트북", "targetCategory": "노트북", "recipient": "본인",
     "context": "특정 상황(출장/여행)에 맞춘 구매", "offered": True, "studyOrder": 3, "hiddenIntentionMechanism": MECH["S3"],
     "initialUserNeed": "출장이랑 여행 다닐 때 들고 쓸 노트북을 찾고 있어요.", "groundTruthHiddenIntentions": []},
    {"id": "gift_earphones", "title": "선물용 무선 이어폰", "targetCategory": "무선이어폰", "recipient": "운동을 좋아하는 친구",
     "context": "선물", "offered": True, "studyOrder": 4, "hiddenIntentionMechanism": MECH["S4"],
     "initialUserNeed": "운동 좋아하는 친구에게 줄 무선 이어폰을 찾고 있어요. 브랜드는 잘 몰라요.", "groundTruthHiddenIntentions": []},
    {"id": "high_involvement_coat", "title": "큰맘 먹고 사는 겨울 코트", "targetCategory": "코트", "recipient": "본인",
     "context": "고관여 구매", "offered": True, "studyOrder": 5, "hiddenIntentionMechanism": MECH["S5"],
     "initialUserNeed": "몇 년 입을 겨울 코트를 신중하게 고르고 싶어요.", "groundTruthHiddenIntentions": []},
]


async def translate_one(provider, sem, p, counter):
    msg = ("다음 아마존 상품의 제목과 설명을 한국 쇼핑앱 스타일의 자연스러운 한국어로 번역해. "
           "브랜드·모델명은 알아볼 수 있게 유지(필요하면 한글 음차). 설명은 1~2문장으로. "
           'JSON만 출력: {"title": "...", "description": "..."}\n'
           f"제목: {p.get('title', '')}\n설명: {(p.get('description') or '')[:400]}")
    out = {}
    async with sem:
        try:
            out = await provider.generate_json([LLMMessage(role="user", content=msg)], task=None)
        except Exception:  # noqa: BLE001
            out = {}
    if isinstance(out, dict) and out.get("title"):
        p.setdefault("attributes", {})["titleEn"] = p.get("title")
        p["title"] = str(out["title"]).strip()
        if out.get("description"):
            p["description"] = str(out["description"]).strip()[:600]
    # USD → KRW (100원 단위 반올림)
    if isinstance(p.get("price"), (int, float)) and p["price"]:
        p["price"] = round(p["price"] * RATE / 100) * 100
    p["category"] = CAT_KO.get(p["category"], p["category"])
    counter[0] += 1
    if counter[0] % 50 == 0:
        print(f"  {counter[0]} translated", flush=True)


async def main():
    products = json.loads((OUT / "products.json").read_text(encoding="utf-8"))
    provider = get_provider()
    print(f"[enrich] {len(products)} products · model={getattr(provider, 'model', '?')} · USDKRW={RATE} · conc={CONC}", flush=True)
    sem = asyncio.Semaphore(CONC)
    counter = [0]
    await asyncio.gather(*(translate_one(provider, sem, p, counter) for p in products))
    (OUT / "products.json").write_text(json.dumps(products, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "scenarios.json").write_text(json.dumps(SCENARIOS_KO, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "product_vectors.json").unlink(missing_ok=True)   # 한국어로 재임베딩
    import collections
    print("\n완료:", len(products), "상품 한국어 번역 + KRW + 카테고리 한국어; 시나리오 5개 한국어.")
    print("카테고리:", dict(collections.Counter(p["category"] for p in products)))
    print("벡터 캐시 삭제 — 다음 startup이 한국어 텍스트로 재임베딩.")


if __name__ == "__main__":
    asyncio.run(main())

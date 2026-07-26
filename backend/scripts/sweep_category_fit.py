"""전 카테고리 추천 품질 스윕 — 발화 유형 6종 × 카테고리 층화 24케이스 (2026-07-06).

배경: 풀이 30카테고리×300(9,000개)으로 확장되며 크로스 카테고리 의미 충돌이 표면화
(예: "여자친구 생일 선물 주얼리" → 생일 캔들 / "노트북 넣을 가방" → 노트북 4개).
dense retrieval의 타입 취약성(Sciavolino et al. EMNLP'21) × rerank 채우기 우선 현상.

채점:
- categoryFit: 기계 채점 — 노출 상품의 category 필드가 기대 카테고리인 비율 (재현 가능)
- constraintOK: LLM judge — 명시 제약(부정·속성·가격대)을 노출 셋이 지켰는지
- priceSpread: 기계 — 노출 셋 가격 max/min 비 (trade-off 다양성 프록시)

  cd backend && VC_SEED_DIR=seed_amazon VC_LLM_PROVIDER=deepseek VC_DEEPSEEK_MODEL=deepseek-v4-flash \
      PYTHONPATH=. .venv/bin/python scripts/sweep_category_fit.py
출력: data/sweep_category_fit.json + 콘솔 요약
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("VC_SEED_DIR", str(BACKEND / "seed_amazon"))
os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_sweep_"), "sweep.db"))

# (유형, 기대 카테고리(들), 발화, 명시 제약 요약 — judge용 / None이면 judge 생략)
CASES = [
    # A. 직접 지목 — 카테고리만 정확히 부르는 기본형
    ("직접지목", ["시계"], "가볍게 찰 손목시계 추천해줘", None),
    ("직접지목", ["스커트"], "여름에 입을 스커트 찾고 있어요", None),
    ("직접지목", ["모니터"], "사무용 모니터 하나 추천해주세요", None),
    ("직접지목", ["텀블러·머그"], "텀블러 하나 사려고요", None),
    # B. 맥락어 동반 — 선물/상황 어휘가 카테고리와 경쟁
    ("맥락어", ["주얼리"], "여자친구 생일 선물로 주얼리를 찾고 있어요. 너무 저렴해 보이는 건 싫어요", "주얼리여야 함; 너무 저렴해 보이면 안 됨"),
    ("맥락어", ["캔들·디퓨저"], "집들이 선물로 캔들이나 디퓨저 추천해줘", None),
    ("맥락어", ["스카프·머플러"], "어머니 생신 선물로 스카프 알아보고 있어요", None),
    ("맥락어", ["스마트워치"], "아버지 은퇴 선물로 스마트워치 어떨까 해서요", None),
    # C. 크로스 카테고리 — 발화에 다른 카테고리 명사가 등장
    ("크로스", ["가방·핸드백"], "출퇴근할 때 노트북 넣고 다닐 가방을 찾고 있어요", "가방이어야 함 (노트북 아님)"),
    ("크로스", ["양말"], "러닝화 신을 때 신을 양말 추천해줘", "양말이어야 함 (러닝화 아님)"),
    ("크로스", ["키보드·마우스"], "맥북이랑 같이 쓸 키보드 찾아요", "키보드여야 함 (맥북/노트북 아님)"),
    ("크로스", ["지갑"], "카드 많이 들어가는 지갑 찾고 있어요. 휴대폰도 같이 들어가면 좋고요", "지갑이어야 함 (휴대폰 아님)"),
    # D. 부정 제약
    ("부정제약", ["청바지"], "청바지 찾는데 스키니는 싫어요", "스키니 핏 제외"),
    ("부정제약", ["니트·스웨터"], "니트 사고 싶은데 따가운 소재는 싫어요", "따가운 소재(거친 울 등) 지양"),
    ("부정제약", ["샌들"], "여름 샌들 찾는데 굽 높은 건 싫어요", "하이힐/높은 굽 제외"),
    ("부정제약", ["원피스"], "원피스 찾고 있어요. 화려한 무늬는 싫고 단색이 좋아요", "화려한 무늬 제외, 단색 위주"),
    # E. 속성 제약
    ("속성제약", ["반바지"], "무릎 위로 오는 여름 반바지 추천해줘", "짧은 기장(무릎 위)"),
    ("속성제약", ["수영복"], "래시가드 스타일 수영복 찾아요", "래시가드형"),
    ("속성제약", ["후드·맨투맨"], "기모 있는 따뜻한 후드티 추천해줘", "기모/따뜻한 소재"),
    ("속성제약", ["블루투스 스피커"], "캠핑에서 쓸 방수 블루투스 스피커 추천해주세요", "방수"),
    # F. 선물 + 가격대
    ("선물가격", ["지갑"], "남자친구 선물로 10만원대 지갑 보고 있어요", "10만원대(약 10~20만원) 가격"),
    ("선물가격", ["텀블러·머그"], "회사 동료 선물로 부담 없는 머그컵 추천해줘", "부담 없는(저렴한) 가격"),
    ("선물가격", ["시계"], "부모님 선물로 고급스러운 시계 찾고 있어요", "고급스러운(중고가 이상) 인상"),
    ("선물가격", ["헤드폰"], "동생 생일 선물로 5만원 이하 헤드폰 찾아요", "5만원 이하"),
]

JUDGE_CONTRACT = (
    '다음은 쇼핑 추천 결과다. 사용자의 명시 제약을 노출 상품들이 지켰는지 판정하라.\n'
    'JSON만 출력: {"violations": [{"title": "...", "why": "..."}], "ok": true|false}\n'
    'ok는 5개 중 4개 이상이 제약을 지키면 true.\n'
)


async def judge_constraints(provider, constraint: str, cards: list[dict]) -> dict:
    from app.llm.provider import LLMMessage
    lines = [f"- {c['title']} ({c['price']}원) / 카테고리: {c['category']} / 특징: {c.get('attrs','')}" for c in cards]
    msg = JUDGE_CONTRACT + f"\n[제약] {constraint}\n[노출 상품]\n" + "\n".join(lines)
    try:
        return await provider.generate_json([LLMMessage(role="user", content=msg)], task=None)
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:80]}


def main():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.llm.provider import get_provider
    from app.products import profiles

    results = []
    with TestClient(app) as client:
        provider = get_provider()
        for i, (kind, expect_cats, utt, constraint) in enumerate(CASES, 1):
            sid = client.post("/api/sessions", json={"mode": "manual", "scenarioId": "custom",
                                                     "studyCondition": "correctable"}).json()["sessionId"]
            out = client.post(f"/api/sessions/{sid}/turns", json={"role": "user", "content": utt}).json()
            action = out["agentResponse"]["agentAction"]
            clarified = False
            if action != "recommend":  # clarify → 한 번 재촉 (스터디 참가자 행동 근사)
                clarified = True
                out = client.post(f"/api/sessions/{sid}/turns",
                                  json={"role": "user", "content": "특별한 건 없어요, 바로 추천해주세요"}).json()
            cards = []
            for p in out.get("recommendedProducts", []):
                pr = p["product"]
                prof = profiles.get(pr["id"]) or {}
                cards.append({"title": pr["title"], "price": pr["price"], "category": pr["category"],
                              "attrs": ", ".join((prof.get("keyAttributes") or [])[:4])})
            n = len(cards)
            fit = sum(1 for c in cards if c["category"] in expect_cats)
            prices = [c["price"] for c in cards if c.get("price")]
            spread = round(max(prices) / max(min(prices), 1), 2) if prices else None
            verdict = None
            if constraint and cards:
                verdict = asyncio.run(judge_constraints(provider, constraint, cards))
            row = {"kind": kind, "utterance": utt, "expected": expect_cats, "clarifiedFirst": clarified,
                   "nShown": n, "categoryFit": f"{fit}/{n}", "fitRatio": round(fit / n, 2) if n else 0,
                   "priceSpread": spread, "constraint": constraint, "judge": verdict,
                   "cards": cards}
            results.append(row)
            flag = "✅" if n and fit == n else ("⚠️" if n and fit >= n - 1 else "❌")
            print(f"[{i:2d}/{len(CASES)}] {flag} {kind} | fit {fit}/{n} | {utt[:34]}", flush=True)

    outp = BACKEND / "data" / "sweep_category_fit.json"
    outp.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")

    # 요약
    from collections import defaultdict
    by_kind = defaultdict(list)
    for r in results:
        by_kind[r["kind"]].append(r["fitRatio"])
    print("\n=== 유형별 카테고리 정합률(평균) ===")
    for k, v in by_kind.items():
        print(f"  {k}: {sum(v)/len(v):.2f}  (n={len(v)})")
    bad = [r for r in results if r["fitRatio"] < 0.8]
    print(f"\n정합률 0.8 미만: {len(bad)}건")
    for r in bad:
        print(f"  ❌ [{r['kind']}] {r['utterance'][:36]} → fit {r['categoryFit']} | 노출 카테고리: "
              + ", ".join(sorted({c['category'] for c in r['cards']})))
    jbad = [r for r in results if r.get("judge") and r["judge"].get("ok") is False]
    print(f"\n제약 위반 판정: {len(jbad)}건")
    for r in jbad:
        v = (r["judge"].get("violations") or [{}])[0]
        print(f"  ⚠️ [{r['kind']}] {r['utterance'][:36]} → {v.get('title','')[:30]}: {v.get('why','')[:40]}")
    print(f"\n→ {outp}")


if __name__ == "__main__":
    main()

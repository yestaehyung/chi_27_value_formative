"""상호작용 패턴 스윕 (2라운드) — 선물 심화·풀밖 정직성·멀티턴 누적·번복·복합제약·비교 (2026-07-06).

1라운드(sweep_category_fit.py)가 단일 발화의 카테고리 정합을 쟀다면, 2라운드는
대화 패턴 자체를 검증한다. 케이스마다 턴 리스트(멀티턴)와 기대치(expectation)를
정의하고, 카테고리 정합은 기계 채점(가능한 경우), 기대치 충족은 LLM judge로 채점.

  cd backend && VC_SEED_DIR=seed_amazon VC_LLM_PROVIDER=deepseek VC_DEEPSEEK_MODEL=deepseek-v4-flash \
      PYTHONPATH=. .venv/bin/python scripts/sweep_interaction_patterns.py
출력: data/sweep_interactions.json + 콘솔 요약
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
os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_sweep2_"), "sweep.db"))

# (id, 유형, 턴들, 기대 카테고리(None=해당없음), judge용 기대치 서술)
CASES = [
    # G. 선물 심화
    ("g1", "선물·미정", ["여자친구 생일 선물 뭐가 좋을까요?"], None,
     "카테고리가 정해지지 않은 선물 요청 — 되묻거나(취향·예산), 추천한다면 선물로 적절한 상품군이어야 함"),
    ("g2", "선물·수령자", ["60대 어머니가 쓰실 선물 찾아요. 스카프나 지갑 생각 중이에요"], ["스카프·머플러", "지갑"],
     "스카프 또는 지갑이어야 하고, 60대 여성에게 어울리는 톤이어야 함 (아동용/남성 전용 부적절)"),
    ("g3", "선물·미정가격", ["남자 동료 승진 선물로 5만원 안쪽에서 뭐가 좋을까요"], None,
     "5만원 이하 + 남성 동료에게 무난한 선물 상품군 (승진 축하 맥락에 이상하지 않아야)"),
    ("g4", "선물·세트", ["커플로 맞출 시계 보고 있어요"], ["시계"],
     "시계여야 하고, 커플 매칭 맥락(공용/유사 디자인)이 어색하지 않아야 함"),
    ("g5", "선물·부정", ["집들이 선물 추천해줘. 캔들 말고 다른 걸로"], None,
     "캔들·디퓨저 카테고리가 노출되면 안 됨 (명시적으로 제외 요청)"),
    ("g6", "선물·아동", ["초등학생 조카 선물로 헤드폰 어때요?"], ["헤드폰"],
     "헤드폰이어야 하고, 가능하면 아동 사용 맥락(볼륨제한·사이즈 등)을 고려하거나 언급해야 함"),
    # H. 풀 밖 정직성 — 없는 걸 있는 척하지 않는가
    ("h1", "풀밖", ["향수 추천해줘"], None,
     "카탈로그에 향수가 없음 — 없다고 알리거나 인접 대체(캔들·디퓨저)를 대체임을 밝히고 제안해야 함. 향수인 척 다른 상품을 내밀면 실패"),
    ("h2", "풀밖", ["운동화 하나 사려고요"], None,
     "카탈로그에 운동화가 없음(신발은 샌들뿐) — 없음을 알리거나 대체를 명시해야 함. 샌들을 운동화인 척 추천하면 실패"),
    ("h3", "풀밖", ["아이패드 케이스 찾아요"], None,
     "케이스/액세서리가 없음 — 태블릿 본체를 보여주며 케이스인 척하면 실패. 없음 고지가 정답"),
    # I. 멀티턴 기준 누적
    ("i1", "누적·부정", ["무선이어폰 추천해줘", "10만원 이하로 보여줘. 그리고 귀에 꽂는 커널형은 싫어요"], ["무선이어폰"],
     "두 번째 추천은 10만원 이하 + 커널형 아님(오픈형/골전도 등)이어야 함"),
    ("i2", "누적·가격", ["원피스 보여줘", "더 저렴한 걸로 보여줘"], ["원피스"],
     "두 번째 추천은 원피스를 유지하면서 첫 세트보다 가격대가 내려가야 함"),
    ("i3", "누적·용도", ["노트북 추천해줘", "게임용은 아니고 문서작업용이에요. 가벼우면 좋겠어요"], ["노트북"],
     "두 번째 추천은 게이밍 노트북 제외 + 경량 위주여야 함"),
    # J. 기준 번복
    ("j1", "번복·종류", ["검정색 백팩 찾아요", "생각해보니 백팩보다 토트백이 낫겠어요"], ["가방·핸드백"],
     "최종 추천은 토트백 위주여야 함 (백팩이 다수면 번복 미반영)"),
    ("j2", "번복·속성", ["유선 키보드 추천해줘", "아 사실 무선이 더 좋겠어요"], ["키보드·마우스"],
     "최종 추천은 무선 키보드여야 함 (유선 다수면 번복 미반영)"),
    # K. 복합 제약
    ("k1", "복합", ["방수 되는 스마트워치 30만원 이하로 찾아줘. 애플은 비싸서 빼주세요"], ["스마트워치"],
     "방수 + 30만원 이하 + 애플 제외 세 제약을 모두 지켜야 함"),
    ("k2", "복합", ["여름 출근용 반팔 셔츠 찾아요. 구김 안 가는 소재면 좋겠고, 흰색은 말고요"], ["셔츠·블라우스", "티셔츠"],
     "반팔 셔츠 + 구김 적은 소재 언급 + 흰색 제외를 지켜야 함"),
    # L. 비교(answer 경로)
    ("l1", "비교", ["블루투스 스피커 추천해줘", "첫 번째랑 두 번째 중에 뭐가 더 나아요?"], ["블루투스 스피커"],
     "두 번째 응답은 새 검색 없이 이미 보여준 두 상품을 비교·설명해야 함 (새 상품 5개를 또 쏟아내면 실패)"),
    # M. 모호
    ("m1", "모호", ["쇼핑 좀 도와줘"], None,
     "정보가 전혀 없음 — 무엇을 찾는지 되묻는 게 정답. 아무 상품이나 추천하면 실패"),
]

JUDGE = (
    '쇼핑 에이전트의 응답을 평가하라. JSON만 출력:\n'
    '{"pass": true|false, "why": "한 문장", "violations": ["..."]}\n'
)


async def judge_case(provider, expectation: str, transcript: list[str], cards: list[dict]) -> dict:
    from app.llm.provider import LLMMessage
    card_lines = [f"- {c['title']} ({c['price']}원, {c['category']}) 특징: {c.get('attrs','')}" for c in cards] or ["(상품 노출 없음)"]
    msg = (JUDGE + f"\n[기대치] {expectation}\n\n[대화]\n" + "\n".join(transcript)
           + "\n\n[최종 노출 상품]\n" + "\n".join(card_lines))
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
        for i, (cid, kind, turns, expect_cats, expectation) in enumerate(CASES, 1):
            sid = client.post("/api/sessions", json={"mode": "manual", "scenarioId": "custom",
                                                     "studyCondition": "correctable"}).json()["sessionId"]
            transcript, last = [], None
            for t in turns:
                last = client.post(f"/api/sessions/{sid}/turns", json={"role": "user", "content": t}).json()
                transcript.append(f"사용자: {t}")
                transcript.append(f"에이전트({last['agentResponse']['agentAction']}): {last['agentResponse']['content'][:220]}")
            action = last["agentResponse"]["agentAction"]
            cards = []
            for p in last.get("recommendedProducts", []):
                pr = p["product"]
                prof = profiles.get(pr["id"]) or {}
                cards.append({"title": pr["title"], "price": pr["price"], "category": pr["category"],
                              "attrs": ", ".join((prof.get("keyAttributes") or [])[:4])})
            n = len(cards)
            fit = sum(1 for c in cards if c["category"] in (expect_cats or [])) if expect_cats else None
            verdict = asyncio.run(judge_case(provider, expectation, transcript, cards))
            ok = verdict.get("pass")
            row = {"id": cid, "kind": kind, "turns": turns, "finalAction": action,
                   "nShown": n, "expected": expect_cats,
                   "categoryFit": (f"{fit}/{n}" if fit is not None and n else None),
                   "judgePass": ok, "judgeWhy": verdict.get("why"), "violations": verdict.get("violations"),
                   "transcript": transcript, "cards": cards}
            results.append(row)
            fitstr = f"fit {fit}/{n}" if fit is not None and n else f"action={action}"
            print(f"[{i:2d}/{len(CASES)}] {'✅' if ok else '❌'} {kind} | {fitstr} | {turns[-1][:32]}"
                  + (f" | {verdict.get('why','')[:44]}" if not ok else ""), flush=True)

    outp = BACKEND / "data" / "sweep_interactions.json"
    outp.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")

    from collections import defaultdict
    by_kind = defaultdict(lambda: [0, 0])
    for r in results:
        by_kind[r["kind"].split("·")[0]][0] += 1 if r["judgePass"] else 0
        by_kind[r["kind"].split("·")[0]][1] += 1
    print("\n=== 유형별 judge 통과율 ===")
    for k, (p, t) in by_kind.items():
        print(f"  {k}: {p}/{t}")
    print(f"\n→ {outp}")


if __name__ == "__main__":
    main()

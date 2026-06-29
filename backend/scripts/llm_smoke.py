"""실 LLM 스모크 — 이번 세션 수정(A 답변/카드 일치, B 충돌메시지 누수, recommend-first)을
실제 provider(.env=deepseek, 임베딩=openai)로 몇 턴 돌려 눈으로 확인 + soft 단언.

임시 DB에만 씀(스터디 DB 미오염). 실행:
    cd backend && .venv/bin/python scripts/llm_smoke.py
"""
import os
import tempfile

# 임포트 전에 임시 DB로 고정 (config는 setdefault라 이 값이 이김). provider는 .env(deepseek) 사용 — mock 강제 X.
os.environ["VC_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="vc_llmsmoke_"), "smoke.db")
os.environ["VC_EXPORT_DIR"] = tempfile.mkdtemp(prefix="vc_llmsmoke_exp_")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402

LEAK = ("선물", "최저가")  # 비-선물 시나리오에서 이 단어가 나오면 데모 누수 의심
results: list[str] = []


def hr(t: str) -> None:
    print("\n" + "=" * 72 + f"\n{t}\n" + "=" * 72)


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append(f"{'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def main() -> None:
    with TestClient(app) as c:
        print(f"provider={settings.llm_provider} model={settings.deepseek_model} thinking={settings.deepseek_thinking}")
        if settings.llm_provider == "mock":
            print("⚠️  provider가 mock입니다 — 실 LLM 테스트가 아닙니다. .env의 VC_LLM_PROVIDER 확인.")
            return

        def new(scn: str) -> str:
            r = c.post("/api/sessions", json={"mode": "manual", "scenarioId": scn, "studyCondition": "correctable"})
            r.raise_for_status()
            return r.json()["sessionId"]

        def say(sid: str, text: str) -> dict:
            r = c.post(f"/api/sessions/{sid}/turns", json={"role": "user", "content": text})
            r.raise_for_status()
            out = r.json()
            ar = out["agentResponse"]
            print(f"\n👤 {text}\n🤖 [{ar['agentAction']}] {ar['content']}")
            for p in out["recommendedProducts"]:
                pr = p["product"]
                print(f"   · {pr['title']}  ({pr.get('price')}원, cue={pr.get('cueSummary', {}).get('priceCue')})")
                if p.get("recommendationReason"):
                    print(f"       └ {p['recommendationReason']}")
            return out

        # ---- Scenario 1: gift_for_other — recommend-first + A 일치 + 충돌→B ----
        hr("Scenario 1 — gift_for_other (스마트워치): recommend-first · A 일치 · 충돌→B")
        sid = new("gift_for_other")
        last = None
        for utt in ["운동 좋아하는 친구에게 줄 스마트워치를 찾고 있어요",
                    "가능하면 저렴한 게 좋아요",
                    "바로 추천해주세요"]:
            last = say(sid, utt)
        action = last["agentResponse"]["agentAction"]
        prods = last["recommendedProducts"]
        check("recommend-first: 무한 clarify 없이 추천에 도달", action == "recommend", f"action={action}")
        check("A: 추천 카드 3개 노출", len(prods) == 3, f"n={len(prods)}")
        # A 눈검증: 답변 본문이 노출된 카드와 같은 셋을 가리키는지(개수/도메인) — 위 출력 참고.

        # 충돌 유발: '저렴한 게 좋아요'(turn2) + 싼 후보 dislike(너무 저렴해 보임)
        cheapest = min(prods, key=lambda p: p["product"].get("price") or 1e12)["product"] if prods else None
        if cheapest:
            fb = c.post(f"/api/sessions/{sid}/feedback", json={
                "productId": cheapest["id"], "type": "dislike",
                "reasonCode": "too_cheap_looking", "reasonText": "선물인데 너무 저렴해 보이면 좀 그래요",
            })
            fb.raise_for_status()
            conflicts = fb.json().get("newConflicts", [])
            print(f"\n[feedback] dislike '{cheapest['title']}' → 충돌 {len(conflicts)}건")
            if conflicts:
                cf = conflicts[0]
                print(f"   충돌: old='{cf.get('oldAssumption')}' / new='{cf.get('newSignal')}'")
                res = c.post(f"/api/conflicts/{cf['id']}/resolve", json={"optionId": "merge"})
                res.raise_for_status()
                msg = res.json().get("message", "")
                print(f"   해결(merge) 메시지: {msg}")
                check("B: 충돌메시지가 비어있지 않음", bool(msg), msg)

        # ---- Scenario 2: budget_value(비-선물) — recommend-first + 누수 없음 ----
        hr("Scenario 2 — budget_value (비-선물): recommend-first · 도메인 누수 없음")
        sid2 = new("budget_value")
        last2 = None
        for utt in ["가성비 좋은 스마트워치 찾고 있어요", "바로 보여주세요"]:
            last2 = say(sid2, utt)
        action2 = last2["agentResponse"]["agentAction"]
        reply2 = last2["agentResponse"]["content"]
        check("recommend-first(비-선물)", action2 == "recommend", f"action={action2}")
        check("비-선물 답변에 '선물' 누수 없음", "선물" not in reply2, reply2[:60])

    hr("요약")
    for r in results:
        print(r)


if __name__ == "__main__":
    main()

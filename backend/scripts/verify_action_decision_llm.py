"""Rigorous real-LLM verification of the recommend-first action_decision agent.

Drives the REAL agent (deepseek + seed_naver, throwaway temp DB) across diverse
conversation cases, then uses an LLM judge (the app's own provider) to score each
transcript against the failure modes we care about. Writes a JSON report + summary.

Run:  .venv/bin/python scripts/verify_action_decision_llm.py
(Makes real API calls. Never touches the study DB — uses a temp VC_DB_PATH.)
"""
import asyncio
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ on path

os.environ["VC_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="vc_verify_"), "t.db")
os.environ["VC_SEED_DIR"] = "seed_naver"
os.environ["VC_LLM_PROVIDER"] = "deepseek"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402 (loads .env)
from app.llm.json_parser import extract_json  # noqa: E402
from app.llm.provider import LLMMessage, get_provider  # noqa: E402
from app.main import app  # noqa: E402

PROVIDER = get_provider()

# 다양한 케이스 — 회귀 2 + 도메인전환 + 막연한 첫턴 + 즉시추천 + 충돌
CASES = [
    {"name": "earphone_gift_explicit",
     "intent": "운동하는 친구 선물용 무선이어폰. 2턴째 '바로 추천' 명시.",
     "turns": ["운동 좋아하는 친구에게 줄 무선 이어폰을 찾고 있어요. 브랜드는 잘 몰라요.",
               "헬스 위주로 해요, 바로 추천해주세요", "10만원 정도 생각 중이에요"]},
    {"name": "dress_unique",
     "intent": "남들과 안 겹치는 독특한 원피스. 도메인=원피스 유지돼야.",
     "turns": ["남들과 잘 안 겹치는 원피스를 찾고 있어요.", "나 독특한거 좋아", "예산은 10만원 정도"]},
    {"name": "domain_switch",
     "intent": "이어폰 보다가 노트북으로 전환 — 에이전트가 새 도메인(노트북)을 따라가야.",
     "turns": ["무선 이어폰 보고 있었는데요.", "아 사실 작업용 노트북이 더 급해요.", "가볍고 오래 쓰는 게 좋아요"]},
    {"name": "vague_first_turn",
     "intent": "첫 발화가 막연 → 적절히 되묻고, 단서 주면 추천으로.",
     "turns": ["뭘 사야 할지 잘 모르겠어요.", "20대 여성한테 줄 선물이에요", "5만원 정도로요"]},
    {"name": "explicit_immediate",
     "intent": "첫 턴부터 추천 요청 — 심문 없이 바로 추천해야.",
     "turns": ["그냥 무난한 무선 이어폰 아무거나 추천해줘", "좀 더 저렴한 건?"]},
    {"name": "conflict_cheap_but_not_cheaplooking",
     "intent": "저렴 원하지만 싸보이긴 싫음 — 충돌을 자연스럽게 다뤄야(깨지지 않기).",
     "turns": ["가능하면 저렴한 원피스요.", "근데 너무 싸보이는 건 싫어요", "그럼 적당한 걸로 추천해줘"]},
]

JUDGE_SYS = """너는 쇼핑 추천 에이전트의 대화 로그를 채점하는 엄격한 평가자다.
각 기준을 pass / warn / fail (해당없으면 n/a)로 매기고, 문제가 있으면 근거를 한 줄로 든다.

기준:
- on_domain: 추천 상품·질문이 사용자가 말한 상품 도메인과 일치하는가(도메인 전환도 따라가는가). 엉뚱한 카테고리면 fail.
- action_appropriate: 단서가 있으면 추천하고, 정말 막연할 때만 되묻는가. 충분한데 계속 질문만 하면 fail.
- honors_explicit: 사용자가 추천을 명시 요청한 턴에서 추천했는가(요청 없으면 n/a).
- hedged: 사용자의 숨은 의도를 단정하지 않고 추측·확인형(§36)으로 말하는가.
- no_repeat: 같은 질문·같은 말을 반복하지 않는가.
- brevity: 에이전트 발화가 사람처럼 짧고 자연스러운가. 한두 문장이면 pass, 상품을 줄줄이 나열하거나 설명이 길고 장황하면 warn/fail.
출력은 JSON만."""

JUDGE_FMT = """출력 JSON:
{"verdict":"pass"|"fail","criteria":{"on_domain":"pass|warn|fail|n/a","action_appropriate":"...","honors_explicit":"...","hedged":"...","no_repeat":"...","brevity":"..."},"issues":[string],"summary":string}
verdict는 fail이 하나라도 있으면 fail, 아니면 pass."""


def run_case(client, case):
    sid = client.post("/api/sessions", json={
        "mode": "manual", "scenarioId": "custom", "studyCondition": "correctable",
    }).json()["sessionId"]
    transcript = []
    for t in case["turns"]:
        out = client.post(f"/api/sessions/{sid}/turns", json={"role": "user", "content": t}).json()
        ar = out.get("agentResponse", {})
        prods = out.get("recommendedProducts") or []
        content = ar.get("content", "")
        transcript.append({
            "user": t,
            "action": ar.get("agentAction"),
            "recommendedCategories": [p["product"].get("category") for p in prods],
            "agent": content,
            "agentLen": len(content),
            "summary": (out.get("preferenceState") or {}).get("userVisibleSummary", {}).get("oneSentenceSummary", ""),
        })
    return transcript


def judge_case(case, transcript):
    user_msg = (f"케이스 의도: {case['intent']}\n\n대화 로그:\n"
                + json.dumps(transcript, ensure_ascii=False, indent=1)
                + "\n\n" + JUDGE_FMT)
    raw = asyncio.run(PROVIDER.generate_text(
        [LLMMessage(role="system", content=JUDGE_SYS), LLMMessage(role="user", content=user_msg)],
        temperature=0, max_tokens=900,
    ))
    try:
        parsed = extract_json(raw)
    except Exception:  # noqa: BLE001
        parsed = None
    if not isinstance(parsed, dict):
        return {"verdict": "parse_error", "raw": (raw or "")[:400]}
    return parsed


def main():
    print(f"PROVIDER={settings.llm_provider} MODEL={settings.deepseek_model} SEED={os.environ['VC_SEED_DIR']}")
    results = []
    with TestClient(app) as client:
        for case in CASES:
            print(f"... running {case['name']}")
            try:
                tr = run_case(client, case)
                verdict = judge_case(case, tr)
            except Exception as e:  # noqa: BLE001
                tr, verdict = [], {"verdict": "error", "error": str(e)}
            results.append({"case": case["name"], "intent": case["intent"],
                            "transcript": tr, "verdict": verdict})

    out_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "verify_action_decision.json"))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 78 + "\nSUMMARY\n" + "=" * 78)
    for r in results:
        v = r["verdict"]
        crit = v.get("criteria", {})
        lens = [t.get("agentLen", 0) for t in r["transcript"]]
        avglen = round(sum(lens) / len(lens)) if lens else 0
        print(f"[{v.get('verdict', '?').upper():5}] {r['case']}  (agent발화 평균 {avglen}자, 최대 {max(lens) if lens else 0}자)")
        if crit:
            print("        " + " ".join(f"{k}={vv}" for k, vv in crit.items()))
        for issue in (v.get("issues") or []):
            print(f"        ⚠ {issue}")
        if v.get("summary"):
            print(f"        → {v['summary']}")
    print(f"\nfull report: {out_path}")


if __name__ == "__main__":
    main()

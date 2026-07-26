"""전멸 풀 정직 응답의 '구속 제약 질문' 품질 평가 (설계 1, 2026-07-07).

렌더러(AGENT_REPLY_SYSTEM 규칙 12)가 recommendationNote(noExactMatch)를 받았을 때:
(a) 부재를 고지하는가, (b) 대안이 요청과 다른 점을 밝히는가,
(c) 탈락 이유가 두 조건으로 갈리면 **어느 조건이 더 중요한지** 고르는 질문을 하는가
(QuickXplain/제약기반 추천의 완화 진단 계보 — 막연한 "조건을 넓혀볼까요?" 대체).

체커는 기계식 토큰 검사 (LLM judge 없음). 케이스당 REPEAT회 반복해 다수결 —
generate_text는 temp 0.2라 런 간 변동이 있다.

  cd backend && VC_LLM_PROVIDER=deepseek VC_DEEPSEEK_MODEL=deepseek-v4-flash \
      PYTHONPATH=. LABEL=q_base .venv/bin/python scripts/eval_relaxation_question.py
출력: data/relaxation_eval_{LABEL}.json
"""
import asyncio
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

LABEL = os.environ.get("LABEL", "run")
REPEAT = int(os.environ.get("REPEAT", "3"))


class _P:
    def __init__(self, pid, title, price=30000):
        self.id = pid
        self.title = title
        self.price = price
        self.rating = 4.2
        self.review_count = 120
        self.long_term_review_ratio = 0.2
        self.recent_sales_count = 10
        self.seller_grade = "빅파워"
        self.delivery_fee = 0
        self.cue_summary = {}


class _T:
    def __init__(self, role, content):
        self.role = role
        self.content = content


# (id, 대화, 근접대안 [(title, differsHow)], 필수토큰그룹들, 설명)
# 필수토큰그룹: 각 그룹에서 최소 1개 토큰이 응답에 있어야 통과. "?"는 전 케이스 공통.
CASES = [
    ("q1_두갈래_버뮤다",
     [("user", "남자 데님 버뮤다 팬츠 찾고 있어요")],
     [("리바이스 여성 버뮤다 데님 쇼츠", "여성용"),
      ("Wrangler 남성 카고 반바지", "버뮤다가 아닌 일반 반바지"),
      ("Lee 여성 데님 버뮤다", "여성용")],
     [["없", "찾지 못", "찾진 못", "못 찾", "찾을 수 없"],          # (a) 부재 고지
      ["여성", "남성"],                          # (b1) 갈래 1 언급
      ["버뮤다", "기장", "반바지"],              # (b2) 갈래 2 언급
      ["중요", "우선", "어느 쪽", "어느 조건", "어떤 조건", "완화", "양보", "포기", "조정", "어떤 부분"]],  # (c) 선택 질문
     "탈락 이유 두 갈래(성별/종류) → 트레이드오프 질문"),
    ("q2_두갈래_이어폰",
     [("user", "5만원 이하 노이즈캔슬링 무선이어폰 있어요?")],
     [("소니 WH-CH520 무선 헤드폰", "이어폰이 아닌 헤드폰"),
      ("QCY T13 무선이어폰", "노이즈캔슬링 없음"),
      ("앤커 사운드코어 노캔 이어폰", "가격 5만원 초과")],
     [["없", "찾지 못", "찾진 못", "못 찾", "찾을 수 없"],
      ["노이즈캔슬링", "노캔"],
      ["가격", "예산", "5만", "만원"],
      ["중요", "우선", "어느 쪽", "어느 조건", "어떤 조건", "완화", "양보", "포기", "조정", "어떤 부분"]],
     "탈락 이유 세 갈래 → 어느 조건을 지킬지 질문"),
    ("q3_한갈래_가격",
     [("user", "동생 생일 선물로 3만원 이하 시계 찾아요")],
     [("카시오 클래식 디지털", "가격 3만원 초과 (3.8만원)"),
      ("타이맥스 위켄더", "가격 3만원 초과 (4.5만원)"),
      ("세이코5 오토매틱", "가격 3만원 초과 (12만원)")],
     [["없", "찾지 못", "찾진 못", "못 찾", "찾을 수 없"],
      ["가격", "예산", "3만", "만원"]],           # 한 갈래 — 그 조건을 완화할지 물으면 됨
     "탈락 이유 한 갈래(가격) → 그 조건 완화 질문"),
    ("q4_대안없음",
     [("user", "왼손잡이용 기계식 키보드 있나요?")],
     [],
     [["없", "찾지 못", "찾진 못", "못 찾", "찾을 수 없"]],
     "대안 0개 → 부재 고지 + 방향 질문"),
]


def check(reply: str, groups: list[list[str]]) -> tuple[bool, list[str]]:
    missing = []
    if "?" not in reply:
        missing.append("질문 없음")
    for g in groups:
        if not any(tok in reply for tok in g):
            missing.append("|".join(g[:3]))
    return (not missing), missing


def main():
    from app.agents import response_generator as rg
    from app.llm.provider import get_provider

    provider = get_provider()

    async def one(cid, dialogue, alts, groups, desc):
        products = [_P(f"{cid}_{i}", t) for i, (t, _) in enumerate(alts)]
        near_miss = {p.id: how for p, (_, how) in zip(products, alts)}
        rec_note = {
            "noExactMatch": True,
            "nearestAlternatives": [
                {"title": p.title, "differsHow": near_miss[p.id]} for p in products
            ],
        }
        turns = [_T(r, c) for r, c in dialogue]
        passes, replies = 0, []
        for _ in range(REPEAT):
            reply = await rg.generate_reply(
                provider, action="recommend",
                template_text=rg.near_miss_text(
                    [type("S", (), {"product": p})() for p in products]),
                recent_turns=turns, products=products, state_summary=None,
                recommendation_note=rec_note,
            )
            ok, missing = check(reply, groups)
            passes += ok
            replies.append({"ok": ok, "missing": missing, "reply": reply})
        return {"cid": cid, "desc": desc, "passRate": round(passes / REPEAT, 2),
                "replies": replies}

    async def run():
        return [await one(*c) for c in CASES]

    rows = asyncio.run(run())
    avg = sum(r["passRate"] for r in rows) / len(rows)
    print(f"\n[{LABEL}] 평균 통과율 {avg:.2f} (케이스당 {REPEAT}회)")
    for r in rows:
        worst = next((x for x in r["replies"] if not x["ok"]), None)
        print(f"  {r['cid']}: {r['passRate']}"
              + (f"  누락: {worst['missing']}" if worst else ""))
    out = BACKEND / "data" / f"relaxation_eval_{LABEL}.json"
    out.write_text(json.dumps({"label": LABEL, "avg": avg, "rows": rows},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {out}")


if __name__ == "__main__":
    main()

"""축 2 실험 턴 루프 — 대화 에이전트 하나 + search_and_rank 도구 (2026-07-07).

파이프라인(planner→recommender→renderer 3분리)과의 대조 실험용. VC_TURN_LOOP=agentic
으로 켠다 (기본 pipeline — 기존 경로 무접촉, mock provider에선 자동 비활성).

가설: 해석·행동결정·문장화가 한 컨텍스트에서 일어나면 계층 간 해석 불일치 버그 계열
(코트 허위진술·전멸 풀 침묵·페인팅 재해석 — 전부 "렌더러에게 근거를 안 줘서 지어내게
만든" 병리)이 구조적으로 소멸한다. 대가: 행동 결정이 명시적 action JSON이 아니라 도구
호출 패턴에 암묵적으로 남아 연구 코딩이 한 다리 건너가 된다.

멀티 에이전트 구조는 유지된다: ① user-model agent(commit engine)는 이 루프 *앞에서*
그대로 실행되고(사용자 모델의 유일한 작성자), recommender는 도구 내부로 통째 생존
(하이브리드 검색→rerank→exclude→evidence purity — purity는 도구 경계에서 강제),
show_conflict 구조 가드도 이 루프 밖(service_agent)에서 선행한다. 합쳐지는 것은
planner+renderer뿐이다.
"""
import json
import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session as DbSession

from app.db import models

# 도구 인자 지침은 파이프라인 planner의 DSPy 검증 문구(ACTION_DECISION_SYSTEM 2026-07-06)를,
# 정직 응답 지침은 AGENT_REPLY 규칙 12의 A/B 검증 문구(relaxation eval 0.50→1.00)를 승계 —
# 두 아키텍처가 같은 지침을 쓰므로 비교 실험에서 프롬프트가 아니라 구조가 변인이 된다.
AGENTIC_SYSTEM = """너는 쇼핑 대화 에이전트다. 사용자와 대화하며, 상품을 보여줄 때는
search_and_rank 도구를 호출해 실제 카탈로그에서 찾은 결과로만 추천한다.

행동 판단:
- 기본은 추천이다 — 가진 단서로 도구를 호출한다 (숨은 기준은 시스템이 background로
  감지하니 다 알 필요 없다).
- 무엇을 찾는지 감이 전혀 없을 때만 짧게 한 번 되묻는다. 직전 답변에서 이미 되물었으면
  이번엔 도구를 호출한다.
- 사용자가 방금 보여준 상품이나 상품 지식에 대해 물으면 새 검색 없이 대화 이력으로 답한다.
- 구매 결정 발화("이걸로 할게요")면 짧게 마무리한다. 결정에 새 요구가 붙어 있으면 계속한다.

도구 인자:
- searchText: 찾는 제품의 종류 + 사용자가 직접 언급한 선호 특징만 담은 완결된 한국어
  검색문. 예산·비선호 요소·곁에 언급된 다른 물건·받는 사람·상황(선물·생일 등)은 넣지
  않는다 — 검색은 단어의 존재만 신호로 쓴다.
- constraintsNote: 예산·필수 조건·비선호·수령자 맥락을 자연어 한두 문장으로.
예시:
- "청바지 찾는데 스키니는 싫어요" → searchText "청바지" / constraintsNote "스키니 핏은 싫어함"
- "여자친구 생일 선물로 주얼리 찾고 있어요" → searchText "여성 주얼리" / constraintsNote "여자친구 생일 선물"
- "출퇴근할 때 노트북 넣고 다닐 가방 찾아요" → searchText "출퇴근용 가방" / constraintsNote "노트북이 들어가야 함"

응답 작성:
1. 시스템이 추론한 내용을 확정 사실처럼 말하지 않는다 — "~을 중요하게 보고 계신 것
   같아요"처럼 추측·확인형으로 쓰고, 사용자가 바로잡을 수 있게 한다.
2. 사람처럼 짧게, 한두 문장. 마크다운 문법 없이 일반 텍스트로만.
3. 추천 시 개별 상품 설명은 화면 카드가 하므로, 왜 이 조합인지만 한 문장으로 짚는다.
   상품 정보는 도구 결과에 있는 것만 쓴다.
4. 도구 결과의 noExactMatch가 true면: 조건에 맞는 상품을 찾지 못했다는 사실을 첫
   문장에서 알리고, 보여주는 대안이 어떤 점에서 다른지(differsHow) 밝힌다. 대안들이
   서로 다른 조건에서 걸렸으면 어느 조건이 더 중요한지 고르게 묻고, 걸린 조건이
   하나뿐이면 그 조건을 완화할지 묻는다. 대안을 조건에 맞는 상품처럼 소개하지 않는다.
5. 사용자가 이전 추천의 전제(대상·조건 등)를 바로잡아 주면, 그 점을 짧게 인정하고
   이번 결과에 어떻게 반영했는지 밝힌다."""

TOOLS = [{
    "type": "function",
    "function": {
        "name": "search_and_rank",
        "description": (
            "카탈로그에서 상품을 검색하고 사용자의 명시 제약·확인된 기준으로 선별해 "
            "최대 5개를 화면 카드로 노출한다. 반환된 shown 목록이 실제로 사용자 화면에 보인다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "searchText": {
                    "type": "string",
                    "description": "완결된 한국어 검색문 — 제품 종류 + 직접 언급된 선호 특징만",
                },
                "constraintsNote": {
                    "type": "string",
                    "description": "예산·필수·비선호·수령자 맥락 요약. 없으면 빈 문자열",
                },
            },
            "required": ["searchText"],
        },
    },
}]


@dataclass
class AgenticResult:
    text: str
    scored: list = field(default_factory=list)
    card_texts: dict = field(default_factory=dict)
    rec_diag: dict | None = None
    tool_args: dict | None = None
    trace: list = field(default_factory=list)


async def run_turn(
    db: DbSession,
    provider,
    session: models.Session,
    commit,
    content: str,
    recent_turns: list[models.Turn],
) -> AgenticResult:
    """한 턴을 단일 대화 에이전트로 처리. 도구가 여러 번 불리면 마지막 검색 결과가
    노출 셋이다 (파이프라인과 동일하게 턴당 노출은 한 세트)."""
    from app.agents import recommender

    state = commit.snapshot.user_visible_summary if commit.snapshot else None
    meta = session.meta or {}
    context_block = {
        "scenarioGoal": meta.get("shoppingGoal") or meta.get("category") or "",
        "currentUnderstanding": state or {},
    }
    msgs: list[dict] = [{
        "role": "system",
        "content": AGENTIC_SYSTEM + "\n\n[세션 컨텍스트]\n"
        + json.dumps(context_block, ensure_ascii=False),
    }]
    for t in (recent_turns or [])[-8:]:
        if not getattr(t, "content", None):
            continue
        role = "user" if t.role in ("user", "user_agent") else "assistant"
        msgs.append({"role": role, "content": t.content})
    if not any(m["role"] == "user" for m in msgs[1:]):
        msgs.append({"role": "user", "content": content})

    holder: dict = {}

    async def execute(name: str, args: dict) -> dict:
        if name != "search_and_rank":
            return {"error": f"unknown tool: {name}"}
        search_text = (args.get("searchText") or "").strip() or content.strip()
        note = (args.get("constraintsNote") or "").strip()
        scored, cards, diag = await recommender.run_recommendation(
            db, provider, session,
            search_text=search_text, constraints_note=note,
            recent_turns=recent_turns, snapshot=commit.snapshot,
        )
        holder["scored"], holder["cards"], holder["diag"] = scored, cards, diag
        holder["args"] = {"searchText": search_text, "constraintsNote": note}
        near = diag.get("nearMiss") or {}
        return {
            "noExactMatch": bool(near) or not scored,
            "shown": [
                {
                    "n": i + 1,
                    "title": sp.product.title,
                    "price": sp.product.price,
                    "category": sp.product.category,
                    "reason": (cards.get(sp.product.id) or {}).get("reason", ""),
                    "weak": (cards.get(sp.product.id) or {}).get("weak", []),
                    **({"differsHow": near[sp.product.id]} if sp.product.id in near else {}),
                }
                for i, sp in enumerate(scored)
            ],
        }

    text, trace = await provider.generate_with_tools(msgs, TOOLS, execute)
    if not text.strip():
        raise RuntimeError("agentic loop returned empty text")
    logging.info("agentic_loop.tool_calls=%d", len(trace))
    return AgenticResult(
        text=text.strip(),
        scored=holder.get("scored") or [],
        card_texts=holder.get("cards") or {},
        rec_diag=holder.get("diag"),
        tool_args=holder.get("args"),
        trace=trace,
    )

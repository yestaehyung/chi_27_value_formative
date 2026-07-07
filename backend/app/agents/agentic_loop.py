"""축 2 실험 턴 루프 — 대화 에이전트 하나 + search_and_rank 도구 (2026-07-07).

파이프라인(planner→recommender→renderer 3분리)과의 대조 실험용. VC_TURN_LOOP=agentic
으로 켠다 (기본 pipeline — 기존 경로 무접촉, mock provider에선 자동 비활성).

가설: 해석·행동결정·문장화가 한 컨텍스트에서 일어나면 계층 간 해석 불일치 버그 계열
(코트 허위진술·전멸 풀 침묵·페인팅 재해석)이 구조적으로 소멸한다.

## 변인 통제 (v2, 2026-07-07 — 사용자 지적로 v1의 각색 이식을 폐기)

공정 비교의 원칙: **지침·정보는 두 아키텍처가 문자 그대로 공유하고, 다른 것은 집행
구조뿐이어야 한다.** v1은 지침을 요약 이식해서 "구조 차이"와 "지침 누락"이 교란됐다.
- 지침 동일: 시스템 프롬프트를 ACTION_DECISION_SYSTEM(플래너 지침)+AGENT_REPLY_SYSTEM
  (응답 지침) **verbatim import로 조립** — 파이프라인 프롬프트 수정이 자동으로 여기에도
  반영된다(단일 진실). 새로 쓴 텍스트는 아래 _AGENTIC_SHIM(인터페이스 매핑) 하나뿐.
- 정보 동일: 파이프라인 플래너가 받는 컨텍스트 객체(build_planner_context — userUtterances·
  feedbackEvents·lastShownProducts·values·motivations·ragPrediction·lastAgentAction 포함)를
  그대로 받는다. 대화는 도구 프로토콜상 chat message로도 흐른다(recentTurns와 중복 —
  구조상 불가피, 기록해 둠).
- 아키텍처 팔에만 있는 것(= 독립변수의 구성 요소이지 교란이 아님): 파이프라인의 코드
  집행 장치들 — action 정규화 가드(answer/close 강등·연속 clarify 금지·searchText 폴백),
  question_strategy.build_value_question 폴백, 질문 보존 검증. 전부 "명시적 action JSON"
  이라는 구조가 있어야 성립하는 장치라 agentic엔 대응물이 없다.

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
from app.llm.prompts import ACTION_DECISION_SYSTEM, AGENT_REPLY_SYSTEM

# 유일하게 새로 쓴 텍스트 — 정책이 아니라 인터페이스 매핑만 담는다 (파이프라인의
# action JSON·컨텍스트 필드가 도구 호출·대화에 어떻게 대응되는지). 정책 문구를 여기
# 덧붙이면 변인 통제가 깨진다 — 정책 수정은 반드시 prompts.py 원문에서.
_AGENTIC_SHIM = """[실행 방식 — 위 두 지침의 이 모드 매핑]
너는 위 '플래너 지침'으로 다음 행동을 판단하고, 위 '응답 지침'의 원칙으로 말한다.
단, JSON을 출력하지 않는다. 판단 결과는 이렇게 실행한다:
- recommend로 판단하면: search_and_rank(searchText, constraintsNote) 도구를 호출한다.
  인자 작성 규칙은 플래너 지침의 searchText/constraintsNote 규칙 그대로.
- clarify로 판단하면: 도구 없이, probe에 해당하는 hedged 질문을 직접 말한다.
- answer/close로 판단하면: 도구 없이 대화 이력과 이미 보여준 상품 정보로 답하거나 마무리한다.
- 도구 결과의 shown 목록이 화면 카드로 노출된다(응답 지침의 productsToShow에 해당).
  noExactMatch가 true면 응답 지침의 recommendationNote(noExactMatch) 규칙을 적용한다
  (shown의 differsHow가 nearestAlternatives에 해당).
- 응답 지침의 draftTemplate·mustAskQuestion은 이 모드에는 주어지지 않는다 — 해당
  규칙은 건너뛴다."""

AGENTIC_SYSTEM = (
    "너는 쇼핑 대화 에이전트다. 아래 플래너 지침으로 판단하고 응답 지침으로 말한다.\n\n"
    "[플래너 지침]\n" + ACTION_DECISION_SYSTEM
    + "\n\n[응답 지침]\n" + AGENT_REPLY_SYSTEM
    + "\n\n" + _AGENTIC_SHIM
)

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
    planner_context: dict | None = None,
) -> AgenticResult:
    """한 턴을 단일 대화 에이전트로 처리. 도구가 여러 번 불리면 마지막 검색 결과가
    노출 셋이다 (파이프라인과 동일하게 턴당 노출은 한 세트).

    planner_context = 파이프라인 planner.fetch_plan이 받는 것과 **같은 객체**
    (service_agent가 build_planner_context로 한 번 만들어 양쪽에 공급) — 정보 동일성."""
    from app.agents import recommender

    msgs: list[dict] = [{
        "role": "system",
        "content": AGENTIC_SYSTEM
        + "\n\n[플래너 컨텍스트 — 파이프라인 플래너와 동일 입력]\n"
        + json.dumps(planner_context or {}, ensure_ascii=False, default=str),
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
    # 챗 버블은 일반 텍스트 렌더 — 파이프라인 렌더러와 동일한 스트립 적용
    # (2026-07-07 로컬 실측: pro가 프롬프트 지침에도 **볼드**를 냄)
    from app.agents.response_generator import _strip_markdown

    return AgenticResult(
        text=_strip_markdown(text.strip()),
        scored=holder.get("scored") or [],
        card_texts=holder.get("cards") or {},
        rec_diag=holder.get("diag"),
        tool_args=holder.get("args"),
        trace=trace,
    )

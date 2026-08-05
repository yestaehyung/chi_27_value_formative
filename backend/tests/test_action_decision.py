"""action_decision task — LLM이 '추천할까 / (가치냐 동기냐) 무엇을 물을까'를 판단.
mock = 결정론 계약(데모 재현 + 폴백). 설계: docs/plans/2026-06-25-action-decision-design.md
"""
import asyncio
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_test_"), "test.db"))
os.environ.setdefault("VC_LLM_PROVIDER", "mock")

from app.llm.provider import LLMMessage, get_provider
from app.ontology.anchor_mapper import MOTIVATION_DIMS, TRAIT_ANCHORS

VOCAB12 = set(TRAIT_ANCHORS) | set(MOTIVATION_DIMS)


def _decide(context: dict) -> dict:
    return asyncio.run(get_provider().generate_json(
        [LLMMessage(role="user", content="x")], task="action_decision", context=context,
    ))


def test_honors_explicit_recommend_request():
    # "바로 추천해주세요" — 명시적 요구는 무한 clarify를 끊고 추천으로.
    out = _decide({
        "recentUtterance": "헬스 위주, 바로 추천해주세요",
        "hasRecommendations": False, "lastAgentAction": "clarify",
        "values": {}, "motivations": {},
    })
    assert out["action"] == "recommend", out


def test_clarifies_with_valid_12vocab_dimension_when_sparse():
    # 가치·동기 신호가 빈약하고 아직 안 물었으면 → clarify + 12 vocab 중 한 축 probe.
    out = _decide({
        "recentUtterance": "음악 들을 때 쓸 거예요",
        "hasRecommendations": False, "lastAgentAction": None,
        "values": {}, "motivations": {},
    })
    assert out["action"] == "clarify", out
    assert out["probe"]["dimension"] in VOCAB12, out
    assert out["probe"]["question"], out


def test_recommends_after_already_clarified_once():
    # 연속 clarify 금지 (PSCon 패턴) — 직전이 clarify면 추천으로 전환.
    out = _decide({
        "recentUtterance": "잘 모르겠어요",
        "hasRecommendations": False, "lastAgentAction": "clarify",
        "values": {}, "motivations": {},
    })
    assert out["action"] == "recommend", out


def test_context_keeps_recent_turns_so_domain_persists():
    # belt-and-suspenders: 구조화 상태 옆에 최근 원문 턴을 둔다 → 이전 턴의 도메인(원피스)이
    # 최신 발화에 없어도 컨텍스트에 살아있어, 모델이 도메인을 잃지 않는다.
    from app.agents.planner import build_planner_context

    class _T:
        def __init__(self, role, content):
            self.role, self.content = role, content

    turns = [
        _T("user", "남들과 잘 안 겹치는 원피스를 찾고 있어요."),
        _T("service_agent", "어떤 느낌을 원하시는지 여쭤봐도 될까요?"),
        _T("user", "나 독특한거 좋아"),
    ]
    ctx = build_planner_context(
        turns, snapshot=None, has_recommendations=False,
        last_agent_action="clarify", rag_prediction=None, scenario_goal="자유 대화",
    )
    blob = " ".join(m["content"] for m in ctx["recentTurns"])
    assert "원피스" in blob, ctx["recentTurns"]                       # 도메인 유지
    assert ctx["recentTurns"][-1]["content"] == "나 독특한거 좋아"      # 최신 발화 포함


def test_free_chat_honors_explicit_recommend_no_infinite_clarify():
    # 원래 버그 회귀 가드: 자유대화(custom, category=None)에서 "바로 추천해주세요"를 줘도
    # 예전엔 무한 clarify. 이제 추천이 나와야 한다(end-to-end).
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        sid = c.post("/api/sessions", json={
            "mode": "manual", "scenarioId": "custom", "studyCondition": "ours",
        }).json()["sessionId"]
        c.post(f"/api/sessions/{sid}/turns", json={
            "role": "user", "content": "운동 좋아하는 친구 줄 무선 이어폰 찾아요. 브랜드는 몰라요.",
        })
        out = c.post(f"/api/sessions/{sid}/turns", json={
            "role": "user", "content": "헬스 위주, 바로 추천해주세요",
        }).json()
        assert out["agentResponse"]["agentAction"] == "recommend", out["agentResponse"]["agentAction"]
        assert len(out["recommendedProducts"]) >= 1, out["recommendedProducts"]


# ── 실 LLM 경로의 구조 정규화 (2026-07-06) — mock 계약을 fetch_plan에 정렬 ──────
# FS1 참가자 실측 실패: flash가 4연속 clarify(참가자 세션 포기) + 노출 0에서 answer
# 선택(빈 상품 설명). 독스트링·mock 계약에는 있던 가드가 실 경로에 없었다.

class _StubProvider:
    """fetch_plan에 주입하는 가짜 실-provider — LLM 출력을 그대로 지정."""
    name = "stub"

    def __init__(self, out):
        self._out = out

    async def generate_json(self, messages, task=None, context=None):
        return self._out


def _plan(out, **ctx_overrides):
    from app.agents.planner import fetch_plan

    ctx = {"recentTurns": [], "userUtterances": ["운동화 신을 때 신을 양말", "얇은 걸로요"],
           "feedbackEvents": [], "lastShownProducts": [], "values": {}, "motivations": {},
           "ragPrediction": None, "hasRecommendations": False, "lastAgentAction": None,
           "scenarioGoal": ""}
    ctx.update(ctx_overrides)
    return asyncio.run(fetch_plan(_StubProvider(out), ctx, fallback_search_text="얇은 걸로요"))


def test_answer_without_impressions_demotes_to_recommend():
    # 노출 이력이 없으면 '설명할 상품'이 없다 — answer는 성립 불가 → recommend 강등
    d = _plan({"action": "answer"}, hasRecommendations=False)
    assert d.action == "recommend", d


def test_consecutive_clarify_demotes_to_recommend():
    # 직전 턴도 clarify였으면 또 묻지 않는다 (mock 계약과 동일 — 무한 질문 방지)
    d = _plan({"action": "clarify", "probe": {"question": "어떤 색을 좋아하세요?"}},
              lastAgentAction="clarify")
    assert d.action == "recommend", d
    # 강제 recommend의 검색문은 얇은 최신 발화가 아니라 발화 전량 합성으로 폴백
    assert "양말" in (d.search_text or ""), d.search_text


def test_first_clarify_still_allowed():
    # 가드는 '연속'만 막는다 — 첫 clarify는 정상 통과
    d = _plan({"action": "clarify", "probe": {"question": "어떤 용도세요?"}},
              lastAgentAction=None)
    assert d.action == "clarify", d

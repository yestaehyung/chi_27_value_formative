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


def test_free_chat_honors_explicit_recommend_no_infinite_clarify():
    # 원래 버그 회귀 가드: 자유대화(custom, category=None)에서 "바로 추천해주세요"를 줘도
    # 예전엔 무한 clarify. 이제 추천이 나와야 한다(end-to-end).
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        sid = c.post("/api/sessions", json={
            "mode": "manual", "scenarioId": "custom", "studyCondition": "correctable",
        }).json()["sessionId"]
        c.post(f"/api/sessions/{sid}/turns", json={
            "role": "user", "content": "운동 좋아하는 친구 줄 무선 이어폰 찾아요. 브랜드는 몰라요.",
        })
        out = c.post(f"/api/sessions/{sid}/turns", json={
            "role": "user", "content": "헬스 위주, 바로 추천해주세요",
        }).json()
        assert out["agentResponse"]["agentAction"] == "recommend", out["agentResponse"]["agentAction"]
        assert len(out["recommendedProducts"]) >= 1, out["recommendedProducts"]

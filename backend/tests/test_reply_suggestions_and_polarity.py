"""2026-08-14 지연·극성 개선 회귀 테스트.

① 답변 칩 분리: 턴/피드백 응답은 칩을 인라인으로 싣지 않고(크리티컬 패스 단축),
   POST /api/sessions/{id}/reply-suggestions 가 마지막 에이전트 턴 기준으로 만든다.
② 극성 전달: 추출 설계상 라벨은 극성 없이 대상만 이름 붙인다(예: 회피 기준 "흔한 디자인").
   rerank 기준(_stated_and_confirmed_criteria)이 kind·avoid·mustHave를 함께 실어야
   회피 기준이 선호로 뒤집혀 읽히지 않는다.
"""
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_test_"), "test.db"))
os.environ.setdefault("VC_LLM_PROVIDER", "mock")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _new_session(client):
    r = client.post("/api/sessions", json={"mode": "manual", "scenarioId": "gift_for_other",
                                           "studyCondition": "ours"})
    assert r.status_code == 200, r.text
    return r.json()["sessionId"]


def test_turn_response_defers_chips_to_dedicated_endpoint(client):
    sid = _new_session(client)
    out = client.post(f"/api/sessions/{sid}/turns",
                      json={"role": "user", "content": "운동 좋아하는 친구에게 줄 스마트워치를 추천해주세요"}).json()
    # 턴 응답은 칩을 싣지 않는다 — 프론트는 이 필드가 비면 별도 요청으로 받는다
    assert out["replySuggestions"] == []

    sug = client.post(f"/api/sessions/{sid}/reply-suggestions")
    assert sug.status_code == 200, sug.text
    body = sug.json()
    assert len(body["suggestions"]) == 3
    assert body["forTurnId"] == out["agentResponse"]["id"]


def test_reply_suggestions_before_any_agent_turn_is_empty(client):
    sid = _new_session(client)
    body = client.post(f"/api/sessions/{sid}/reply-suggestions").json()
    assert body == {"suggestions": [], "forTurnId": None}


def test_reply_suggestions_unknown_session_404(client):
    assert client.post("/api/sessions/sess_nope/reply-suggestions").status_code == 404


def test_rerank_criteria_carry_polarity(client):
    """회피 토픽은 kind/avoid가, 제약 토픽은 mustHave가 rerank 기준에 실린다."""
    from app.agents.recommender import _stated_and_confirmed_criteria
    from app.core.ids import new_id
    from app.db import models
    from app.db.database import SessionLocal

    sid = _new_session(client)
    db = SessionLocal()
    try:
        db.add(models.IntentionTopic(
            id=new_id("topic"), session_id=sid, label="흔한 디자인",
            description="어디서나 보이는 흔한 디자인은 피하고 싶다.",
            source="user_utterance", status="confirmed", priority="high",
            confidence=0.9, explicitness="explicit", evidence_ids=[],
            related_product_ids=[],
            hints={"kind": "avoidance", "impliedAvoidance": "흔한 디자인"},
        ))
        db.add(models.IntentionTopic(
            id=new_id("topic"), session_id=sid, label="20만원 이하 예산",
            description="예산 상한 20만원.",
            source="user_utterance", status="confirmed", priority="high",
            confidence=0.9, explicitness="explicit", evidence_ids=[],
            related_product_ids=[],
            hints={"kind": "constraint", "impliedHardConstraint": "20만원 이하"},
        ))
        db.commit()

        crits = {c["label"]: c for c in _stated_and_confirmed_criteria(db, sid)}
        assert crits["흔한 디자인"]["kind"] == "avoidance"
        assert crits["흔한 디자인"]["avoid"] == "흔한 디자인"
        assert crits["20만원 이하 예산"]["kind"] == "constraint"
        assert crits["20만원 이하 예산"]["mustHave"] == "20만원 이하"
        # 극성 필드가 없는 옛 토픽(hints 빈 dict)도 kind 기본값으로 안전하게 나간다
        db.add(models.IntentionTopic(
            id=new_id("topic"), session_id=sid, label="부드러운 촉감",
            description=None, source="user_utterance", status="confirmed",
            priority="medium", confidence=0.7, explicitness="explicit",
            evidence_ids=[], related_product_ids=[], hints={},
        ))
        db.commit()
        crits = {c["label"]: c for c in _stated_and_confirmed_criteria(db, sid)}
        assert crits["부드러운 촉감"]["kind"] == "preference"
        assert "avoid" not in crits["부드러운 촉감"]
    finally:
        db.close()

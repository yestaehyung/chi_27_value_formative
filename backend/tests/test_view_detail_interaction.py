"""자세히(view_detail) 클릭 = 탐색 신호 — 조용한 추론 대신 상호작용 (2026-07-03).

버그(live): 최고가 상품 자세히 클릭 1건 → flash가 '가격 부담' 토픽 날조(conf 0.9)
→ 메타 토픽과 ambiguous 충돌 → 유령 충돌 카드. 자세히 버튼은 UI상 아무것도 안 보여줬음.

새 설계: view_detail은 (a) FeedbackEvent 로그는 남기되 커밋 엔진(토픽 생성)을 태우지
않고, (b) 해당 상품 설명 + "어떤 점이 궁금하세요?" 질문을 Turn으로 반환한다 —
사용자의 답변이 진짜 명시 증거가 된다 (conflict_resolver의 해소-턴 영속화 패턴 재사용).

+ 충돌 카드 direct 게이트: 참가자 페이로드의 충돌은 severity=direct만
(구조 가드 show_conflict와 같은 철학 — 개입은 DB 사실일 때만, 가설은 칩으로).
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


def _recommend(client, sid):
    out = client.post(f"/api/sessions/{sid}/turns",
                      json={"role": "user", "content": "운동 좋아하는 친구에게 줄 스마트워치를 추천해주세요"}).json()
    assert out["agentResponse"]["agentAction"] == "recommend", out["agentResponse"]
    return out


def _topic_count(sid):
    from app.db import models
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        return db.query(models.IntentionTopic).filter(models.IntentionTopic.session_id == sid).count()
    finally:
        db.close()


def test_view_detail_returns_explanation_turn_and_mints_no_topics(client):
    sid = _new_session(client)
    out = _recommend(client, sid)
    product = out["recommendedProducts"][0]["product"]

    topics_before = _topic_count(sid)
    r = client.post(f"/api/sessions/{sid}/feedback",
                    json={"productId": product["id"], "type": "view_detail"})
    assert r.status_code == 200, r.text
    body = r.json()

    # (b) 상품 설명 + 질문이 에이전트 턴으로 반환된다
    turn = body.get("agentTurn")
    assert turn is not None, "view_detail must return an agent turn"
    assert turn["role"] == "service_agent"
    assert product["title"] in turn["content"]
    assert "?" in turn["content"]  # 궁금점 질문 포함
    # 답변 칩은 크리티컬 패스 밖 — 별도 엔드포인트가 마지막 에이전트 턴 기준으로 만든다 (2026-08-14)
    sug = client.post(f"/api/sessions/{sid}/reply-suggestions").json()
    assert sug["suggestions"], "answer chips must be available for the question"
    assert sug["forTurnId"] == turn["id"]

    # (a) 탐색 클릭은 토픽을 만들지 않는다 (커밋 엔진 미실행)
    assert _topic_count(sid) == topics_before
    assert body["newConflicts"] == []

    # 턴이 영속화되어 새로고침(세션 재로드)에도 남는다
    d = client.get(f"/api/sessions/{sid}").json()
    last = d["turns"][-1]
    assert last["role"] == "service_agent" and product["title"] in last["content"]

    # FeedbackEvent 로그는 유지 (행동 데이터)
    assert any(f["type"] == "view_detail" for f in d["feedback"])


def test_participant_conflicts_gate_direct_only(client):
    """참가자 세션 응답의 충돌은 direct만 — ambiguous는 DB/연구자 뷰 전용."""
    from app.db import models
    from app.db.database import SessionLocal

    sid = _new_session(client)
    db = SessionLocal()
    try:
        for i, sev in enumerate(("direct", "ambiguous")):
            db.add(models.PreferenceConflict(
                id=f"cf_test_{sev}_{sid[-4:]}", session_id=sid,
                severity=sev, status="open", conflict_type="priority_shift",
                old_assumption=f"old{i}", new_signal=f"new{i}",
                explanation_for_user="테스트", suggested_resolutions=[],
            ))
        db.commit()
    finally:
        db.close()

    d = client.get(f"/api/sessions/{sid}").json()
    sevs = {c["severity"] for c in d["conflicts"]}
    assert sevs == {"direct"}, f"participant payload must gate to direct only, got {sevs}"

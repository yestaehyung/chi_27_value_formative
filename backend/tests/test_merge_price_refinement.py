"""2026-08-16 가격 정제 병합 — "$300→$150로 좁혔는데 칩·필터가 $300 유지" 스테일 해소.

머지의 매칭 분기가 증거·신뢰도·우선순위만 갱신하고 값(priceMin/priceMax)·라벨을
방치했다 → 정제 발화("under $150")가 기존 토픽("budget under $300")에 유사 매칭되며
새 값이 조용히 버려졌다(라이브 실측). 이제 가격 필드를 담은 재추출은 값+라벨을
최신으로 갱신한다. 단 사용자가 직접 쓴 라벨(corrected_by_user)은 값만 갱신하고
문구는 보존한다 — test_edit_label_reinterpretation의 "사용자 문구 불가침" 보장은
이 좁혀진 형태로 유지된다.
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


def _merge(sid, extracted):
    from app.db import models
    from app.db.database import SessionLocal
    from app.ontology.merge import merge_topics

    db = SessionLocal()
    try:
        session = db.get(models.Session, sid)
        touched, created = merge_topics(db, session, extracted, source="turn")
        db.commit()
        rows = db.query(models.IntentionTopic).filter(
            models.IntentionTopic.session_id == sid).all()
        return ([(t.label, (t.hints or {}).get("priceMax")) for t in rows], len(created))
    finally:
        db.close()


BUDGET_300 = {"label": "budget under $300", "kind": "constraint", "priceMax": 405000,
              "confidence": 0.9, "priority": "must_have",
              "sourceEvidence": [{"type": "turn", "id": "tn_1", "quoteOrSummary": "under $300"}]}
BUDGET_150 = {"label": "budget under $150", "kind": "constraint", "priceMax": 202500,
              "confidence": 0.9, "priority": "must_have",
              "sourceEvidence": [{"type": "turn", "id": "tn_2", "quoteOrSummary": "under $150"}]}


def test_price_refinement_updates_value_and_label(client):
    sid = _new_session(client)
    rows, created = _merge(sid, [BUDGET_300])
    assert created == 1 and rows == [("budget under $300", 405000)]

    rows, created = _merge(sid, [BUDGET_150])
    assert created == 0, "정제는 새 칩이 아니라 기존 토픽 갱신이어야 한다"
    assert rows == [("budget under $150", 202500)]


def test_user_authored_label_survives_refinement(client):
    sid = _new_session(client)
    _merge(sid, [BUDGET_300])
    # 사용자가 라벨을 직접 수정한 상태를 만든다
    from app.db import models
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        t = db.query(models.IntentionTopic).filter(
            models.IntentionTopic.session_id == sid).one()
        t.label = "my absolute price cap"
        t.status = "corrected_by_user"
        db.commit()
    finally:
        db.close()

    rows, created = _merge(sid, [{**BUDGET_150, "label": "my absolute price cap"}])
    assert created == 0
    # 값은 최신으로, 사용자 문구는 그대로
    assert rows == [("my absolute price cap", 202500)]


def test_non_price_topics_keep_original_label(client):
    """가격 없는 토픽은 종전대로 라벨 불변 — 정제 갱신은 가격 필드가 있을 때만."""
    sid = _new_session(client)
    base = {"label": "mesh backrest", "kind": "preference", "confidence": 0.8,
            "sourceEvidence": [{"type": "turn", "id": "tn_1", "quoteOrSummary": "mesh"}]}
    _merge(sid, [base])
    rows, created = _merge(sid, [{**base, "label": "mesh backrest style",
                                  "sourceEvidence": [{"type": "turn", "id": "tn_2",
                                                      "quoteOrSummary": "breathable"}]}])
    assert created == 0
    assert rows[0][0] == "mesh backrest"

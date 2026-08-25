"""2026-08-25 기준 수정(revision) 일반화 — "$35→$50 올렸는데 칩·카드가 $35 유지" 해소.

가격 특례(test_merge_price_refinement)의 일반화: 추출이 revisesLabel로 기존 기준을
지목하면 라벨을 새 내용으로 교체한다. 가격뿐 아니라 색상 변경·완화도 같은 통로.
- directly_stated(사용자가 직접 말함)일 때만 — 약한 재추론은 라벨을 못 바꾼다.
- corrected_by_user 라벨은 문구 보존 (사용자 문구 불가침).
- rejected_by_user는 수정으로도 되살리지 않는다.
- 교체는 CorrectionEvent(action="revised_by_utterance")로 남는다 — 칩에서 고치든
  말로 고치든 같은 '사용자 수정' 사건이다.
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


def _corrections(sid):
    from app.db import models
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        return [(c.action, c.before.get("label"), c.after.get("label"))
                for c in db.query(models.CorrectionEvent).filter(
                    models.CorrectionEvent.session_id == sid).all()]
    finally:
        db.close()


def _ext(label, **kw):
    base = {"label": label, "kind": "preference", "confidence": 0.9,
            "confidenceLevel": "directly_stated",
            "sourceEvidence": [{"type": "turn", "id": kw.pop("ev", "tn_1"),
                                "quoteOrSummary": label}]}
    base.update(kw)
    return base


def test_budget_raise_via_revision(client):
    """$35→$50: 라벨·가격 값이 함께 최신이 되고 CorrectionEvent가 남는다."""
    sid = _new_session(client)
    rows, created = _merge(sid, [_ext("budget under $35", kind="constraint", priceMax=47250)])
    assert created == 1 and rows == [("budget under $35", 47250)]

    rows, created = _merge(sid, [_ext("budget under $50", kind="constraint", priceMax=67500,
                                      revisesLabel="budget under $35", ev="tn_2")])
    assert created == 0, "수정은 새 칩이 아니라 기존 토픽 교체여야 한다"
    assert rows == [("budget under $50", 67500)]
    assert ("revised_by_utterance", "budget under $35", "budget under $50") in _corrections(sid)


def test_non_price_revision_updates_label(client):
    """색상 변경처럼 가격이 없는 수정도 같은 통로로 라벨이 갱신된다."""
    sid = _new_session(client)
    _merge(sid, [_ext("white color")])
    rows, created = _merge(sid, [_ext("light blue color",
                                      revisesLabel="white color", ev="tn_2")])
    assert created == 0
    assert rows[0][0] == "light blue color"


def test_weak_inference_cannot_revise(client):
    """directly_stated가 아니면 revisesLabel이 있어도 라벨을 못 바꾼다."""
    sid = _new_session(client)
    _merge(sid, [_ext("white color")])
    rows, created = _merge(sid, [_ext("light blue color", revisesLabel="white color",
                                      confidenceLevel="strong_inference", ev="tn_2")])
    labels = [r[0] for r in rows]
    assert "white color" in labels, "약한 추론이 기존 라벨을 바꿔선 안 된다"
    assert _corrections(sid) == []


def test_user_authored_label_survives_revision(client):
    """사용자가 칩에서 손수 쓴 문구는 발화 수정으로도 덮지 않는다."""
    sid = _new_session(client)
    _merge(sid, [_ext("budget under $35", kind="constraint", priceMax=47250)])
    from app.db import models
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        t = db.query(models.IntentionTopic).filter(
            models.IntentionTopic.session_id == sid).one()
        t.label = "my price line"
        t.status = "corrected_by_user"
        db.commit()
    finally:
        db.close()

    rows, created = _merge(sid, [_ext("budget under $50", kind="constraint", priceMax=67500,
                                      revisesLabel="my price line", ev="tn_2")])
    assert created == 0
    # 값은 최신으로(기존 가격 특례), 문구는 사용자 것 그대로
    assert rows == [("my price line", 67500)]


def test_revision_does_not_resurrect_rejected(client):
    sid = _new_session(client)
    _merge(sid, [_ext("budget under $35", kind="constraint", priceMax=47250)])
    from app.db import models
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        t = db.query(models.IntentionTopic).filter(
            models.IntentionTopic.session_id == sid).one()
        t.status = "rejected_by_user"
        db.commit()
    finally:
        db.close()

    rows, created = _merge(sid, [_ext("budget under $50", kind="constraint", priceMax=67500,
                                      revisesLabel="budget under $35", ev="tn_2")])
    labels = [r[0] for r in rows]
    assert "budget under $35" in labels and created == 0, \
        "거부된 기준은 수정 발화로도 되살아나지 않는다 (유사 매칭 → 스킵)"


def test_plan_new_topics_treats_revision_as_existing(client):
    """plan 단계도 revision을 새 토픽으로 세지 않는다 (merge와 판정 일치)."""
    from app.ontology.merge import plan_new_topics

    class T:  # 최소 스텁
        def __init__(self, label, status="confirmed"):
            self.label, self.status = label, status

    existing = [T("white color")]
    ext = _ext("light blue color", revisesLabel="white color")
    assert plan_new_topics(existing, [ext]) == []
    # revisesLabel 없이 안 닮은 라벨이면 종전대로 새 토픽
    assert plan_new_topics(existing, [_ext("light blue color")]) != []

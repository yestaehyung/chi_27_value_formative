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


def test_polarity_reversal_updates_kind_and_implied(client):
    """반전 revision(원함→회피)은 라벨만이 아니라 kind·implied 파생까지 갱신한다
    (2026-08-26 전체 갱신 승인) — 옛 impliedHardConstraint가 남으면 화면과 정반대
    집행이 된다 (5차 QA: no drawers인데 서랍 책상 1위)."""
    sid = _new_session(client)
    _merge(sid, [_ext("desk with drawers", kind="constraint",
                      impliedHardConstraint="includes drawers")])
    _merge(sid, [_ext("no drawers", revisesLabel="desk with drawers",
                      kind="avoidance", impliedAvoidance="desks with drawers",
                      impliedHardConstraint=None, ev="tn_2")])

    from app.db import models
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        t = db.query(models.IntentionTopic).filter(
            models.IntentionTopic.session_id == sid).one()
        assert t.label == "no drawers"
        h = t.hints or {}
        assert h.get("kind") == "avoidance"
        assert h.get("impliedHardConstraint") is None, "옛 하드 제약 함의가 남으면 안 된다"
        assert h.get("impliedAvoidance") == "desks with drawers"
    finally:
        db.close()
    corr = _corrections(sid)
    assert ("revised_by_utterance", "desk with drawers", "no drawers") in corr


def test_revision_only_commit_regenerates_summary(client):
    """revision-only 턴(새 칩 0)에서도 요약이 새 라벨로 다시 생성된다 (2026-08-26).

    이전에는 요약 재생성이 '새 칩이 생긴 커밋'에만 걸려, 칩은 $50인데 요약은
    $35에 머물렀다 (5·6차 QA). 스크립트된 provider로 추출 출력을 고정하고,
    state_summary 호출 여부와 그 재료(criteria 라벨)를 검사한다.
    """
    import asyncio as _asyncio

    from app.core.ids import new_id
    from app.db import models
    from app.db.database import SessionLocal
    from app.llm.mock_rules import TASK_HANDLERS
    from app.preference_commit.commit_engine import run_preference_commit

    db = SessionLocal()
    try:
        session = db.get(models.Session, _new_session(client))

        calls: list[tuple[str, dict]] = []

        class Scripted:
            name = "stub"
            def __init__(self):
                self.step = 0
            async def generate_json(self, _messages, task=None, context=None, **_kw):
                calls.append((task, context or {}))
                if task == "topic_extraction":
                    if self.step == 0:
                        self.step = 1
                        return {"topics": [{
                            "label": "budget under $35", "kind": "constraint",
                            "confidence": 0.9, "confidenceLevel": "directly_stated",
                            "priceMax": 47250,
                            "sourceEvidence": [{"type": "turn", "id": self.tid1,
                                                "quoteOrSummary": "under $35"}],
                        }], "questionSignals": [], "interpretationCandidate": None}
                    return {"topics": [{
                        "label": "budget under $50", "kind": "constraint",
                        "confidence": 0.9, "confidenceLevel": "directly_stated",
                        "revisesLabel": "budget under $35", "priceMax": 67500,
                        "sourceEvidence": [{"type": "turn", "id": self.tid2,
                                            "quoteOrSummary": "raise to $50"}],
                    }], "questionSignals": [], "interpretationCandidate": None}
                return TASK_HANDLERS[task](context or {})

        prov = Scripted()
        t1 = models.Turn(id=new_id("turn"), session_id=session.id, turn_index=0,
                         role="user", content="Keep it under $35.")
        db.add(t1); db.commit(); prov.tid1 = t1.id
        _asyncio.run(run_preference_commit(db, prov, session, [t1.id], [], "user_utterance"))

        calls.clear()
        t2 = models.Turn(id=new_id("turn"), session_id=session.id, turn_index=2,
                         role="user", content="You may raise it to $50.")
        db.add(t2); db.commit(); prov.tid2 = t2.id
        _asyncio.run(run_preference_commit(db, prov, session, [t2.id], [], "user_utterance"))

        summary_calls = [(t, c) for t, c in calls if t == "state_summary"]
        assert summary_calls, "revision-only 턴에서 요약이 재생성돼야 한다"
        labels = [c.get("criteria") or c for _, c in summary_calls]
        assert "budget under $50" in str(labels), f"요약 재료가 새 라벨이어야 한다: {labels}"
        assert "budget under $35" not in str(labels), "옛 라벨이 요약 재료에 남으면 안 된다"
        # revision-only 턴에서는 충돌 감지를 돌리지 않는다
        assert not any(t == "conflict_detection" for t, _ in calls)
    finally:
        db.rollback(); db.close()

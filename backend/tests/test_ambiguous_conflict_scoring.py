"""ambiguous 충돌이 가치 점수를 지우지 않는다 (2026-08-02).

배경 — FS1 라이브 26세션 실측에서 발견:
  · ambiguous 충돌 42개 전부 `open` (해소된 것 0개)
  · 26세션 중 12세션이 **끝까지 anchorScores가 전부 0**
  · 원인: 값 계산이 ambiguous 토픽까지 제외하는데, ambiguous는 참가자에게 카드로
    띄우지 않아 사용자가 풀 방법이 없었다 → 한번 걸리면 영구 제외

두 가지를 고정한다:
  ① ambiguous 충돌은 anchorScores에서 토픽을 제외하지 않는다 (direct만 제외)
  ② 칩 확인/거부가 그 토픽의 ambiguous 충돌을 닫는다 (direct는 그대로 둔다)
"""
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_amb_"), "test.db"))
os.environ.setdefault("VC_EXPORT_DIR", tempfile.mkdtemp(prefix="vc_amb_exp_"))
os.environ["VC_LLM_PROVIDER"] = "mock"

import pytest
from fastapi.testclient import TestClient

from app.core.ids import new_id
from app.db import models
from app.db.database import SessionLocal
from app.main import app
from app.ontology.state_builder import build_snapshot, get_active_topics


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _mk_session(db, sid):
    s = models.Session(id=sid, mode="manual", scenario_id="gift_for_other",
                       current_stage="exploration", status="active", meta={})
    db.add(s)
    return s


def _mk_topic(db, sid, label, anchor):
    t = models.IntentionTopic(
        id=new_id("topic"), session_id=sid, label=label, description=label,
        source="utterance", explicitness="explicit", status="confirmed",
        priority="high", confidence=0.9, evidence_ids=[], hints={},
    )
    db.add(t)
    db.flush()
    db.add(models.AnchorMapping(
        id=new_id("anch"), topic_id=t.id, anchor=anchor, score=0.95,
        confidence="confirmed", evidence_strength="strong",
        decision_impact="high", temporal_status="active",
    ))
    return t


def _mk_conflict(db, sid, old_t, new_t, severity):
    c = models.PreferenceConflict(
        id=new_id("conflict"), session_id=sid, severity=severity, status="open",
        conflict_type="scope_change", old_topic_id=old_t.id, new_topic_id=new_t.id,
        old_assumption=old_t.label, new_signal=new_t.label,
        explanation_for_user="확인이 필요해요", suggested_resolutions=[],
    )
    db.add(c)
    return c


def _scores(db, session):
    db.flush()
    snap = build_snapshot(db, session)
    return {k: v for k, v in (snap.anchor_scores or {}).items() if v}


def test_ambiguous_conflict_keeps_scores(client):
    """ambiguous 충돌에 묶여도 두 토픽 모두 값에 반영된다 — 이게 이번 수정의 핵심."""
    db = SessionLocal()
    try:
        sid = new_id("sess")
        session = _mk_session(db, sid)
        a = _mk_topic(db, sid, "태블릿 구매 기준을 모름", "Epistemic")
        b = _mk_topic(db, sid, "영상 시청에 적합한 태블릿", "Functional")
        _mk_conflict(db, sid, a, b, "ambiguous")
        db.flush()

        scores = _scores(db, session)
        assert "Epistemic" in scores, f"ambiguous가 값을 지웠다: {scores}"
        assert "Functional" in scores, f"ambiguous가 값을 지웠다: {scores}"
    finally:
        db.rollback()
        db.close()


def test_direct_conflict_still_excludes(client):
    """direct는 그대로 제외한다 — 확실한 모순 상태로 값을 오염시키지 않는다."""
    db = SessionLocal()
    try:
        sid = new_id("sess")
        session = _mk_session(db, sid)
        a = _mk_topic(db, sid, "가격이 낮을수록 좋음", "Functional")
        b = _mk_topic(db, sid, "저렴해 보이지 않기", "Social")
        _mk_conflict(db, sid, a, b, "direct")
        # 충돌에 안 걸린 토픽 하나 — 이건 남아야 direct 제외가 동작한 걸 확인할 수 있다
        _mk_topic(db, sid, "오래 쓸 수 있는 것", "Emotional")
        db.flush()

        scores = _scores(db, session)
        assert "Emotional" in scores
        assert "Functional" not in scores, f"direct가 제외되지 않았다: {scores}"
        assert "Social" not in scores, f"direct가 제외되지 않았다: {scores}"
    finally:
        db.rollback()
        db.close()


def test_chip_confirm_resolves_ambiguous_conflict(client):
    """칩 '맞아요'가 그 토픽의 ambiguous 충돌을 닫는다 — 사용자 행동에 효과를 준다."""
    sid = None
    db = SessionLocal()
    try:
        sid = new_id("sess")
        _mk_session(db, sid)
        a = _mk_topic(db, sid, "영상 시청에 적합한 태블릿", "Functional")
        b = _mk_topic(db, sid, "태블릿 구매 기준을 모름", "Epistemic")
        c = _mk_conflict(db, sid, a, b, "ambiguous")
        db.commit()
        topic_id, conflict_id = a.id, c.id
    finally:
        db.close()

    r = client.post(f"/api/preferences/chips/{topic_id}/action", json={"action": "confirm"})
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        conf = db.get(models.PreferenceConflict, conflict_id)
        assert conf.status == "manually_resolved", f"충돌이 안 닫혔다: {conf.status}"
        assert conf.resolved_at is not None
    finally:
        db.close()


def test_chip_confirm_leaves_direct_conflict_open(client):
    """direct는 칩 확인으로 닫히지 않는다 — 전용 충돌 카드로 명시 해소해야 한다."""
    db = SessionLocal()
    try:
        sid = new_id("sess")
        _mk_session(db, sid)
        a = _mk_topic(db, sid, "가격이 낮을수록 좋음", "Functional")
        b = _mk_topic(db, sid, "저렴해 보이지 않기", "Social")
        c = _mk_conflict(db, sid, a, b, "direct")
        db.commit()
        topic_id, conflict_id = a.id, c.id
    finally:
        db.close()

    r = client.post(f"/api/preferences/chips/{topic_id}/action", json={"action": "confirm"})
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        conf = db.get(models.PreferenceConflict, conflict_id)
        assert conf.status == "open", f"direct가 칩 확인으로 닫혔다: {conf.status}"
    finally:
        db.close()

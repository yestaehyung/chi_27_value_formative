"""ours-v3 칩 확인 게이트 (2026-08-27 파일럿) — 추천 전 칩 확인 흐름.

새 칩이 생긴 추천 턴은 상품 대신 confirm_chips 턴(결정론 템플릿, 노출 0)을 반환하고
meta.pendingRecommend를 세운다. /proceed-recommend가 확인된 기준으로 추천을 수행한다.
플래그(ui_variant) 미설정이면 기존 동작 그대로 — 본실험 경로 보존이 계약이다.
"""
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_test_"), "test.db"))
os.environ.setdefault("VC_LLM_PROVIDER", "mock")

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _new_ours_session(client):
    r = client.post("/api/sessions", json={"mode": "manual", "scenarioId": "gift_for_other",
                                           "studyCondition": "ours"})
    assert r.status_code == 200, r.text
    return r.json()["sessionId"]


UTTER = "동생 생일 선물로 스마트워치 알아보고 있어요. 예산은 20만원 정도예요."


def test_flag_off_recommends_directly(client):
    sid = _new_ours_session(client)
    r = client.post(f"/api/sessions/{sid}/turns", json={"role": "user", "content": UTTER})
    assert r.status_code == 200
    assert r.json()["agentResponse"]["agentAction"] == "recommend"
    assert len(r.json()["recommendedProducts"]) > 0


def test_v3_gates_then_proceeds(client):
    settings.ui_variant = "ours-v3"
    try:
        sid = _new_ours_session(client)
        r = client.post(f"/api/sessions/{sid}/turns", json={"role": "user", "content": UTTER})
        assert r.status_code == 200
        body = r.json()
        # 게이트 턴: 상품 없이 칩 확인 요청
        assert body["agentResponse"]["agentAction"] == "confirm_chips"
        assert body["recommendedProducts"] == []
        assert "right" in body["agentResponse"]["content"] or "오른쪽" in body["agentResponse"]["content"]
        # 칩은 이미 생겨 있어야 확인할 대상이 있다
        assert len((body["preferenceState"].get("userVisibleSummary") or {}).get("chips") or []) > 0

        # 2단계: 확인 후 추천 수행
        r2 = client.post(f"/api/sessions/{sid}/proceed-recommend")
        assert r2.status_code == 200, r2.text
        b2 = r2.json()
        assert b2["agentResponse"]["agentAction"] == "recommend"
        assert len(b2["recommendedProducts"]) > 0

        # 플래그 소모 — 재호출은 409
        r3 = client.post(f"/api/sessions/{sid}/proceed-recommend")
        assert r3.status_code == 409
    finally:
        settings.ui_variant = ""


def test_v3_does_not_gate_baseline2(client):
    settings.ui_variant = "ours-v3"
    try:
        r = client.post("/api/sessions", json={"mode": "manual", "scenarioId": "gift_for_other",
                                               "studyCondition": "baseline2"})
        sid = r.json()["sessionId"]
        r = client.post(f"/api/sessions/{sid}/turns", json={"role": "user", "content": UTTER})
        assert r.json()["agentResponse"]["agentAction"] == "recommend"
        assert len(r.json()["recommendedProducts"]) > 0
    finally:
        settings.ui_variant = ""


def test_v3_gate_blocks_debounced_refresh_bypass(client):
    """게이트 대기 중 칩 수정→디바운스 재추천이 게이트를 우회하면 안 된다 (2026-08-27).

    수정 자체는 저장되고, 재추천은 'gate'로 보류 — /proceed-recommend가 수정
    반영분까지 실어 나른다."""
    settings.ui_variant = "ours-v3"
    try:
        sid = _new_ours_session(client)
        r = client.post(f"/api/sessions/{sid}/turns", json={"role": "user", "content": UTTER})
        assert r.json()["agentResponse"]["agentAction"] == "confirm_chips"
        chips = (r.json()["preferenceState"].get("userVisibleSummary") or {}).get("chips") or []
        assert chips
        # 게이트 중 칩 수정 (deferRecommend=True — 프론트 기본)
        ra = client.post(f"/api/preferences/chips/{chips[0]['id']}/action",
                         json={"action": "increase_priority", "deferRecommend": True})
        assert ra.status_code == 200, ra.text
        assert ra.json().get("recommendationDeferred") == "gate"
        # 디바운스 플러시 시뮬레이션 — 역시 게이트로 보류
        rf = client.post(f"/api/preferences/sessions/{sid}/refresh-recommendation",
                         json={"corrections": [{"action": "increase_priority"}]})
        assert rf.status_code == 200
        assert rf.json().get("recommendationDeferred") == "gate"
        assert "recommendTurn" not in rf.json()
        # proceed가 수정 반영 추천을 수행
        rp = client.post(f"/api/sessions/{sid}/proceed-recommend")
        assert rp.status_code == 200
        assert len(rp.json()["recommendedProducts"]) > 0
    finally:
        settings.ui_variant = ""


def test_recommendation_delivery_consumes_gate(client):
    """어떤 경로로든 추천이 나가면 게이트 플래그가 소모된다 — 충돌 해소 경로가
    추천을 내보낸 뒤 proceed가 이중 추천을 쏘는 엣지 차단 (2026-08-27)."""
    import asyncio as _asyncio

    from app.agents.service_agent import recommend_after_resolution
    from app.db import models
    from app.db.database import SessionLocal
    from app.ontology.state_builder import build_snapshot

    settings.ui_variant = "ours-v3"
    try:
        sid = _new_ours_session(client)
        r = client.post(f"/api/sessions/{sid}/turns", json={"role": "user", "content": UTTER})
        assert r.json()["agentResponse"]["agentAction"] == "confirm_chips"

        db = SessionLocal()
        try:
            session = db.get(models.Session, sid)
            assert (session.meta or {}).get("pendingRecommend") is True
            snapshot = build_snapshot(db, session)
            db.commit()
            # 충돌 해소 경로가 호출하는 함수 — 추천을 내보내며 게이트를 소모해야 한다
            _asyncio.run(recommend_after_resolution(db, session, snapshot))
            db.refresh(session)
            assert not (session.meta or {}).get("pendingRecommend")
        finally:
            db.close()
        # 소모된 게이트에 대한 proceed는 409 — 이중 추천 없음
        assert client.post(f"/api/sessions/{sid}/proceed-recommend").status_code == 409
    finally:
        settings.ui_variant = ""


def test_v4_keeps_gate_without_hypotheses(client):
    """ours-v4(해석 칩판)도 게이트는 유지한다 — v4 = 구과제 + 게이트 + 해석 표시.
    가설 칩 프롬프트(ours-v3 전용)는 v4에서 꺼진 채로 남는다."""
    settings.ui_variant = "ours-v4"
    try:
        sid = _new_ours_session(client)
        r = client.post(f"/api/sessions/{sid}/turns", json={"role": "user", "content": UTTER})
        assert r.json()["agentResponse"]["agentAction"] == "confirm_chips"
        assert client.post(f"/api/sessions/{sid}/proceed-recommend").status_code == 200
    finally:
        settings.ui_variant = ""

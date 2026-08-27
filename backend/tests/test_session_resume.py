"""미완주 세션 재개 (2026-08-27, v4 파일럿 관찰 대응).

같은 참가자가 같은 카테고리 과제를 다시 열면 진행 중 세션을 돌려준다 —
빈손 후 이탈→재진입이 세션을 쪼개던 문제(모니터 과제 2회 생성)의 수정.
감사 완료 세션은 불가침, category 없는 경로(데모·시뮬레이션)는 미발동.
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


@pytest.fixture(scope="module")
def category(client):
    from app.db import models
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        return db.query(models.Product.category).filter(
            models.Product.category.isnot(None)).first()[0]
    finally:
        db.close()


def _create(client, category, pid):
    r = client.post("/api/sessions", json={"mode": "manual", "category": category,
                                           "participantId": pid, "studyCondition": "ours"})
    assert r.status_code == 200, r.text
    return r.json()


def test_reentry_returns_same_session(client, category):
    first = _create(client, category, "part_resume_a")
    again = _create(client, category, "part_resume_a")
    assert again["sessionId"] == first["sessionId"]
    assert again.get("resumed") is True


def test_audited_session_not_reused(client, category):
    from app.db import models
    from app.db.database import SessionLocal
    first = _create(client, category, "part_resume_b")
    db = SessionLocal()
    try:
        s = db.get(models.Session, first["sessionId"])
        s.meta = {**(s.meta or {}), "criterionAudit": {"ownCriteria": []}}
        db.commit()
    finally:
        db.close()
    again = _create(client, category, "part_resume_b")
    assert again["sessionId"] != first["sessionId"], "감사 완료 세션은 재사용 금지"


def test_no_participant_no_reuse(client, category):
    r1 = client.post("/api/sessions", json={"mode": "manual", "category": category})
    r2 = client.post("/api/sessions", json={"mode": "manual", "category": category})
    assert r1.json()["sessionId"] != r2.json()["sessionId"]


def test_scenario_path_unaffected(client):
    a = client.post("/api/sessions", json={"mode": "manual", "scenarioId": "gift_for_other",
                                           "participantId": "part_resume_c"}).json()
    b = client.post("/api/sessions", json={"mode": "manual", "scenarioId": "gift_for_other",
                                           "participantId": "part_resume_c"}).json()
    assert a["sessionId"] != b["sessionId"], "시나리오 경로(시뮬레이션)는 종전대로 매번 새 세션"

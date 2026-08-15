"""관리자 수동 조건 배정 (2026-08-16) — 조건별 순차 모집.

/api/research/study-config 로 forcedCondition을 지정하면 신규 참가자 전원이 그 조건으로
배정된다(균형 알고리즘 우회). null이면 자동 균형으로 복귀. 이미 배정된 참가자는 불변.
StudySetting(key-value) 테이블에 저장 — 재배포 없이 관리자 페이지에서 전환한다.
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


def _survey_condition(client):
    r = client.post("/api/study/survey", json={"answers": {}, "profile": {}})
    assert r.status_code == 200, r.text
    return r.json()["studyCondition"]


def test_forced_condition_overrides_balancing(client):
    r = client.put("/api/research/study-config", json={"forcedCondition": "ours"})
    assert r.status_code == 200 and r.json()["forcedCondition"] == "ours"
    # 균형이라면 연속 배정이 조건을 순환해야 하지만, 고정 모드에선 전원 ours
    assert [_survey_condition(client) for _ in range(3)] == ["ours", "ours", "ours"]
    assert client.get("/api/research/study-config").json()["forcedCondition"] == "ours"


def test_forced_condition_applies_to_session_path_too(client):
    """조건 없는 참가자가 세션 생성으로 들어와도(경로 ③) 고정 조건을 받는다."""
    client.put("/api/research/study-config", json={"forcedCondition": "baseline2"})
    r = client.post("/api/sessions", json={"mode": "manual", "scenarioId": "gift_for_other"})
    assert r.status_code == 200, r.text
    sid = r.json()["sessionId"]
    d = client.get(f"/api/sessions/{sid}").json()
    assert d["session"]["metadata"]["studyCondition"] == "baseline2"


def test_explicit_request_condition_still_wins(client):
    """테스트 세션 생성(경로 ② — 요청 명시)은 고정 모드와 무관하게 요청값을 쓴다."""
    client.put("/api/research/study-config", json={"forcedCondition": "baseline1"})
    r = client.post("/api/sessions", json={"mode": "manual", "scenarioId": "gift_for_other",
                                           "participantId": "test_admin_x1", "studyCondition": "ours"})
    d = client.get(f"/api/sessions/{r.json()['sessionId']}").json()
    assert d["session"]["metadata"]["studyCondition"] == "ours"


def test_null_returns_to_balanced(client):
    r = client.put("/api/research/study-config", json={"forcedCondition": None})
    assert r.json()["forcedCondition"] is None
    # 자동 균형 복귀 — 유효 조건 중 하나가 배정되면 충분 (정확한 값은 카운트 의존)
    assert _survey_condition(client) in ("baseline1", "baseline2", "ours")


def test_invalid_condition_rejected(client):
    assert client.put("/api/research/study-config", json={"forcedCondition": "nope"}).status_code == 400

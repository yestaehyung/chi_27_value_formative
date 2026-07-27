"""본실험 between-subjects 조건 배정 검증.

핵심 불변식 두 개:
  ① 한 참가자의 모든 과제는 같은 조건 — 클라이언트가 다른 값을 보내도 바뀌지 않는다
  ② 배정은 균형을 맞춘다 — 과제를 시작한 참가자 수 기준
"""
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_cond_"), "test.db"))
os.environ.setdefault("VC_EXPORT_DIR", tempfile.mkdtemp(prefix="vc_cond_exp_"))
os.environ["VC_LLM_PROVIDER"] = "mock"

import pytest
from fastapi.testclient import TestClient

from app.core.conditions import STUDY_CONDITIONS
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def enroll(client, label):
    r = client.post("/api/study/survey", json={
        "answers": {"PRE_C1": "예"}, "profile": {}, "label": label,
    })
    assert r.status_code == 200, r.text
    return r.json()


def start_task(client, pid, scenario="gift_for_other", condition="correctable"):
    """프론트가 보내는 studyCondition은 일부러 항상 correctable — 참가자 조건이 이겨야 한다."""
    r = client.post("/api/sessions", json={
        "mode": "manual", "scenarioId": scenario,
        "studyCondition": condition, "participantId": pid,
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_survey_assigns_a_condition(client):
    body = enroll(client, "cond-01")
    assert body["studyCondition"] in STUDY_CONDITIONS


def test_participant_condition_beats_request(client):
    """세션 생성 요청이 'correctable'을 보내도 참가자에 배정된 조건이 적용된다."""
    body = enroll(client, "cond-02")
    pid, assigned = body["participantId"], body["studyCondition"]

    out = start_task(client, pid, condition="correctable")
    assert out["session"]["metadata"]["studyCondition"] == assigned


def test_same_participant_keeps_condition_across_tasks(client):
    """3개 과제(세션)가 전부 같은 조건이어야 between-subjects가 성립한다."""
    body = enroll(client, "cond-03")
    pid, assigned = body["participantId"], body["studyCondition"]

    conditions = {
        start_task(client, pid, s)["session"]["metadata"]["studyCondition"]
        for s in ("gift_for_other", "gift_for_other", "gift_for_other")
    }
    assert conditions == {assigned}


def test_assignment_balances_across_started_participants(client):
    """과제를 시작한 참가자 기준으로 조건이 고르게 퍼진다 (조건당 최대 1명 차이)."""
    for i in range(9):
        body = enroll(client, f"cond-bal-{i}")
        start_task(client, body["participantId"])

    balance = client.get("/api/research/condition-balance").json()
    started = {c["condition"]: c["started"] for c in balance["conditions"]}
    assert set(started) == set(STUDY_CONDITIONS)
    assert max(started.values()) - min(started.values()) <= 1, started
    assert balance["totalStarted"] >= 9


def test_survey_only_participant_counts_as_dropped(client):
    """설문만 내고 과제를 시작하지 않으면 균형 계산에서 빠진다 (이탈이 배정을 영구 왜곡하지 않게)."""
    before = client.get("/api/research/condition-balance").json()
    enroll(client, "cond-dropout")  # 세션을 만들지 않는다
    after = client.get("/api/research/condition-balance").json()

    assert after["totalStarted"] == before["totalStarted"]
    assert after["dropped"] == before["dropped"] + 1


def test_condition_is_visible_to_researcher(client):
    body = enroll(client, "cond-visible")
    start_task(client, body["participantId"])
    parts = client.get("/api/research/participants").json()["participants"]
    row = next(p for p in parts if p["id"] == body["participantId"])
    assert row["studyCondition"] == body["studyCondition"]

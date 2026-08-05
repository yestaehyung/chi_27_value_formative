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


def start_task(client, pid, scenario="gift_for_other", condition="ours"):
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

    out = start_task(client, pid, condition="ours")
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


def _assigned_counts(client) -> dict[str, int]:
    """지금까지 배정된 조건별 인원 — 테스트가 전역 DB 상태에 기대지 않기 위해 직접 읽는다."""
    rows = client.get("/api/research/participants").json()["participants"]
    counts = {c: 0 for c in STUDY_CONDITIONS}
    for p in rows:
        if p.get("studyCondition") in counts:
            counts[p["studyCondition"]] += 1
    return counts


def test_consecutive_enrollments_get_different_conditions(client):
    """**아무도 과제를 시작하기 전에** 연달아 등록해도 배정이 계속 갈려야 한다.

    랩 세션/온라인 배치에서 참가자 여럿이 동시에 설문을 내는 건 정상 상황이다.
    배정을 '과제를 시작한 인원'으로 세면 이때 카운트가 전부 0이라 전원 같은 조건을
    받아버린다 (2026-07-28 라이브 스모크에서 실제로 3명 전원 baseline이 나왔다).

    "3명이 서로 다른 조건"으로 단언하면 DB가 비어 있을 때만 성립한다. 테스트 모듈들이
    임시 DB를 공유하는 구조라 다른 모듈이 만든 참가자가 이미 균형을 기울여 놓는다.
    그래서 실제 불변식 — **매 배정이 그 시점의 최소 조건을 고른다** — 을 직접 검사한다.
    이게 minimization의 정의이자 원래 버그(모두 같은 조건)를 그대로 잡아낸다.
    """
    for i in range(len(STUDY_CONDITIONS) * 2):
        before = _assigned_counts(client)
        got = enroll(client, f"cond-batch-{i}")["studyCondition"]
        lowest = min(before.values())
        assert before[got] == lowest, (
            f"{i}번째 배정이 최소 조건을 고르지 않았다: {got}(={before[got]}) vs {before}"
        )


def test_assignment_balances_across_participants(client):
    """배정된 참가자 기준으로 조건이 고르게 퍼진다 (조건당 최대 1명 차이)."""
    for i in range(9):
        body = enroll(client, f"cond-bal-{i}")
        start_task(client, body["participantId"])

    balance = client.get("/api/research/condition-balance").json()
    assigned = {c["condition"]: c["assigned"] for c in balance["conditions"]}
    assert set(assigned) == set(STUDY_CONDITIONS)
    assert max(assigned.values()) - min(assigned.values()) <= 1, assigned


def test_dropout_is_visible_but_still_holds_a_slot(client):
    """설문만 내고 이탈하면 assigned에는 남고 started에는 안 잡힌다 — 과모집 판단 근거."""
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

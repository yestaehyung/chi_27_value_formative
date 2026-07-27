"""본실험(메인 스터디) 설문 5종의 저장 경로 검증 — MockLLMProvider 기준.

설문 도구 자체는 프론트(`lib/mainSurvey.ts`)에 선언돼 있고, 여기서는 백엔드가
응답을 **어디에 어떤 모양으로** 넣는지를 고정한다:
  사전 → participants.survey / 과제직전 → sessions.meta.preTaskSurvey /
  과제직후 → sessions.meta.postSurvey / 전체종료 → participants.survey.postStudy /
  기준별 → criterion_validations 테이블
"""
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_survey_"), "test.db"))
os.environ.setdefault("VC_EXPORT_DIR", tempfile.mkdtemp(prefix="vc_survey_exp_"))
os.environ["VC_LLM_PROVIDER"] = "mock"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def task_session(client):
    """사전 설문으로 참가자를 만들고, 그 참가자의 세션에서 대화를 한 턴 진행한다."""
    r = client.post("/api/study/survey", json={
        "answers": {"PRE_C1": "예", "PRE_C2": "예", "PRE_C3": "예",
                    "PRE_1": "일주일에 여러 번", "PRE_3": 6, "PRE_4": 5,
                    "PRE_7": 6, "PRE_8": 7, "PRE_9": 5, "PRE_10": 7},
        "profile": {"llm": 5.5, "agent_knowledge": 6.5, "prior_trust": 6.0},
        "label": "P-main-01",
    })
    assert r.status_code == 200, r.text
    pid = r.json()["participantId"]

    r = client.post("/api/sessions", json={
        "mode": "manual", "scenarioId": "gift_for_other",
        "studyCondition": "correctable", "participantId": pid,
    })
    assert r.status_code == 200, r.text
    sid = r.json()["sessionId"]

    # 기준이 추론되도록 한 턴 발화
    r = client.post(f"/api/sessions/{sid}/turns", json={
        "role": "user",
        "content": "운동 좋아하는 친구에게 줄 스마트워치를 찾고 있어요. 너무 저렴해 보이면 곤란해요.",
    })
    assert r.status_code == 200, r.text
    return pid, sid


def test_pre_task_survey_lands_on_session_meta(client, task_session):
    _pid, sid = task_session
    answers = {"TPRE_K1": 3, "TPRE_K2": 4, "TPRE_E1": "1회 있다", "TPRE_E2": "없다",
               "TPRE_CLARITY_1": 3, "TPRE_CLARITY_2": 2, "TPRE_CLARITY_3": 4}
    r = client.put(f"/api/study/sessions/{sid}/pre-task-survey", json={
        "answers": answers, "category": "스마트워치",
        "profile": {"domain_knowledge": 3.5, "criteria_clarity": 3.0},
    })
    assert r.status_code == 200, r.text
    assert r.json()["profile"]["criteria_clarity"] == 3.0

    meta = client.get(f"/api/sessions/{sid}").json()["session"]["metadata"]
    pre = meta["preTaskSurvey"]
    assert pre["category"] == "스마트워치"
    assert pre["answers"]["TPRE_CLARITY_1"] == 3
    assert pre["submittedAt"]


def test_post_task_survey_coexists_with_pre(client, task_session):
    """직후 설문은 기존 post-survey 채널을 그대로 쓴다 — 직전 응답을 덮지 않아야 Δ를 낼 수 있다."""
    _pid, sid = task_session
    r = client.put(f"/api/study/sessions/{sid}/post-survey", json={
        "answers": {"TPOST_CLARITY_1": 6, "TPOST_CLARITY_2": 5, "TPOST_CLARITY_3": 6,
                    "TPOST_A1": 6, "TPOST_TLX_MENTAL": 3, "TPOST_TLX_PERFORMANCE": 6},
        "profile": {"criteria_clarity": 5.67, "tlx": 2.5},
    })
    assert r.status_code == 200, r.text

    meta = client.get(f"/api/sessions/{sid}").json()["session"]["metadata"]
    assert meta["preTaskSurvey"]["answers"]["TPRE_CLARITY_1"] == 3   # 직전 응답 보존
    assert meta["postSurvey"]["answers"]["TPOST_CLARITY_1"] == 6
    # Δ(명확성) = 5.67 - 3.0 을 두 채널에서 계산할 수 있다
    assert meta["postSurvey"]["profile"]["criteria_clarity"] > meta["preTaskSurvey"]["profile"]["criteria_clarity"]


def test_criterion_candidates_returns_topics_with_evidence(client, task_session):
    _pid, sid = task_session
    r = client.get(f"/api/study/sessions/{sid}/criterion-candidates?limit=5")
    assert r.status_code == 200, r.text
    criteria = r.json()["criteria"]
    assert 1 <= len(criteria) <= 5
    first = criteria[0]
    assert first["topic"]["label"]
    assert isinstance(first["evidence"], list)


def test_criterion_validations_save_and_replace(client, task_session):
    _pid, sid = task_session
    criteria = client.get(f"/api/study/sessions/{sid}/criterion-candidates").json()["criteria"]
    topic_id = criteria[0]["topic"]["id"]

    r = client.post(f"/api/study/sessions/{sid}/criterion-validations", json={
        "items": [{
            "topicId": topic_id,
            "topicLabel": criteria[0]["topic"]["label"],
            "matches": "일치한다",
            "importance": 6,
            "evidenceSupports": "뒷받침한다",
            "formation": "처음부터_미표현",
        }],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["saved"] == 1
    assert body["validations"][0]["formation"] == "처음부터_미표현"
    assert body["validations"][0]["importance"] == 6

    # 재제출은 덮어쓴다 — 과제당 1회이므로 행이 쌓이면 안 된다
    r = client.post(f"/api/study/sessions/{sid}/criterion-validations", json={
        "items": [{"topicId": topic_id, "matches": "부분적으로 일치한다",
                   "importance": 4, "formation": "대화중_새로형성"}],
    })
    assert r.status_code == 200, r.text
    assert r.json()["saved"] == 1
    assert r.json()["validations"][0]["matches"] == "부분적으로 일치한다"


def test_unknown_topic_does_not_wipe_previous_answers(client, task_session):
    """전부 알 수 없는 topic인 요청은 0건 저장하되, **이전 응답을 지우지 않는다**
    (교체는 쓸 행이 있을 때만 — 빈 제출이 수집된 데이터를 날리면 복구 불가)."""
    _pid, sid = task_session
    r = client.post(f"/api/study/sessions/{sid}/criterion-validations", json={
        "items": [{"topicId": "topic_does_not_exist", "matches": "일치한다"}],
    })
    assert r.status_code == 200, r.text
    assert r.json()["saved"] == 0

    # 직전 테스트가 저장한 응답이 그대로 살아있어야 한다
    files = client.post("/api/exports/run").json()["files"]
    assert files["criterion_validations.jsonl"] >= 1


def test_post_study_survey_lands_on_participant(client, task_session):
    pid, _sid = task_session
    r = client.put(f"/api/study/participants/{pid}/post-study-survey", json={
        "answers": {"END_I1": 6, "END_I2": 5, "END_I3": 6,
                    "END_V1": 5, "END_V2": 6, "END_V3": 5,
                    "END_E1": 7, "END_E2": 6, "END_E3": 6},
        "profile": {"interpretability": 5.67, "evidence": 5.33, "edit_usability": 6.33},
    })
    assert r.status_code == 200, r.text
    assert r.json()["profile"]["edit_usability"] == 6.33

    # 연구자 열람 API가 사전(answers)과 종료(postStudy)를 함께 돌려줘야 한다
    survey = client.get(f"/api/research/participants/{pid}/survey").json()
    assert survey["answers"]["PRE_C1"] == "예"
    assert survey["postStudy"]["answers"]["END_E1"] == 7


def test_criterion_validations_are_exported(client, task_session):
    r = client.post("/api/exports/run")
    assert r.status_code == 200, r.text
    files = r.json()["files"]
    assert "criterion_validations.jsonl" in files
    assert files["criterion_validations.jsonl"] >= 1

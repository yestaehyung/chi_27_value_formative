"""본실험 과제 계획의 서버 진실 (2026-08-16).

진행 상태가 sessionStorage에만 있으면 탭 유실·이전 라운드 잔존 큐로 4과제가 2과제 만에
"전부 완료"로 표시된다(실측). 계획은 Participant.task_plan에 저장하고, 완료는 세션 meta의
finalChoice+postSurvey 마커로 서버가 센다 — 클라이언트 큐는 캐시로 강등.
"""
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_test_"), "test.db"))
os.environ.setdefault("VC_LLM_PROVIDER", "mock")

import pytest
from fastapi.testclient import TestClient

from app.main import app

PLAN = [
    {"category": "헤드폰", "familiarity": "familiar"},
    {"category": "노트북", "familiarity": "familiar"},
    {"category": "데스크체어", "familiarity": "unfamiliar"},
    {"category": "책상", "familiarity": "unfamiliar"},
]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def pid(client):
    r = client.post("/api/study/survey", json={"answers": {}, "profile": {}})
    assert r.status_code == 200, r.text
    return r.json()["participantId"]


def _complete_session(client, pid, category):
    """카테고리 세션을 만들고 종료 플로우의 두 마커(finalChoice+postSurvey)를 채운다."""
    r = client.post("/api/sessions", json={
        "scenarioId": f"cat:{category}", "participantId": pid,
        "metadata": {"category": category},
    })
    assert r.status_code == 200, r.text
    sid = r.json()["session"]["id"]
    r = client.put(f"/api/study/sessions/{sid}/post-survey",
                   json={"answers": {"SAT_1": "5"}, "profile": {}})
    assert r.status_code == 200, r.text
    r = client.put(f"/api/study/sessions/{sid}/final-choice",
                   json={"status": "none_suitable", "noneReason": "test"})
    assert r.status_code == 200, r.text
    return sid


def test_plan_save_and_validation(client, pid):
    r = client.put(f"/api/study/participants/{pid}/task-plan", json={"tasks": PLAN})
    assert r.status_code == 200 and r.json()["count"] == 4
    # 잘못된 familiarity는 거부
    r = client.put(f"/api/study/participants/{pid}/task-plan",
                   json={"tasks": [{"category": "책상", "familiarity": "nope"}]})
    assert r.status_code == 422
    # 없는 참가자는 404
    r = client.put("/api/study/participants/no_such/task-plan", json={"tasks": PLAN})
    assert r.status_code == 404


def test_progress_counts_only_fully_finished_sessions(client, pid):
    client.put(f"/api/study/participants/{pid}/task-plan", json={"tasks": PLAN})
    p = client.get(f"/api/study/participants/{pid}/task-progress").json()
    assert p["remaining"] == 4 and p["next"]["category"] == "헤드폰"

    _complete_session(client, pid, "헤드폰")
    p = client.get(f"/api/study/participants/{pid}/task-progress").json()
    assert p["remaining"] == 3
    assert p["next"] == {"category": "노트북", "familiarity": "familiar"}
    assert [t["done"] for t in p["tasks"]] == [True, False, False, False]

    # 중간에 끊긴 세션(마커 없음)은 완료로 세지 않는다
    r = client.post("/api/sessions", json={
        "scenarioId": "cat:노트북", "participantId": pid, "metadata": {"category": "노트북"}})
    assert r.status_code == 200
    p = client.get(f"/api/study/participants/{pid}/task-progress").json()
    assert p["remaining"] == 3 and p["next"]["category"] == "노트북"

    # 같은 카테고리를 다시 완주해도(재시도) 그 과제 하나만 done — 이중 전진 없음
    _complete_session(client, pid, "헤드폰")
    p = client.get(f"/api/study/participants/{pid}/task-progress").json()
    assert p["remaining"] == 3

    for cat in ("노트북", "데스크체어", "책상"):
        _complete_session(client, pid, cat)
    p = client.get(f"/api/study/participants/{pid}/task-progress").json()
    assert p["remaining"] == 0 and p["next"] is None


def test_progress_without_plan_is_empty(client):
    r = client.post("/api/study/survey", json={"answers": {}, "profile": {}})
    pid2 = r.json()["participantId"]
    p = client.get(f"/api/study/participants/{pid2}/task-progress").json()
    assert p == {"tasks": [], "remaining": 0, "next": None, "knowledgeDone": []}


def test_knowledge_survey_merges_per_category(client, pid):
    """과제 직전 카테고리 단위 제출(2026-08-17) — 병합 저장, knowledgeDone 노출."""
    r = client.put(f"/api/study/participants/{pid}/knowledge-survey",
                   json={"answers": {"k:헤드폰:SPK_1": "5"}, "scores": {"헤드폰": 4.2},
                         "categories": ["헤드폰"]})
    assert r.status_code == 200
    r = client.put(f"/api/study/participants/{pid}/knowledge-survey",
                   json={"answers": {"k:노트북:SPK_1": "3"}, "scores": {"노트북": 2.8},
                         "categories": ["노트북"]})
    assert r.json()["scores"] == {"헤드폰": 4.2, "노트북": 2.8}, "이전 카테고리 점수가 보존돼야 한다"
    p = client.get(f"/api/study/participants/{pid}/task-progress").json()
    assert p["knowledgeDone"] == ["헤드폰", "노트북"]

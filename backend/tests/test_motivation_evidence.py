"""동기 감지 제거 가드 (2026-08-25).

원래 이 파일은 동기 근거 인용(meta.motivationEvidence)이 참가자 preferenceState로
노출되는지를 검증했다. 이론 프레이밍을 TCV 단일 축으로 좁히면서 턴 루프의
motivation_detection 호출을 제거했으므로(commit_engine Stage 1), 이제는 반대로
새 세션에서 동기 점수·근거가 더 이상 쌓이지 **않는 것**을 보증한다.
(agents/motivation.py 모듈과 mock 핸들러, 과거 세션의 저장 데이터는 그대로 둔다.)
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


def test_motivation_no_longer_accumulates(client):
    r = client.post("/api/sessions", json={"mode": "manual", "scenarioId": "gift_for_other",
                                           "studyCondition": "ours"})
    sid = r.json()["sessionId"]
    # 예전 mock 규칙에서 Utilitarian cue였던 발화 — 이제 아무 동기도 쌓이면 안 된다
    out = client.post(f"/api/sessions/{sid}/turns",
                      json={"role": "user", "content": "운동하는 친구에게 줄 스마트워치가 급해서 빨리 필요해요"}).json()

    state = out["preferenceState"] or {}
    assert not (state.get("motivationScores") or {})
    assert not (state.get("motivationEvidence") or {})

    # 세션 재로드에도 동일
    d = client.get(f"/api/sessions/{sid}").json()
    state2 = d["preferenceState"] or {}
    assert not (state2.get("motivationScores") or {})
    assert not (state2.get("motivationEvidence") or {})

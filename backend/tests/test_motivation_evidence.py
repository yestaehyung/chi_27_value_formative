"""동기 근거 노출 (2026-07-03) — 동기 radar가 발화와 연결되도록.

배경: 감지 LLM은 quote(발화 인용)를 내고 apply_motivation_signals가
meta.motivationEvidence = {dim: {best, counts, quotes}}로 저장하지만, 직렬화가
motivationScores(숫자)만 내보내 UI는 제네릭 문구("대화에서 이 동기가 보였어요")뿐이었다.
참가자 preferenceState에 {dim: quotes}를 실어 근거 인용을 보이게 한다 (DG3 정합).
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


def test_motivation_evidence_quotes_exposed_to_participant(client):
    r = client.post("/api/sessions", json={"mode": "manual", "scenarioId": "gift_for_other",
                                           "studyCondition": "correctable"})
    sid = r.json()["sessionId"]
    # "빨리/필요해" = mock motivation_detection의 Utilitarian cue → quote가 잡힌다
    out = client.post(f"/api/sessions/{sid}/turns",
                      json={"role": "user", "content": "운동하는 친구에게 줄 스마트워치가 급해서 빨리 필요해요"}).json()

    ev = (out["preferenceState"] or {}).get("motivationEvidence") or {}
    assert "Utilitarian" in ev and ev["Utilitarian"], f"turn response missing motivation quotes: {ev}"
    assert all(isinstance(q, str) and q for q in ev["Utilitarian"])

    # 세션 재로드(새로고침)에도 같은 근거가 실린다
    d = client.get(f"/api/sessions/{sid}").json()
    ev2 = (d["preferenceState"] or {}).get("motivationEvidence") or {}
    assert "Utilitarian" in ev2 and ev2["Utilitarian"]

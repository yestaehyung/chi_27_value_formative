"""④′ 직전 노출 요약 → planner 컨텍스트 (2026-07-06).

버튼 없이 말로만 하는 직전 세트 참조("더 저렴한 걸로", "첫 번째 거 비슷한 걸로")는
기준점이 파이프라인에 없어 번역 불능이었다 (F6 — 스윕 i2: "더 저렴한 걸로" 후
"각각 가격은 비슷하지만"이라는 자기모순 응답). renderer에 previouslyShownProducts를
공급한 수술과 동일 패턴으로, planner 컨텍스트에 lastShownProducts(제목·가격·카테고리·
핵심속성 2개로 바운딩)를 공급한다 — 참조 해소용 읽기 정보이며 선별 권한은 아니다.
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


def _new_session(client):
    r = client.post("/api/sessions", json={"mode": "manual", "scenarioId": "gift_for_other",
                                           "studyCondition": "ours"})
    assert r.status_code == 200, r.text
    return r.json()["sessionId"]


def _say(client, sid, text):
    r = client.post(f"/api/sessions/{sid}/turns", json={"role": "user", "content": text})
    assert r.status_code == 200, r.text
    return r.json()


def test_planner_receives_bounded_last_shown_summary(client, monkeypatch):
    import app.agents.service_agent as sa

    captured: list = []
    orig = sa.planner.fetch_plan

    async def spy(provider, context, fallback_search_text):
        captured.append(context.get("lastShownProducts"))
        return await orig(provider, context, fallback_search_text)

    monkeypatch.setattr(sa.planner, "fetch_plan", spy)

    sid = _new_session(client)
    out1 = _say(client, sid, "운동 좋아하는 친구에게 줄 스마트워치를 추천해주세요")
    assert out1["agentResponse"]["agentAction"] == "recommend", out1["agentResponse"]
    first_titles = {p["product"]["title"] for p in out1["recommendedProducts"]}

    _say(client, sid, "더 저렴한 걸로 보여주세요")

    # 첫 턴: 직전 노출 없음 → 빈 목록
    assert captured[0] == []
    # 둘째 턴: 직전 = 첫 노출 셋 — 바운딩된 요약(title/price/category, 무거운 필드 없음)
    last = captured[1]
    assert last and {e["title"] for e in last} == first_titles
    for e in last:
        assert "price" in e and "category" in e
        assert "description" not in e and "imageUrl" not in e  # 요약 바운딩 (컨텍스트 비대 방지)

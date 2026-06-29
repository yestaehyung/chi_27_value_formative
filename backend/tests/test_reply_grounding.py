"""A: 추천 답변(reply)은 실제로 노출되는 카드 셋에 근거해야 한다.

버그: recommend 분기에서 generate_reply가 pool[:3](rerank 전 임베딩 순)에 근거하지만
실제 노출 카드는 select_tradeoff_set(reranked)다 → 에이전트가 보여주지 않는 상품을
말로 설명할 수 있다. 이 테스트는 generate_reply가 받은 products == 최종 impression 상품
임을 검증한다 (수정 전 fail, 수정 후 pass).
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
                                           "studyCondition": "correctable"})
    assert r.status_code == 200, r.text
    return r.json()["sessionId"]


def _say(client, sid, text):
    r = client.post(f"/api/sessions/{sid}/turns", json={"role": "user", "content": text})
    assert r.status_code == 200, r.text
    return r.json()


def test_reply_is_grounded_on_the_shown_product_set(client, monkeypatch):
    import app.agents.service_agent as sa

    captured: dict = {}
    orig = sa.rg.generate_reply

    async def spy(provider, **kw):
        if kw.get("action") == "recommend":
            captured["product_ids"] = [p.id for p in (kw.get("products") or [])]
        return await orig(provider, **kw)

    monkeypatch.setattr(sa.rg, "generate_reply", spy)

    sid = _new_session(client)
    out = _say(client, sid, "운동 좋아하는 친구에게 줄 스마트워치를 찾고 있어요")
    if out["agentResponse"]["agentAction"] != "recommend":
        out = _say(client, sid, "바로 추천해주세요")

    assert out["agentResponse"]["agentAction"] == "recommend", out["agentResponse"]
    shown_ids = [p["product"]["id"] for p in out["recommendedProducts"]]
    assert len(shown_ids) == 3

    # 답변은 정확히 노출되는 3개 카드에 근거해야 한다 (pool[:3]가 아니라).
    assert captured.get("product_ids") == shown_ids, (
        f"reply grounded on {captured.get('product_ids')} but cards show {shown_ids}"
    )

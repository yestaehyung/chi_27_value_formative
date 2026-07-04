"""A: 추천 답변(reply)은 실제로 노출되는 카드 셋에 근거해야 한다.

버그(당시): recommend 분기에서 generate_reply가 pool[:3](rerank 전 임베딩 순)에 근거하지만
실제 노출 카드는 rerank 이후 셋 → 에이전트가 보여주지 않는 상품을 말로 설명할 수 있다.
이 테스트는 generate_reply가 받은 products == 최종 impression 상품임을 검증한다.
(2026-07-02: 노출 셋 = reranked[:3] — select_tradeoff_set 제거됨.)
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


def test_second_recommend_passes_previously_shown_set(client, monkeypatch):
    """B: 재추천 턴의 reply는 '직전에 무엇을 보여줬는지'(previously_shown)를 근거로 받아야 한다.

    버그(2026-07-03, live flash): 사용자가 "저는 여성이에요"로 교정하자 renderer가
    직전 노출 셋 데이터 없이 "앞서 보여드린 상품들은 전부 여성용"(실제 2/3 남성용)이라는
    허위 진술을 생성. 과거 노출 셋이 컨텍스트에 없으면 그 발화 공간은 전부 추측이 된다.
    """
    import app.agents.service_agent as sa

    captured: list = []
    orig = sa.rg.generate_reply

    async def spy(provider, **kw):
        if kw.get("action") == "recommend":
            captured.append([p.id for p in (kw.get("previously_shown") or [])])
        return await orig(provider, **kw)

    monkeypatch.setattr(sa.rg, "generate_reply", spy)

    sid = _new_session(client)
    out1 = _say(client, sid, "운동 좋아하는 친구에게 줄 스마트워치를 추천해주세요")
    assert out1["agentResponse"]["agentAction"] == "recommend", out1["agentResponse"]
    first_shown = [p["product"]["id"] for p in out1["recommendedProducts"]]

    out2 = _say(client, sid, "너무 비싸지 않은 걸로 다시 추천해주세요")
    assert out2["agentResponse"]["agentAction"] == "recommend", out2["agentResponse"]

    # 첫 추천 턴: 직전 노출 없음 → 빈 목록 / 재추천 턴: 직전 = 첫 노출 셋 그대로.
    assert captured[0] == []
    assert captured[1] == first_shown, (
        f"reply got previously_shown={captured[1]} but first turn showed {first_shown}"
    )


def test_generate_reply_context_carries_previously_shown_products():
    """previouslyShownProducts가 LLM 유저 컨텍스트에 실려야 과거 노출 언급이 근거를 갖는다."""
    import asyncio

    from app.agents import response_generator as rg
    from app.db import models

    class CaptureProvider:
        name = "capture"  # "mock"이면 short-circuit되므로 다른 이름

        async def generate_text(self, messages, max_tokens=700):
            self.user_msg = messages[-1].content
            return "ok"

    prev = [models.Product(id="p_prev1", title="ELETOP 남성 울 트렌치 코트", price=108000)]
    new = [models.Product(id="p_new1", title="추야투 여성 롱 패딩 코트", price=97200)]
    cap = CaptureProvider()
    asyncio.run(rg.generate_reply(
        cap, action="recommend", template_text="초안",
        recent_turns=[], products=new, state_summary=None,
        previously_shown=prev,
    ))
    assert "previouslyShownProducts" in cap.user_msg
    assert "ELETOP 남성 울 트렌치 코트" in cap.user_msg


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
    assert len(shown_ids) == 5  # 노출 셋 5개 (2026-07-04: 3→5 확대)

    # 답변은 정확히 노출되는 3개 카드에 근거해야 한다 (pool[:3]가 아니라).
    assert captured.get("product_ids") == shown_ids, (
        f"reply grounded on {captured.get('product_ids')} but cards show {shown_ids}"
    )

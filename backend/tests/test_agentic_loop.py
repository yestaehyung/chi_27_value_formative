"""축 2 agentic 턴 루프 배관 검증 (2026-07-07) — 실 API 없이 스텁 provider로.

보장할 계약:
- 기본(pipeline)·mock 환경에서 agentic 경로는 절대 타지 않는다 (기존 83개 테스트가 그 증거).
- run_turn: 도구 호출 → recommender 실행 → 노출 셋·카드·diag가 결과에 실림, 응답 텍스트는
  도구 결과를 본 같은 컨텍스트의 출력.
- 도구를 안 부르면 scored 빈 채 텍스트만 (clarify성 답변).
- mock provider는 generate_with_tools 미구현 (NotImplementedError) — 폴백 가드의 근거.
"""
import asyncio
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


class _ToolStubProvider:
    """generate_with_tools에서 도구를 정확히 한 번 부르고 고정 텍스트를 반환.
    도구 내부 rerank(generate_json)는 빈 랭킹 → append-back 순서 폴백."""
    name = "stub"

    def __init__(self, tool_args=None):
        self.tool_args = tool_args  # None이면 도구를 부르지 않음

    async def generate_with_tools(self, messages, tools, execute_tool, **kwargs):
        trace = []
        if self.tool_args is not None:
            result = await execute_tool("search_and_rank", self.tool_args)
            trace.append({"name": "search_and_rank", "args": self.tool_args, "result": result})
            return "**도구 결과**를 반영한 추천 답변입니다", trace
        return "어떤 상품을 찾고 계세요?", trace

    async def generate_json(self, messages, task=None, context=None, **kwargs):
        return {"ranking": []}


def _make_session(client):
    r = client.post("/api/sessions", json={"mode": "manual", "scenarioId": "gift_for_other",
                                           "studyCondition": "correctable"})
    assert r.status_code == 200, r.text
    return r.json()["sessionId"]


class _FakeCommit:
    snapshot = None


def test_run_turn_with_tool_call_produces_shown_set(client):
    from app.agents import agentic_loop
    from app.db import models
    from app.db.database import SessionLocal

    sid = _make_session(client)
    db = SessionLocal()
    try:
        session = db.get(models.Session, sid)
        result = asyncio.run(agentic_loop.run_turn(
            db, _ToolStubProvider({"searchText": "스마트워치", "constraintsNote": "선물용"}),
            session, _FakeCommit(), "운동 좋아하는 친구 선물로 스마트워치 찾아요",
            recent_turns=[],
        ))
        # 마크다운은 챗 버블에서 스트립 (파이프라인 렌더러와 동일 계약)
        assert result.text == "도구 결과를 반영한 추천 답변입니다"
        assert result.scored, "도구 호출이 노출 셋을 만들어야 함"
        assert result.rec_diag and result.rec_diag["searchText"] == "스마트워치"
        assert result.tool_args == {"searchText": "스마트워치", "constraintsNote": "선물용"}
        assert len(result.trace) == 1
        # 카드 텍스트가 노출 상품 전부에 존재 (rerank 폴백 카드 포함)
        for sp in result.scored:
            assert result.card_texts.get(sp.product.id, {}).get("reason")
    finally:
        db.close()


def test_run_turn_without_tool_call_is_clarify_like(client):
    from app.agents import agentic_loop
    from app.db import models
    from app.db.database import SessionLocal

    sid = _make_session(client)
    db = SessionLocal()
    try:
        session = db.get(models.Session, sid)
        result = asyncio.run(agentic_loop.run_turn(
            db, _ToolStubProvider(None), session, _FakeCommit(),
            "뭐 살지 고민이에요", recent_turns=[],
        ))
        assert result.text
        assert result.scored == [] and result.rec_diag is None
    finally:
        db.close()


class _MultiToolStub:
    """Rufus형 도구셋 검증용 — 프로필 조회 + 상세 조회를 부르고 텍스트 반환."""
    name = "stub"

    def __init__(self, detail_title):
        self.detail_title = detail_title

    async def generate_with_tools(self, messages, tools, execute_tool, **kwargs):
        assert {t["function"]["name"] for t in tools} == {
            "search_and_rank", "get_product_details", "get_user_profile"}
        profile = await execute_tool("get_user_profile", {})
        detail = await execute_tool("get_product_details", {"title": self.detail_title})
        trace = [{"name": "get_user_profile", "args": {}, "result": profile},
                 {"name": "get_product_details", "args": {"title": self.detail_title},
                  "result": detail}]
        return "상세 정보를 반영한 답변", trace

    async def generate_json(self, messages, task=None, context=None, **kwargs):
        return {"ranking": []}


def test_rufus_toolset_profile_and_details(client):
    """v3 도구셋: get_user_profile은 층의 출력만(확인 기준·요약), get_product_details는
    카탈로그 사실을 반환. 도구만 부르고 검색을 안 하면 노출 셋은 비어 있다(answer성)."""
    from app.agents import agentic_loop
    from app.db import models
    from app.db.database import SessionLocal

    sid = _make_session(client)
    db = SessionLocal()
    try:
        session = db.get(models.Session, sid)
        any_product = db.query(models.Product).first()
        result = asyncio.run(agentic_loop.run_turn(
            db, _MultiToolStub(any_product.title[:6]), session, _FakeCommit(),
            "이 상품 자세히 알려줘", recent_turns=[],
        ))
        assert result.scored == []  # 검색 안 함 → 노출 없음
        prof_result = result.trace[0]["result"]
        assert "confirmedCriteria" in prof_result and "understandingSummary" in prof_result
        # 층 출력만 — 미확인 원점수 축은 프로필 도구에 없다
        assert "values" not in prof_result and "motivations" not in prof_result
        detail = result.trace[1]["result"]
        assert detail["found"] is True and detail["title"] == any_product.title
        assert "price" in detail and "caveats" in detail
    finally:
        db.close()


def test_product_details_not_found(client):
    from app.agents import agentic_loop
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        out = agentic_loop._product_details(db, type("S", (), {"id": "none"})(), "존재하지않는상품명XYZ")
        assert out["found"] is False
    finally:
        db.close()


def test_mock_provider_has_no_tool_loop():
    from app.llm.provider import MockLLMProvider

    with pytest.raises(NotImplementedError):
        asyncio.run(MockLLMProvider().generate_with_tools([], [], None))


def test_agentic_flag_with_mock_stays_on_pipeline(client, monkeypatch):
    """VC_TURN_LOOP=agentic이어도 mock provider면 파이프라인 그대로 —
    데모·테스트 환경은 플래그와 무관하게 불변이어야 한다."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "turn_loop", "agentic")
    sid = _make_session(client)
    out = client.post(f"/api/sessions/{sid}/turns",
                      json={"role": "user",
                            "content": "운동 좋아하는 친구에게 줄 스마트워치를 추천해주세요"}).json()
    assert out["agentResponse"]["agentAction"] in ("recommend", "clarify")
    assert out["agentResponse"]["content"]

"""Unit tests for build_user_visible_summary (spec §30, §36).

The one-sentence summary must reflect the ACTUAL chip labels (dynamic) and must
not emit hardcoded smartwatch-era domain wording ("운동 기능", "장기 사용 신뢰")
that mis-describes other product domains (earphones, dresses…).
"""
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_test_"), "test.db"))
os.environ.setdefault("VC_LLM_PROVIDER", "mock")

from app.db import models
from app.preference_commit.summary_builder import build_user_visible_summary


def _topic(label: str, priority: str = "high", status: str = "inferred",
           confidence: float = 0.6) -> models.IntentionTopic:
    return models.IntentionTopic(
        id=f"topic_{label}", session_id="s1", label=label, description=label,
        source="llm_extraction", status=status, priority=priority,
        confidence=confidence, explicitness="implicit",
        evidence_ids=[], related_product_ids=[], hints={},
    )


def test_gift_summary_reflects_actual_labels_not_hardcoded_domain():
    # 선물 + "저렴해 보이지 않기" + "신뢰" 라벨 — 현재는 하드코딩 분기로 "운동 기능"이 박힌다.
    topics = [_topic("선물용 적절한 인상"), _topic("저렴해 보이지 않기"), _topic("신뢰감 있는 브랜드")]
    sentence = build_user_visible_summary(topics, has_open_conflict=False)["oneSentenceSummary"]
    assert "운동 기능" not in sentence, sentence          # 도메인 하드코딩 금지
    assert "신뢰감 있는 브랜드" in sentence, sentence       # 실제 라벨 반영(동적)


def test_gift_summary_is_dynamic_not_frozen():
    # 같은 선물 맥락이라도 기준이 다르면 요약 문장이 달라야 한다(캔 문장 고정 금지).
    s1 = build_user_visible_summary(
        [_topic("선물용 적절한 인상"), _topic("저렴해 보이지 않기"), _topic("내구성")],
        has_open_conflict=False,
    )["oneSentenceSummary"]
    s2 = build_user_visible_summary(
        [_topic("선물용 적절한 인상"), _topic("저렴해 보이지 않기"), _topic("가벼운 무게")],
        has_open_conflict=False,
    )["oneSentenceSummary"]
    assert s1 != s2, f"summary frozen across different criteria: {s1!r}"


def test_summary_is_hedged_for_correctability():
    # §36: 단정이 아니라 확인을 청하는 hedged 표현이어야 한다.
    sentence = build_user_visible_summary(
        [_topic("내구성"), _topic("가벼운 무게")], has_open_conflict=False
    )["oneSentenceSummary"]
    assert ("확인" in sentence) or ("같아요" in sentence), sentence


# ── 1b: LLM trade-off 문장을 받아서 쓰되, 없으면 B1(라벨조합)로 폴백 ──
def test_summary_uses_llm_sentence_when_provided():
    topics = [_topic("내구성"), _topic("가벼운 무게")]
    out = build_user_visible_summary(
        topics, has_open_conflict=False,
        llm_sentence="최저가보다 내구성을 더 중요하게 보시는 것 같아요. 맞는지 확인해 주세요.",
    )
    assert out["oneSentenceSummary"] == "최저가보다 내구성을 더 중요하게 보시는 것 같아요. 맞는지 확인해 주세요."


def test_summary_falls_back_to_labels_when_llm_sentence_missing():
    topics = [_topic("내구성"), _topic("가벼운 무게")]
    for missing in (None, "", "   "):
        out = build_user_visible_summary(topics, has_open_conflict=False, llm_sentence=missing)
        assert "내구성" in out["oneSentenceSummary"], (missing, out["oneSentenceSummary"])


def test_mock_state_summary_task_returns_hedged_sentence_from_labels():
    # state_summary task: 제공된 라벨만 반영, §36 hedged. (mock = 결정론 계약/폴백)
    import asyncio
    from app.llm.provider import LLMMessage, get_provider

    provider = get_provider()
    out = asyncio.run(provider.generate_json(
        [LLMMessage(role="user", content="x")],
        task="state_summary",
        context={"labels": ["내구성", "선물 인상"], "scenario": "선물용 무선 이어폰"},
    ))
    sentence = out["summary"]
    assert "내구성" in sentence, sentence                       # 제공 라벨 반영
    assert ("확인" in sentence) or ("같아요" in sentence), sentence  # §36 hedged


def test_turn_produces_non_hardcoded_hedged_summary():
    # end-to-end: 턴 → commit → snapshot. 옛 하드코딩이 아닌 hedged 요약이 나온다.
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        sid = c.post("/api/sessions", json={
            "mode": "manual", "scenarioId": "gift_for_other", "studyCondition": "correctable",
        }).json()["sessionId"]
        out = c.post(f"/api/sessions/{sid}/turns", json={
            "role": "user",
            "content": "운동 좋아하는 친구에게 줄 스마트워치를 찾고 있어요. 브랜드는 잘 몰라요.",
        }).json()
        summary = out["preferenceState"]["userVisibleSummary"]["oneSentenceSummary"]
        assert "운동 기능, 장기 사용 신뢰" not in summary, summary    # 옛 하드코딩 제거 확인
        assert ("보시는 것 같아요" in summary) or ("이해했어요" in summary) \
            or ("확인" in summary), summary                          # §36 hedged

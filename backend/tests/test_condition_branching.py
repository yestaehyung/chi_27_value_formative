"""조건별 동작 분기 검증 (2026-08-06 설계).

  baseline1 — 의도 추론 자체를 하지 않는다 → 토픽·스냅샷이 생기지 않는다
  baseline2 — 추론하고, **사용자 확인 없이** 그 기준을 리랭크에 넣는다
  ours      — 추론하고, 확인된 기준만 리랭크에 넣는다 (evidence purity)

세 조건이 같은 발화에 다르게 반응하는지를 API 수준에서 본다. UI 노출 여부는 프론트
책임이라 여기서 다루지 않는다 — 여기서 지키는 건 **데이터가 실제로 갈리는가**이다.
"""
import os
import tempfile
from types import SimpleNamespace

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_condbr_"), "test.db"))
os.environ.setdefault("VC_EXPORT_DIR", tempfile.mkdtemp(prefix="vc_condbr_exp_"))
os.environ["VC_LLM_PROVIDER"] = "mock"

import pytest
from fastapi.testclient import TestClient

from app.agents.recommender import _stated_and_confirmed_criteria, _uses_unconfirmed
from app.core.conditions import (
    INFERS_INTENTION,
    SHOWS_CRITERIA,
    STUDY_CONDITIONS,
    USES_UNCONFIRMED_INFERENCE,
    normalize_condition,
)
from app.db import models
from app.db.database import SessionLocal
from app.main import app

UTTERANCE = "운동 좋아하는 친구에게 줄 스마트워치를 찾고 있어요. 브랜드는 잘 몰라요."


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def run_session(client, condition: str) -> dict:
    sid = client.post("/api/sessions", json={
        "mode": "manual", "scenarioId": "gift_for_other", "studyCondition": condition,
    }).json()["sessionId"]
    out = client.post(f"/api/sessions/{sid}/turns",
                      json={"role": "user", "content": UTTERANCE}).json()
    return {"sessionId": sid, "out": out}


def topic_count(session_id: str) -> int:
    db = SessionLocal()
    try:
        return (db.query(models.IntentionTopic)
                .filter(models.IntentionTopic.session_id == session_id).count())
    finally:
        db.close()


# ── 조건 정의 자체 ─────────────────────────────────────────────────────────────

def test_three_conditions_are_distinct_on_every_axis():
    """세 조건이 적어도 한 축에서 서로 구분돼야 실험이 성립한다."""
    profiles = {
        c: (INFERS_INTENTION[c], SHOWS_CRITERIA[c], USES_UNCONFIRMED_INFERENCE[c])
        for c in STUDY_CONDITIONS
    }
    assert len(set(profiles.values())) == 3, f"조건 프로필이 겹친다: {profiles}"


def test_legacy_slugs_map_forward():
    """옛 슬러그가 현재 슬러그로 옮겨진다 — 기존 DB 행이 재배정되지 않도록."""
    assert normalize_condition("baseline") == "baseline2"
    assert normalize_condition("correctable") == "ours"
    # 폐기된 조건은 매핑하지 않는다 → ensure_condition이 새로 배정한다
    assert normalize_condition("explanation_only") is None


# ── baseline1: 추론 없음 ───────────────────────────────────────────────────────

def test_baseline1_produces_no_intention_topics(client):
    """baseline1은 파이프라인을 건너뛰므로 의도 토픽이 하나도 생기지 않는다."""
    r = run_session(client, "baseline1")
    assert topic_count(r["sessionId"]) == 0
    assert r["out"].get("preferenceState") is None


def test_baseline1_still_answers_and_recommends(client):
    """추론을 껐다고 대화가 죽으면 안 된다 — 순수 LLM 추천은 정상 동작해야 한다."""
    r = run_session(client, "baseline1")
    assert r["out"]["agentResponse"]["content"].strip()


def test_baseline1_never_reads_cross_session_rig_or_latent_planner_state(client, monkeypatch):
    """의도 추론 없음은 현재 세션 토픽뿐 아니라 cross-session RIG 가설까지 포함한다."""
    import app.rig as rig
    from app.agents import service_agent

    called = False
    captured = {}
    original_fetch = service_agent.planner.fetch_plan

    def forbidden_rig(*_args, **_kwargs):
        nonlocal called
        called = True
        return {"label": "latent cross-session guess"}

    async def capture_plan(provider, context, fallback_search_text):
        captured.update(context)
        return await original_fetch(provider, context, fallback_search_text)

    monkeypatch.setattr(rig, "top_predicted_concept", forbidden_rig)
    monkeypatch.setattr(service_agent.planner, "fetch_plan", capture_plan)

    run_session(client, "baseline1")

    assert called is False
    assert "values" not in captured and "motivations" not in captured
    assert "ragPrediction" not in captured
    assert captured["hypothesesForClarification"] == {
        "values": {}, "motivations": {}, "ragPrediction": None,
    }


def test_baseline1_planner_sanitizes_even_a_stale_snapshot():
    """오래된 DB에 snapshot이 남아 있어도 condition gate가 planner 입력을 비운다."""
    from app.agents.planner import build_planner_context

    stale = SimpleNamespace(
        anchor_scores={"Social": 0.9}, motivation_scores={"Role": 0.8},
    )
    session = models.Session(id="stale_b1", meta={"studyCondition": "baseline1"})
    context = build_planner_context(
        [], stale, False, None, {"label": "cross-session guess"}, "goal",
        session=session,
    )
    assert context["hypothesesForClarification"] == {
        "values": {}, "motivations": {}, "ragPrediction": None,
    }


def test_inferring_conditions_do_produce_topics(client):
    """baseline2·ours는 같은 발화에서 토픽을 만든다 — baseline1과의 대비가 실재함을 보인다."""
    for cond in ("baseline2", "ours"):
        r = run_session(client, cond)
        assert topic_count(r["sessionId"]) > 0, f"{cond}에서 토픽이 생성되지 않았다"


# ── baseline2: 미확인 추론도 추천에 투입 ────────────────────────────────────────

def _fake_session(condition: str) -> models.Session:
    return models.Session(id="x", meta={"studyCondition": condition})


def test_only_baseline2_uses_unconfirmed_inference():
    assert _uses_unconfirmed(_fake_session("baseline2")) is True
    assert _uses_unconfirmed(_fake_session("baseline1")) is False
    assert _uses_unconfirmed(_fake_session("ours")) is False
    # 조건이 없는 세션(데모·시뮬레이션)은 종래대로 evidence purity를 지킨다
    assert _uses_unconfirmed(_fake_session(None)) is False


def test_unconfirmed_inferred_topic_reaches_rerank_only_in_baseline2(client):
    """미확인·추론 토픽 하나를 심고, 조건별로 리랭크가 그것을 읽는지 본다.

    이게 baseline2 정의의 핵심이다 — 확인 UI가 없으므로 evidence purity를 그대로 적용하면
    추론이 추천에 영원히 닿지 못해 baseline1과 구분이 사라진다.
    """
    sid = run_session(client, "ours")["sessionId"]
    db = SessionLocal()
    try:
        db.add(models.IntentionTopic(
            id="topic_unconfirmed_x", session_id=sid,
            label="조용한 디자인", description="드러나지 않는 디자인 선호",
            source="llm_extraction", explicitness="implicit", status="inferred",
        ))
        db.commit()
        labels_pure = [c["label"] for c in _stated_and_confirmed_criteria(db, sid)]
        labels_b2 = [c["label"] for c in
                     _stated_and_confirmed_criteria(db, sid, include_unconfirmed=True)]
    finally:
        db.close()
    assert "조용한 디자인" not in labels_pure, "ours는 미확인 추론을 리랭크에 넣지 않는다"
    assert "조용한 디자인" in labels_b2, "baseline2는 미확인 추론도 넣어야 한다"

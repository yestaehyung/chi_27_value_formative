"""LLM user agent 합성 루프 테스트 (mock provider — 결정론)."""
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_test_"), "test.db"))
os.environ.setdefault("VC_EXPORT_DIR", os.path.join(tempfile.mkdtemp(prefix="vc_test_exp_")))
os.environ.setdefault("VC_LLM_PROVIDER", "mock")

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

SEED = Path(__file__).resolve().parent.parent / "seed"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # startup: init_db + seed load
        yield c


def test_llm_simulation_loop(client):
    from app.agents.llm_user_agent import run_llm_simulation
    from app.db.database import SessionLocal
    from app.llm.mock_rules import persona_profile
    from app.products.seed_loader import get_scenario

    personas = json.loads((SEED / "personas_nemotron.json").read_text(encoding="utf-8"))
    persona = personas[0]
    scenario = get_scenario("budget_value")
    assert scenario is not None
    # v2: GT는 persona×scenario 조건부 — 시나리오를 먼저 정하고 그 상황의 GT를 도출
    profile = {**persona_profile({"scenario": scenario}), "speechStyle": "짧게 말함"}

    db = SessionLocal()
    try:
        res = asyncio.run(run_llm_simulation(
            db, persona, profile, scenario, max_user_turns=5, gt_version="v2"))
    finally:
        db.close()

    assert res["ended"] in ("purchase", "stop", "max_turns")
    user_turns = [t for t in res["transcript"] if t["role"] == "user"]
    assert len(user_turns) >= 1
    # 첫 발화는 시나리오 표면 요구 (hidden intention을 직접 말하지 않음)
    assert user_turns[0]["content"] == scenario["initialUserNeed"]
    # GT 은닉: 세션 meta에 프로필 내용이 저장되지 않아야 한다 (service agent가 meta를 읽으므로)
    # gtVersion 스탬프(내용 아닌 연결고리)만 허용된다.
    r = client.get(f"/api/sessions/{res['sessionId']}").json()
    meta = r["session"]["metadata"] if "metadata" in r.get("session", {}) else r.get("session", {}).get("meta", {})
    meta_str = json.dumps(meta or {}, ensure_ascii=False)
    assert "hiddenIntention" not in meta_str and "valueLevels" not in meta_str \
        and "traitLevels" not in meta_str and "motivationLevels" not in meta_str
    assert (meta or {}).get("gtVersion") == "v2"
    # 파이프라인 산출: 12축 키가 존재
    assert set(res["anchorScores"].keys()) >= {"Functional", "Social"}
    assert isinstance(res["motivationScores"], dict)


def test_scenario_match_mock_contract():
    """풀 확장 신규 persona 캐스팅 task — mock 출력이 계약(scenarioId/speechStyle/matchReason)을 지킨다."""
    from app.llm.mock_rules import scenario_match

    out = scenario_match({"scenarios": [{"id": "budget_value"}, {"id": "gift_for_other"}]})
    assert out["scenarioId"] == "budget_value"
    assert out["speechStyle"] and out["matchReason"]


def test_persona_profile_mock_is_scenario_conditional():
    """v2 핵심: 같은 사람이라도 시나리오가 다르면 GT가 달라야 한다 (mock도 그 구조를 재현)."""
    from app.llm.mock_rules import persona_profile

    gift = persona_profile({"scenario": {"id": "gift_for_other"}})
    own = persona_profile({"scenario": {"id": "budget_value"}})
    assert gift["valueLevels"] != own["valueLevels"]
    assert gift["motivationLevels"]["Role"] == "high"  # 선물 상황에서만 Role이 뜬다
    assert own["motivationLevels"]["Role"] == "low"
    for out in (gift, own):
        assert set(out["valueLevels"]) == {"Functional", "Social", "Emotional", "Epistemic", "Conditional"}
        assert len(out["motivationLevels"]) == 7
        assert out["hiddenIntentions"] and out["personaDistinction"]


def test_multi_session_with_participant(client):
    """멀티 세션: Participant 연결 → 세션 횡단 누적(spec) 동작 확인."""
    from app.agents.llm_user_agent import run_llm_simulation
    from app.db import models
    from app.db.database import SessionLocal
    from app.llm.mock_rules import persona_profile
    from app.products.seed_loader import get_scenario

    personas = json.loads((SEED / "personas_nemotron.json").read_text(encoding="utf-8"))
    persona = personas[1]
    sc1, sc2 = get_scenario("gift_for_other"), get_scenario("budget_value")
    # v2: 세션마다 그 상황의 GT를 주입 (같은 사람, 다른 상황 → 다른 GT)
    prof1 = {**persona_profile({"scenario": sc1}), "speechStyle": "짧게"}
    prof2 = {**persona_profile({"scenario": sc2}), "speechStyle": "짧게"}

    db = SessionLocal()
    try:
        part_id = f"part_{persona['id']}"
        if db.get(models.Participant, part_id) is None:
            db.add(models.Participant(id=part_id, label="[합성] 테스트"))
            db.commit()
        r1 = asyncio.run(run_llm_simulation(
            db, persona, prof1, sc1, 4, participant_id=part_id, gt_version="v2"))
        r2 = asyncio.run(run_llm_simulation(
            db, persona, prof2, sc2, 4, participant_id=part_id, gt_version="v2"))
        # 두 세션이 같은 participant에 연결됨
        s1 = db.get(models.Session, r1["sessionId"])
        s2 = db.get(models.Session, r2["sessionId"])
        assert s1.participant_id == s2.participant_id == part_id
        # 세션 횡단 누적: participant spec이 생성/갱신됨 (KG의 자연어 미러)
        part = db.get(models.Participant, part_id)
        assert part.spec_markdown
        assert part.spec_version >= 1
    finally:
        db.close()

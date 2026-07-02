"""Demo Acceptance Tests (spec §35, Test 1-6) — run against MockLLMProvider."""
import os
import tempfile

os.environ["VC_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="vc_test_"), "test.db")
os.environ["VC_EXPORT_DIR"] = os.path.join(tempfile.mkdtemp(prefix="vc_test_exp_"))
os.environ["VC_LLM_PROVIDER"] = "mock"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def new_session(client, scenario="gift_for_other"):
    r = client.post("/api/sessions", json={"mode": "manual", "scenarioId": scenario,
                                           "studyCondition": "correctable"})
    assert r.status_code == 200, r.text
    return r.json()["sessionId"]


def say(client, session_id, text):
    r = client.post(f"/api/sessions/{session_id}/turns", json={"role": "user", "content": text})
    assert r.status_code == 200, r.text
    return r.json()


def feedback(client, session_id, product_id, fb_type, reason_code=None, reason_text=None):
    r = client.post(f"/api/sessions/{session_id}/feedback", json={
        "productId": product_id, "type": fb_type,
        "reasonCode": reason_code, "reasonText": reason_text,
    })
    assert r.status_code == 200, r.text
    return r.json()


def replay(client, session_id):
    r = client.get(f"/api/research/sessions/{session_id}/replay")
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Test 1. Basic recommendation
# ---------------------------------------------------------------------------
def test_1_basic_recommendation(client):
    sid = new_session(client)
    out = say(client, sid, "운동 좋아하는 친구에게 줄 스마트워치를 찾고 있어요")

    action = out["agentResponse"]["agentAction"]
    assert action in ("clarify", "recommend")
    if action == "recommend":
        products = out["recommendedProducts"]
        assert len(products) == 3
        # trade-offs: not all from the same price band
        cues = {p["product"]["cueSummary"]["priceCue"] for p in products}
        assert len(cues) >= 2, f"expected trade-off price cues, got {cues}"
        # impressions logged
        session = client.get(f"/api/sessions/{sid}").json()
        assert len(session["impressions"]) == 3


# ---------------------------------------------------------------------------
# Test 2. Hidden intention extraction
# ---------------------------------------------------------------------------
def test_2_hidden_intention_extraction(client):
    sid = new_session(client)
    say(client, sid, "운동 좋아하는 친구에게 줄 스마트워치를 찾고 있어요. 브랜드는 잘 몰라요.")
    out = feedback(client, sid, "watch_low_001", "dislike",
                   reason_code="too_cheap_looking",
                   reason_text="선물인데 너무 저렴해 보이면 좀 그래요")

    assert out["feedbackEvent"]["id"]

    data = replay(client, sid)
    topics = {t["label"]: t for t in data["topics"]}
    assert "선물로 너무 저렴해 보이지 않기" in topics

    topic = topics["선물로 너무 저렴해 보이지 않기"]
    concept_labels = {c["label"] for c in topic["concepts"]}
    assert concept_labels & {"선물의 체면", "사회적 적절성"}

    anchors = {a["anchor"] for a in topic["anchorMappings"]}
    assert {"Social", "Conditional"} <= anchors

    # CurrentUnderstandingPanel chip
    chips = out["updatedPreferenceState"]["userVisibleSummary"]["chips"]
    assert any(c["label"] == "선물로 너무 저렴해 보이지 않기" for c in chips)


# ---------------------------------------------------------------------------
# Test 3. Conflict detection
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def conflict_session(client):
    sid = new_session(client)
    say(client, sid, "운동 좋아하는 친구에게 줄 스마트워치를 찾고 있어요. 브랜드는 잘 몰라요.")
    say(client, sid, "가능하면 저렴한 게 좋아요.")
    # 플래너 searchText(사용자 발화 전체 join, 2026-07-02) 기준 mock 노출 셋의 싼 워치 =
    # watch_low_001. (조인 쿼리 도입 전 한때 cheap_006이 노출되어 재고정했던 이력 있음 —
    # 픽스처는 항상 "실제 노출되는 상품"에 고정한다: 피드백은 노출 없이는 pair가 안 됨.)
    out = feedback(client, sid, "watch_low_001", "dislike",
                   reason_code="too_cheap_looking",
                   reason_text="선물인데 너무 저렴해 보이면 좀 그래요.")
    return sid, out


def test_3_conflict_detection(client, conflict_session):
    _sid, out = conflict_session
    conflicts = out["newConflicts"]
    assert len(conflicts) >= 1
    conflict = conflicts[0]
    assert conflict["severity"] in ("direct", "ambiguous")
    assert conflict["oldAssumption"] == "가격이 낮을수록 좋음"
    assert "저렴해 보이" in conflict["newSignal"]
    assert conflict["explanationForUser"]
    assert len(conflict["suggestedResolutions"]) >= 3


# ---------------------------------------------------------------------------
# Test 4. Conflict resolution (merge: keep budget cap, exclude too-cheap-looking)
# ---------------------------------------------------------------------------
def test_4_conflict_resolution(client, conflict_session):
    sid, out = conflict_session
    conflict = out["newConflicts"][0]
    r = client.post(f"/api/conflicts/{conflict['id']}/resolve",
                    json={"optionId": "merge_price_cap_and_gift_appropriateness"})
    assert r.status_code == 200, r.text
    res = r.json()

    assert res["resolvedConflict"]["status"] not in ("open", "shown_to_user")
    assert res["resolvedConflict"]["resolvedAt"]

    state = res["newPreferenceState"]
    assert any("초저가로 보이는 상품 제외" in a for a in state["avoidances"])

    # old price preference is NOT deleted
    data = replay(client, sid)
    old = next(t for t in data["topics"] if t["label"] == "가격이 낮을수록 좋음")
    assert old["status"] not in ("rejected_by_user", "inactive")


# ---------------------------------------------------------------------------
# Test 5. Chosen-rejected pair
# ---------------------------------------------------------------------------
def test_5_chosen_rejected_pair(client, conflict_session):
    sid, _ = conflict_session
    out = feedback(client, sid, "watch_trust_002", "like",
                   reason_text="한달 사용 리뷰 비율이 높은 게 마음에 들어요.")
    pairs = out["chosenRejectedPairsCreated"]
    assert len(pairs) >= 1
    pair = next(p for p in pairs if p["chosenId"] == "watch_trust_002"
                and p["rejectedId"] == "watch_low_001")
    assert pair["labelSource"] == "like_vs_dislike"
    diff = pair["productDiff"]
    assert diff["chosenMoreExpensive"] is True
    assert diff["longTermReviewRatioDiff"] > 0.15
    assert diff["naturalLanguageSummary"]
    assert pair["inferredHiddenReason"]


# ---------------------------------------------------------------------------
# Test 6. WIMHF-style feature discovery
# ---------------------------------------------------------------------------
def test_6_wimhf_feature_discovery(client):
    # generate pairs from two simulated gift sessions (different personas)
    for persona in ("ua_gift_smartwatch_social_risk_averse", "ua_distinctive_gift_giver"):
        r = client.post("/api/simulations/run", json={
            "scenarioId": "gift_for_other", "userAgentProfileId": persona,
            "maxTurns": 8, "autoResolveConflicts": True,
        })
        assert r.status_code == 200, r.text

    pair_count = len(client.get("/api/research/pairs").json()["pairs"])
    assert pair_count >= 5, f"need >=5 pairs for mining, got {pair_count}"

    r = client.post("/api/research/pair-mining/run", json={"minPairs": 5})
    assert r.status_code == 200, r.text
    features = r.json()["features"]
    assert len(features) >= 1

    labels = {f["label"] for f in features}
    expected = {"장기 사용 신뢰", "흔하지 않은 선물의 특별함", "셀러 신뢰 기반 실패 회피",
                "선물 가격 하한(체면 가격대)"}
    assert labels & expected, f"got {labels}"
    for f in features:
        assert f["coverageScore"] is not None
        assert f["predictivenessScore"] is not None
        assert f["sourcePairIds"]
        assert f["suggestedOntologyAction"] in (
            "new_concept", "new_relation", "refine_existing_concept", "new_anchor_dimension", "reject"
        )


# ---------------------------------------------------------------------------
# Extras: simulation evaluation + exports + chip correction round-trip
# ---------------------------------------------------------------------------
def test_simulation_returns_evaluation(client):
    r = client.post("/api/simulations/run", json={
        "scenarioId": "gift_for_other",
        "userAgentProfileId": "ua_gift_smartwatch_social_risk_averse",
        "maxTurns": 8, "autoResolveConflicts": True,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["evaluation"]["topicRecall"] is not None
    assert body["evaluation"]["topicRecall"] >= 0.5
    assert len(body["preferenceSnapshots"]) >= 3
    assert len(body["turns"]) >= 4


def test_chip_correction(client):
    sid = new_session(client)
    out = say(client, sid, "운동 좋아하는 친구에게 줄 스마트워치를 찾고 있어요. 브랜드는 잘 몰라요.")
    chips = out["preferenceState"]["userVisibleSummary"]["chips"]
    target = chips[0]
    r = client.post(f"/api/preferences/chips/{target['id']}/action", json={"action": "reject"})
    assert r.status_code == 200
    new_chips = r.json()["newPreferenceState"]["userVisibleSummary"]["chips"]
    assert all(c["id"] != target["id"] for c in new_chips)

    # evidence drawer
    other = next(c for c in chips if c["id"] != target["id"])
    r = client.get(f"/api/preferences/topics/{other['id']}/evidence")
    assert r.status_code == 200
    assert len(r.json()["evidence"]) >= 1


def test_exports(client):
    r = client.post("/api/exports/run")
    assert r.status_code == 200
    files = r.json()["files"]
    expected = {"sessions.jsonl", "turns.jsonl", "product_impressions.jsonl",
                "feedback_events.jsonl", "ontology_topics.jsonl", "ontology_relations.jsonl",
                "preference_state_snapshots.jsonl", "conflicts.jsonl", "conflict_resolutions.jsonl",
                "chosen_rejected_pairs.jsonl", "discovered_features.jsonl"}
    assert expected <= set(files.keys())
    assert files["sessions.jsonl"] >= 1
    assert files["chosen_rejected_pairs.jsonl"] >= 5

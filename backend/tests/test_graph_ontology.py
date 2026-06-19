"""Graph ontology tests (docs/ontology-graph-design.md, decisions D1–D4 / A1–A4).

Runs against MockLLMProvider like test_acceptance.py.
"""
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_test_"), "test.db"))
os.environ.setdefault("VC_EXPORT_DIR", os.path.join(tempfile.mkdtemp(prefix="vc_test_exp_")))
os.environ.setdefault("VC_LLM_PROVIDER", "mock")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def new_session(client):
    r = client.post("/api/sessions", json={"mode": "manual", "scenarioId": "gift_for_other",
                                           "studyCondition": "correctable"})
    assert r.status_code == 200, r.text
    return r.json()["sessionId"]


def say(client, sid, text):
    r = client.post(f"/api/sessions/{sid}/turns", json={"role": "user", "content": text})
    assert r.status_code == 200, r.text
    return r.json()


def feedback(client, sid, product_id, fb_type, reason_code=None, reason_text=None):
    r = client.post(f"/api/sessions/{sid}/feedback", json={
        "productId": product_id, "type": fb_type,
        "reasonCode": reason_code, "reasonText": reason_text,
    })
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def demo_session(client):
    """Gift-smartwatch demo: utterance topics (explicit) + feedback avoidance (latent).
    세 번째 발화가 장기신뢰 topic을 만들어 strong_inference 인과 관계까지 생성한다."""
    sid = new_session(client)
    say(client, sid, "운동 좋아하는 친구에게 줄 스마트워치를 찾고 있어요. 브랜드는 잘 몰라요.")
    say(client, sid, "가능하면 저렴한 게 좋아요.")
    say(client, sid, "오래 써도 괜찮을 만한 걸로요. 한달 사용 리뷰가 궁금해요.")
    feedback(client, sid, "watch_low_001", "dislike",
             reason_code="too_cheap_looking",
             reason_text="선물인데 너무 저렴해 보이면 좀 그래요.")
    return sid


# ---------------------------------------------------------------------------
# D1 — evidence edges carry per-edge channel + explicitness
# ---------------------------------------------------------------------------
def test_evidence_edges_created_per_channel(client, demo_session):
    g = client.get(f"/api/research/graph?scope=session&id={demo_session}").json()
    ev_edges = [e for e in g["edges"] if e["type"] == "evidence"]
    assert ev_edges, "evidence edges must be materialized"
    channels = {e["channel"] for e in ev_edges}
    assert "user_utterance" in channels
    assert "feedback" in channels
    # feedback-channel edges are never explicit (structural explicitness)
    for e in ev_edges:
        if e["channel"] == "feedback":
            assert e["explicitness"] in ("implicit", "latent")


def test_hidden_derivation_no_explicit_edge(client, demo_session):
    g = client.get(f"/api/research/graph?scope=session&id={demo_session}").json()
    intentions = {n["label"]: n for n in g["nodes"] if n["type"] == "intention"}
    # feedback-derived avoidance: no explicit edge anywhere → hidden
    avoid = intentions["선물로 너무 저렴해 보이지 않기"]
    assert avoid["kind"] == "avoidance"
    assert avoid["isHidden"] is True
    # directly stated price preference → not hidden
    cheap = intentions["가격이 낮을수록 좋음"]
    assert cheap["isHidden"] is False
    # A1 — kind split present in meta
    assert g["meta"]["intentionsByKind"].get("avoidance", 0) >= 1
    assert g["meta"]["hiddenIntentions"] >= 1


def test_evidence_drawer_exposes_channel(client, demo_session):
    g = client.get(f"/api/research/graph?scope=session&id={demo_session}").json()
    avoid = next(n for n in g["nodes"]
                 if n["type"] == "intention" and n["label"] == "선물로 너무 저렴해 보이지 않기")
    r = client.get(f"/api/preferences/topics/{avoid['id']}/evidence")
    assert r.status_code == 200
    items = r.json()["evidence"] if "evidence" in r.json() else r.json().get("items", [])
    if not items and isinstance(r.json(), dict):  # tolerate shape: {evidence:[...]} or flat
        items = next((v for v in r.json().values() if isinstance(v, list)), [])
    assert any(i.get("channel") == "feedback" for i in items)
    assert all(i.get("explicitness") in ("explicit", "implicit", "latent") for i in items)


# ---------------------------------------------------------------------------
# Latent Yield v2 — edge-based hidden definition
# ---------------------------------------------------------------------------
def test_latent_yield_v2(client, demo_session):
    m = client.get(f"/api/research/metrics/latent-yield?sessionId={demo_session}").json()
    assert "v2" in m
    assert m["v2"]["hiddenCount"] >= 1
    assert 0.0 <= m["v2"]["hiddenRatio"] <= 1.0
    # v1과 v2가 같은 데모에서 동일한 hidden 집합을 봐야 한다 (엣지=노드 라벨 생성 직후)
    assert m["v2"]["hiddenCount"] == m["implicitLatentCount"]


# ---------------------------------------------------------------------------
# D4 + M1/M5 — causal evidence levels, judge verdicts, derived plausibility cache
# ---------------------------------------------------------------------------
def test_causal_relations_verified(client, demo_session):
    r = client.get(f"/api/research/sessions/{demo_session}/replay").json()
    relations = r["relations"]
    causal = [x for x in relations if x["nature"] == "causal"]
    assert causal, "demo must produce causal (MOTIVATES) relations"
    # turns/feedback ran through the API, so the background judge already adjudicated
    assert any(x["verification"].startswith("judge_") for x in causal)
    # stated_cause (사용자가 인과를 직접 발화: "선물인데") → causal accepted
    accepted = [x for x in causal if x["causalEvidence"] == "stated_cause"]
    assert accepted
    for x in accepted:
        assert x["verification"] in ("llm_thresholded", "judge_supported")
        assert x["effectiveNature"] == "causal"
        assert x["plausibility"] == 0.95  # derived cache (levels.py), not LLM-emitted
    # strong_inference / weak → downgraded to co_occurrence (행 보존)
    weaker = [x for x in causal if x["causalEvidence"] in ("strong_inference", "weak")]
    assert weaker
    for x in weaker:
        assert x["verification"] in ("llm_downgraded", "judge_downgraded")
        assert x["effectiveNature"] == "co_occurrence"
        assert x["plausibility"] < 0.9
    # non-causal types stay unverified with no level / no plausibility
    for x in relations:
        if x["nature"] != "causal":
            assert x["verification"] == "unverified"
            assert x["causalEvidence"] is None
            assert x["plausibility"] is None


def test_judge_manual_trigger(client, demo_session):
    out = client.post(f"/api/research/judge/run?sessionId={demo_session}").json()
    assert out["sessionId"] == demo_session
    # 이미 judge_*로 평결된 엣지는 재평결하지 않는다 (멱등) — human_* 권위 보호와 같은 게이트
    assert out["judged"] == 0
    assert out["skipped"] >= 1


# ---------------------------------------------------------------------------
# Graph scopes (§5) + fixed theory tier (D2)
# ---------------------------------------------------------------------------
def test_graph_scope_session(client, demo_session):
    g = client.get(f"/api/research/graph?scope=session&id={demo_session}").json()
    types = {n["type"] for n in g["nodes"]}
    assert {"dialogue", "intention", "concept", "theory", "product"} <= types
    theory = [n for n in g["nodes"] if n["type"] == "theory"]
    assert len(theory) == 12  # trait 5 + motivation 7, materialized only here
    assert {n["tier"] for n in theory} == {"trait", "motivation"}
    # D2 — no theory–theory edges, ever
    theory_ids = {n["id"] for n in theory}
    assert not [e for e in g["edges"]
                if e["source"] in theory_ids and e["target"] in theory_ids]
    # intention→theory edges exist (trait tier)
    assert [e for e in g["edges"] if e["type"] == "intention_theory"]


def test_graph_scope_validation(client):
    assert client.get("/api/research/graph?scope=session").status_code == 400
    assert client.get("/api/research/graph?scope=nope&id=x").status_code == 400
    g = client.get("/api/research/graph?scope=population").json()
    assert g["meta"]["sessions"] >= 1
    assert "sessionModes" in g["meta"]


# ---------------------------------------------------------------------------
# M8 + M4 — survey-rubric motivation levels with promotion + polarity guard
# ---------------------------------------------------------------------------
def test_motivation_levels_and_promotion(client):
    sid = new_session(client)
    out = say(client, sid, "친구 생일 선물 찾고 있어요. 요즘 뭐가 인기인지 잘 몰라서요.")
    scores = out["preferenceState"]["motivationScores"]
    assert scores.get("Role") == 0.5  # suggests 레벨의 캐시값 (levels.py)
    # 같은 차원의 독립 신호 2개째 → M4 승격 (suggests×2 → asserts 등가 0.8)
    out2 = say(client, sid, "친구가 좋아할 만한 선물이면 좋겠어요.")
    assert out2["preferenceState"]["motivationScores"].get("Role") == 0.8


def test_motivation_polarity_guard(client):
    sid = new_session(client)
    out = say(client, sid, "너무 저렴해 보이는 건 좀 그래요.")
    scores = out["preferenceState"]["motivationScores"]
    # '저렴' cue가 있지만 회피 맥락 — BargainValue의 증거가 아니다 (M8 극성 검사)
    assert "BargainValue" not in scores


# ---------------------------------------------------------------------------
# M1/M2 — anchor score is a derived cache from the categorical triple
# ---------------------------------------------------------------------------
def test_anchor_score_derived_from_categories(client, demo_session):
    r = client.get(f"/api/research/sessions/{demo_session}/replay").json()
    topic = next(t for t in r["topics"] if t["label"] == "선물로 너무 저렴해 보이지 않기")
    social = next(a for a in topic["anchorMappings"] if a["anchor"] == "Social")
    # confirmed × high × high → 0.95 (levels.derive_anchor_score) — LLM 스칼라가 아님
    assert social["confidence"] == "confirmed"
    assert social["score"] == 0.95

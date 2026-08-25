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
                                           "studyCondition": "ours"})
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
def test_live_turns_do_not_materialize_relations(client, demo_session):
    r = client.get(f"/api/research/sessions/{demo_session}/replay").json()
    assert r["relations"] == []


def test_judge_manual_trigger(client, demo_session):
    out = client.post(f"/api/research/judge/run?sessionId={demo_session}").json()
    assert out["sessionId"] == demo_session
    # New participant sessions have no live relation rows, so the compatibility endpoint is a no-op.
    assert out["judged"] == 0
    assert out["skipped"] == 0


# ---------------------------------------------------------------------------
# Graph scopes (§5) + fixed theory tier (D2)
# ---------------------------------------------------------------------------
def test_graph_scope_session(client, demo_session):
    """2026-08-19: AnchorMapping(TCV 매핑)은 실시간 커밋에서 제거 — 측정층은 분석 전
    scripts/backfill_offline_ontology.py 로 일괄 계산한다. 실시간 세션 그래프의 계약은
    대화·의도·상품 노드까지이고, 의도→이론 엣지는 백필 후에만 나타난다."""
    g = client.get(f"/api/research/graph?scope=session&id={demo_session}").json()
    types = {n["type"] for n in g["nodes"]}
    assert {"dialogue", "intention", "product"} <= types
    assert "concept" not in types
    # D2 — no theory–theory edges, ever (백필 전이므로 theory 엣지 자체가 없어야 한다)
    theory_ids = {n["id"] for n in g["nodes"] if n["type"] == "theory"}
    assert not [e for e in g["edges"]
                if e["source"] in theory_ids and e["target"] in theory_ids]
    assert not [e for e in g["edges"] if e["type"] == "intention_theory"]


def test_graph_scope_validation(client):
    assert client.get("/api/research/graph?scope=session").status_code == 400
    assert client.get("/api/research/graph?scope=nope&id=x").status_code == 400
    g = client.get("/api/research/graph?scope=population").json()
    assert g["meta"]["sessions"] >= 1
    assert "sessionModes" in g["meta"]


# ---------------------------------------------------------------------------
# 동기 감지 제거 가드 (2026-08-25) — 이론 프레이밍을 TCV 단일 축으로 좁히면서
# 턴 루프의 motivation_detection 호출을 뺐다. 다시 살아나면 여기서 잡는다.
# ---------------------------------------------------------------------------
def test_motivation_detection_removed(client):
    sid = new_session(client)
    out = say(client, sid, "친구 생일 선물 찾고 있어요. 요즘 뭐가 인기인지 잘 몰라서요.")
    assert not (out["preferenceState"].get("motivationScores") or {})


# ---------------------------------------------------------------------------
# M1/M2 — anchor score is a derived cache from the categorical triple
# ---------------------------------------------------------------------------
def test_anchor_score_derived_from_categories(client, demo_session):
    """2026-08-19: 실시간 세션에는 anchorMappings가 비어 있다 — TCV 매핑은 분석 전
    오프라인 백필로만 생성된다 (범주→점수 변환 자체는 levels.py 단위 테스트가 커버)."""
    r = client.get(f"/api/research/sessions/{demo_session}/replay").json()
    topic = next(t for t in r["topics"] if t["label"] == "선물로 너무 저렴해 보이지 않기")
    assert topic["anchorMappings"] == []

"""2026-08-15 칩 수정 정합성 — 극성 재해석 + 사용자 문구 재사용.

① edit_label은 라벨 문자열만 바꾸고 kind/impliedAvoidance/priceMax 등 해석 필드를
   방치했다 → 회피 칩을 긍정형 요구로 고치면 rerank가 그 요구를 '피할 것'으로 읽을
   수 있었다(극성 역전). 이제 edit_label이 topic_reinterpretation LLM 태스크로
   새 문구 기준의 해석을 재유도한다. 실패 시엔 종전 동작(라벨만 반영)으로 강등.
② 수정된 라벨은 대화의 자연스러운 표현과 멀어져 재추출 시 중복 칩이 생기기 쉽다
   → 추출 컨텍스트에 state.userAuthoredLabels를 실어 "글자 그대로 재사용" 지시의
   대상으로 삼는다. 머지는 기존 토픽의 라벨을 절대 덮어쓰지 않는다(구조 보장).
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


def _new_session(client):
    r = client.post("/api/sessions", json={"mode": "manual", "scenarioId": "gift_for_other",
                                           "studyCondition": "ours"})
    assert r.status_code == 200, r.text
    return r.json()["sessionId"]


def _add_topic(sid, label, hints, description=None):
    from app.core.ids import new_id
    from app.db import models
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        topic = models.IntentionTopic(
            id=new_id("topic"), session_id=sid, label=label, description=description,
            source="feedback", status="inferred", priority="high", confidence=0.8,
            explicitness="latent", evidence_ids=[], related_product_ids=[], hints=hints,
        )
        db.add(topic)
        db.commit()
        return topic.id
    finally:
        db.close()


def _get_topic(topic_id):
    from app.db import models
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        t = db.get(models.IntentionTopic, topic_id)
        return {"label": t.label, "status": t.status, "description": t.description,
                "hints": dict(t.hints or {})}
    finally:
        db.close()


def test_edit_label_reinterprets_avoidance_to_constraint(client):
    """회피 칩을 긍정형 요구로 고치면 kind가 constraint로 재유도되고 옛 회피 대상이 지워진다."""
    sid = _new_session(client)
    tid = _add_topic(sid, "Celeron 성능 부족 피하기",
                     {"kind": "avoidance", "impliedAvoidance": "Celeron과 4GB RAM"},
                     description="저사양 프로세서를 피하려 한다.")
    r = client.post(f"/api/preferences/chips/{tid}/action",
                    json={"action": "edit_label", "manualLabel": "최소 8GB RAM과 Core i5 이상"})
    assert r.status_code == 200, r.text
    t = _get_topic(tid)
    assert t["label"] == "최소 8GB RAM과 Core i5 이상"  # 사용자 문구 verbatim
    assert t["status"] == "corrected_by_user"
    assert t["hints"]["kind"] == "constraint"
    assert t["hints"]["impliedAvoidance"] is None
    assert t["hints"]["impliedHardConstraint"] == "최소 8GB RAM과 Core i5 이상"
    assert t["description"] and "최소 8GB RAM" in t["description"]  # 설명도 새 문구와 정합


def test_edit_label_extracts_price_bound(client):
    """금액 경계로 고치면 priceMax가 구조 필드로 잡혀 다음 검색의 하드 필터에 들어간다."""
    sid = _new_session(client)
    tid = _add_topic(sid, "저렴한 가격 선호", {"kind": "preference"})
    client.post(f"/api/preferences/chips/{tid}/action",
                json={"action": "edit_label", "manualLabel": "20만원 이하만"})
    t = _get_topic(tid)
    assert t["hints"]["kind"] == "constraint"
    assert t["hints"]["priceMax"] == 200000
    assert t["hints"]["impliedHardConstraint"] is None  # 금액 경계는 price 필드가 원본


def test_edit_label_to_avoidance_wording(client):
    sid = _new_session(client)
    tid = _add_topic(sid, "심플한 디자인 선호", {"kind": "preference"})
    client.post(f"/api/preferences/chips/{tid}/action",
                json={"action": "edit_label", "manualLabel": "번쩍이는 게이밍 디자인은 빼고"})
    t = _get_topic(tid)
    assert t["hints"]["kind"] == "avoidance"
    assert t["hints"]["impliedAvoidance"] == "번쩍이는 게이밍 디자인은 빼고"


def test_edit_label_degrades_gracefully_when_reinterpretation_fails(client, monkeypatch):
    """재해석 LLM이 죽어도 수정 자체는 성공한다 — 종전 동작(라벨만 반영)으로 강등."""
    async def _boom(topic, new_label):
        raise RuntimeError("llm down")

    monkeypatch.setattr("app.api.preferences._reinterpret_edited_topic", _boom)
    sid = _new_session(client)
    old_hints = {"kind": "avoidance", "impliedAvoidance": "화려한 디자인"}
    tid = _add_topic(sid, "화려한 디자인 피하기", dict(old_hints))
    r = client.post(f"/api/preferences/chips/{tid}/action",
                    json={"action": "edit_label", "manualLabel": "무난한 디자인이면 좋겠어요"})
    assert r.status_code == 200, r.text
    t = _get_topic(tid)
    assert t["label"] == "무난한 디자인이면 좋겠어요"
    assert t["status"] == "corrected_by_user"
    for k, v in old_hints.items():
        assert t["hints"][k] == v  # 해석은 그대로 — 다음 커밋이 자연 갱신할 때까지 유지


def test_extraction_context_carries_user_authored_labels(client):
    """추출 컨텍스트에 사용자 문구 라벨이 별도 필드로 실린다 (프롬프트 재사용 지시의 대상)."""
    from app.db import models
    from app.db.database import SessionLocal
    from app.ontology.topic_extractor import extract_topics

    class _Capture:
        context = None

        async def generate_json(self, messages, task=None, context=None, **kw):
            _Capture.context = context
            return {"topics": []}

    sid = _new_session(client)
    db = SessionLocal()
    try:
        session = db.get(models.Session, sid)
        asyncio.run(extract_topics(
            db, _Capture(), session, [], [],
            {"activeTopicLabels": ["저렴한 가격 선호", "20만원 이하만"],
             "userAuthoredLabels": ["20만원 이하만"]},
        ))
    finally:
        db.close()
    assert _Capture.context["state"]["userAuthoredLabels"] == ["20만원 이하만"]


def test_merge_never_renames_user_corrected_topic(client):
    """재추출이 사용자 문구와 같은 라벨로 돌아오면 그 토픽에 증거만 쌓인다 — 라벨 불변, 새 칩 없음."""
    from app.db import models
    from app.db.database import SessionLocal
    from app.ontology.merge import merge_topics

    sid = _new_session(client)
    tid = _add_topic(sid, "20만원 이하만",
                     {"kind": "constraint", "priceMax": 200000, "evidence": []})
    db = SessionLocal()
    try:
        topic = db.get(models.IntentionTopic, tid)
        topic.status = "corrected_by_user"
        db.commit()
        session = db.get(models.Session, sid)
        touched, created = merge_topics(db, session, [{
            "label": "20만원 이하만",
            "description": "예산 상한 20만원.",
            "explicitness": "explicit",
            "confidenceLevel": "directly_stated",
            "priority": "high",
            "kind": "constraint",
            "sourceEvidence": [{"type": "turn", "id": "turn_merge_test", "quoteOrSummary": "예산 안에서요"}],
        }], source="user_utterance")
        db.commit()
        assert created == []  # 새 칩이 생기지 않는다
        merged = db.get(models.IntentionTopic, tid)
        assert merged.label == "20만원 이하만"
        assert merged.status == "corrected_by_user"
        assert "turn_merge_test" in (merged.evidence_ids or [])
    finally:
        db.close()

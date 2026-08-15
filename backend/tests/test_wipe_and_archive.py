"""전체 삭제(배치 리셋) + 전체 데이터 ZIP (2026-08-16, 관리자 페이지 데이터 관리).

wipe는 참가자·세션·파생 데이터 전부를 지우되 상품·시드 concept·운영 설정은 남긴다.
confirm 문자열이 정확히 "전체삭제"가 아니면 400 (연구 키 게이트는 study 모드에서 추가로 작동).
archive는 export_all(참가자·llm_calls 포함)을 ZIP으로 묶는다.
"""
import io
import os
import tempfile
import zipfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_test_"), "test.db"))
os.environ.setdefault("VC_LLM_PROVIDER", "mock")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _make_data(client):
    r = client.post("/api/sessions", json={"mode": "manual", "scenarioId": "gift_for_other",
                                           "studyCondition": "ours"})
    sid = r.json()["sessionId"]
    client.post(f"/api/sessions/{sid}/turns",
                json={"role": "user", "content": "운동 좋아하는 친구에게 줄 스마트워치를 추천해주세요"})
    return sid


def test_archive_zip_contains_all_tables(client):
    _make_data(client)
    r = client.get("/api/exports/archive")
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(z.namelist())
    for required in ("participants.jsonl", "sessions.jsonl", "turns.jsonl",
                     "product_impressions.jsonl", "llm_calls.jsonl", "ontology_topics.jsonl"):
        assert required in names, f"{required} missing from archive"


def test_wipe_requires_exact_confirm(client):
    assert client.post("/api/research/wipe", json={"confirm": "delete"}).status_code == 400
    assert client.post("/api/research/wipe", json={}).status_code == 400


def test_wipe_clears_study_data_keeps_products_and_seed_concepts(client):
    from app.db import models
    from app.db.database import SessionLocal

    _make_data(client)
    db = SessionLocal()
    try:
        products_before = db.query(models.Product).count()
        seed_concepts = [c.id for c in db.query(models.Concept).all()
                         if "top_down_seed" in (c.origin or [])]
        assert db.query(models.Session).count() > 0
    finally:
        db.close()

    r = client.post("/api/research/wipe", json={"confirm": "전체삭제"})
    assert r.status_code == 200
    assert r.json()["totalRows"] > 0

    db = SessionLocal()
    try:
        for m in (models.Participant, models.Session, models.Turn, models.IntentionTopic,
                  models.ProductImpression, models.FeedbackEvent, models.LLMCall):
            assert db.query(m).count() == 0, m.__tablename__
        assert db.query(models.Product).count() == products_before  # 상품 풀 유지
        remaining = [c.id for c in db.query(models.Concept).all()]
        assert set(remaining) == set(seed_concepts)  # 시드 concept만 잔존
    finally:
        db.close()

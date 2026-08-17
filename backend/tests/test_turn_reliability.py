"""턴 신뢰성 (2026-08-18) — 부분 저장의 식별·복구.

배포 재시작이 파이프라인 중간에 프로세스를 죽이면 사용자 턴·칩만 남고 응답이
유실된다(스마트워치 세션 실측: 고아 사용자 턴 2개). 원자 트랜잭션은 불가(LLM 왕복
동안 SQLite 잠금 보유 = 전 세션 데드락 — LLM-first-write-last 설계)하므로 등가
안전성: ① 턴 상태(pending→completed/failed)로 미완을 식별 ② clientRequestId로
재전송 중복 차단 ③ 같은 턴 재처리(retry)로 새 턴 없이 응답 복구.
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
                                           "studyCondition": "ours"})
    assert r.status_code == 200, r.text
    return r.json()["sessionId"]


def _turns(client, sid):
    return client.get(f"/api/sessions/{sid}").json()["turns"]


def test_completed_turn_and_duplicate_guard(client):
    sid = _new_session(client)
    r = client.post(f"/api/sessions/{sid}/turns",
                    json={"content": "선물용 스마트워치 찾아요", "clientRequestId": "req-1"})
    assert r.status_code == 200
    assert r.json()["turn"]["status"] == "completed", "응답까지 저장되면 completed"
    n_before = len(_turns(client, sid))

    # 같은 clientRequestId 재전송 → 새 턴이 만들어지지 않는다
    r2 = client.post(f"/api/sessions/{sid}/turns",
                     json={"content": "선물용 스마트워치 찾아요", "clientRequestId": "req-1"})
    assert r2.status_code == 200 and r2.json().get("duplicate") is True
    assert len(_turns(client, sid)) == n_before


def test_orphan_turn_retry_recovers_without_duplicate(client):
    sid = _new_session(client)
    # 고아 사용자 턴 시뮬레이션 — 파이프라인이 죽어 응답 없이 pending으로 남은 상태
    from app.core.ids import new_id
    from app.db import models
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        orphan = models.Turn(id=new_id("turn"), session_id=sid, turn_index=99,
                             role="user", content="예산은 20만원 이하로요",
                             dialogue_acts=[], status="pending")
        db.add(orphan)
        db.commit()
        orphan_id = orphan.id
    finally:
        db.close()

    r = client.post(f"/api/sessions/{sid}/turns/{orphan_id}/retry")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["turn"]["id"] == orphan_id, "새 턴이 아니라 같은 턴이어야 한다"
    assert body["turn"]["status"] == "completed"
    assert body["agentResponse"]["role"] == "service_agent"
    # 사용자 턴은 여전히 1개(고아) + 응답 1개 — 중복 발화 없음
    contents = [t["content"] for t in _turns(client, sid) if t["role"] == "user"]
    assert contents.count("예산은 20만원 이하로요") == 1

    # 응답이 생긴 턴의 재시도는 거부된다 (이중 응답 방지)
    r2 = client.post(f"/api/sessions/{sid}/turns/{orphan_id}/retry")
    assert r2.status_code == 409

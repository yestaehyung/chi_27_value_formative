"""③ 최종 선택 확정 검증 (2026-08-11) — 사후 기준 확인 전에 선택을 잠근다.

지키는 것:
  ① 노출된 상품만 확정 가능 — 임의 id는 422 (프론트 버그·조작 방어)
  ② 확정 시점의 기준 스냅샷·좋아요가 함께 저장 — '필수 조건 위반' 분석의 재료
  ③ "이 중에는 없어요"(noneReason)도 유효한 응답 — 억지 선택 강제 안 함
  ④ 둘 다 없으면 422 — 빈 확정은 데이터가 아니다
"""
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_final_"), "test.db"))
os.environ.setdefault("VC_EXPORT_DIR", tempfile.mkdtemp(prefix="vc_final_exp_"))
os.environ["VC_LLM_PROVIDER"] = "mock"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def shopped_session(client):
    """추천까지 받은 세션 — 노출 상품과 좋아요 하나를 만들어 둔다."""
    cat = client.get("/api/meta/categories").json()["categories"][0]["category"]
    sid = client.post("/api/sessions", json={
        "mode": "manual", "category": cat, "studyCondition": "ours",
    }).json()["sessionId"]
    out = client.post(f"/api/sessions/{sid}/turns",
                      json={"role": "user", "content": "추천해 주세요."}).json()
    products = [p["product"]["id"] for p in out.get("recommendedProducts") or []]
    assert products, "노출 상품이 있어야 확정을 테스트할 수 있다"
    client.post(f"/api/sessions/{sid}/feedback",
                json={"productId": products[0], "type": "like"})
    return sid, products


def test_final_choice_locks_a_shown_product(client, shopped_session):
    """①·② 노출 상품 확정 → meta.finalChoice에 선택·기준 스냅샷·좋아요가 남는다."""
    sid, products = shopped_session
    r = client.put(f"/api/study/sessions/{sid}/final-choice",
                   json={"productId": products[1]})
    assert r.status_code == 200, r.text
    fc = client.get(f"/api/sessions/{sid}").json()["session"]["metadata"]["finalChoice"]
    assert fc["productId"] == products[1]
    assert fc["decidedAt"]
    assert isinstance(fc["criteriaAtDecision"], list)
    assert products[0] in fc["likedIds"]


def test_unknown_product_is_rejected(client, shopped_session):
    """① 이 세션에서 노출된 적 없는 상품은 422."""
    sid, _ = shopped_session
    r = client.put(f"/api/study/sessions/{sid}/final-choice",
                   json={"productId": "prod_없던상품"})
    assert r.status_code == 422


def test_none_chosen_with_reason(client, shopped_session):
    """③ 선택 없음 + 이유 — 추천 실패 신호로 그대로 저장된다."""
    sid, _ = shopped_session
    r = client.put(f"/api/study/sessions/{sid}/final-choice",
                   json={"productId": None, "noneReason": "원하는 색상이 없었어요"})
    assert r.status_code == 200
    fc = client.get(f"/api/sessions/{sid}").json()["session"]["metadata"]["finalChoice"]
    assert fc["productId"] is None
    assert fc["noneReason"] == "원하는 색상이 없었어요"


def test_empty_confirmation_is_rejected(client, shopped_session):
    """④ productId도 noneReason도 없으면 422."""
    sid, _ = shopped_session
    r = client.put(f"/api/study/sessions/{sid}/final-choice", json={})
    assert r.status_code == 422

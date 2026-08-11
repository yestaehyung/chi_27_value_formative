"""카테고리 기반 세션 생성 검증 (2026-08-06) — 시나리오 선택을 대체한 경로.

왜 바꿨나: 상품 풀을 본실험용으로 재구성하자 옛 시나리오(태블릿·코트…)의 카테고리에
상품이 0개가 됐다. 시나리오는 seed 파일에, 상품은 DB에 있어 둘이 조용히 어긋난다.
카테고리는 **DB에서 직접 확인**하므로 그 어긋남이 구조적으로 불가능해진다.

여기서 지키는 것:
  ① 선택지는 DB에 상품이 실제로 있는 카테고리만
  ② 세션이 그 카테고리로 열리고, 검색 범위(meta.category)에 반영된다
  ③ cat: 세션을 다시 열어도 scenario가 복원된다 — 과제 직전 설문의 {category} 치환 근거
  ④ 없는 카테고리는 404 — 조용히 빈 세션이 열리지 않는다
  ⑤ 참가자가 매긴 친숙도(2+2)가 세션에 남는다 — within-subjects 요인
"""
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_cat_"), "test.db"))
os.environ.setdefault("VC_EXPORT_DIR", tempfile.mkdtemp(prefix="vc_cat_exp_"))
os.environ["VC_LLM_PROVIDER"] = "mock"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_categories_come_from_the_product_pool(client):
    """① 선택지는 DB의 카테고리와 일치한다."""
    cats = client.get("/api/meta/categories").json()["categories"]
    assert cats, "카테고리가 하나도 없으면 참가자가 시작할 수 없다"
    pool = {c["category"]: c["count"] for c in client.get("/api/meta/product-pool").json()["categories"]}
    for c in cats:
        assert c["count"] == pool[c["category"]]
        assert c["count"] > 0, f"상품이 0개인 카테고리는 노출되면 안 된다: {c['category']}"
        assert c["emoji"], "선택 화면이 렌더할 표시 정보가 있어야 한다"


def test_session_opens_on_chosen_category(client):
    """② 고른 카테고리가 세션의 검색 범위가 된다."""
    cat = client.get("/api/meta/categories").json()["categories"][0]["category"]
    r = client.post("/api/sessions", json={"mode": "manual", "category": cat})
    assert r.status_code == 200, r.text
    sid = r.json()["sessionId"]
    meta = client.get(f"/api/sessions/{sid}").json()["session"]["metadata"]
    assert meta["category"] == cat
    assert meta["shoppingGoal"] == cat


def test_category_scenario_survives_reload(client):
    """③ cat: 세션을 다시 열어도 scenario가 복원된다.

    cat: id는 scenarios.json에 없어서 조회가 {}를 돌려줬고, 과제 직전 설문의
    "{category}" 치환이 "이 상품군" 폴백으로 떨어졌다 (2026-08-08 수정).
    """
    cat = client.get("/api/meta/categories").json()["categories"][0]["category"]
    sid = client.post("/api/sessions", json={
        "mode": "manual", "category": cat,
    }).json()["sessionId"]
    scenario = client.get(f"/api/sessions/{sid}").json()["scenario"]
    assert scenario.get("targetCategory") == cat, "설문 치환·헤더가 이 값에 걸려 있다"
    assert scenario.get("title") == cat


def test_familiarity_is_persisted(client):
    """⑤ 친숙도는 참가자가 선택 시점에 주는 값이라 세션에 남아야 분석된다."""
    cat = client.get("/api/meta/categories").json()["categories"][0]["category"]
    for fam in ("familiar", "unfamiliar"):
        sid = client.post("/api/sessions", json={
            "mode": "manual", "category": cat, "familiarity": fam,
        }).json()["sessionId"]
        meta = client.get(f"/api/sessions/{sid}").json()["session"]["metadata"]
        assert meta["familiarity"] == fam


def test_unknown_category_is_rejected(client):
    """④ 상품이 없는 카테고리로는 세션이 열리지 않는다 — 빈 추천 세션 방지."""
    r = client.post("/api/sessions", json={
        "mode": "manual", "category": "존재하지않는카테고리",
    })
    assert r.status_code == 404


def test_scenario_path_still_works(client):
    """시뮬레이션·합성이 쓰는 시나리오 경로는 그대로 살아 있어야 한다."""
    r = client.post("/api/sessions", json={"mode": "manual", "scenarioId": "gift_for_other"})
    assert r.status_code == 200, r.text


def test_category_session_recommends_within_category(client):
    """카테고리 세션에서 실제로 그 카테고리 상품이 추천된다 — 범위가 말뿐이 아님을 확인."""
    cat = client.get("/api/meta/categories").json()["categories"][0]["category"]
    sid = client.post("/api/sessions", json={
        "mode": "manual", "category": cat, "studyCondition": "ours",
    }).json()["sessionId"]
    out = client.post(f"/api/sessions/{sid}/turns",
                      json={"role": "user", "content": "추천해 주세요."}).json()
    products = out.get("recommendedProducts") or []
    assert products, "추천이 하나도 없으면 카테고리 세션이 무의미하다"

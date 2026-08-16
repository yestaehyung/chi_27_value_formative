"""VC_OFFERED_CATEGORIES — 풀에는 15개 카테고리를 두고 스터디 선택지는 10개만 노출
(2026-08-17). 미설정이면 DB 전체 카테고리 노출(기존 동작)."""
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_test_"), "test.db"))
os.environ.setdefault("VC_LLM_PROVIDER", "mock")

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _cats(client):
    return [c["category"] for c in client.get("/api/meta/categories").json()["categories"]]


def test_unset_shows_all(client):
    assert settings.offered_categories == []
    all_cats = _cats(client)
    assert len(all_cats) > 0


def test_whitelist_filters(client, monkeypatch):
    all_cats = _cats(client)
    keep = all_cats[:1]
    monkeypatch.setattr(settings, "offered_categories", keep)
    assert _cats(client) == keep
    # 화이트리스트에 있지만 DB에 없는 카테고리는 만들어내지 않는다
    monkeypatch.setattr(settings, "offered_categories", keep + ["없는카테고리"])
    assert _cats(client) == keep

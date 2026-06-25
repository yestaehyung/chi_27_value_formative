"""upsert_seed_products는 비파괴 — 시드의 새 상품만 INSERT하고 기존 Product/ProductImpression을
보존한다. reseed는 노출(추천기록)을 전부 지우므로(연구 데이터 손실), 풀에 N개만 추가할 땐
upsert를 써야 한다. 이 테스트가 그 계약(노출 0건 삭제 + 멱등)을 잠근다.
"""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db import models
from app.db.database import Base
from app.products import seed_loader


@pytest.fixture
def db(tmp_path, monkeypatch):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "products.json").write_text(json.dumps([
        {"id": "p1", "title": "기존 코트", "category": "코트·패딩·자켓", "price": 100000, "tags": ["코트"]},
        {"id": "p2", "title": "기존 패딩", "category": "코트·패딩·자켓", "price": 120000, "tags": ["패딩"]},
    ], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(settings, "seed_dir", seed)
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s, seed
    s.close()


def _add_seed(seed, item):
    raw = json.loads((seed / "products.json").read_text(encoding="utf-8"))
    raw.append(item)
    (seed / "products.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")


def test_upsert_adds_new_without_deleting_impressions(db):
    s, seed = db
    seed_loader.load_seed_products(s)
    # 추천노출(연구 데이터)을 심는다 — upsert가 이걸 지우면 안 된다
    s.add(models.ProductImpression(id="imp1", session_id="sess1", turn_id="t1", product_id="p1"))
    s.add(models.ProductImpression(id="imp2", session_id="sess1", turn_id="t1", product_id="p2"))
    s.commit()
    assert s.query(models.Product).count() == 2
    assert s.query(models.ProductImpression).count() == 2

    _add_seed(seed, {"id": "p3", "title": "신규 여성 코트", "category": "코트·패딩·자켓",
                     "price": 150000, "tags": ["코트", "방한"], "attributes": {"gender": "여성"}})
    added = seed_loader.upsert_seed_products(s)

    assert added == 1                                       # 신규 1개만 INSERT
    assert s.query(models.Product).count() == 3            # 기존 2 + 신규 1
    assert s.query(models.ProductImpression).count() == 2  # ★ 노출 0건 삭제 (핵심 계약)
    p3 = s.get(models.Product, "p3")
    assert p3.tags == ["코트", "방한"] and (p3.attributes or {}).get("gender") == "여성"


def test_upsert_is_idempotent(db):
    s, seed = db
    seed_loader.load_seed_products(s)
    assert seed_loader.upsert_seed_products(s) == 0        # 새 상품 없음 → 0
    assert s.query(models.Product).count() == 2


def test_upsert_does_not_touch_existing_product_fields(db):
    s, seed = db
    seed_loader.load_seed_products(s)
    # 기존 p1을 런타임에 바꿔도 upsert가 시드 값으로 덮어쓰지 않는다(기존행 불변)
    s.get(models.Product, "p1").tags = ["런타임수정"]
    s.commit()
    _add_seed(seed, {"id": "p9", "title": "신규", "category": "코트·패딩·자켓", "price": 90000})
    seed_loader.upsert_seed_products(s)
    assert s.get(models.Product, "p1").tags == ["런타임수정"]  # 기존행 보존
